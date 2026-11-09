"""Adapters against a local HTTP server that injects faults. Nothing leaves localhost."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from swb.clients.base import CallFailed, HttpEndpoint, StopModel, StopRun
from swb.clients.decision_api import DecisionApiClient
from swb.clients.openai_chat import OpenAIChatClient, build_payload
from swb.clients.registry import ConfigError, close_clients, get_client, load_models
from swb.contracts import ModelEntry, Question
from swb.runner.backoff import Backoff, BackoffConfig

FAST = BackoffConfig(base_s=0.001, cap_s=0.005, max_attempts=6)
QUESTIONS = {
    "risk__r0": Question(key="risk", instructions="Which?", options=["Darro", "Kell"]),
}
GOOD = {
    "model": "fake-1",
    "answers": {"risk__r0": {"probabilities": {"Darro": 0.7, "Kell": 0.3}, "choice": "Darro"}},
    "usage": {"input_tokens": 123},
}
FENCE = "`" * 3


class FaultServer:
    """Replays a scripted list of (status, body); then serves `default`."""

    def __init__(self, script: list[tuple[int, Any]], default: tuple[int, Any]) -> None:
        self.script = list(script)
        self.default = default
        self.requests: list[dict[str, Any]] = []
        self.headers: list[dict[str, str]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("content-length", "0"))
                outer.requests.append(json.loads(self.rfile.read(length)))
                outer.headers.append(dict(self.headers))
                status, body = outer.script.pop(0) if outer.script else outer.default
                payload = body.encode() if isinstance(body, str) else json.dumps(body).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args: object) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def serve() -> Iterator[Any]:
    servers: list[FaultServer] = []

    def start(script: list[tuple[int, Any]], default: tuple[int, Any] = (200, GOOD)) -> FaultServer:
        server = FaultServer(script, default)
        servers.append(server)
        return server

    yield start
    for server in servers:
        server.close()


def _client(server: FaultServer) -> DecisionApiClient:
    endpoint = HttpEndpoint("fake", f"{server.url}/v1/d", "secret", Backoff(FAST, seed=1))
    return DecisionApiClient("fake", "fake-1", 1000, endpoint)


async def test_success_shape_and_auth(serve: Any) -> None:
    server = serve([])
    result = await _client(server).decide("diary", QUESTIONS)
    assert result.probabilities["risk__r0"] == {"Darro": 0.7, "Kell": 0.3}
    assert result.input_tokens == 123
    assert result.model_version == "fake-1"
    assert result.http_status == 200
    assert server.headers[0]["Authorization"] == "Bearer secret"
    request = server.requests[0]
    assert request["model"] == "fake-1"
    assert request["state"] == "diary"
    assert request["questions"]["risk__r0"] == {
        "type": "choice",
        "instructions": "Which?",
        "criteria": {"Darro": None, "Kell": None},
    }


@pytest.mark.parametrize(
    "fault",
    [
        (429, {"error": "slow down"}),
        (503, "unavailable"),
        (200, "this is not json"),
        (200, {"answers": {}, "usage": {"input_tokens": 1}}),
        (
            200,
            {
                "answers": {"risk__r0": {"probabilities": {"Darro": 0.9, "Kell": 0.9}}},
                "usage": {"input_tokens": 1},
            },
        ),
        (200, {"answers": GOOD["answers"]}),
    ],
)
async def test_transient_faults_are_retried(serve: Any, fault: tuple[int, Any]) -> None:
    server = serve([fault, fault])
    result = await _client(server).decide("diary", QUESTIONS)
    assert result.input_tokens == 123
    assert len(server.requests) == 3


async def test_402_stops_without_retry(serve: Any) -> None:
    server = serve([], default=(402, {"error": "no credits"}))
    with pytest.raises(StopRun):
        await _client(server).decide("diary", QUESTIONS)
    assert len(server.requests) == 1


async def test_401_stops_without_retry(serve: Any) -> None:
    server = serve([], default=(401, {"error": "bad key"}))
    with pytest.raises(StopRun):
        await _client(server).decide("diary", QUESTIONS)
    assert len(server.requests) == 1


async def test_daily_cap_stops_the_model(serve: Any) -> None:
    server = serve([], default=(429, {"code": "REQUEST_LIMIT_EXCEEDED"}))
    with pytest.raises(StopModel):
        await _client(server).decide("diary", QUESTIONS)
    assert len(server.requests) == 1


async def test_persistent_503_fails_the_job_as_unbilled(serve: Any) -> None:
    server = serve([], default=(503, "down"))
    with pytest.raises(CallFailed) as caught:
        await _client(server).decide("diary", QUESTIONS)
    assert not caught.value.maybe_billed
    assert len(server.requests) == FAST.max_attempts


async def test_persistent_malformed_may_be_billed(serve: Any) -> None:
    server = serve([], default=(200, "garbage"))
    with pytest.raises(CallFailed) as caught:
        await _client(server).decide("diary", QUESTIONS)
    assert caught.value.maybe_billed


async def test_400_fails_without_retry(serve: Any) -> None:
    server = serve([], default=(400, {"error": "too long"}))
    with pytest.raises(CallFailed):
        await _client(server).decide("diary", QUESTIONS)
    assert len(server.requests) == 1


def test_backoff_is_seeded_bounded_and_honours_retry_after() -> None:
    config = BackoffConfig(base_s=1.0, cap_s=4.0)
    first = [Backoff(config, seed=7).delay(a) for a in range(6)]
    second = [Backoff(config, seed=7).delay(a) for a in range(6)]
    assert first == second
    assert all(0 <= delay <= 4.0 for delay in first)
    assert Backoff(config, seed=7).delay(0, retry_after=30.0) == 30.0


def _chat_reply(content: Any) -> dict[str, Any]:
    return {
        "model": "chat-1",
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 55},
    }


def _chat_client(server: FaultServer) -> OpenAIChatClient:
    endpoint = HttpEndpoint("chat", f"{server.url}/chat", "k", Backoff(FAST, seed=2))
    return OpenAIChatClient("chat", "chat-1", 1000, endpoint)


async def test_openai_chat_is_one_hot_and_verbalized(serve: Any) -> None:
    fenced = f'{FENCE}json\n{{"risk__r0": "Kell"}}\n{FENCE}'
    server = serve([(200, _chat_reply(fenced))])
    result = await _chat_client(server).decide("diary", QUESTIONS)
    assert result.probabilities["risk__r0"] == {"Darro": 0.0, "Kell": 1.0}
    assert result.probabilities_source == "verbalized"
    assert result.input_tokens == 55


async def test_openai_chat_retries_an_invalid_option(serve: Any) -> None:
    server = serve(
        [(200, _chat_reply('{"risk__r0": "Nowhere"}'))],
        default=(200, _chat_reply('{"risk__r0": "Darro"}')),
    )
    result = await _chat_client(server).decide("diary", QUESTIONS)
    assert result.probabilities["risk__r0"]["Darro"] == 1.0
    assert len(server.requests) == 2


def test_chat_payload_names_every_option() -> None:
    content = build_payload("m", "diary", QUESTIONS)["messages"][1]["content"]
    assert "diary" in content and '"Darro"' in content and '"Kell"' in content


def test_load_models_reads_the_registry() -> None:
    entries = load_models("configs/models.yaml")
    assert {entry.adapter for entry in entries} == {"decision_api"}
    assert next(e for e in entries if e.id == "snap").budget_capped


async def test_get_client_builds_each_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_KEY", "k")
    common: dict[str, Any] = {"display": "x", "window": 1000, "price_input_per_m": 0.1}
    decision = ModelEntry(
        id="a",
        adapter="decision_api",
        model_id="m",
        base_url="http://x/",
        path="/p",
        api_key_env="FAKE_KEY",
        **common,
    )
    chat = ModelEntry(
        id="b",
        adapter="openai_chat",
        model_id="m",
        base_url="http://x",
        api_key_env="FAKE_KEY",
        **common,
    )
    mock = ModelEntry(id="c", adapter="mock", model_id="kind=window,horizon=10", **common)
    clients = {e.id: get_client(e) for e in (decision, chat, mock)}
    first, second = clients["a"], clients["b"]
    assert isinstance(first, DecisionApiClient)
    assert first.endpoint.url == "http://x/p"
    assert isinstance(second, OpenAIChatClient)
    assert second.endpoint.url == "http://x/v1/chat/completions"
    assert getattr(clients["c"], "is_mock", False)
    await close_clients(clients)


def test_missing_key_names_the_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISSING_KEY", raising=False)
    entry = ModelEntry(
        id="a",
        display="x",
        adapter="decision_api",
        model_id="m",
        window=1000,
        price_input_per_m=0.1,
        base_url="http://x",
        api_key_env="MISSING_KEY",
    )
    with pytest.raises(ConfigError, match="MISSING_KEY"):
        get_client(entry)
