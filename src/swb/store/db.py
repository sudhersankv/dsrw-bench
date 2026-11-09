"""Postgres store. Budget checks and job reservation share one transaction."""

from __future__ import annotations

import queue
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
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
_POOL_SIZE = 12
# Replaces a job's reservation and moves the running total by the difference, or changes nothing
# and returns 0 rows counted when the new total would pass the cap.
_RESERVE = """
WITH cur AS (SELECT tokens, usd FROM budget WHERE id = 1 FOR UPDATE),
prior AS (SELECT tokens, usd FROM budget_reservations WHERE job_id = %(job)s),
next AS (
  SELECT cur.tokens - COALESCE((SELECT tokens FROM prior), 0) + %(tokens)s::bigint AS tokens,
         cur.usd - COALESCE((SELECT usd FROM prior), 0) + %(usd)s::numeric AS usd
  FROM cur
),
allowed AS (SELECT * FROM next WHERE %(cap)s::numeric IS NULL OR usd <= %(cap)s::numeric),
moved AS (
  UPDATE budget SET tokens = allowed.tokens, usd = allowed.usd
  FROM allowed WHERE budget.id = 1 RETURNING 1
),
saved AS (
  INSERT INTO budget_reservations (job_id, tokens, usd)
  SELECT %(job)s, %(tokens)s::bigint, %(usd)s::numeric FROM allowed
  ON CONFLICT (job_id) DO UPDATE SET tokens = EXCLUDED.tokens, usd = EXCLUDED.usd
  RETURNING 1
)
SELECT count(*) FROM allowed
"""


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
    """A small connection pool, so worker threads do not queue behind one network connection."""

    def __init__(self, url: str) -> None:
        self._url = url
        self._idle: queue.LifoQueue[psycopg.Connection[Any]] = queue.LifoQueue()
        self._slots = threading.BoundedSemaphore(_POOL_SIZE)
        with self._connection() as conn, conn.transaction():
            conn.execute(schema_sql())

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection[Any]]:
        with self._slots:
            try:
                conn = self._idle.get_nowait()
            except queue.Empty:
                conn = psycopg.connect(self._url, autocommit=True)
            try:
                yield conn
            finally:
                if not conn.closed and not conn.broken:
                    self._idle.put(conn)

    def write(self, rows: list[ResultRow]) -> None:
        if not rows:
            return
        with self._connection() as conn, conn.transaction(), conn.cursor() as cursor:
            cursor.executemany(_INSERT, [row_params(row) for row in rows])

    def done_job_ids(self) -> set[str]:
        with self._connection() as conn:
            records = conn.execute("SELECT DISTINCT call_id FROM results").fetchall()
        return {str(record[0]) for record in records}

    def job_row_counts(self) -> dict[str, int]:
        with self._connection() as conn:
            records = conn.execute(
                "SELECT call_id, count(*) FROM results GROUP BY call_id"
            ).fetchall()
        return {str(record[0]): int(record[1]) for record in records}

    def rows(self) -> list[ResultRow]:
        with self._connection() as conn:
            records = conn.execute(_SELECT).fetchall()
        return [row_from_record(record) for record in records]

    def _replace_reservation(
        self, job_id: str, tokens: int, usd: float, cap_usd: float | None
    ) -> bool:
        """One statement, so the budget row stays locked for a single network round trip."""
        params = {"job": job_id, "tokens": tokens, "usd": usd, "cap": cap_usd}
        with self._connection() as conn:
            record = conn.execute(_RESERVE, params).fetchone()
        assert record is not None
        return bool(record[0])

    def reserve_budget(
        self, tokens: int, usd: float, cap_usd: float | None = None, job_id: str | None = None
    ) -> bool:
        return self._replace_reservation(job_id or str(uuid.uuid4()), tokens, usd, cap_usd)

    def settle_budget(self, job_id: str, tokens: int, usd: float) -> None:
        self._replace_reservation(job_id, tokens, usd, None)

    def spent(self) -> tuple[int, float]:
        with self._connection() as conn:
            record = conn.execute("SELECT tokens, usd FROM budget WHERE id = 1").fetchone()
        return (int(record[0]), float(record[1])) if record else (0, 0.0)

    def close(self) -> None:
        while not self._idle.empty():
            self._idle.get_nowait().close()
