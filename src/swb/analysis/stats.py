"""Studentized bootstrap over seeds and Holm correction.

Every statistic in the benchmark is a signed sum of ratios of per-seed means: a mean is a ratio
over 1, a paired difference is a mean of differences, a score is a single ratio, and H2 is the
difference of two ratios. One resampler therefore serves all of them, with the standard error of
each resample taken from the linearized (delta-method) influence values.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

BOOT_SEED = 20261108
RESAMPLES_FINAL = 10_000
RESAMPLES_DEMO = 2_000
ALPHA = 0.05

Array = NDArray[np.float64]


@dataclass(frozen=True)
class Term:
    numerator: Array
    denominator: Array
    sign: float = 1.0


@dataclass(frozen=True)
class Estimate:
    value: float
    lo: float | None
    hi: float | None
    se: float | None
    n: int
    t_star: Array


def mean_term(values: Array) -> Term:
    return Term(values, np.ones_like(values))


def _linearize(terms: Sequence[Term]) -> tuple[float, Array]:
    value = 0.0
    influence = np.zeros_like(terms[0].numerator, dtype=float)
    for term in terms:
        den = float(term.denominator.mean())
        ratio = float(term.numerator.mean()) / den
        value += term.sign * ratio
        influence += term.sign * (term.numerator - ratio * term.denominator) / den
    return value, influence


def _resample(terms: Sequence[Term], idx: NDArray[np.int64], root_n: float) -> tuple[Array, Array]:
    stat = np.zeros(idx.shape[0])
    influence = np.zeros(idx.shape, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        for term in terms:
            x, y = term.numerator[idx], term.denominator[idx]
            y_bar = y.mean(axis=1)
            ratio = x.mean(axis=1) / y_bar
            stat += term.sign * ratio
            influence += term.sign * (x - ratio[:, None] * y) / y_bar[:, None]
        return stat, influence.std(axis=1, ddof=1) / root_n


def bootstrap(
    terms: Sequence[Term], resamples: int = RESAMPLES_FINAL, seed: int = BOOT_SEED
) -> Estimate:
    """Point estimate and 95% studentized CI. Terms must be aligned on the same seeds."""
    n = len(terms[0].numerator)
    value, influence = _linearize(terms)
    empty: Array = np.empty(0)
    if n < 2:
        return Estimate(value, None, None, None, n, empty)
    root_n = float(np.sqrt(n))
    se = float(influence.std(ddof=1)) / root_n
    if se == 0.0:
        return Estimate(value, value, value, 0.0, n, empty)
    if resamples == 0:
        return Estimate(value, None, None, se, n, empty)
    idx = np.random.default_rng(seed).integers(0, n, size=(resamples, n))
    stat, se_star = _resample(terms, idx, root_n)
    valid = np.isfinite(stat) & np.isfinite(se_star) & (se_star > 0)
    t_star = (stat[valid] - value) / se_star[valid]
    if t_star.size == 0:
        return Estimate(value, None, None, se, n, empty)
    lo = value - float(np.quantile(t_star, 0.975)) * se
    hi = value - float(np.quantile(t_star, 0.025)) * se
    return Estimate(value, lo, hi, se, n, t_star)


def p_greater(estimate: Estimate, null: float = 0.0) -> float | None:
    """One-sided bootstrap p-value for H0: statistic <= null."""
    if estimate.se is None:
        return None
    if estimate.se == 0.0:
        return 0.0 if estimate.value > null else 1.0
    if estimate.t_star.size == 0:
        return None
    t_observed = (estimate.value - null) / estimate.se
    exceed = int(np.count_nonzero(estimate.t_star >= t_observed))
    return (1 + exceed) / (1 + estimate.t_star.size)


def holm(p_values: Sequence[float | None]) -> list[float | None]:
    """Holm-adjusted p-values. An untestable member keeps its place in the registered family, so
    a missing test can never loosen the correction applied to the others."""
    family = len(p_values)
    order = sorted((i for i, p in enumerate(p_values) if p is not None), key=lambda i: p_values[i])
    adjusted: list[float | None] = [None] * family
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (family - rank) * float(p_values[index])))
        adjusted[index] = running
    return adjusted


def align(*tables: dict[int, float]) -> tuple[list[int], list[Array]]:
    """Inner join per-seed tables on seed, so paired statistics compare the same diaries."""
    shared = sorted(set.intersection(*(set(table) for table in tables)))
    return shared, [np.array([table[seed] for seed in shared], dtype=float) for table in tables]
