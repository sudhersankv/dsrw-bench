"""Expands a run config into jobs and estimates their cost without calling anything."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path

from pydantic import BaseModel

from swb.config import Cell, ModelLimit, RunConfig, load_run_config
from swb.contracts import Job, LadderSpec, ModelEntry, Policy, WorldKind, WorldSpec
from swb.diary.lengths import days_for_tokens, reversal_ms

W1000_DAYS = 1000
SUMMARY_TOKENS = {"e700": 100, "table": 100, "oracle": 20}
# Header and questions on top of the diary; a generous figure until the pilot measures it.
PROMPT_OVERHEAD_TOKENS = 250


def job_id_for(job_fields: dict[str, object]) -> str:
    """Stable hash shaped as a uuid, so it can double as the results table's call_id."""
    canonical = json.dumps(job_fields, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).hexdigest()[:32]
    return f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:]}"


def estimated_tokens(policy: Policy, n_days: int, tokens_per_day: float) -> int:
    if policy in SUMMARY_TOKENS:
        return SUMMARY_TOKENS[policy]
    days = min(n_days, W1000_DAYS) if policy == "w1000" else n_days
    return int(days * tokens_per_day)


def _within_limit(limit: ModelLimit | None, target_tokens: int, n_days: int) -> bool:
    if limit is None:
        return True
    if limit.max_tokens is not None and target_tokens > limit.max_tokens:
        return False
    return limit.max_days is None or n_days <= limit.max_days


def _model_runs_cell(entry: ModelEntry, cell: Cell) -> bool:
    if cell.only_models is not None and entry.id not in cell.only_models:
        return False
    return entry.id not in cell.skip_models


def _fits(
    entry: ModelEntry,
    config: RunConfig,
    world: WorldKind,
    policy: Policy,
    n_days: int,
    target_tokens: int,
) -> bool:
    diary_tokens = estimated_tokens(policy, n_days, config.tokens_per_day_for(world))
    if diary_tokens + PROMPT_OVERHEAD_TOKENS > entry.usable_window:
        return False
    return _within_limit(config.model_limits.get(entry.id), target_tokens, n_days)


class _Point(BaseModel):
    """One world setting of a cell, before policies, seeds and models are applied."""

    world: WorldSpec
    target_tokens: int
    label: str
    policy_override: Policy | None = None


def _lengths(cell: Cell, config: RunConfig) -> Iterator[tuple[int, int, str]]:
    """Yields (n_days, target_tokens, label) for every length in the cell."""
    tokens_per_day = config.tokens_per_day_for(cell.world)
    for tokens in cell.lengths_tokens:
        days = days_for_tokens(tokens, tokens_per_day)
        yield days + cell.extra_days, tokens, f"L{tokens}t"
    for days in cell.lengths_days:
        tokens = int(days * tokens_per_day)
        yield days + cell.extra_days, tokens, f"L{days}d"


def _steady_points(cell: Cell, config: RunConfig) -> Iterator[_Point]:
    for contrast in cell.contrasts:
        for days, tokens, label in _lengths(cell, config):
            world = WorldSpec(kind="steady", n_days=days, contrast=contrast)
            yield _Point(world=world, target_tokens=tokens, label=f"{contrast}|{label}")


def _reversal_points(cell: Cell, config: RunConfig) -> Iterator[_Point]:
    for contrast in cell.contrasts:
        for days, tokens, label in _lengths(cell, config):
            for m in cell.reversal_ms or reversal_ms(days):
                world = WorldSpec(kind="reversal", n_days=days, contrast=contrast, reversal_m=m)
                yield _Point(world=world, target_tokens=tokens, label=f"{contrast}|{label}|m{m}")


def _ladder_world(days: int, rung: str, lag: int, side: str) -> WorldSpec:
    ladder = LadderSpec.model_validate({"rung": rung, "lag_days": lag, "pair_side": side})
    return WorldSpec(kind="ladder", n_days=days, ladder=ladder)


def _ladder_points(cell: Cell, config: RunConfig) -> Iterator[_Point]:
    for days, tokens, label in _lengths(cell, config):
        lags = sorted({min(lag, days - 100) for lag in cell.lags[tokens]})
        for rung in cell.rungs:
            for side in ("A", "B"):
                for lag in lags:
                    yield _Point(
                        world=_ladder_world(days, rung, lag, side),
                        target_tokens=tokens,
                        label=f"{rung}|{label}|k{lag}",
                    )
                if cell.shuffled_lag is not None:
                    yield _Point(
                        world=_ladder_world(days, rung, cell.shuffled_lag, side),
                        target_tokens=tokens,
                        label=f"{rung}|{label}|k{cell.shuffled_lag}",
                        policy_override="shuffled",
                    )


def _points(cell: Cell, config: RunConfig) -> Iterator[_Point]:
    if cell.world == "steady":
        return _steady_points(cell, config)
    if cell.world == "reversal":
        return _reversal_points(cell, config)
    return _ladder_points(cell, config)


def _policies_for(cell: Cell, point: _Point) -> list[Policy]:
    if point.policy_override is not None:
        return [point.policy_override]
    return [p for p in cell.policies if p != "w1000" or point.world.n_days > W1000_DAYS]


def _condition_id(cell: Cell, point: _Point, policy: Policy, repeat: int) -> str:
    parts = [point.world.kind, point.label, policy]
    if cell.tag:
        parts.append(cell.tag)
    if cell.repeats > 1:
        parts.append(f"repeat{repeat}")
    return "|".join(parts)


def _make_job(
    config: RunConfig,
    cell: Cell,
    point: _Point,
    policy: Policy,
    model: str,
    seed: int,
    repeat: int,
) -> Job:
    fields: dict[str, object] = {
        "run_id": config.run_id,
        "condition_id": _condition_id(cell, point, policy, repeat),
        "model": model,
        "world": point.world.model_dump(mode="json"),
        "seed": seed,
        "policy": policy,
        "length_tokens_target": point.target_tokens,
        "question_keys": list(cell.question_keys),
        "replicates": cell.replicates or config.replicates,
        "root_seed": config.root_seed,
    }
    return Job.model_validate({**fields, "job_id": job_id_for(fields)})


def _expand_cell(config: RunConfig, cell: Cell, models: list[ModelEntry]) -> Iterator[Job]:
    """Jobs are grouped by diary, then model, so one prepared diary serves every model in turn."""
    runnable = [entry for entry in models if _model_runs_cell(entry, cell)]
    seeds = (cell.seeds or config.seeds).values()
    for point in _points(cell, config):
        for policy in _policies_for(cell, point):
            for seed in seeds:
                for repeat in range(cell.repeats):
                    for entry in runnable:
                        if _fits(
                            entry,
                            config,
                            point.world.kind,
                            policy,
                            point.world.n_days,
                            point.target_tokens,
                        ):
                            yield _make_job(config, cell, point, policy, entry.id, seed, repeat)


def expand_config(config: RunConfig, models: list[ModelEntry]) -> list[Job]:
    return [job for cell in config.cells for job in _expand_cell(config, cell, models)]


def expand(config_path: str | Path, models: list[ModelEntry]) -> list[Job]:
    return expand_config(load_run_config(config_path), models)


class ModelEstimate(BaseModel):
    run_id: str
    model: str
    calls: int = 0
    tokens: int = 0
    usd: float = 0.0
    hours_at_limit: float | None = None


def estimate(config: RunConfig, jobs: list[Job], models: list[ModelEntry]) -> list[ModelEstimate]:
    """Calls, tokens, dollars and rate-limit hours per model. Costs nothing and calls nothing."""
    by_id = {entry.id: entry for entry in models}
    estimates: dict[str, ModelEstimate] = {}
    for job in jobs:
        row = estimates.setdefault(job.model, ModelEstimate(run_id=job.run_id, model=job.model))
        tokens = estimated_tokens(
            job.policy, job.world.n_days, config.tokens_per_day_for(job.world.kind)
        )
        row.calls += 1
        row.tokens += tokens
        row.usd += tokens * by_id[job.model].price_input_per_m / 1e6
    for row in estimates.values():
        rate = config.rate_limits.get(by_id[row.model].api_key_env or "")
        row.hours_at_limit = row.tokens / rate / 60 if rate else None
    return list(estimates.values())
