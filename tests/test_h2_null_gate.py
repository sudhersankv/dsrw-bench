"""Spec gate: one shared memory trace with saturating gains must not pass H2.

Everything goes through generate, render and the mock's text parser, so the gate exercises what a
real run would.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from swb.analysis import hypotheses
from swb.baselines.mock_readers import MockReader
from swb.contracts import LadderSpec, Question, ResultRow, WorldSpec
from swb.diary.render import render
from swb.diary.worlds import generate
from swb.questions.build import build
from swb.questions.truth import truth

N_DAYS = 4000
SEEDS = 20
LAGS = (1, 3, 10, 100, 300, 1000, 1900)
RESAMPLES = 500


def _diary(rung: str, lag: int, side: str, seed: int) -> dict[str, Any]:
    ladder = LadderSpec.model_validate({"rung": rung, "lag_days": lag, "pair_side": side})
    diary = generate(WorldSpec(kind="ladder", n_days=N_DAYS, ladder=ladder), seed, 7)
    questions = build(diary, ["report", "decide"], 1, seed)
    return {
        "rung": rung,
        "lag": lag,
        "side": side,
        "seed": seed,
        "state": render(diary),
        "questions": questions,
        "truth": {name: truth(diary, q.key) for name, q in questions.items()},
    }


@pytest.fixture(scope="module")
def diaries() -> list[dict[str, Any]]:
    return [
        _diary(rung, lag, side, seed)
        for rung in ("statistical", "n9")
        for lag in LAGS
        for side in "AB"
        for seed in range(SEEDS)
    ]


def _rows(reader: MockReader, diaries: list[dict[str, Any]]) -> list[ResultRow]:
    rows = []
    for index, item in enumerate(diaries):
        result = asyncio.run(reader.decide(item["state"], item["questions"]))
        question: Question
        for name, question in item["questions"].items():
            rows.append(
                ResultRow(
                    row_id=f"{index}-{name}",
                    call_id=str(index),
                    run_id="null-gate",
                    condition_id="c",
                    model="m",
                    world="ladder",
                    policy="raw",
                    length_tokens_target=128_000,
                    input_tokens=1,
                    n_days=N_DAYS,
                    seed=item["seed"],
                    lag_days=item["lag"],
                    rung=item["rung"],
                    pair_side=item["side"],
                    diary_sha256="d",
                    question_key=question.key,
                    option_order=question.options,
                    probabilities=result.probabilities[name],
                    truth=item["truth"][name],
                    latency_ms=1,
                    http_status=200,
                    created_at="t",
                )
            )
    return rows


def _h2(rows: list[ResultRow]) -> Any:
    registered = {"H1": 30, "H2": SEEDS, "H3": 30}
    return hypotheses.evaluate(rows, RESAMPLES, False, registered)[1]


@pytest.mark.parametrize(
    ("report_gain", "decide_gain", "horizon"),
    [
        (3.0, 1.0, 800.0),
        (3.0, 0.5, 3000.0),
        (5.0, 1.0, 800.0),
        (1.0, 0.2, 800.0),
        (1.7, 1.7, 800.0),
    ],
)
def test_one_shared_trace_with_saturating_gains_does_not_pass_h2(
    diaries: list[dict[str, Any]], report_gain: float, decide_gain: float, horizon: float
) -> None:
    reader = MockReader(
        "s", "saturating", horizon, 0.3, 1, report_gain=report_gain, decide_gain=decide_gain
    )
    assert _h2(_rows(reader, diaries)).verdict != "supported"


class _TwoTraces(MockReader):
    """A true dissociation: `report` remembers far back and `decide` does not."""

    def _pasture_logits(self, state: str, diary: Any, question: Question) -> Any:
        self.horizon = 50.0 if question.key == "decide" else 8000.0
        return super()._pasture_logits(state, diary, question)


def test_a_true_report_decide_dissociation_still_passes_h2(
    diaries: list[dict[str, Any]],
) -> None:
    result = _h2(_rows(_TwoTraces("d", "exponential", 8000.0, 0.05, 1), diaries))
    assert result.verdict == "supported", result.note
