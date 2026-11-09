"""Fixed-horizon, exponentially discounted and change-detecting tallies."""

from __future__ import annotations

import numpy as np

from swb.baselines.counter import N_PASTURES, beta_posterior, prob_extreme
from swb.contracts import FOG, WOLF, Diary

_CUSUM_DRIFT = 0.03
_CUSUM_THRESHOLD = 12.0
_CUSUM_WARMUP = 100


def window_top(diary: Diary, days: int, *, lowest: bool = False) -> list[float]:
    """P(each pasture has the highest rate), counting only the last `days` days."""
    return beta_posterior(diary, max(0, diary.spec.n_days - days), lowest=lowest)


def decay_top(diary: Diary, half_life: float, *, lowest: bool = False) -> list[float]:
    """P(each pasture has the highest rate), from exponentially discounted counts."""
    ages = np.arange(diary.spec.n_days - 1, -1, -1, dtype=float)
    weights = 0.5 ** (ages / half_life)
    grazed = diary.grazed.astype(np.int64)
    seen = diary.sighting != FOG
    is_wolf = diary.sighting == WOLF
    visits = np.bincount(grazed[seen], weights=weights[seen], minlength=N_PASTURES)
    wolves = np.bincount(grazed[is_wolf], weights=weights[is_wolf], minlength=N_PASTURES)
    return prob_extreme(1.0 + wolves, 1.0 + visits - wolves, lowest=lowest)


def _first_alarm(wolf_on_visit: np.ndarray) -> int | None:
    """Index of the first two-sided CUSUM alarm against the expanding mean, or None."""
    n = wolf_on_visit.size
    if n <= _CUSUM_WARMUP:
        return None
    expanding = np.cumsum(wolf_on_visit) / np.arange(1, n + 1)
    deviation = wolf_on_visit[1:] - expanding[:-1]
    deviation[: _CUSUM_WARMUP - 1] = 0.0
    up = np.cumsum(deviation - _CUSUM_DRIFT)
    down = np.cumsum(-deviation - _CUSUM_DRIFT)
    statistic = np.maximum(up - np.minimum.accumulate(up), down - np.minimum.accumulate(down))
    crossed = np.flatnonzero(statistic > _CUSUM_THRESHOLD)
    return int(crossed[0]) + 1 if crossed.size else None


def _last_alarm_day(diary: Diary) -> int:
    """Day after the most recent alarm on any pasture; 0 if none fired."""
    last = 0
    for pasture in range(N_PASTURES):
        days = np.flatnonzero((diary.grazed == pasture) & (diary.sighting != FOG))
        wolf_on_visit = (diary.sighting[days] == WOLF).astype(float)
        offset = 0
        while (alarm := _first_alarm(wolf_on_visit[offset:])) is not None:
            offset += alarm + 1
            last = max(last, int(days[offset - 1]) + 1)
    return last


def cusum(diary: Diary, *, lowest: bool = False) -> list[float]:
    """P(each pasture has the highest rate), counting only since the last detected change."""
    return beta_posterior(diary, _last_alarm_day(diary), lowest=lowest)
