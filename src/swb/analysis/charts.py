"""Curves and plain-language takeaways for the three charts on a model card."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from swb.analysis.effective import effective_evidence
from swb.analysis.harness import POLICY_LABELS
from swb.analysis.ladder import shift_table
from swb.analysis.metrics import (
    Value,
    baseline_margin,
    baseline_p,
    format_tokens,
    margin_new_old,
    p_correct,
    seed_means,
)
from swb.analysis.reversal import describe_crossing
from swb.analysis.stats import align, bootstrap, mean_term
from swb.contracts import Chart, Curve, CurvePoint, Policy, QuestionKey, ResultRow, Rung

CONTRAST_LABELS = {"7pt": "narrow gap", "2pt": "tiny gap", "high": "wide gap"}
STEADY_POLICIES: tuple[Policy, ...] = ("raw", "w1000", "table")
REVERSAL_POLICIES: tuple[Policy, ...] = ("raw", "w1000")
REVERSAL_REFERENCES = {
    "filter": "Change detector",
    "w1000": "Last-1,000-day code",
}
_QUESTION_LABELS: dict[QuestionKey, str] = {
    "report": "Where wolves were seen",
    "decide": "Which field to avoid",
}


def mean_point(x: float, per_seed: dict[int, float], resamples: int) -> CurvePoint | None:
    if not per_seed:
        return None
    _, (values,) = align(per_seed)
    estimate = bootstrap([mean_term(values)], resamples)
    return CurvePoint(x=x, y=estimate.value, lo=estimate.lo, hi=estimate.hi)


def _within(point: CurvePoint | None, floor: float, ceiling: float) -> CurvePoint | None:
    """Clip a CI to the range a mean of this quantity can take."""
    if point is None:
        return None
    lo = None if point.lo is None else max(point.lo, floor)
    hi = None if point.hi is None else min(point.hi, ceiling)
    return point.model_copy(update={"lo": lo, "hi": hi})


def baseline_point(x: float, rows: list[ResultRow], value: Value) -> CurvePoint | None:
    per_seed = seed_means(rows, value)
    return CurvePoint(x=x, y=float(np.mean(list(per_seed.values())))) if per_seed else None


def _series(
    rows: list[ResultRow], key: Callable[[ResultRow], int | None]
) -> dict[int, list[ResultRow]]:
    groups: dict[int, list[ResultRow]] = {}
    for row in rows:
        x = key(row)
        if x is not None:
            groups.setdefault(x, []).append(row)
    return dict(sorted(groups.items()))


def _model_curve(
    curve_id: str,
    label: str,
    rows: list[ResultRow],
    key: Callable[[ResultRow], int | None],
    value: Value,
    resamples: int,
    floor: float,
) -> Curve | None:
    points = [
        _within(mean_point(float(x), seed_means(g, value), resamples), floor, 1.0)
        for x, g in _series(rows, key).items()
    ]
    present = [p for p in points if p is not None]
    return Curve(id=curve_id, label=label, kind="model", points=present) if present else None


def _baseline_curve(
    curve_id: str,
    label: str,
    rows: list[ResultRow],
    key: Callable[[ResultRow], int | None],
    value: Value,
) -> Curve | None:
    points = [baseline_point(float(x), g, value) for x, g in _series(rows, key).items()]
    present = [p for p in points if p is not None]
    return Curve(id=curve_id, label=label, kind="baseline", points=present) if present else None


def _at(curves: list[Curve], curve_id: str, x: float) -> float | None:
    for curve in curves:
        if curve.id == curve_id:
            return next((p.y for p in curve.points if p.x == x), None)
    return None


def _by_length(row: ResultRow) -> int:
    return row.length_tokens_target


def _by_swap_age(row: ResultRow) -> int | None:
    return row.reversal_m


def _beta_value(row: ResultRow) -> float | None:
    return baseline_p(row, "beta")


def _reference_margin(name: str) -> Value:
    def value(row: ResultRow) -> float | None:
        return baseline_margin(row, name)

    return value


def steady_curves(rows: list[ResultRow], resamples: int) -> list[Curve]:
    steady = [r for r in rows if r.world == "steady" and r.question_key == "risk"]
    curves: list[Curve | None] = []
    for contrast in sorted({r.contrast for r in steady if r.contrast}):
        in_contrast = [r for r in steady if r.contrast == contrast]
        gap = CONTRAST_LABELS.get(contrast, contrast)
        for policy in STEADY_POLICIES:
            cell = [r for r in in_contrast if r.policy == policy]
            curves.append(
                _model_curve(
                    f"{policy}_{contrast}",
                    f"{POLICY_LABELS[policy]}, {gap}",
                    cell,
                    _by_length,
                    p_correct,
                    resamples,
                    floor=0.0,
                )
            )
        raw = [r for r in in_contrast if r.policy == "raw"]
        curves.append(
            _baseline_curve(
                f"beta_ceiling_{contrast}", f"Simple counter, {gap}", raw, _by_length, _beta_value
            )
        )
    return [curve for curve in curves if curve is not None]


def _longest_contrast(curves: list[Curve]) -> str | None:
    raw = [c for c in curves if c.id.startswith("raw_") and c.points]
    return max(raw, key=lambda c: c.points[-1].x).id.removeprefix("raw_") if raw else None


def steady_days(rows: list[ResultRow]) -> dict[float, int]:
    """Diary days actually given at each target length."""
    return {
        float(r.length_tokens_target): r.n_days
        for r in rows
        if r.world == "steady" and r.policy == "raw"
    }


def _effective_sentence(
    curves: list[Curve], contrast: str, length: float, days: dict[float, int]
) -> str:
    raw = _at(curves, f"raw_{contrast}", length)
    if raw is None or contrast not in CONTRAST_LABELS or length not in days:
        return ""
    share = effective_evidence(raw, days[length], contrast)
    if share is None:
        return ""
    return f" A simple counter would match that with about {share:.0%} of the days the model was given."


def steady_takeaway(curves: list[Curve], days: dict[float, int]) -> str:
    contrast = _longest_contrast(curves)
    if contrast is None:
        return "This model was not run on steady diaries."
    raw_curve = next(c for c in curves if c.id == f"raw_{contrast}")
    length = raw_curve.points[-1].x
    raw = raw_curve.points[-1].y
    text = f"At {format_tokens(length)} tokens the model put {raw:.0%} on the wolf's real favorite field from the whole diary"
    counter = _at(curves, f"beta_ceiling_{contrast}", length)
    text += f"; simple counting got {counter:.0%}." if counter is not None else "."
    window = _at(curves, f"w1000_{contrast}", length)
    if window is not None:
        text += f" With only the last 1,000 days it got {window:.0%}."
    return text + _effective_sentence(curves, contrast, length, days)


def steady_chart(rows: list[ResultRow], resamples: int) -> Chart:
    curves = steady_curves(rows, resamples)
    return Chart(
        id="steady",
        title="Does a longer diary help?",
        x_label="Diary length (tokens)",
        y_label="Probability on the true favorite field",
        curves=curves,
        takeaway=steady_takeaway(curves, steady_days(rows)),
    )


def _longest_reversal(rows: list[ResultRow]) -> int | None:
    days = {
        r.n_days
        for r in rows
        if r.world == "reversal" and r.question_key == "current" and r.policy == "raw"
    }
    return max(days) if days else None


def reversal_curves(
    rows: list[ResultRow], resamples: int, n_days: int | None = None
) -> list[Curve]:
    length = n_days if n_days is not None else _longest_reversal(rows)
    if length is None:
        return []
    cell = [
        r
        for r in rows
        if r.world == "reversal" and r.question_key == "current" and r.n_days == length
    ]
    curves: list[Curve | None] = []
    for contrast in sorted({r.contrast for r in cell if r.contrast}):
        in_contrast = [r for r in cell if r.contrast == contrast]
        gap = CONTRAST_LABELS.get(contrast, contrast)
        for policy in REVERSAL_POLICIES:
            group = [r for r in in_contrast if r.policy == policy]
            curves.append(
                _model_curve(
                    f"{policy}_{contrast}",
                    f"{POLICY_LABELS[policy]}, {gap}",
                    group,
                    _by_swap_age,
                    margin_new_old,
                    resamples,
                    floor=-1.0,
                )
            )
        raw = [r for r in in_contrast if r.policy == "raw"]
        for name, label in REVERSAL_REFERENCES.items():
            curves.append(
                _baseline_curve(
                    f"ref_{name}_{contrast}",
                    f"{label}, {gap}",
                    raw,
                    _by_swap_age,
                    _reference_margin(name),
                )
            )
    return [curve for curve in curves if curve is not None]


def curve_points(curve: Curve) -> list[tuple[float, float]]:
    return [(p.x, p.y) for p in curve.points]


def reversal_takeaway(curves: list[Curve], n_days: int | None) -> str:
    raw = [c for c in curves if c.id.startswith("raw_")]
    if not raw or n_days is None:
        return "This model was not run on reversal diaries."
    parts = [
        f"on the {CONTRAST_LABELS.get(c.id.removeprefix('raw_'), c.id)} the whole diary {describe_crossing(curve_points(c))}"
        for c in raw
    ]
    lead = f"In a {n_days:,}-day diary, after the safest and most dangerous fields swapped, "
    return lead + "; ".join(parts) + "."


def reversal_chart(rows: list[ResultRow], resamples: int) -> Chart:
    curves = reversal_curves(rows, resamples)
    return Chart(
        id="reversal",
        title="When the wolf moves",
        x_label="Days since the swap",
        y_label="How much more the AI points at the new danger field than the old one",
        y_min=-1,
        y_max=1,
        curves=curves,
        takeaway=reversal_takeaway(curves, _longest_reversal(rows)),
    )


def ladder_curves(rows: list[ResultRow], rung: Rung, length: int, resamples: int) -> list[Curve]:
    curves = []
    for question, label in _QUESTION_LABELS.items():
        table = shift_table(rows, question, rung, length)
        points = [mean_point(float(lag), table[lag], resamples) for lag in sorted(table)]
        present = [point for point in points if point is not None]
        if present:
            curves.append(Curve(id=question, label=label, kind="model", points=present))
    return curves


def longest_ladder(rows: list[ResultRow]) -> int | None:
    lengths = {
        r.length_tokens_target
        for r in rows
        if r.world == "ladder" and r.rung == "statistical" and r.policy == "raw"
    }
    return max(lengths) if lengths else None


def ladder_takeaway(curves: list[Curve], verbalized: bool, length: int | None) -> str:
    if verbalized:
        return "This model gives one answer instead of probabilities, so the old-clue test cannot be read for it (top-1 only)."
    if length is None or len(curves) < 2:
        return "This model was not run on the old-clue test."
    report, decide = curves[0], curves[1]
    fresh_report, fresh_decide = report.points[0], decide.points[0]
    old_report, old_decide = report.points[-1], decide.points[-1]
    fresh_age = f"{fresh_report.x:,.0f} day{'' if fresh_report.x == 1 else 's'}"
    return (
        f"At {format_tokens(length)} tokens, a clue {fresh_age} old moved the 'where seen' answer by "
        f"{fresh_report.y:.1f} and the 'avoid' answer by {fresh_decide.y:.1f} (0 is no effect); "
        f"at {old_report.x:,.0f} days the same clue moved them by {old_report.y:.1f} and {old_decide.y:.1f}."
    )


def ladder_chart(rows: list[ResultRow], resamples: int, verbalized: bool) -> Chart:
    length = None if verbalized else longest_ladder(rows)
    curves = ladder_curves(rows, "statistical", length, resamples) if length is not None else []
    bounds = [v for c in curves for p in c.points for v in (p.y, p.lo, p.hi) if v is not None]
    return Chart(
        id="ladder",
        title="Does an old clue still count?",
        x_label="Days since the clue",
        y_label="How much the clue changed the answer",
        y_min=min([0.0, *bounds]),
        y_max=max([1.0, *bounds]),
        curves=curves,
        takeaway=ladder_takeaway(curves, verbalized, length),
    )
