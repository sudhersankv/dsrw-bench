"""Reversal crossover m* (spec "Aggregate metrics")."""

from __future__ import annotations

import math
from collections.abc import Sequence


def crossover_m(points: Sequence[tuple[float, float]]) -> float | None:
    """The swap age where P(new) - P(old) turns positive for good, interpolated on log m.

    Noise can cross zero more than once, so the crossing after the last negative point is used:
    beyond it the model stays on the new pasture across the tested range.
    """
    ordered = sorted(points)
    negatives = [i for i, (_, y) in enumerate(ordered) if y < 0]
    if not negatives or negatives[-1] == len(ordered) - 1:
        return None
    last = negatives[-1]
    (m0, y0), (m1, y1) = ordered[last], ordered[last + 1]
    fraction = -y0 / (y1 - y0)
    return math.exp(math.log(m0) + fraction * (math.log(m1) - math.log(m0)))


def describe_crossing(points: Sequence[tuple[float, float]]) -> str:
    """Plain-language account of where the crossing sits, or why there is none."""
    if not points:
        return "was not measured"
    crossing = crossover_m(points)
    if crossing is not None:
        return f"switched to the new danger field once the swap was about {crossing:,.0f} days old"
    if all(y < 0 for _, y in points):
        return "kept pointing at the old field for every swap age tested"
    return "already pointed at the new field at every swap age tested"
