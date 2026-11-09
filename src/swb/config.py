"""Run configuration: the YAML files in configs/ and the environment settings the runner reads."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from swb.contracts import Contrast, Policy, QuestionKey, Rung, WorldKind

DEFAULT_BUDGET_CAP_USD = 45.0


class SeedRange(BaseModel):
    start: int = 0
    count: int

    def values(self) -> list[int]:
        return list(range(self.start, self.start + self.count))


class ModelLimit(BaseModel):
    """Per-run limit for one model, on top of its window."""

    max_tokens: int | None = None
    max_days: int | None = None


class Cell(BaseModel):
    """One block of a sweep. Lengths are given in tokens or in days, never both."""

    world: WorldKind
    question_keys: list[QuestionKey]
    policies: list[Policy]
    contrasts: list[Contrast] = Field(default_factory=list)
    lengths_tokens: list[int] = Field(default_factory=list)
    lengths_days: list[int] = Field(default_factory=list)
    reversal_ms: list[int] | None = None  # None means the spec's nine geometric values
    rungs: list[Rung] = Field(default_factory=list)
    lags: dict[int, list[int]] = Field(default_factory=dict)  # by length in tokens
    shuffled_lag: int | None = None  # adds one shuffled arm per rung and length at this lag
    seeds: SeedRange | None = None  # overrides the run's seeds
    replicates: int | None = None  # overrides the run's replicates
    repeats: int = 1  # same request sent this many times
    extra_days: int = 0  # days appended beyond the target length (latency "append" probe)
    tag: str = ""  # separates otherwise identical cells
    only_models: list[str] | None = None
    skip_models: list[str] = Field(default_factory=list)


class RunConfig(BaseModel):
    run_id: str
    root_seed: int = 0
    seeds: SeedRange
    replicates: int = 1
    concurrency: int = 4
    tokens_per_day: float = 8.0
    # Measured per world by `swb calibrate`; ladder days are mostly short "Fog." lines.
    world_tokens_per_day: dict[WorldKind, float] = Field(default_factory=dict)
    # Per model where its tokenizer differs. Day counts always come from world_tokens_per_day,
    # so every model reads byte-identical diaries; these only decide what fits and what it costs.
    model_tokens_per_day: dict[str, dict[WorldKind, float]] = Field(default_factory=dict)
    requires_calibration: bool = False  # refuse paid calls until the token check has passed
    cells: list[Cell]
    model_limits: dict[str, ModelLimit] = Field(default_factory=dict)
    # Input tokens per minute per account, keyed by the account's api_key_env.
    rate_limits: dict[str, int] = Field(default_factory=dict)

    def tokens_per_day_for(self, world: WorldKind, model: str | None = None) -> float:
        rate = self.model_tokens_per_day.get(model or "", {}).get(world)
        return rate if rate is not None else self.world_tokens_per_day.get(world, self.tokens_per_day)


def load_run_config(path: str | Path) -> RunConfig:
    with Path(path).open(encoding="utf-8") as handle:
        return RunConfig.model_validate(yaml.safe_load(handle))


def budget_cap_usd() -> float:
    raw = os.environ.get("SWB_BUDGET_CAP_USD", "").strip()
    return float(raw) if raw else DEFAULT_BUDGET_CAP_USD
