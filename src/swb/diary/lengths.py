"""Convert token budgets to day counts and pick reversal lengths."""

from __future__ import annotations

import numpy as np

TOKENS_PER_DAY = 8.0
N_REVERSAL_MS = 9
MIN_REVERSAL_M = 6
MAX_REVERSAL_FRACTION = 0.7


def days_for_tokens(tokens: int, tokens_per_day: float = TOKENS_PER_DAY) -> int:
    if tokens <= 0 or tokens_per_day <= 0:
        raise ValueError("tokens and tokens_per_day must be positive")
    return round(tokens / tokens_per_day)


def reversal_ms(n_days: int) -> list[int]:
    """Nine distinct integers, geometric from 6 to 0.7 of the diary."""
    top = MAX_REVERSAL_FRACTION * n_days
    if top < MIN_REVERSAL_M:
        raise ValueError(f"n_days={n_days} is too short for a reversal sweep")
    values = [round(v) for v in np.geomspace(MIN_REVERSAL_M, top, N_REVERSAL_MS)]
    if len(set(values)) != N_REVERSAL_MS:
        raise ValueError(f"n_days={n_days} is too short for nine distinct reversal lengths")
    return values
