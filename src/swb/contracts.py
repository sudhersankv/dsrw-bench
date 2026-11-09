"""Shared types. Every module boundary uses these. Change only with all owners in mind."""

from __future__ import annotations

from typing import Any, Literal, Protocol

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

# (hot, middle, safe); spec "Rates" table. Mean is always 0.25.
CONTRASTS: dict[str, tuple[float, float, float]] = {
    "7pt": (0.285, 0.25, 0.215),
    "2pt": (0.26, 0.25, 0.24),
    "high": (0.45, 0.25, 0.05),
}
HARMLESS = ["crow", "butterfly", "rabbit", "hawk", "beetle", "deer", "heron"]
# Codes in Diary.sighting: 0..6 index HARMLESS.
WOLF = -1
FOG = -2

Contrast = Literal["7pt", "2pt", "high"]
WorldKind = Literal["steady", "reversal", "ladder"]
Rung = Literal["n1", "n9", "statistical"]
Vocab = Literal["neutral", "natural"]
Policy = Literal["raw", "w1000", "e700", "table", "oracle", "shuffled"]
QuestionKey = Literal["risk", "current", "act", "report", "decide", "find"]


class LadderSpec(BaseModel):
    rung: Rung
    lag_days: int
    block_days: int = 100
    pair_side: Literal["A", "B"] = "A"


class WorldSpec(BaseModel):
    kind: WorldKind
    n_days: int
    contrast: Contrast | None = None  # steady, reversal
    reversal_m: int | None = None  # reversal
    ladder: LadderSpec | None = None  # ladder
    vocab: Vocab = "neutral"


class Diary(BaseModel):
    """One sheep life. Arrays are length n_days, oldest first. Pasture indices 0..3 index `names`."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    spec: WorldSpec
    seed: int
    names: list[str]  # 4 non-word pasture names
    header_order: list[int]  # order pastures are listed in the header
    grazed: np.ndarray  # int8
    sighting: np.ndarray  # int8: HARMLESS index, WOLF or FOG
    bell_day: int | None = None
    hot: int  # hot pasture now (tomorrow's truth). Ladder: the target in this pair side.
    safe: int | None = None  # unique safest pasture now; None on ladder
    old_hot: int | None = None  # reversal: hot pasture before the swap
    tomorrow_rates: list[float] | None = None  # None on ladder


class View(BaseModel):
    """What the model is handed for one policy."""

    policy: Policy
    text: str
    est_tokens: int


class Question(BaseModel):
    key: QuestionKey
    replicate: int = 0
    instructions: str
    options: list[str]  # display order, shuffled, logged as option_order

    @property
    def name(self) -> str:
        return f"{self.key}__r{self.replicate}"


class DecisionResult(BaseModel):
    """One request's response. `probabilities` is keyed by Question.name, then option."""

    probabilities: dict[str, dict[str, float]]
    input_tokens: int
    latency_ms: int
    http_status: int
    model_version: str | None = None
    probabilities_source: Literal["model", "verbalized"] = "model"
    billed_attempts: int = 1  # requests the provider answered with 200, retries included
    raw: dict[str, Any] = Field(default_factory=dict)


class ModelEntry(BaseModel):
    """One row of configs/models.yaml."""

    id: str
    display: str
    adapter: Literal["decision_api", "openai_chat", "mock"]
    model_id: str
    window: int
    price_input_per_m: float
    base_url: str | None = None
    base_url_env: str | None = None
    path: str | None = None
    api_key_env: str | None = None
    budget_capped: bool = False

    @property
    def usable_window(self) -> int:
        return int(self.window * 0.9)


class DecisionClient(Protocol):
    name: str
    model_id: str
    window: int

    async def decide(self, state: str, questions: dict[str, Question]) -> DecisionResult: ...


class Job(BaseModel):
    """One request to one model on one diary and policy."""

    job_id: str  # stable hash of everything below, used to resume
    run_id: str
    condition_id: str
    model: str
    world: WorldSpec
    seed: int
    policy: Policy
    length_tokens_target: int
    question_keys: list[QuestionKey]
    replicates: int = 1
    root_seed: int = 0


class ResultRow(BaseModel):
    """Spec results table: one row per question replicate."""

    row_id: str
    call_id: str
    run_id: str
    condition_id: str
    model: str
    model_version: str | None = None
    world: WorldKind
    contrast: str | None = None
    format: str = "compact"
    policy: Policy
    vocab: Vocab = "neutral"
    length_tokens_target: int
    input_tokens: int
    n_days: int
    seed: int
    reversal_m: int | None = None
    lag_days: int | None = None
    rung: Rung | None = None
    pair_side: Literal["A", "B"] | None = None
    diary_sha256: str
    question_key: QuestionKey
    replicate: int = 0
    option_order: list[str]
    probabilities: dict[str, float]
    probabilities_source: Literal["model", "verbalized"] = "model"
    truth: str
    truth_empirical: str | None = None
    old_truth: str | None = None  # reversal: name of the pasture that was hot before the swap
    true_rates: dict[str, float] | None = None
    baseline_scores: dict[str, dict[str, float]] = Field(default_factory=dict)
    latency_ms: int
    http_status: int
    cost_usd: float | None = None
    is_mock: bool = False
    created_at: str


# ---- Website data. analysis/cards.py writes these; web/ reads them from /data. ----


class CurvePoint(BaseModel):
    x: float
    y: float
    lo: float | None = None  # 95% CI
    hi: float | None = None


class Curve(BaseModel):
    id: str  # e.g. "raw", "w1000", "beta_ceiling"
    label: str
    kind: Literal["model", "baseline"] = "model"
    points: list[CurvePoint]


class Chart(BaseModel):
    id: Literal["steady", "reversal", "ladder"]
    title: str
    x_label: str
    y_label: str
    x_log: bool = True
    y_min: float = 0
    y_max: float = 1
    curves: list[Curve]
    takeaway: str  # one plain sentence computed from the numbers


class SubScore(BaseModel):
    id: Literal["history", "adapt", "recall", "use"]
    label: str  # "Uses history", "Adapts", "Recalls", "Acts on old evidence"
    score: float | None  # 0-100; None = untestable for this model
    lo: float | None = None
    hi: float | None = None
    how: str  # one plain sentence on how it was calculated, with the actual numbers
    cells_used: int
    note: str | None = None  # e.g. "unmeasurable at this length"


class HarnessResult(BaseModel):
    policy: Policy
    label: str
    rescue: float | None  # model(view) - model(raw)
    value_added: float | None  # model(view) - code(same view)
    tokens_per_decision: int
    usd_per_life: float


class HypothesisResult(BaseModel):
    id: Literal["H1", "H2", "H3"]
    statement: str
    verdict: Literal["supported", "not supported", "untestable"]
    effect: float | None
    lo: float | None
    hi: float | None
    p_holm: float | None
    seeds_used: int | None = None
    seeds_expected: int | None = None
    note: str | None = None  # why it is untestable, in plain words


class ModelCard(BaseModel):
    model_id: str
    display: str
    is_demo: bool  # True if any row came from a mock reader. The site must say so on the card.
    flock_score: float | None  # descriptive mean of history, adapt, use. See docs/SCORING.md
    subscores: list[SubScore]
    charts: list[Chart]
    harness: list[HarnessResult]
    hypotheses: list[HypothesisResult]
    max_tokens_tested: int
    probabilities_source: Literal["model", "verbalized"]
    calls: int
    input_tokens: int
    usd_spent: float
    seeds: int
    verdict_line: str  # plain one-liner for the card, computed from numbers
    generated_at: str
    flock_shared: float | None = None  # the leaderboard's flock score, on shared lengths only
    shared_length_tokens: int = 0
    registration_url: str | None = None  # public preregistration, once it exists


class SiteIndex(BaseModel):
    is_demo: bool
    generated_at: str
    spec_version: str = "v2"
    models: list[
        dict[str, Any]
    ]  # {model_id, display, flock_score, subscores:{id:score}, max_tokens_tested}
    shared_length_tokens: int  # the length used for like-for-like model comparison
    disclaimers: list[str]
    registration_url: str | None = None  # public preregistration, once it exists
