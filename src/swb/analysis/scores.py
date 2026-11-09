"""Sub-scores and the Flock score, exactly as defined in docs/SCORING.md."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from typing import Literal

import numpy as np

from swb.analysis.ladder import ShiftTable, long_lags, rk_inputs, shift_table
from swb.analysis.metrics import CHANCE_PASTURE, baseline_p, format_tokens, p_correct
from swb.analysis.stats import Estimate, Term, align, bootstrap
from swb.contracts import QuestionKey, ResultRow, SubScore

USABLE_MARGIN = 0.20
_TOLERANCE = 1e-9
TOP1_ONLY = "top-1 only: this model gives one answer, so log-odds shifts are not meaningful"

CellKey = Callable[[ResultRow], Hashable]
SubScoreId = Literal["history", "adapt", "recall", "use"]


@dataclass(frozen=True)
class Pooled:
    estimate: Estimate
    model_mean: float
    ceiling_mean: float
    usable: int
    total: int


def is_usable(ceiling: float) -> bool:
    return ceiling - CHANCE_PASTURE >= USABLE_MARGIN - _TOLERANCE


def ceiling_of(rows: list[ResultRow], baseline: str) -> float | None:
    values = [p for row in rows if (p := baseline_p(row, baseline)) is not None]
    return float(np.mean(values)) if values else None


def _usable_cells(
    rows: list[ResultRow], key: CellKey, baseline: str
) -> tuple[list[list[ResultRow]], int]:
    cells: dict[Hashable, list[ResultRow]] = defaultdict(list)
    for row in rows:
        cells[key(row)].append(row)
    usable = []
    for cell in cells.values():
        ceiling = ceiling_of(cell, baseline)
        if ceiling is not None and is_usable(ceiling):
            usable.append(cell)
    return usable, len(cells)


def _seed_excess(
    cells: list[list[ResultRow]], baseline: str
) -> tuple[dict[int, float], dict[int, float]]:
    """Per-seed mean excess over chance, for the model and its ceiling, pooled over usable cells."""
    model_by_seed: dict[int, list[float]] = defaultdict(list)
    ceiling_by_seed: dict[int, list[float]] = defaultdict(list)
    for cell in cells:
        per_seed: dict[int, list[tuple[float, float]]] = defaultdict(list)
        for row in cell:
            ceiling = baseline_p(row, baseline)
            if ceiling is not None:
                per_seed[row.seed].append(
                    (p_correct(row) - CHANCE_PASTURE, ceiling - CHANCE_PASTURE)
                )
        for seed, pairs in per_seed.items():
            model_by_seed[seed].append(float(np.mean([p[0] for p in pairs])))
            ceiling_by_seed[seed].append(float(np.mean([p[1] for p in pairs])))
    return (
        {seed: float(np.mean(v)) for seed, v in model_by_seed.items()},
        {seed: float(np.mean(v)) for seed, v in ceiling_by_seed.items()},
    )


def pooled_ratio(
    rows: list[ResultRow], key: CellKey, baseline: str, resamples: int
) -> Pooled | None:
    """Ratio of means over usable cells: mean(model - chance) / mean(ceiling - chance)."""
    cells, total = _usable_cells(rows, key, baseline)
    if not cells:
        return None
    model, ceiling = _seed_excess(cells, baseline)
    _, (x, y) = align(model, ceiling)
    return Pooled(
        bootstrap([Term(x, y)], resamples), float(x.mean()), float(y.mean()), len(cells), total
    )


def _versus_chance(excess: float) -> str:
    return f"{abs(excess):.3f} {'above' if excess >= 0 else 'below'} guessing"


def _capped(pooled: Pooled) -> str:
    if pooled.estimate.value > 1.0:
        return f" ({100 * pooled.estimate.value:.0f} before capping at 100)"
    if pooled.estimate.value < 0.0:
        return " (below zero, so shown as 0)"
    return ""


def _to_score(value: float | None) -> float | None:
    return None if value is None else float(np.clip(100.0 * value, 0.0, 100.0))


def _unavailable(score_id: SubScoreId, label: str, how: str, note: str | None = None) -> SubScore:
    return SubScore(id=score_id, label=label, score=None, how=how, cells_used=0, note=note)


def _dropped_note(pooled: Pooled, unit: str) -> str | None:
    dropped = pooled.total - pooled.usable
    if dropped == 0:
        return None
    return f"{dropped} of {pooled.total} {unit} skipped because even the reference could not beat chance by 0.20."


def uses_history(rows: list[ResultRow], resamples: int) -> SubScore:
    label = "Uses history"
    selected = [
        r for r in rows if r.world == "steady" and r.question_key == "risk" and r.policy == "raw"
    ]
    pooled = pooled_ratio(
        selected, lambda r: (r.contrast, r.length_tokens_target), "beta", resamples
    )
    if pooled is None:
        return _unavailable(
            "history",
            label,
            "Not testable: no steady diary long enough for a counter to beat chance by 0.20.",
        )
    how = (
        f"Compared the whole diary with simple counting on {pooled.usable} diary lengths and "
        f"{pooled.estimate.n} sheep lives: the model sat {_versus_chance(pooled.model_mean)}, "
        f"the counter {_versus_chance(pooled.ceiling_mean)}, and the score is the first divided "
        f"by the second{_capped(pooled)}."
    )
    return _score_card("history", label, pooled, how, "diary lengths")


def adapts(rows: list[ResultRow], resamples: int) -> SubScore:
    label = "Adapts"
    selected = [
        r
        for r in rows
        if r.world == "reversal" and r.question_key == "current" and r.policy == "raw"
    ]
    pooled = pooled_ratio(
        selected, lambda r: (r.contrast, r.n_days, r.reversal_m), "filter", resamples
    )
    if pooled is None:
        return _unavailable(
            "adapt",
            label,
            "Not testable: no reversal condition where a change-point filter beat chance by 0.20.",
        )
    how = (
        f"After the wolf moved, compared the model with a change-point filter over "
        f"{pooled.usable} conditions and {pooled.estimate.n} sheep lives: the model sat "
        f"{_versus_chance(pooled.model_mean)} on the new danger field, the filter "
        f"{_versus_chance(pooled.ceiling_mean)}, and the score is the first divided by the "
        f"second{_capped(pooled)}."
    )
    return _score_card("adapt", label, pooled, how, "conditions")


def _score_card(score_id: SubScoreId, label: str, pooled: Pooled, how: str, unit: str) -> SubScore:
    estimate = pooled.estimate
    return SubScore(
        id=score_id,
        label=label,
        score=_to_score(estimate.value),
        lo=_to_score(estimate.lo),
        hi=_to_score(estimate.hi),
        how=how,
        cells_used=pooled.usable,
        note=_dropped_note(pooled, unit),
    )


def _longest_ladder(rows: list[ResultRow]) -> int | None:
    lengths = {
        r.length_tokens_target
        for r in rows
        if r.world == "ladder"
        and r.rung == "statistical"
        and r.policy == "raw"
        and r.question_key == "report"
    }
    return max(lengths) if lengths else None


def _usable_lags(rows: list[ResultRow], table: ShiftTable, length: int) -> tuple[int, ...]:
    """Lags k >= 100 where the Beta counter's report ceiling clears the usable-cell rule."""
    usable = []
    for lag in long_lags(table):
        cell = [
            r
            for r in rows
            if r.world == "ladder"
            and r.rung == "statistical"
            and r.policy == "raw"
            and r.question_key == "report"
            and r.length_tokens_target == length
            and r.lag_days == lag
        ]
        ceiling = ceiling_of(cell, "beta")
        if ceiling is not None and is_usable(ceiling):
            usable.append(lag)
    return tuple(usable)


def _ladder_score(
    rows: list[ResultRow],
    score_id: SubScoreId,
    label: str,
    question: QuestionKey,
    resamples: int,
    verbalized: bool,
) -> SubScore:
    if verbalized:
        return _unavailable(
            score_id,
            label,
            "Not testable: this model gives one answer instead of probabilities.",
            TOP1_ONLY,
        )
    length = _longest_ladder(rows)
    if length is None:
        return _unavailable(
            score_id, label, "Not testable: no old-clue diaries were run for this model."
        )
    report_table = shift_table(rows, "report", "statistical", length)
    lags = _usable_lags(rows, report_table, length)
    if not lags:
        return _unavailable(
            score_id,
            label,
            "Not testable: no old-clue lag of 100 days or more had a usable counter ceiling.",
        )
    table = (
        report_table if question == "report" else shift_table(rows, question, "statistical", length)
    )
    inputs = rk_inputs(table, lags)
    if inputs is None:
        return _unavailable(
            score_id,
            label,
            f"Not testable at {format_tokens(length)} tokens: fresh clues did not move this answer reliably enough to compare old clues against.",
            "unmeasurable at this length",
        )
    estimate = bootstrap([Term(inputs.numerator, inputs.denominator)], resamples)
    verb = "report where wolves were seen" if question == "report" else "pick which field to avoid"
    how = (
        f"How strongly a clue 100 or more days old moved the answer when asked to {verb}, as a "
        f"share of a clue 1 to 10 days old: {inputs.numerator.mean():.2f} versus "
        f"{inputs.denominator.mean():.2f} on the same scale, over {len(lags)} ages at "
        f"{format_tokens(length)} tokens and {estimate.n} sheep lives."
    )
    return SubScore(
        id=score_id,
        label=label,
        score=_to_score(estimate.value),
        lo=_to_score(estimate.lo),
        hi=_to_score(estimate.hi),
        how=how,
        cells_used=len(lags),
    )


def subscores(rows: list[ResultRow], resamples: int, verbalized: bool) -> list[SubScore]:
    return [
        uses_history(rows, resamples),
        adapts(rows, resamples),
        _ladder_score(rows, "recall", "Recalls", "report", resamples, verbalized),
        _ladder_score(rows, "use", "Acts on old evidence", "decide", resamples, verbalized),
    ]


def flock_score(scores: list[SubScore]) -> float | None:
    """Mean of Uses history, Adapts and Acts on old evidence. Null unless all three exist."""
    wanted = [score.score for score in scores if score.id in ("history", "adapt", "use")]
    if len(wanted) != 3 or any(value is None for value in wanted):
        return None
    return float(np.mean([value for value in wanted if value is not None]))
