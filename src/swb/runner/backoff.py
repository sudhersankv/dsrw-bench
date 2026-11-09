"""Exponential backoff with full jitter from a seeded generator."""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class BackoffConfig:
    base_s: float = 1.0
    cap_s: float = 60.0
    max_attempts: int = 8


class Backoff:
    def __init__(self, config: BackoffConfig, seed: int) -> None:
        self.config = config
        self._rng = random.Random(seed)

    def delay(self, attempt: int, retry_after: float | None = None) -> float:
        """Seconds to wait before retry number `attempt` (0-based). Never shorter than Retry-After."""
        ceiling = min(self.config.cap_s, self.config.base_s * 2**attempt)
        jittered = self._rng.uniform(0.0, ceiling)
        return max(jittered, retry_after) if retry_after is not None else jittered
