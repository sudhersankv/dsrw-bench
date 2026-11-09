"""Ladder shift and RK(k) (spec "Aggregate metrics")."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from swb.analysis.metrics import CLIP
from swb.analysis.stats import Array
from swb.contracts import Policy, QuestionKey, ResultRow, Rung

SHORT_LAGS: tuple[int, ...] = (1, 3, 10)
MIN_LAG_FOR_RK = 100
MIN_SHIFT_OVER_SE = 5.0

ShiftTable = dict[int, dict[int, float]]  # lag -> seed -> shift in nats


@dataclass(frozen=True)
class RkInputs:
    """Per-seed numerator and denominator of RK, averaged over the lags asked for."""

    seeds: list[int]
    numerator: Array
    denominator: Array
    lags: tuple[int, ...]


def _log_odds(row: ResultRow, first: str, second: str) -> float:
    a = max(row.probabilities.get(first, 0.0), CLIP)
    b = max(row.probabilities.get(second, 0.0), CLIP)
    return math.log(a) - math.log(b)


def pair_shift(side_a: ResultRow, side_b: ResultRow) -> float:
    """Half the change in (log pi_A - log pi_B) between D_A and D_B; positive means evidence used."""
    first, second = side_a.truth, side_b.truth
    return 0.5 * (_log_odds(side_a, first, second) - _log_odds(side_b, first, second))


def shift_table(
    rows: list[ResultRow],
    question: QuestionKey,
    rung: Rung,
    length_tokens: int,
    policy: Policy = "raw",
) -> ShiftTable:
    """Shift per lag and seed. A swapped pair is one seed; replicates are averaged within it."""
    sides: dict[tuple[int, int, int], dict[str, ResultRow]] = defaultdict(dict)
    for row in rows:
        if (
            row.world == "ladder"
            and row.question_key == question
            and row.rung == rung
            and row.length_tokens_target == length_tokens
            and row.policy == policy
            and row.lag_days is not None
            and row.pair_side is not None
        ):
            sides[(row.lag_days, row.seed, row.replicate)][row.pair_side] = row
    per_seed: dict[tuple[int, int], list[float]] = defaultdict(list)
    for (lag, seed, _), pair in sides.items():
        if "A" in pair and "B" in pair:
            per_seed[(lag, seed)].append(pair_shift(pair["A"], pair["B"]))
    table: ShiftTable = defaultdict(dict)
    for (lag, seed), values in per_seed.items():
        table[lag][seed] = float(np.mean(values))
    return dict(table)


def _complete_seeds(table: ShiftTable, lags: tuple[int, ...]) -> list[int]:
    if not lags or any(lag not in table for lag in lags):
        return []
    return sorted(set.intersection(*(set(table[lag]) for lag in lags)))


def denominator_by_seed(table: ShiftTable) -> dict[int, float]:
    """Mean shift over the three shortest lags, for seeds that have all three."""
    seeds = _complete_seeds(table, SHORT_LAGS)
    return {seed: float(np.mean([table[lag][seed] for lag in SHORT_LAGS])) for seed in seeds}


def denominator_measurable(denominator: dict[int, float]) -> bool:
    """The spec rule: RK exists only when the short-lag shift is at least 5 standard errors."""
    if len(denominator) < 2:
        return False
    values = np.array(list(denominator.values()))
    se = float(values.std(ddof=1)) / math.sqrt(len(values))
    mean = float(values.mean())
    if se == 0.0:
        return mean > 0.0
    return mean / se >= MIN_SHIFT_OVER_SE


def rk_inputs(table: ShiftTable, lags: tuple[int, ...]) -> RkInputs | None:
    """Inputs for mean RK over `lags`, or None when RK is unavailable under the spec rule."""
    denominator = denominator_by_seed(table)
    if not denominator_measurable(denominator):
        return None
    seeds = sorted(set(denominator) & set(_complete_seeds(table, lags)))
    if len(seeds) < 2:
        return None
    numerator = np.array([np.mean([table[lag][seed] for lag in lags]) for seed in seeds])
    return RkInputs(seeds, numerator, np.array([denominator[seed] for seed in seeds]), lags)


def rk_at(table: ShiftTable, lag: int) -> float | None:
    """RK(lag) as a ratio of means, or None when unavailable."""
    inputs = rk_inputs(table, (lag,))
    return None if inputs is None else float(inputs.numerator.mean() / inputs.denominator.mean())


def long_lags(table: ShiftTable) -> tuple[int, ...]:
    return tuple(sorted(lag for lag in table if lag >= MIN_LAG_FOR_RK))
