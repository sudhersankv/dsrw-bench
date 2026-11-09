"""CLI commands that cost nothing: dry-run, and mock runs through the store and export."""

from __future__ import annotations

from pathlib import Path

import polars as pl
from typer.testing import CliRunner

from swb.cli import app, open_store
from swb.store.jsonl import JsonlStore

RUNNER = CliRunner()
CONFIGS = Path(__file__).resolve().parent.parent / "configs"
MOCK_MODELS = """models:
  - {id: demo-a, display: A, adapter: mock, model_id: "kind=counter", window: 100000, price_input_per_m: 0.0}
"""
TINY_CONFIG = """run_id: tiny
seeds: {start: 0, count: 2}
cells:
  - world: steady
    contrasts: [high]
    lengths_days: [30]
    policies: [raw]
    question_keys: [risk, act]
"""


def test_dry_run_prints_each_run_and_totals() -> None:
    configs = [CONFIGS / name for name in ("pilot.yaml", "r1_steady.yaml", "r3_ladder.yaml")]
    result = RUNNER.invoke(
        app,
        [
            "dry-run",
            *[str(path) for path in configs],
            "--models-file",
            str(CONFIGS / "models.yaml"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Neon hours" in result.output
    assert "r1_steady" in result.output
    assert "total snap" in result.output


def _write(tmp_path: Path) -> tuple[Path, Path]:
    models = tmp_path / "models.yaml"
    config = tmp_path / "tiny.yaml"
    models.write_text(MOCK_MODELS, encoding="utf-8")
    config.write_text(TINY_CONFIG, encoding="utf-8")
    return models, config


def test_run_then_resume_then_export(tmp_path: Path) -> None:
    models, config = _write(tmp_path)
    store = f"jsonl:{tmp_path / 'r.jsonl'}"
    args = ["run", str(config), "--models-file", str(models), "--store", store]

    first = RUNNER.invoke(app, args)
    assert first.exit_code == 0, first.output
    assert "completed 2" in first.output

    second = RUNNER.invoke(app, args)
    assert "skipped 2" in second.output

    parquet = tmp_path / "r.parquet"
    exported = RUNNER.invoke(app, ["export", "--store", store, "--out", str(parquet)])
    assert exported.exit_code == 0, exported.output
    assert pl.read_parquet(parquet).height == 4


def test_unknown_model_is_rejected(tmp_path: Path) -> None:
    models, config = _write(tmp_path)
    store = f"jsonl:{tmp_path / 'r.jsonl'}"
    result = RUNNER.invoke(
        app,
        ["run", str(config), "--models-file", str(models), "--store", store, "--models", "nope"],
    )
    assert result.exit_code != 0


def test_open_store_parses_jsonl_spec(tmp_path: Path) -> None:
    store = open_store(f"jsonl:{tmp_path / 'r.jsonl'}")
    assert isinstance(store, JsonlStore)
