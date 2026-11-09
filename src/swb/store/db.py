"""Postgres store. Budget checks and job reservation share one transaction."""

from __future__ import annotations

import threading
import uuid
from importlib import resources
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from swb.contracts import ResultRow

_JSON_COLUMNS = {
    "option_order",
    "probabilities",
    "true_rates",
    "baseline_scores",
}
_COLUMNS = list(ResultRow.model_fields)
_INSERT = (
    f"INSERT INTO results ({', '.join(_COLUMNS)}) "
    f"VALUES ({', '.join('%s' for _ in _COLUMNS)}) "
    "ON CONFLICT (row_id) DO NOTHING"
)
_SELECT = f"SELECT {', '.join(_COLUMNS)} FROM results ORDER BY created_at, row_id"


def schema_sql() -> str:
    return resources.files("swb.store").joinpath("schema.sql").read_text(encoding="utf-8")


def _to_param(column: str, value: Any) -> Any:
    if column in _JSON_COLUMNS and value is not None:
        return Jsonb(value)
    return value


def row_params(row: ResultRow) -> list[Any]:
    dumped = row.model_dump()
    return [_to_param(column, dumped[column]) for column in _COLUMNS]


def row_from_record(record: tuple[Any, ...]) -> ResultRow:
    values = dict(zip(_COLUMNS, record, strict=True))
    for key, value in values.items():
        if isinstance(value, uuid.UUID):
            values[key] = str(value)
    values["created_at"] = values["created_at"].isoformat()
    if values["cost_usd"] is not None:
        values["cost_usd"] = float(values["cost_usd"])
    return ResultRow.model_validate(values)


class PostgresStore:
    """One connection. The lock keeps worker threads from interleaving inside a transaction."""

    def __init__(self, url: str) -> None:
        self._conn = psycopg.connect(url, autocommit=True)
        self._lock = threading.Lock()
        with self._lock, self._conn.transaction():
            self._conn.execute(schema_sql())

    def write(self, rows: list[ResultRow]) -> None:
        if not rows:
            return
        with self._lock, self._conn.transaction(), self._conn.cursor() as cursor:
            cursor.executemany(_INSERT, [row_params(row) for row in rows])

    def done_job_ids(self) -> set[str]:
        with self._lock, self._conn.transaction():
            records = self._conn.execute("SELECT DISTINCT call_id FROM results").fetchall()
        return {str(record[0]) for record in records}

    def job_row_counts(self) -> dict[str, int]:
        with self._lock, self._conn.transaction():
            records = self._conn.execute(
                "SELECT call_id, count(*) FROM results GROUP BY call_id"
            ).fetchall()
        return {str(record[0]): int(record[1]) for record in records}

    def rows(self) -> list[ResultRow]:
        with self._lock, self._conn.transaction():
            records = self._conn.execute(_SELECT).fetchall()
        return [row_from_record(record) for record in records]

    def _prior(self, job_id: str) -> tuple[int, float]:
        record = self._conn.execute(
            "SELECT tokens, usd FROM budget_reservations WHERE job_id = %s", (job_id,)
        ).fetchone()
        return (int(record[0]), float(record[1])) if record else (0, 0.0)

    def _apply(self, job_id: str, tokens: int, usd: float, spent: tuple[int, float]) -> None:
        self._conn.execute(
            "INSERT INTO budget_reservations (job_id, tokens, usd) VALUES (%s, %s, %s) "
            "ON CONFLICT (job_id) DO UPDATE SET tokens = EXCLUDED.tokens, usd = EXCLUDED.usd",
            (job_id, tokens, usd),
        )
        self._conn.execute(
            "UPDATE budget SET tokens = %s, usd = %s WHERE id = 1", (spent[0], spent[1])
        )

    def _locked_totals(self) -> tuple[int, float]:
        record = self._conn.execute(
            "SELECT tokens, usd FROM budget WHERE id = 1 FOR UPDATE"
        ).fetchone()
        assert record is not None  # schema.sql inserts the single row
        return int(record[0]), float(record[1])

    def reserve_budget(
        self, tokens: int, usd: float, cap_usd: float | None = None, job_id: str | None = None
    ) -> bool:
        key = job_id or str(uuid.uuid4())
        with self._lock, self._conn.transaction():
            total_tokens, total_usd = self._locked_totals()
            prior_tokens, prior_usd = self._prior(key)
            new_usd = total_usd - prior_usd + usd
            if cap_usd is not None and new_usd > cap_usd:
                return False
            self._apply(key, tokens, usd, (total_tokens - prior_tokens + tokens, new_usd))
            return True

    def settle_budget(self, job_id: str, tokens: int, usd: float) -> None:
        with self._lock, self._conn.transaction():
            total_tokens, total_usd = self._locked_totals()
            prior_tokens, prior_usd = self._prior(job_id)
            new_totals = (total_tokens - prior_tokens + tokens, total_usd - prior_usd + usd)
            self._apply(job_id, tokens, usd, new_totals)

    def spent(self) -> tuple[int, float]:
        with self._lock, self._conn.transaction():
            record = self._conn.execute("SELECT tokens, usd FROM budget WHERE id = 1").fetchone()
        return (int(record[0]), float(record[1])) if record else (0, 0.0)

    def close(self) -> None:
        self._conn.close()
