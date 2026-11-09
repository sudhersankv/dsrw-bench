"""The store protocol. A job is done when its rows exist; `call_id` carries the job id."""

from __future__ import annotations

from typing import Protocol

from swb.contracts import ResultRow


class ResultStore(Protocol):
    def write(self, rows: list[ResultRow]) -> None: ...

    def done_job_ids(self) -> set[str]: ...

    def job_row_counts(self) -> dict[str, int]:
        """Rows stored per job. A job is finished only when all of its rows are here."""
        ...

    def rows(self) -> list[ResultRow]: ...

    def reserve_budget(
        self, tokens: int, usd: float, cap_usd: float | None = None, job_id: str | None = None
    ) -> bool:
        """Adds the amounts unless that would pass `cap_usd`, in one transaction.

        With a `job_id`, a resumed job replaces its own earlier reservation instead of adding a
        second one. A failed call that may have been billed is carried under its own key first, so
        it still counts.
        """
        ...

    def settle_budget(self, job_id: str, tokens: int, usd: float) -> None:
        """Replaces the job's reservation with the final amounts."""
        ...

    def spent(self) -> tuple[int, float]:
        """Cumulative (tokens, usd), including reservations still open."""
        ...
