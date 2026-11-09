"""Token calibration: measuring the pilot and refusing to spend on an unmatched config."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from swb.cli import app
from swb.config import Cell, RunConfig, SeedRange
from swb.contracts import ModelEntry, ResultRow
from swb.runner import tokens
from swb.runner.tokens import WorldRate


def _row(call: str, world: str, n_days: int, input_tokens: int, model: str = "m") -> ResultRow:
    return ResultRow(
        row_id=call,
        call_id=call,
        run_id="pilot",
        condition_id="c",
        model=model,
        world=world,
        policy="raw",
        length_tokens_target=1,
        input_tokens=input_tokens,
        n_days=n_days,
        seed=0,
        diary_sha256="d",
        question_key="risk",
        option_order=["a"],
        probabilities={"a": 1.0},
        truth="a",
        latency_ms=1,
        http_status=200,
        created_at="t",
    )


def _entry(entry_id: str = "m") -> ModelEntry:
    return ModelEntry(
        id=entry_id,
        display="M",
        adapter="decision_api",
        model_id="m",
        window=100_000,
        price_input_per_m=0.0,
    )


def _config(**extra: object) -> RunConfig:
    cell = Cell(world="steady", question_keys=["risk"], policies=["raw"], contrasts=["7pt"])
    return RunConfig(run_id="r", seeds=SeedRange(count=1), cells=[cell], **extra)


def test_measure_recovers_rate_and_overhead_per_world() -> None:
    rows = [
        _row("a", "steady", 1000, 8150),
        _row("b", "steady", 2000, 16150),
        _row("c", "ladder", 1000, 5150),
        _row("d", "ladder", 2000, 10150),
    ]
    measured = tokens.measure(rows)["m"]
    assert measured["steady"].tokens_per_day == pytest.approx(8.0)
    assert measured["steady"].overhead == pytest.approx(150.0)
    assert measured["ladder"].tokens_per_day == pytest.approx(5.0)
    assert measured["reversal"] == measured["steady"]


def test_measure_ignores_non_pilot_rows() -> None:
    row = _row("a", "steady", 1000, 8000).model_copy(update={"run_id": "r1_steady"})
    assert tokens.measure([row]) == {}


def test_config_must_match_the_measured_rate() -> None:
    calibration = {"m": {"steady": WorldRate(tokens_per_day=9.36, overhead=100.0)}}
    assert tokens.calibration_problems(calibration, _config(), [_entry()])
    matched = _config(world_tokens_per_day={"steady": 9.36})
    assert tokens.calibration_problems(calibration, matched, [_entry()]) == []


def test_missing_calibration_or_model_is_a_problem() -> None:
    assert tokens.calibration_problems(None, _config(), [_entry()])
    calibration = {"other": {"steady": WorldRate(tokens_per_day=8.0, overhead=0.0)}}
    assert (
        "no pilot measurement" in tokens.calibration_problems(calibration, _config(), [_entry()])[0]
    )


def test_calibration_round_trips(tmp_path: Path) -> None:
    calibration = {"m": {"steady": WorldRate(tokens_per_day=8.0, overhead=10.0)}}
    tokens.save(calibration, tmp_path / "x" / "c.json")
    assert tokens.load(tmp_path / "x" / "c.json") == calibration
    assert tokens.load(tmp_path / "missing.json") is None


def test_run_refuses_a_main_config_without_calibration(tmp_path: Path) -> None:
    models = tmp_path / "models.yaml"
    models.write_text(
        "models:\n  - {id: paid, display: P, adapter: decision_api, base_url: http://x, path: /d,"
        " model_id: p, window: 100000, price_input_per_m: 0.0}\n",
        encoding="utf-8",
    )
    config = tmp_path / "c.yaml"
    config.write_text(
        "run_id: r\nseeds: {count: 1}\nrequires_calibration: true\ncells:\n"
        "  - {world: steady, contrasts: [7pt], lengths_tokens: [1000], policies: [raw],"
        " question_keys: [risk]}\n",
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        app,
        [
            "run",
            str(config),
            "--models-file",
            str(models),
            "--store",
            f"jsonl:{tmp_path / 'r.jsonl'}",
            "--calibration",
            str(tmp_path / "missing.json"),
            "--yes",
        ],
    )
    assert result.exit_code == 2
    assert not (tmp_path / "r.jsonl").exists()
