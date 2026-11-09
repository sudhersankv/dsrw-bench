"""The three preregistered confirmatory tests, Holm-corrected as one family."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from swb.analysis.ladder import ShiftTable, denominator_by_seed, long_lags, rk_inputs, shift_table
from swb.analysis.metrics import format_tokens, p_correct, seed_means
from swb.analysis.stats import ALPHA, Estimate, Term, align, bootstrap, holm, mean_term, p_greater
from swb.contracts import HypothesisResult, ResultRow

EFFECT_FLOOR = 0.05
H2_MARGIN = 0.15
H3_M = 2_000
# Registered seeds per cell. The pilot may raise these, never lower them.
REGISTERED_SEEDS: Mapping[str, int] = {"H1": 30, "H2": 20, "H3": 30}
# A short-lag statistical block holds about twice the excess wolves of an n9 block, so a response
# still growing with evidence shifts it about 2x as far. Below this the response has saturated,
# and RK no longer measures memory: an unequally saturating shared trace would pass H2.
MIN_DOSE_RATIO = 1.2
_H1_TOKENS = 256_000
_H2_TOKENS = 128_000
_H3_TOKENS = 256_000
_H3_DAYS = 32_000
_WEAK_RUNG = "n9"
_STRONG_RUNG = "statistical"


@dataclass(frozen=True)
class Tested:
    estimate: Estimate
    p: float | None


@dataclass(frozen=True)
class Untestable:
    note: str
    seeds_used: int | None = None


Outcome = Tested | Untestable


def _short(seeds_used: int, expected: int) -> Untestable:
    note = f"Only {seeds_used} of the {expected} registered sheep lives finished every condition."
    return Untestable(note, seeds_used)


def _paired_mean(
    first: list[ResultRow], second: list[ResultRow], resamples: int, expected: int
) -> Outcome:
    _, (a, b) = align(seed_means(first, p_correct), seed_means(second, p_correct))
    if a.size == 0:
        return Untestable("This model was not run on these diaries.", 0)
    if a.size < expected:
        return _short(int(a.size), expected)
    estimate = bootstrap([mean_term(a - b)], resamples)
    return Tested(estimate, p_greater(estimate))


def _h1_cell(rows: list[ResultRow], policy: str) -> list[ResultRow]:
    return [
        r
        for r in rows
        if r.world == "steady"
        and r.contrast == "2pt"
        and r.question_key == "risk"
        and r.length_tokens_target == _H1_TOKENS
        and r.policy == policy
    ]


def _h1(rows: list[ResultRow], resamples: int, expected: int) -> Outcome:
    return _paired_mean(_h1_cell(rows, "raw"), _h1_cell(rows, "w1000"), resamples, expected)


def _h3_rows(rows: list[ResultRow], policy: str) -> list[ResultRow]:
    return [
        r
        for r in rows
        if r.world == "reversal"
        and r.contrast == "7pt"
        and r.question_key == "current"
        and (r.length_tokens_target == _H3_TOKENS or r.n_days == _H3_DAYS)
        and r.reversal_m == H3_M
        and r.policy == policy
    ]


def _h3(rows: list[ResultRow], resamples: int, expected: int) -> Outcome:
    return _paired_mean(_h3_rows(rows, "w1000"), _h3_rows(rows, "raw"), resamples, expected)


def _short_lag_mean(table: ShiftTable) -> float | None:
    by_seed = denominator_by_seed(table)
    return float(np.mean(list(by_seed.values()))) if by_seed else None


def _saturated_question(rows: list[ResultRow], question: str) -> str | None:
    """Why this answer's response is not in its growing range, or None when it is."""
    strong = _short_lag_mean(shift_table(rows, question, _STRONG_RUNG, _H2_TOKENS))
    weak = _short_lag_mean(shift_table(rows, question, _WEAK_RUNG, _H2_TOKENS))
    if strong is None or weak is None:
        return f"The {_WEAK_RUNG} evidence needed to check the {question} response for saturation is missing."
    if weak > 0 and strong / weak < MIN_DOSE_RATIO:
        return (
            f"The {question} answer has saturated: three times the evidence moved it only "
            f"{strong / weak:.2f}x as far, so an old-clue ratio would not measure memory."
        )
    return None


def _h2(rows: list[ResultRow], resamples: int, verbalized: bool, expected: int) -> Outcome:
    if verbalized:
        return Untestable("This model gives one answer instead of probabilities.")
    report = shift_table(rows, "report", _STRONG_RUNG, _H2_TOKENS)
    decide = shift_table(rows, "decide", _STRONG_RUNG, _H2_TOKENS)
    if not report or not decide:
        return Untestable(f"This model was not run on the {format_tokens(_H2_TOKENS)} ladder.", 0)
    lags = tuple(sorted(set(long_lags(report)) | set(long_lags(decide))))
    if not lags:
        return Untestable("No clue was placed 100 or more days back.", 0)
    for_report, for_decide = rk_inputs(report, lags), rk_inputs(decide, lags)
    if for_report is None or for_decide is None:
        return Untestable(
            "Fresh clues did not move this answer reliably enough to compare old ones against."
        )
    seeds = sorted(set(for_report.seeds) & set(for_decide.seeds))
    if len(seeds) < expected:
        return _short(len(seeds), expected)
    for question in ("report", "decide"):
        reason = _saturated_question(rows, question)
        if reason is not None:
            return Untestable(reason, len(seeds))
    r_index = [for_report.seeds.index(s) for s in seeds]
    d_index = [for_decide.seeds.index(s) for s in seeds]
    terms = [
        Term(for_report.numerator[r_index], for_report.denominator[r_index]),
        Term(for_decide.numerator[d_index], for_decide.denominator[d_index], sign=-1.0),
    ]
    estimate = bootstrap(terms, resamples)
    return Tested(estimate, p_greater(estimate, H2_MARGIN))


def _verdict(outcome: Outcome, adjusted: float | None, min_effect: float) -> str:
    if not isinstance(outcome, Tested) or adjusted is None:
        return "untestable"
    return (
        "supported"
        if outcome.estimate.value >= min_effect and adjusted < ALPHA
        else "not supported"
    )


def _clean(value: float | None) -> float | None:
    return None if value is None or not np.isfinite(value) else float(value)


def _result(
    hid: str, statement: str, outcome: Outcome, p_holm: float | None, floor: float, expected: int
) -> HypothesisResult:
    estimate = outcome.estimate if isinstance(outcome, Tested) else None
    return HypothesisResult(
        id=hid,
        statement=statement,
        verdict=_verdict(outcome, p_holm, floor),
        effect=None if estimate is None else _clean(estimate.value),
        lo=None if estimate is None else _clean(estimate.lo),
        hi=None if estimate is None else _clean(estimate.hi),
        p_holm=p_holm,
        seeds_used=estimate.n if estimate is not None else outcome.seeds_used,
        seeds_expected=expected,
        note=None if isinstance(outcome, Tested) else outcome.note,
    )


def evaluate(
    rows: list[ResultRow],
    resamples: int,
    verbalized: bool,
    registered_seeds: Mapping[str, int] = REGISTERED_SEEDS,
) -> list[HypothesisResult]:
    """H1 to H3 for one model's rows. H2's p-value tests the 0.15 margin, not zero.

    A cell short of its registered seeds is untestable: a partial run never gets a verdict.
    """
    outcomes = [
        _h1(rows, resamples, registered_seeds["H1"]),
        _h2(rows, resamples, verbalized, registered_seeds["H2"]),
        _h3(rows, resamples, registered_seeds["H3"]),
    ]
    adjusted = holm([o.p if isinstance(o, Tested) else None for o in outcomes])
    statements = [
        "History beyond the last 1,000 days adds information at 256K tokens, when the gap between fields is tiny.",
        "At 128K tokens the model can report old evidence it no longer acts on.",
        f"After a reversal {H3_M:,} days ago, the last 1,000 days beat the full diary at 256K tokens.",
    ]
    floors = [EFFECT_FLOOR, H2_MARGIN, EFFECT_FLOOR]
    return [
        _result(hid, statement, outcome, p_holm, floor, registered_seeds[hid])
        for hid, statement, outcome, p_holm, floor in zip(
            ("H1", "H2", "H3"), statements, outcomes, adjusted, floors, strict=True
        )
    ]
