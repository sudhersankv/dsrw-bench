"""Append-only JSONL store for offline runs. One process at a time."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from swb.contracts import ResultRow


def _drop_torn_tail(path: Path) -> None:
    """A crash mid-write leaves a line with no newline; keeping it would corrupt the next append."""
    if not path.exists() or path.stat().st_size == 0:
        return
    data = path.read_bytes()
    if data.endswith(b"\n"):
        return
    with path.open("r+b") as handle:
        handle.truncate(data.rfind(b"\n") + 1)


class JsonlStore:
    """Rows go to `path`; budget entries go to `<path>.budget`, where the last entry per job wins."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._budget_path = self.path.with_name(self.path.name + ".budget")
        self._lock = threading.Lock()
        _drop_torn_tail(self.path)
        _drop_torn_tail(self._budget_path)
        self._job_rows: dict[str, set[str]] = {}
        for row in self.rows():
            self._job_rows.setdefault(row.call_id, set()).add(row.row_id)
        self._budget = self._load_budget()

    def _load_budget(self) -> dict[str, tuple[int, float]]:
        if not self._budget_path.exists():
            return {}
        budget: dict[str, tuple[int, float]] = {}
        with self._budget_path.open(encoding="utf-8") as handle:
            for line in handle:
                entry = json.loads(line)
                budget[entry["job_id"]] = (entry["tokens"], entry["usd"])
        return budget

    def write(self, rows: list[ResultRow]) -> None:
        with self._lock, self.path.open("a", encoding="utf-8") as handle:
            for row in rows:
                handle.write(row.model_dump_json() + "\n")
            handle.flush()
            for row in rows:
                self._job_rows.setdefault(row.call_id, set()).add(row.row_id)

    def done_job_ids(self) -> set[str]:
        with self._lock:
            return set(self._job_rows)

    def job_row_counts(self) -> dict[str, int]:
        with self._lock:
            return {job: len(rows) for job, rows in self._job_rows.items()}

    def rows(self) -> list[ResultRow]:
        """One row per row_id: a job resumed after a partial write appends its rows again."""
        if not self.path.exists():
            return []
        loaded: dict[str, ResultRow] = {}
        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                row = ResultRow.model_validate_json(line)
                loaded[row.row_id] = row
        return list(loaded.values())

    def reserve_budget(
        self, tokens: int, usd: float, cap_usd: float | None = None, job_id: str | None = None
    ) -> bool:
        with self._lock:
            key = job_id or f"anonymous-{len(self._budget)}"
            _, prior_usd = self._budget.get(key, (0, 0.0))
            spent_usd = sum(entry[1] for entry in self._budget.values()) - prior_usd
            if cap_usd is not None and spent_usd + usd > cap_usd:
                return False
            self._record(key, tokens, usd)
            return True

    def settle_budget(self, job_id: str, tokens: int, usd: float) -> None:
        with self._lock:
            self._record(job_id, tokens, usd)

    def _record(self, key: str, tokens: int, usd: float) -> None:
        self._budget[key] = (tokens, usd)
        with self._budget_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"job_id": key, "tokens": tokens, "usd": usd}) + "\n")

    def spent(self) -> tuple[int, float]:
        with self._lock:
            tokens = sum(entry[0] for entry in self._budget.values())
            usd = sum(entry[1] for entry in self._budget.values())
        return tokens, usd
