"""Mock results run through the real CLI end to end and come out as valid, stamped site data."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from swb.cli import app
from swb.contracts import ModelCard, SiteIndex

runner = CliRunner()

MODELS = {
    "models": [
        {
            "id": "worker-mock",
            "display": "Worker mock",
            "adapter": "mock",
            "model_id": "kind=counter,noise=0.02,seed=1",
            "window": 393216,
            "price_input_per_m": 0.0,
        }
    ]
}
CONFIG = {
    "run_id": "worker-test",
    "root_seed": 5,
    "seeds": {"start": 0, "count": 2},
    "cells": [
        {
            "world": "steady",
            "contrasts": ["7pt"],
            "lengths_tokens": [1000],
            "policies": ["raw", "table"],
            "question_keys": ["risk", "act"],
        }
    ],
}


@pytest.fixture(scope="module")
def site(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("demo")
    data = root / "data"
    result = runner.invoke(app, ["demo", "--out", str(root / "demo.jsonl"), "--data", str(data)])
    assert result.exit_code == 0, result.output
    return data


def _cards(site: Path) -> list[ModelCard]:
    paths = sorted((site / "models").glob("*.json"))
    return [ModelCard.model_validate_json(path.read_text(encoding="utf-8")) for path in paths]


def test_index_validates_and_is_demo(site: Path) -> None:
    index = SiteIndex.model_validate_json((site / "index.json").read_text(encoding="utf-8"))
    assert index.is_demo
    assert len(index.models) == 3
    assert any("mock readers" in note for note in index.disclaimers)


def test_every_listed_model_has_a_card_stamped_demo(site: Path) -> None:
    index = json.loads((site / "index.json").read_text(encoding="utf-8"))
    cards = _cards(site)
    assert {card.model_id for card in cards} == {entry["model_id"] for entry in index["models"]}
    assert all(card.is_demo for card in cards)
    assert all(card.verdict_line.startswith("DEMO") for card in cards)


def test_demo_cards_use_registry_names_and_the_spec_cost_table(site: Path) -> None:
    for card in _cards(site):
        assert "(fake)" in card.display
        by_policy = {result.policy: result for result in card.harness}
        assert by_policy["w1000"].usd_per_life == pytest.approx(10.24)
        assert by_policy["e700"].usd_per_life == pytest.approx(0.128)


def test_figures_are_written_for_every_card(site: Path) -> None:
    for card in _cards(site):
        assert len(list((site / "figures" / card.model_id).glob("*.png"))) == 5


def _write_worker_files(tmp_path: Path) -> tuple[Path, Path]:
    models = tmp_path / "models.yaml"
    models.write_text(yaml.safe_dump(MODELS), encoding="utf-8")
    config = tmp_path / "run.yaml"
    config.write_text(yaml.safe_dump(CONFIG), encoding="utf-8")
    return models, config


def test_worker_without_configs_spends_nothing(tmp_path: Path) -> None:
    models, _ = _write_worker_files(tmp_path)
    store = tmp_path / "w.jsonl"
    args = ["worker", "--models-file", str(models), "--store", f"jsonl:{store}"]
    result = runner.invoke(app, args, env={"SWB_WORKER_CONFIGS": ""})
    assert result.exit_code == 0, result.output
    assert "nothing to run" in result.output
    assert not store.exists()


def test_worker_runs_env_configs_and_resumes(tmp_path: Path) -> None:
    models, config = _write_worker_files(tmp_path)
    store = tmp_path / "w.jsonl"
    args = ["worker", "--models-file", str(models), "--store", f"jsonl:{store}"]
    env = {"SWB_WORKER_CONFIGS": str(config)}
    first = runner.invoke(app, args, env=env)
    assert first.exit_code == 0, first.output
    assert "completed 4" in first.output
    second = runner.invoke(app, args, env=env)
    assert second.exit_code == 0, second.output
    assert "skipped 4" in second.output
