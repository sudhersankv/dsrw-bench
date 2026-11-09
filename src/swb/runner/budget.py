"""Budget guard for capped models. Spec: refuse any call that would push spend past the cap."""

from __future__ import annotations

import time

from swb.contracts import ModelEntry
from swb.store.base import ResultStore

# Reported tokens run a little above the estimate (spec token check: within 5%).
ESTIMATE_MARGIN = 1.05


def usd_for(tokens: int, entry: ModelEntry) -> float:
    return tokens * entry.price_input_per_m / 1e6


class BudgetGuard:
    def __init__(self, store: ResultStore, cap_usd: float) -> None:
        self._store = store
        self.cap_usd = cap_usd

    def reserve(self, job_id: str, entry: ModelEntry, estimated_tokens: int) -> bool:
        """True if the job may call a capped model. Uncapped models are not tracked."""
        if not entry.budget_capped:
            return True
        tokens = int(estimated_tokens * ESTIMATE_MARGIN)
        return self._store.reserve_budget(
            tokens, usd_for(tokens, entry), cap_usd=self.cap_usd, job_id=job_id
        )

    def settle(self, job_id: str, entry: ModelEntry, actual_tokens: int) -> None:
        """Replaces the job's reservation with what the provider reported."""
        if entry.budget_capped:
            self._store.settle_budget(job_id, actual_tokens, usd_for(actual_tokens, entry))

    def carry(self, job_id: str, entry: ModelEntry, billed_tokens: int) -> None:
        """A failed call may have been billed: keep it as its own entry so a retry adds to it."""
        if entry.budget_capped:
            key = f"{job_id}:maybe-billed:{time.time_ns()}"
            self._store.settle_budget(key, billed_tokens, usd_for(billed_tokens, entry))
            self.settle(job_id, entry, 0)

    def release(self, job_id: str, entry: ModelEntry) -> None:
        """The call was not billed, so its reservation goes back."""
        self.settle(job_id, entry, 0)
