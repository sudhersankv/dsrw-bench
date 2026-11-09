"""JSONL store behaviour, and that the Postgres schema matches the shared row type."""

from __future__ import annotations

import re
from pathlib import Path

from swb.contracts import ResultRow
from swb.store.db import row_params, schema_sql
from swb.store.jsonl import JsonlStore


def _row(row_id: str = "r1") -> ResultRow:
    return ResultRow(
        row_id=row_id,
        call_id="11111111-1111-1111-1111-111111111111",
        run_id="run",
        condition_id="c",
        model="m",
        world="steady",
        policy="raw",
        length_tokens_target=8,
        input_tokens=8,
        n_days=1,
        seed=0,
        diary_sha256="d",
        question_key="risk",
        option_order=["a", "b"],
        probabilities={"a": 0.6, "b": 0.4},
        truth="a",
        latency_ms=1,
        http_status=200,
        created_at="2026-11-08T00:00:00+00:00",
    )


def test_rows_round_trip_and_mark_jobs_done(tmp_path: Path) -> None:
    store = JsonlStore(tmp_path / "x" / "r.jsonl")
    store.write([_row(), _row("r2")])
    assert store.done_job_ids() == {_row().call_id}
    assert store.rows() == [_row(), _row("r2")]
    assert JsonlStore(store.path).done_job_ids() == {_row().call_id}


def test_torn_last_line_is_ignored(tmp_path: Path) -> None:
    path = tmp_path / "r.jsonl"
    store = JsonlStore(path)
    store.write([_row()])
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"row_id": "half')
    assert len(JsonlStore(path).rows()) == 1


def test_torn_tail_is_removed_so_the_next_append_is_not_lost(tmp_path: Path) -> None:
    path = tmp_path / "r.jsonl"
    store = JsonlStore(path)
    store.write([_row()])
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"row_id": "half')
    store = JsonlStore(path)
    store.write([_row("r2")])
    assert [row.row_id for row in JsonlStore(path).rows()] == ["r1", "r2"]


def test_partial_job_counts_only_the_rows_on_disk(tmp_path: Path) -> None:
    path = tmp_path / "r.jsonl"
    store = JsonlStore(path)
    store.write([_row("r1"), _row("r2"), _row("r3")])
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    path.write_text(lines[0], encoding="utf-8")
    assert JsonlStore(path).job_row_counts() == {_row().call_id: 1}


def test_resumed_rows_are_not_duplicated(tmp_path: Path) -> None:
    store = JsonlStore(tmp_path / "r.jsonl")
    store.write([_row("r1")])
    store.write([_row("r1"), _row("r2")])
    assert [row.row_id for row in store.rows()] == ["r1", "r2"]
    assert store.job_row_counts() == {_row().call_id: 2}


def test_torn_budget_line_does_not_swallow_the_next_entry(tmp_path: Path) -> None:
    path = tmp_path / "r.jsonl"
    store = JsonlStore(path)
    store.reserve_budget(100, 1.0, job_id="a")
    with path.with_name("r.jsonl.budget").open("a", encoding="utf-8") as handle:
        handle.write('{"job_id": "b", "tok')
    store = JsonlStore(path)
    store.reserve_budget(200, 2.0, job_id="c")
    assert JsonlStore(path).spent() == (300, 3.0)


def test_reserve_refuses_past_the_cap(tmp_path: Path) -> None:
    store = JsonlStore(tmp_path / "r.jsonl")
    assert store.reserve_budget(100, 4.0, cap_usd=5.0, job_id="a")
    assert not store.reserve_budget(100, 2.0, cap_usd=5.0, job_id="b")
    assert store.spent() == (100, 4.0)


def test_resumed_job_replaces_its_reservation(tmp_path: Path) -> None:
    store = JsonlStore(tmp_path / "r.jsonl")
    assert store.reserve_budget(100, 4.0, cap_usd=5.0, job_id="a")
    assert store.reserve_budget(100, 4.0, cap_usd=5.0, job_id="a")
    assert store.spent() == (100, 4.0)


def test_budget_survives_restart_and_settle_replaces(tmp_path: Path) -> None:
    path = tmp_path / "r.jsonl"
    store = JsonlStore(path)
    store.reserve_budget(100, 4.0, cap_usd=5.0, job_id="a")
    store.settle_budget("a", 90, 3.6)
    assert JsonlStore(path).spent() == (90, 3.6)


def test_schema_has_a_column_for_every_row_field() -> None:
    table = re.search(r"CREATE TABLE IF NOT EXISTS results \((.*?)\n\);", schema_sql(), re.DOTALL)
    assert table is not None
    columns = {line.split()[0] for line in table.group(1).strip().splitlines()}
    assert columns == set(ResultRow.model_fields)


def test_row_params_follow_field_order() -> None:
    params = row_params(_row())
    assert len(params) == len(ResultRow.model_fields)
    assert params[0] == "r1"
