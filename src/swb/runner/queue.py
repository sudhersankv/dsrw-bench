"""Async job queue: prepares each diary, checks the budget, calls the model, stores the rows."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np

from swb.baselines.scores import baseline_scores
from swb.clients.base import CallFailed, StopModel, StopRun
from swb.contracts import (
    DecisionClient,
    DecisionResult,
    Diary,
    Job,
    ModelEntry,
    Question,
    QuestionKey,
    ResultRow,
    View,
)
from swb.diary.render import sha256
from swb.diary.worlds import generate
from swb.harness.policies import apply
from swb.questions.build import build
from swb.questions.truth import empirical, truth
from swb.runner.budget import BudgetGuard, usd_for
from swb.runner.tokens import Calibration, limiter_tokens, token_problem
from swb.store.base import ResultStore

log = logging.getLogger(__name__)

CACHE_SIZE = 256


@dataclass(frozen=True)
class QuestionFacts:
    truth: str
    truth_empirical: str | None
    baselines: dict[str, dict[str, float]]


@dataclass(frozen=True)
class PreparedDiary:
    diary: Diary
    digest: str
    questions: dict[str, Question]
    facts: dict[str, QuestionFacts]  # by question name


@dataclass
class RunSummary:
    completed: int = 0
    skipped: int = 0
    failed: list[str] = field(default_factory=list)
    refused: list[str] = field(default_factory=list)
    token_problems: list[str] = field(default_factory=list)
    stopped_models: dict[str, str] = field(default_factory=dict)
    stopped_run: str | None = None

    @property
    def clean(self) -> bool:
        return not (
            self.failed
            or self.refused
            or self.token_problems
            or self.stopped_models
            or self.stopped_run
        )


def option_seed_for(job: Job) -> int:
    """Independent of model and policy, so every model sees byte-identical questions."""
    sequence = np.random.SeedSequence([job.root_seed, job.seed, 0x6F70])
    return int(sequence.generate_state(1)[0])


def _facts_for(diary: Diary, question: Question) -> QuestionFacts:
    return QuestionFacts(
        truth=truth(diary, question.key),
        truth_empirical=empirical(diary, question.key),
        baselines=baseline_scores(diary, question.key, question.options),
    )


def _generate(job: Job) -> Diary:
    """The pilot's prior-bias check needs an empty diary, which generate() refuses to build."""
    if job.world.n_days > 0:
        return generate(job.world, job.seed, job.root_seed)
    one_day = generate(job.world.model_copy(update={"n_days": 1}), job.seed, job.root_seed)
    return one_day.model_copy(
        update={"spec": job.world, "grazed": one_day.grazed[:0], "sighting": one_day.sighting[:0]}
    )


def _prepare(job: Job) -> PreparedDiary:
    diary = _generate(job)
    questions = build(diary, job.question_keys, job.replicates, option_seed_for(job))
    facts = {name: _facts_for(diary, question) for name, question in questions.items()}
    return PreparedDiary(diary, sha256(diary), questions, facts)


class _PreparedCache:
    """Diaries, truths and baselines are per diary, so all models and policies share them."""

    def __init__(self) -> None:
        self._items: OrderedDict[str, PreparedDiary] = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def _key(job: Job) -> str:
        keys: Sequence[QuestionKey] = job.question_keys
        return f"{job.world.model_dump_json()}|{job.seed}|{job.root_seed}|{keys}|{job.replicates}"

    def get(self, job: Job) -> PreparedDiary:
        key = self._key(job)
        with self._lock:
            if key in self._items:
                self._items.move_to_end(key)
                return self._items[key]
        prepared = _prepare(job)
        with self._lock:
            self._items[key] = prepared
            while len(self._items) > CACHE_SIZE:
                self._items.popitem(last=False)
        return prepared


class TokenRateLimiter:
    """Spaces requests so an account stays under its input tokens per minute."""

    def __init__(self, tokens_per_minute: int) -> None:
        self._per_second = tokens_per_minute / 60
        self._next_free = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: int) -> None:
        async with self._lock:
            now = time.monotonic()
            start = max(now, self._next_free)
            self._next_free = start + tokens / self._per_second
        delay = start - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)


def build_rows(
    job: Job, prepared: PreparedDiary, result: DecisionResult, entry: ModelEntry
) -> list[ResultRow]:
    diary = prepared.diary
    ladder = job.world.ladder
    now = datetime.now(UTC).isoformat()
    true_rates = (
        dict(zip(diary.names, diary.tomorrow_rates, strict=True))
        if diary.tomorrow_rates is not None
        else None
    )
    rows: list[ResultRow] = []
    for name, question in prepared.questions.items():
        facts = prepared.facts[name]
        rows.append(
            ResultRow(
                row_id=str(uuid.uuid5(uuid.UUID(job.job_id), name)),
                call_id=job.job_id,
                run_id=job.run_id,
                condition_id=job.condition_id,
                model=job.model,
                model_version=result.model_version,
                world=job.world.kind,
                contrast=job.world.contrast,
                policy=job.policy,
                vocab=job.world.vocab,
                length_tokens_target=job.length_tokens_target,
                input_tokens=result.input_tokens,
                n_days=job.world.n_days,
                seed=job.seed,
                reversal_m=job.world.reversal_m,
                lag_days=ladder.lag_days if ladder else None,
                rung=ladder.rung if ladder else None,
                pair_side=ladder.pair_side if ladder else None,
                diary_sha256=prepared.digest,
                question_key=question.key,
                replicate=question.replicate,
                option_order=question.options,
                probabilities=result.probabilities[name],
                probabilities_source=result.probabilities_source,
                truth=facts.truth,
                truth_empirical=facts.truth_empirical,
                old_truth=diary.names[diary.old_hot] if diary.old_hot is not None else None,
                true_rates=true_rates,
                baseline_scores=facts.baselines,
                latency_ms=result.latency_ms,
                http_status=result.http_status,
                cost_usd=usd_for(result.input_tokens, entry) if entry.budget_capped else None,
                is_mock=entry.adapter == "mock",
                created_at=now,
            )
        )
    return rows


class _Runner:
    def __init__(
        self,
        clients: dict[str, DecisionClient],
        store: ResultStore,
        entries: dict[str, ModelEntry],
        guard: BudgetGuard,
        limiters: dict[str, TokenRateLimiter],
        calibration: Calibration | None,
    ) -> None:
        self.clients = clients
        self.store = store
        self.entries = entries
        self.guard = guard
        self.limiters = limiters
        self.calibration = calibration
        self.cache = _PreparedCache()
        self.summary = RunSummary()

    async def process(self, job: Job) -> None:
        entry = self.entries[job.model]
        prepared = await asyncio.to_thread(self.cache.get, job)
        view: View = await asyncio.to_thread(apply, job.policy, prepared.diary)
        if not await asyncio.to_thread(self.guard.reserve, job.job_id, entry, view.est_tokens):
            self._refuse(job)
            return
        limiter = self.limiters.get(entry.api_key_env or "")
        if limiter is not None:
            await limiter.acquire(limiter_tokens(job, view.est_tokens, self.calibration))
        await self._call_and_store(job, entry, prepared, view)

    def _refuse(self, job: Job) -> None:
        log.warning("budget guard refused job %s (%s)", job.job_id, job.condition_id)
        self.summary.refused.append(job.job_id)
        self.summary.stopped_models.setdefault(job.model, "budget cap would be exceeded")

    async def _call_and_store(
        self, job: Job, entry: ModelEntry, prepared: PreparedDiary, view: View
    ) -> None:
        try:
            result = await self.clients[job.model].decide(view.text, prepared.questions)
        except StopRun as exc:
            await asyncio.to_thread(self.guard.release, job.job_id, entry)
            log.error("stopping run: %s", exc)
            self.summary.stopped_run = str(exc)
            return
        except StopModel as exc:
            await asyncio.to_thread(self.guard.release, job.job_id, entry)
            log.error("stopping model: %s", exc)
            self.summary.stopped_models.setdefault(job.model, str(exc))
            return
        except CallFailed as exc:
            if exc.maybe_billed:
                billed = view.est_tokens * exc.billed_attempts
                await asyncio.to_thread(self.guard.carry, job.job_id, entry, billed)
            else:
                await asyncio.to_thread(self.guard.release, job.job_id, entry)
            log.error("job %s failed: %s", job.job_id, exc)
            self.summary.failed.append(job.job_id)
            return
        billed = result.input_tokens * result.billed_attempts
        problem = token_problem(job, result.input_tokens, entry, self.calibration)
        if problem is not None:
            await asyncio.to_thread(self.guard.settle, job.job_id, entry, billed)
            self._reject(job, problem)
            return
        rows = build_rows(job, prepared, result, entry)
        await asyncio.to_thread(self.store.write, rows)
        await asyncio.to_thread(self.guard.settle, job.job_id, entry, billed)
        self.summary.completed += 1

    def _reject(self, job: Job, problem: str) -> None:
        """The diary the model read may not be the diary we sent, so no row is stored."""
        log.error("token check failed for job %s: %s", job.job_id, problem)
        self.summary.token_problems.append(job.job_id)
        self.summary.stopped_models.setdefault(job.model, f"token check: {problem}")

    def should_skip(self, job: Job) -> bool:
        return self.summary.stopped_run is not None or job.model in self.summary.stopped_models


async def _worker(runner: _Runner, queue: asyncio.Queue[Job]) -> None:
    while True:
        try:
            job = queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        if runner.should_skip(job):
            continue
        await runner.process(job)


async def run_jobs(
    jobs: list[Job],
    clients: dict[str, DecisionClient],
    store: ResultStore,
    *,
    entries: list[ModelEntry],
    cap_usd: float,
    concurrency: int = 4,
    rate_limits: dict[str, int] | None = None,
    calibration: Calibration | None = None,
) -> RunSummary:
    """Runs every job not already in the store. Safe to call again after a crash or a stop."""
    limiters = {key: TokenRateLimiter(rate) for key, rate in (rate_limits or {}).items()}
    runner = _Runner(
        clients,
        store,
        {e.id: e for e in entries},
        BudgetGuard(store, cap_usd),
        limiters,
        calibration,
    )
    counts = await asyncio.to_thread(store.job_row_counts)
    queue: asyncio.Queue[Job] = asyncio.Queue()
    for job in jobs:
        if counts.get(job.job_id, 0) >= len(job.question_keys) * job.replicates:
            runner.summary.skipped += 1
        else:
            queue.put_nowait(job)
    await asyncio.gather(*(_worker(runner, queue) for _ in range(concurrency)))
    return runner.summary
