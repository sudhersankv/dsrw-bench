"""Effective evidence: days a Beta counter needs to match a model, as a share of days given."""

from __future__ import annotations

from functools import cache

import numpy as np

from swb.analysis.stats import Array
from swb.contracts import CONTRASTS

GRID_DAYS: Array = np.geomspace(16, 256_000, 28)
_REPS = 300
_DRAWS = 300
_SIM_SEED = 7342


def _p_hot_at(n_days: int, contrast: str, rng: np.random.Generator) -> float:
    """Mean Beta(1,1) posterior probability that the true hot pasture has the highest rate."""
    hot, middle, safe = CONTRASTS[contrast]
    rates = np.array([hot, middle, middle, safe])
    visits = rng.multinomial(n_days, [0.25] * 4, size=_REPS)
    wolves = rng.binomial(visits, rates)
    draws = rng.beta(
        1 + wolves[:, None, :], 1 + visits[:, None, :] - wolves[:, None, :], size=(_REPS, _DRAWS, 4)
    )
    return float((draws.argmax(axis=2) == 0).mean())


@cache
def beta_curve(contrast: str) -> tuple[float, ...]:
    """P(hot) on GRID_DAYS, forced non-decreasing so it can be inverted."""
    rng = np.random.default_rng(
        np.random.SeedSequence([_SIM_SEED, sorted(CONTRASTS).index(contrast)])
    )
    values = [_p_hot_at(int(days), contrast, rng) for days in GRID_DAYS]
    return tuple(np.maximum.accumulate(values).tolist())


def effective_days(p_model: float, contrast: str) -> float | None:
    """Days of diary a Beta counter needs to reach `p_model`. None when beyond the grid."""
    curve = np.array(beta_curve(contrast))
    if p_model <= float(curve[0]):
        return 0.0
    if p_model > float(curve[-1]):
        return None
    log_days = np.interp(p_model, curve, np.log(GRID_DAYS))
    return float(np.exp(log_days))


def effective_evidence(p_model: float, days_given: int, contrast: str) -> float | None:
    days = effective_days(p_model, contrast)
    return None if days is None or days_given <= 0 else days / days_given
