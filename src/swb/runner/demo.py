"""The demo run: mock readers at reduced seeds and lengths. Every id says it is not a model."""

from __future__ import annotations

from swb.config import Cell, RunConfig, SeedRange
from swb.contracts import ModelEntry

DEMO_SEEDS = 6
SPEC_PRICE_PER_M = 0.04  # so demo cost panels show the spec's cost-per-life table
_LADDER_LAGS = [1, 3, 10, 100, 300, 1000, 1900]


def _demo_entry(entry_id: str, display: str, spec: str) -> ModelEntry:
    return ModelEntry(
        id=entry_id,
        display=display,
        adapter="mock",
        model_id=spec,
        window=393216,
        price_input_per_m=SPEC_PRICE_PER_M,
    )


def demo_models() -> list[ModelEntry]:
    return [
        _demo_entry(
            "demo-long-memory", "Demo: long memory (fake)", "kind=counter,noise=0.02,seed=1"
        ),
        _demo_entry(
            "demo-recent-only",
            "Demo: recent only (fake)",
            "kind=window,horizon=500,noise=0.02,seed=2",
        ),
        _demo_entry(
            "demo-forgetful",
            "Demo: forgetful (fake)",
            "kind=exponential,horizon=200,noise=0.05,seed=3",
        ),
    ]


def demo_config() -> RunConfig:
    return RunConfig(
        run_id="demo",
        root_seed=999,
        seeds=SeedRange(start=0, count=DEMO_SEEDS),
        concurrency=4,
        cells=[
            Cell(
                world="steady",
                contrasts=["7pt"],
                lengths_tokens=[1000, 4000, 16000, 56000],
                policies=["raw", "w1000", "table", "oracle"],
                question_keys=["risk", "act"],
            ),
            Cell(
                world="reversal",
                contrasts=["7pt", "high"],
                lengths_days=[2000],
                policies=["raw", "w1000", "e700"],
                question_keys=["current", "act"],
            ),
            Cell(
                world="ladder",
                rungs=["n1", "n9", "statistical"],
                lengths_tokens=[16000],
                lags={16000: _LADDER_LAGS},
                shuffled_lag=100,
                policies=["raw"],
                question_keys=["report", "decide", "find"],
            ),
        ],
    )
