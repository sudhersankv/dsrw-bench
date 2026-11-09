"""Beta counter: per-pasture Beta(1,1) posterior over wolf rates."""

from __future__ import annotations

import numpy as np

from swb.contracts import FOG, WOLF, Diary

N_PASTURES = 4


def prob_extreme(
    alpha: np.ndarray, beta: np.ndarray, n_samples: int = 4000, lowest: bool = False
) -> list[float]:
    """P(each pasture has the highest, or lowest, rate) under independent Beta posteriors.

    Deterministic midpoint integration on `n_samples` grid points, so log-ratios of small
    probabilities carry no Monte Carlo noise (the ladder shift is a log-ratio).
    """
    dx = 1.0 / n_samples
    grid = (np.arange(n_samples) + 0.5) * dx
    log_pdf = (alpha[:, None] - 1) * np.log(grid) + (beta[:, None] - 1) * np.log1p(-grid)
    pdf = np.exp(log_pdf - log_pdf.max(axis=1, keepdims=True))
    pdf /= pdf.sum(axis=1, keepdims=True) * dx
    cdf = np.cumsum(pdf, axis=1) * dx - 0.5 * pdf * dx
    other = 1.0 - cdf if lowest else cdf
    probs = np.array(
        [
            (pdf[i] * np.prod(np.delete(other, i, axis=0), axis=0)).sum() * dx
            for i in range(alpha.shape[0])
        ]
    )
    return (probs / probs.sum()).tolist()


def tally(diary: Diary, start: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Visits and wolves per pasture from day `start` on. Fog days carry no observation."""
    grazed = diary.grazed[start:].astype(np.int64)
    sighting = diary.sighting[start:]
    seen = sighting != FOG
    visits = np.bincount(grazed[seen], minlength=N_PASTURES).astype(float)
    wolves = np.bincount(grazed[sighting == WOLF], minlength=N_PASTURES).astype(float)
    return visits, wolves


def beta_posterior(
    diary: Diary, start: int = 0, n_samples: int = 4000, *, lowest: bool = False
) -> list[float]:
    """P(each pasture has the highest rate) from day `start` on. `lowest` asks for the safest."""
    visits, wolves = tally(diary, start)
    return prob_extreme(1.0 + wolves, 1.0 + visits - wolves, n_samples, lowest)
