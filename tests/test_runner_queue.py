"""Full queue runs on real diaries against mock clients and a local fault-injecting server."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from swb.clients.registry import get_client
from swb.config import Cell, RunConfig, SeedRange
from swb.contracts import DecisionClient, DecisionResult, Job, ModelEntry, Question
from swb.runner.backoff import BackoffConfig
from swb.runner.budget import BudgetGuard
from swb.runner.jobs import expand_config
from swb.runner.queue import RunSummary, TokenRateLimiter, run_jobs
from swb.runner.tokens import WorldRate
from swb.store.jsonl import JsonlStore

FAST = BackoffConfig(base_s=0.001, cap_s=0.005, max_attempts=8)


def _config(count: int = 3, days: int = 40) -> RunConfig:
    cell = Cell(
        world="steady",
        contrasts=["high"],
        lengths_days=[days],
        policies=["raw"],
        question_keys=["risk", "act"],
    )
    return RunConfig(run_id="t", root_seed=5, seeds=SeedRange(start=0, count=count), cells=[cell])


def _entry(url: str, **extra: Any) -> ModelEntry:
    fields: dict[str, Any] = {
        "id": "fake",
        "display": "Fake",
        "adapter": "decision_api",
        "model_id": "fake-1",
        "window": 100000,
        "price_input_per_m": 1000.0,
        "base_url": url,
        "path": "/v1/d",
        **extra,
    }
    return ModelEntry(**fields)


def _mock_entry(entry_id: str, spec: str) -> ModelEntry:
    return ModelEntry(
        id=entry_id,
        display=entry_id,
        adapter="mock",
        model_id=spec,
        window=100000,
        price_input_per_m=0.0,
    )


def _answers(request: dict[str, Any]) -> dict[str, Any]:
    answers = {}
    for name, question in request["questions"].items():
        options = list(question["criteria"])
        answers[name] = {"probabilities": {o: 1 / len(options) for o in options}}
    return {"model": "fake-1", "answers": answers, "usage": {"input_tokens": 300}}


class Server:
    """Serves valid answers except for scripted faults, applied by request number."""

    def __init__(self, faults: dict[int, tuple[int, str]]) -> None:
        self.faults = faults
        self.count = 0
        self.lock = threading.Lock()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                request = json.loads(self.rfile.read(int(self.headers["content-length"])))
                with outer.lock:
                    number = outer.count
                    outer.count += 1
                status, body = outer.faults.get(number, (200, json.dumps(_answers(request))))
                payload = body.encode()
                self.send_response(status)
                self.send_header("content-length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args: object) -> None:
                return

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()


@pytest.fixture
def server() -> Iterator[Any]:
    started: list[Server] = []

    def start(faults: dict[int, tuple[int, str]] | None = None) -> Server:
        started.append(Server(faults or {}))
        return started[-1]

    yield start
    for item in started:
        item.httpd.shutdown()
        item.httpd.server_close()


async def _run(
    jobs: list[Job], entry: ModelEntry, store: JsonlStore, cap: float = 45.0, concurrency: int = 2
) -> RunSummary:
    client = get_client(entry, FAST)
    return await run_jobs(
        jobs, {entry.id: client}, store, entries=[entry], cap_usd=cap, concurrency=concurrency
    )


async def test_run_completes_through_faults(server: Any, tmp_path: Path) -> None:
    faults = {0: (429, "{}"), 1: (503, "x"), 2: (200, "not json"), 4: (200, '{"answers": 3}')}
    fake = server(faults)
    entry = _entry(fake.url)
    jobs = expand_config(_config(), [entry])
    store = JsonlStore(tmp_path / "r.jsonl")
    summary = await _run(jobs, entry, store)
    assert summary.clean
    assert summary.completed == 3
    assert fake.count == 3 + len(faults)
    rows = store.rows()
    assert len(rows) == 6
    assert {row.question_key for row in rows} == {"risk", "act"}
    assert all(row.input_tokens == 300 and row.http_status == 200 for row in rows)
    assert all(not row.is_mock and row.truth in row.option_order for row in rows)


async def test_402_stops_the_run_immediately(server: Any, tmp_path: Path) -> None:
    fake = server({1: (402, '{"error": "no credits"}')})
    entry = _entry(fake.url)
    jobs = expand_config(_config(count=6), [entry])
    store = JsonlStore(tmp_path / "r.jsonl")
    summary = await _run(jobs, entry, store, concurrency=1)
    assert summary.stopped_run is not None and "402" in summary.stopped_run
    assert summary.completed == 1
    assert fake.count == 2
    assert not summary.clean


async def test_daily_cap_stops_only_that_model(server: Any, tmp_path: Path) -> None:
    fake = server({0: (429, '{"code": "REQUEST_LIMIT_EXCEEDED"}')})
    entry = _entry(fake.url)
    jobs = expand_config(_config(count=4), [entry])
    summary = await _run(jobs, entry, JsonlStore(tmp_path / "r.jsonl"), concurrency=1)
    assert "fake" in summary.stopped_models
    assert summary.stopped_run is None
    assert fake.count == 1


async def test_resume_skips_finished_jobs(server: Any, tmp_path: Path) -> None:
    fake = server({1: (402, "{}")})
    entry = _entry(fake.url)
    jobs = expand_config(_config(count=4), [entry])
    path = tmp_path / "r.jsonl"
    await _run(jobs, entry, JsonlStore(path), concurrency=1)
    second = await _run(jobs, entry, JsonlStore(path), concurrency=1)
    assert second.clean
    assert second.skipped == 1
    assert second.completed == 3
    assert len(JsonlStore(path).done_job_ids()) == 4


async def test_budget_guard_blocks_an_over_cap_call(server: Any, tmp_path: Path) -> None:
    fake = server()
    # Each call reserves about $0.35 and settles at $0.30 (300 reported tokens at $1000 per 1M),
    # so a $0.40 cap admits one call and refuses the next.
    entry = _entry(fake.url, budget_capped=True, price_input_per_m=1000.0)
    jobs = expand_config(_config(count=4), [entry])
    store = JsonlStore(tmp_path / "r.jsonl")
    summary = await _run(jobs, entry, store, cap=0.40, concurrency=1)
    assert fake.count == 1
    assert summary.completed == 1
    assert len(summary.refused) == 1
    assert summary.stopped_models["fake"]
    tokens, usd = store.spent()
    assert tokens == 300
    assert usd == pytest.approx(0.3)
    assert all(row.cost_usd == pytest.approx(0.3) for row in store.rows())


class _FixedTokens:
    """Answers uniformly and reports whatever token count it is told to."""

    model_id = "fixed"
    window = 65536

    def __init__(self, name: str, tokens: int) -> None:
        self.name = name
        self.tokens = tokens
        self.calls = 0

    async def decide(self, state: str, questions: dict[str, Question]) -> DecisionResult:
        self.calls += 1
        probabilities = {
            name: {option: 1 / len(q.options) for option in q.options}
            for name, q in questions.items()
        }
        return DecisionResult(
            probabilities=probabilities, input_tokens=self.tokens, latency_ms=1, http_status=200
        )


def _windowed(window: int = 65536) -> ModelEntry:
    return ModelEntry(
        id="w",
        display="W",
        adapter="decision_api",
        model_id="w",
        window=window,
        price_input_per_m=0.0,
    )


async def _run_fixed(
    tmp_path: Path, tokens: int, calibration: Any = None
) -> tuple[RunSummary, JsonlStore, _FixedTokens]:
    entry = _windowed()
    client = _FixedTokens("w", tokens)
    store = JsonlStore(tmp_path / "r.jsonl")
    jobs = expand_config(_config(count=2), [entry])
    summary = await run_jobs(
        jobs,
        {"w": client},
        store,
        entries=[entry],
        cap_usd=1.0,
        concurrency=1,
        calibration=calibration,
    )
    return summary, store, client


async def test_call_over_the_window_is_not_stored(tmp_path: Path) -> None:
    summary, store, client = await _run_fixed(tmp_path, 500_000)
    assert summary.completed == 0
    assert summary.token_problems
    assert not summary.clean
    assert "window" in summary.stopped_models["w"]
    assert store.rows() == []
    assert client.calls == 1


async def test_call_outside_five_percent_of_the_measured_length_is_rejected(tmp_path: Path) -> None:
    calibration = {"w": {"steady": WorldRate(tokens_per_day=8.0, overhead=20.0)}}
    summary, store, _ = await _run_fixed(tmp_path, 100, calibration)
    assert summary.token_problems and store.rows() == []


async def test_call_near_the_measured_length_is_stored(tmp_path: Path) -> None:
    calibration = {"w": {"steady": WorldRate(tokens_per_day=8.0, overhead=20.0)}}
    summary, store, _ = await _run_fixed(tmp_path, 8 * 40 + 20, calibration)
    assert summary.clean and summary.completed == 2 and store.rows()


async def test_retries_that_were_billed_are_counted(server: Any, tmp_path: Path) -> None:
    fake = server({0: (200, "not json"), 1: (200, "not json")})
    entry = _entry(fake.url, budget_capped=True, price_input_per_m=1.0)
    jobs = expand_config(_config(count=1), [entry])
    store = JsonlStore(tmp_path / "r.jsonl")
    await _run(jobs, entry, store, cap=10.0, concurrency=1)
    assert fake.count == 3
    assert store.spent()[0] == 3 * 300


def test_maybe_billed_failure_stays_on_the_ledger_after_resume(tmp_path: Path) -> None:
    store = JsonlStore(tmp_path / "r.jsonl")
    entry = _entry("http://unused", budget_capped=True, price_input_per_m=1.0)
    guard = BudgetGuard(store, cap_usd=10.0)
    guard.reserve("job1", entry, 1000)
    guard.carry("job1", entry, 1000)
    guard.reserve("job1", entry, 1000)
    guard.settle("job1", entry, 900)
    assert store.spent()[0] == 1900


async def test_partial_job_is_rerun(tmp_path: Path) -> None:
    entry = _windowed()
    client = _FixedTokens("w", 300)
    path = tmp_path / "r.jsonl"
    jobs = expand_config(_config(count=1), [entry])
    store = JsonlStore(path)
    await run_jobs(jobs, {"w": client}, store, entries=[entry], cap_usd=1.0, concurrency=1)
    first_line = path.read_text(encoding="utf-8").splitlines(keepends=True)[0]
    path.write_text(first_line, encoding="utf-8")
    second = await run_jobs(jobs, {"w": client}, JsonlStore(path), entries=[entry], cap_usd=1.0)
    assert second.completed == 1 and second.skipped == 0
    assert len(JsonlStore(path).rows()) == 2


async def test_uncapped_model_is_not_tracked(server: Any, tmp_path: Path) -> None:
    fake = server()
    entry = _entry(fake.url, price_input_per_m=1e9)
    jobs = expand_config(_config(), [entry])
    store = JsonlStore(tmp_path / "r.jsonl")
    summary = await _run(jobs, entry, store, cap=0.0)
    assert summary.completed == 3
    assert store.spent() == (0, 0.0)
    assert all(row.cost_usd is None for row in store.rows())


def test_released_reservation_returns_the_money(tmp_path: Path) -> None:
    store = JsonlStore(tmp_path / "r.jsonl")
    entry = _entry("http://unused", budget_capped=True)
    guard = BudgetGuard(store, cap_usd=45.0)
    assert guard.reserve("a", entry, 1000)
    assert store.spent()[1] > 0
    guard.release("a", entry)
    assert store.spent() == (0, 0.0)


async def test_mock_adapter_runs_the_real_pipeline(tmp_path: Path) -> None:
    entry = _mock_entry("demo-x", "kind=window,horizon=30,noise=0.01,seed=1")
    store = JsonlStore(tmp_path / "r.jsonl")
    summary = await _run(expand_config(_config(), [entry]), entry, store)
    assert summary.clean
    assert all(row.is_mock for row in store.rows())
    assert store.rows()[0].baseline_scores


async def test_empty_diary_jobs_run(tmp_path: Path) -> None:
    entry = _mock_entry("demo-x", "kind=counter")
    cell = Cell(
        world="steady",
        contrasts=["7pt"],
        lengths_days=[0],
        policies=["raw"],
        question_keys=["risk", "act"],
    )
    config = RunConfig(run_id="t", seeds=SeedRange(count=2), cells=[cell])
    store = JsonlStore(tmp_path / "r.jsonl")
    summary = await _run(expand_config(config, [entry]), entry, store)
    assert summary.clean
    assert {row.n_days for row in store.rows()} == {0}


async def test_every_model_gets_byte_identical_requests(tmp_path: Path) -> None:
    captured: list[tuple[str, dict[str, Question]]] = []

    class Capture:
        name = "cap"
        model_id = "cap"
        window = 100000

        async def decide(self, state: str, questions: dict[str, Question]) -> DecisionResult:
            captured.append((state, questions))
            probabilities = {
                name: {o: 1 / len(q.options) for o in q.options} for name, q in questions.items()
            }
            return DecisionResult(
                probabilities=probabilities, input_tokens=1, latency_ms=1, http_status=200
            )

    entries = [_mock_entry(i, "kind=counter") for i in ("a", "b")]
    client: DecisionClient = Capture()
    await run_jobs(
        expand_config(_config(count=1), entries),
        {"a": client, "b": client},
        JsonlStore(tmp_path / "r.jsonl"),
        entries=entries,
        cap_usd=45.0,
    )
    assert captured[0] == captured[1]


async def test_rate_limiter_books_time_in_proportion_to_tokens() -> None:
    limiter = TokenRateLimiter(tokens_per_minute=60000)  # 1000 tokens per second
    await limiter.acquire(1)
    first = limiter._next_free
    await limiter.acquire(1)
    assert limiter._next_free == pytest.approx(first + 0.001, abs=0.05)
