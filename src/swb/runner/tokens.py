"""The spec's token check: measured tokens per day, and what each call is allowed to report."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from pydantic import BaseModel

from swb.config import RunConfig
from swb.contracts import Job, ModelEntry, Policy, ResultRow, WorldKind
from swb.runner.jobs import W1000_DAYS

TOKEN_TOLERANCE = 0.05
# Pilot overhead was fitted on a few questions; repeated option orders add about 40 tokens each.
QUESTION_TOKEN_ALLOWANCE = 80
_LENGTH_POLICIES: tuple[Policy, ...] = ("raw", "w1000", "shuffled")
# The pilot measures steady and ladder diaries; reversal days read exactly like steady days.
_REVERSAL_AS: WorldKind = "steady"


class WorldRate(BaseModel):
    tokens_per_day: float
    overhead: float  # header and questions


Calibration = dict[str, dict[WorldKind, WorldRate]]  # model id -> world -> measured rate


def _fit(points: list[tuple[int, int]]) -> WorldRate | None:
    if len({days for days, _ in points}) < 2:
        return None
    days, tokens = zip(*points, strict=True)
    slope, intercept = np.polyfit(np.array(days, float), np.array(tokens, float), 1)
    return WorldRate(tokens_per_day=float(slope), overhead=max(float(intercept), 0.0))


def measure(rows: list[ResultRow]) -> Calibration:
    """Tokens per day and overhead for each model and world, fitted on the pilot's whole diaries."""
    calls = {
        row.call_id: row
        for row in rows
        if row.run_id == "pilot" and row.policy == "raw" and row.http_status == 200
    }
    grouped: dict[tuple[str, WorldKind], list[tuple[int, int]]] = {}
    for row in calls.values():
        grouped.setdefault((row.model, row.world), []).append((row.n_days, row.input_tokens))
    calibration: Calibration = {}
    for (model, world), points in grouped.items():
        fitted = _fit(points)
        if fitted is not None:
            calibration.setdefault(model, {})[world] = fitted
    for rates in calibration.values():
        if _REVERSAL_AS in rates:
            rates.setdefault("reversal", rates[_REVERSAL_AS])
    return calibration


def save(calibration: Calibration, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {m: {w: r.model_dump() for w, r in rates.items()} for m, rates in calibration.items()}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def load(path: Path) -> Calibration | None:
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        model: {world: WorldRate.model_validate(rate) for world, rate in rates.items()}
        for model, rates in raw.items()
    }


def calibration_problems(
    calibration: Calibration | None, config: RunConfig, models: list[ModelEntry]
) -> list[str]:
    """Why this config may not spend yet. Empty means its day counts match what the pilot measured."""
    if calibration is None:
        return ["no token calibration; run `swb pilot`, then `swb calibrate`"]
    worlds = {cell.world for cell in config.cells}
    problems = []
    for entry in models:
        rates = calibration.get(entry.id, {})
        for world in sorted(worlds):
            planned = config.tokens_per_day_for(world, entry.id)
            if world not in rates:
                problems.append(f"{entry.id}: no pilot measurement for {world} diaries")
            elif abs(rates[world].tokens_per_day - planned) > TOKEN_TOLERANCE * planned:
                problems.append(
                    f"{entry.id}: {world} diaries measured {rates[world].tokens_per_day:.2f} tokens "
                    f"per day but {config.run_id} plans {planned:g}; "
                    f"set world_tokens_per_day and recompute the budget"
                )
    return problems


def expected_tokens(job: Job, rate: WorldRate) -> float:
    days = min(job.world.n_days, W1000_DAYS) if job.policy == "w1000" else job.world.n_days
    return days * rate.tokens_per_day + rate.overhead


def limiter_tokens(job: Job, estimate: int, calibration: Calibration | None) -> int:
    """Tokens to charge the rate limiter: measured for this model when known, else the estimate."""
    rate = (calibration or {}).get(job.model, {}).get(job.world.kind)
    if rate is None or job.policy not in _LENGTH_POLICIES:
        return estimate
    return int(expected_tokens(job, rate))


def token_problem(
    job: Job, tokens: int, entry: ModelEntry, calibration: Calibration | None
) -> str | None:
    """Why a reported token count cannot be trusted, or None. A truncated diary is not a result."""
    if tokens > entry.window:
        return f"reported {tokens:,} input tokens, over the {entry.window:,} window"
    rate = (calibration or {}).get(job.model, {}).get(job.world.kind)
    if rate is None or job.policy not in _LENGTH_POLICIES:
        return None
    expected = expected_tokens(job, rate)
    allowance = QUESTION_TOKEN_ALLOWANCE * len(job.question_keys) * job.replicates
    if abs(tokens - expected) > TOKEN_TOLERANCE * expected + allowance:
        return f"reported {tokens:,} input tokens, expected about {expected:,.0f}"
    return None
