"""Analysis tests on synthetic ResultRow fixtures. No model, no network."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from swb.analysis import (
    cards,
    charts,
    harness,
    hypotheses,
    ladder,
    metrics,
    reversal,
    scores,
    stats,
)
from swb.analysis.effective import GRID_DAYS, beta_curve, effective_days, effective_evidence
from swb.contracts import ModelCard, ModelEntry, ResultRow, SiteIndex

OPTIONS = ["Aa", "Bb", "Cc", "Dd"]
RESAMPLES = 400


def probs(on_truth: float, truth: str = "Aa") -> dict[str, float]:
    rest = (1.0 - on_truth) / 3
    return {name: (on_truth if name == truth else rest) for name in OPTIONS}


_counter = iter(range(10_000_000))


def row(**kw) -> ResultRow:
    index = next(_counter)
    base = {
        "row_id": f"r{index}",
        "call_id": f"c{index}",
        "run_id": "r1_steady",
        "condition_id": "x",
        "model": "m1",
        "world": "steady",
        "policy": "raw",
        "length_tokens_target": 256_000,
        "input_tokens": 256_000,
        "n_days": 32_000,
        "seed": 0,
        "diary_sha256": "0" * 64,
        "question_key": "risk",
        "option_order": OPTIONS,
        "probabilities": probs(0.5),
        "truth": "Aa",
        "latency_ms": 10,
        "http_status": 200,
        "created_at": "2026-11-08T00:00:00Z",
    }
    return ResultRow(**(base | kw))


def steady_row(
    seed: int,
    model_p: float,
    beta_p: float,
    length: int = 256_000,
    contrast: str = "2pt",
    policy: str = "raw",
    model: str = "m1",
    **kw,
) -> ResultRow:
    return row(
        seed=seed,
        length_tokens_target=length,
        contrast=contrast,
        policy=policy,
        model=model,
        n_days=length // 8,
        probabilities=probs(model_p),
        baseline_scores={"beta": probs(beta_p)},
        **kw,
    )


def ladder_pair(
    seed: int,
    lag: int,
    shift: float,
    question: str = "report",
    length: int = 128_000,
    rung: str = "statistical",
    beta: float = 0.9,
    model: str = "m1",
    **kw,
) -> list[ResultRow]:
    """A swapped pair whose (log piA - log piB) shift is exactly `shift` nats."""

    def side(sign: float, name: str, truth: str) -> ResultRow:
        a, b = 0.25 * math.exp(sign * shift / 2), 0.25 * math.exp(-sign * shift / 2)
        rest = (1.0 - a - b) / 2
        return row(
            world="ladder",
            question_key=question,
            seed=seed,
            lag_days=lag,
            rung=rung,
            pair_side=name,
            length_tokens_target=length,
            n_days=length // 8,
            model=model,
            truth=truth,
            probabilities={"Aa": a, "Bb": b, "Cc": rest, "Dd": rest},
            baseline_scores={"beta": probs(beta, truth)},
            **kw,
        )

    return [side(1.0, "A", "Aa"), side(-1.0, "B", "Bb")]


def reversal_row(
    seed: int,
    m: int,
    new: float,
    old: float,
    filt: float = 0.8,
    contrast: str = "7pt",
    policy: str = "raw",
    n_days: int = 32_000,
    model: str = "m1",
) -> ResultRow:
    rest = (1.0 - new - old) / 2
    return row(
        world="reversal",
        question_key="current",
        seed=seed,
        reversal_m=m,
        contrast=contrast,
        policy=policy,
        n_days=n_days,
        length_tokens_target=n_days * 8,
        truth="Aa",
        old_truth="Bb",
        model=model,
        probabilities={"Aa": new, "Bb": old, "Cc": rest, "Dd": rest},
        baseline_scores={"filter": {"Aa": filt, "Bb": 0.1, "Cc": 0.05, "Dd": 0.05}},
    )


# ---- per-question metrics


def test_p_correct_log_loss_clip_and_top1() -> None:
    r = row(probabilities={"Aa": 0.0, "Bb": 1.0, "Cc": 0.0, "Dd": 0.0})
    assert metrics.p_correct(r) == 0.0
    assert metrics.log_loss(r) == pytest.approx(-math.log(1e-6))
    assert metrics.top1(r) == 0.0


def test_avoidance_chance_is_zero_and_perfect_is_one() -> None:
    rates = {"Aa": 0.45, "Bb": 0.25, "Cc": 0.25, "Dd": 0.05}
    uniform = row(question_key="act", true_rates=rates, probabilities=dict.fromkeys(OPTIONS, 0.25))
    perfect = row(question_key="act", true_rates=rates, probabilities={"Dd": 1.0})
    assert metrics.avoidance(uniform) == pytest.approx(0.0)
    assert metrics.avoidance(perfect) == pytest.approx(1.0)
    assert metrics.log_loss(uniform) is None


def test_core_rows_drops_pilot_errors_and_stretch_formats() -> None:
    kept = row()
    assert metrics.core_rows(
        [kept, row(run_id="pilot"), row(http_status=500), row(format="messy"), row(vocab="natural")]
    ) == [kept]


# ---- statistics


def test_bootstrap_ci_contains_mean_and_is_seeded() -> None:
    values = np.random.default_rng(1).normal(0.3, 0.1, 30)
    first = stats.bootstrap([stats.mean_term(values)], 2_000)
    second = stats.bootstrap([stats.mean_term(values)], 2_000)
    assert first.lo < values.mean() < first.hi
    assert (first.lo, first.hi) == (second.lo, second.hi)


def test_bootstrap_undefined_for_one_seed_and_constant_input() -> None:
    assert stats.bootstrap([stats.mean_term(np.array([0.4]))], 100).lo is None
    constant = stats.bootstrap([stats.mean_term(np.full(5, 0.4))], 100)
    assert constant.lo == constant.hi == pytest.approx(0.4)


def test_p_greater_small_for_clear_effect_large_for_margin_above_it() -> None:
    values = np.random.default_rng(2).normal(0.3, 0.05, 30)
    estimate = stats.bootstrap([stats.mean_term(values)], 2_000)
    assert stats.p_greater(estimate) < 0.01
    assert stats.p_greater(estimate, null=0.5) > 0.9


def test_holm_steps_down_and_keeps_family_size_for_untestable() -> None:
    assert stats.holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    assert stats.holm([0.01, None, 0.04]) == [pytest.approx(0.03), None, pytest.approx(0.08)]


# ---- ratio of means, usable cells


def test_score_is_ratio_of_means_not_mean_of_ratios() -> None:
    # Seed 0: excess 0.10 over 0.20. Seed 1: excess 0.40 over 0.60.
    rows = [steady_row(0, 0.35, 0.45), steady_row(1, 0.65, 0.85)]
    ratio_of_means = 100 * (0.10 + 0.40) / (0.20 + 0.60)
    mean_of_ratios = 100 * (0.10 / 0.20 + 0.40 / 0.60) / 2
    result = scores.uses_history(rows, RESAMPLES)
    assert result.score == pytest.approx(ratio_of_means)
    assert result.score != pytest.approx(mean_of_ratios)


def test_ceiling_rule_keeps_exactly_020_above_chance_and_drops_below() -> None:
    keep = [steady_row(s, 0.40, 0.45, length=56_000) for s in range(3)]
    drop = [steady_row(s, 0.99, 0.449, length=112_000) for s in range(3)]
    result = scores.uses_history(keep + drop, RESAMPLES)
    assert result.cells_used == 1
    assert result.score == pytest.approx(100 * 0.15 / 0.20)
    assert "1 of 2" in result.note


def test_no_usable_cell_is_null_never_zero() -> None:
    result = scores.uses_history([steady_row(s, 0.3, 0.3) for s in range(3)], RESAMPLES)
    assert result.score is None and result.cells_used == 0


def test_score_clipped_to_100() -> None:
    assert (
        scores.uses_history([steady_row(s, 0.9, 0.5) for s in range(4)], RESAMPLES).score == 100.0
    )


def test_adapts_pools_all_m_and_uses_the_filter() -> None:
    rows = [reversal_row(s, m, 0.5, 0.1) for s in range(3) for m in (6, 2000)]
    result = scores.adapts(rows, RESAMPLES)
    assert result.cells_used == 2
    assert result.score == pytest.approx(100 * 0.25 / 0.55)


# ---- ladder and RK


def test_pair_shift_recovers_constructed_shift() -> None:
    a, b = ladder_pair(0, 100, 0.8)
    assert ladder.pair_shift(a, b) == pytest.approx(0.8)


def _ladder_rows(
    short: float, old: float, question: str = "report", seeds: int = 10, **kw
) -> list[ResultRow]:
    rng = np.random.default_rng(3)
    rows: list[ResultRow] = []
    for seed in range(seeds):
        for lag in ladder.SHORT_LAGS:
            rows += ladder_pair(seed, lag, short + float(rng.normal(0, 0.02)), question, **kw)
        for lag in (100, 1000):
            rows += ladder_pair(seed, lag, old + float(rng.normal(0, 0.02)), question, **kw)
    return rows


def test_recalls_is_old_shift_over_short_shift() -> None:
    result = scores.subscores(_ladder_rows(1.0, 0.5), RESAMPLES, verbalized=False)[2]
    assert result.id == "recall"
    assert result.score == pytest.approx(50, abs=3)
    assert result.cells_used == 2


def test_rk_null_when_denominator_shift_over_se_below_five() -> None:
    noisy: list[ResultRow] = []
    for seed, sign in enumerate([1.0, -0.8, 1.2, -0.9, 0.2, -1.0]):
        for lag in ladder.SHORT_LAGS:
            noisy += ladder_pair(seed, lag, sign)
        noisy += ladder_pair(seed, 100, 0.5)
    table = ladder.shift_table(noisy, "report", "statistical", 128_000)
    assert ladder.rk_at(table, 100) is None
    result = scores.subscores(noisy, RESAMPLES, verbalized=False)[2]
    assert result.score is None
    assert result.note == "unmeasurable at this length"


def test_ladder_ceiling_rule_drops_unusable_lag() -> None:
    rows = _ladder_rows(1.0, 0.5)
    for r in rows:
        if r.lag_days == 1000:
            r.baseline_scores = {"beta": probs(0.3, r.truth)}
    result = scores.subscores(rows, RESAMPLES, verbalized=False)[2]
    assert result.cells_used == 1


def test_verbalized_model_has_null_recall_and_use_and_no_flock() -> None:
    rows = [steady_row(s, 0.9, 0.8) for s in range(3)] + _ladder_rows(1.0, 0.5)
    result = scores.subscores(rows, RESAMPLES, verbalized=True)
    by_id = {s.id: s for s in result}
    assert by_id["recall"].score is None and by_id["use"].score is None
    assert by_id["recall"].note == scores.TOP1_ONLY
    assert by_id["history"].score is not None
    assert scores.flock_score(result) is None


def test_flock_is_mean_of_history_adapt_use_and_excludes_recall() -> None:
    make = lambda i, v: scores.SubScore(id=i, label=i, score=v, how="x", cells_used=1)
    subs = [make("history", 60.0), make("adapt", 30.0), make("recall", 100.0), make("use", 30.0)]
    assert scores.flock_score(subs) == pytest.approx(40.0)
    subs[1] = make("adapt", None)
    assert scores.flock_score(subs) is None


# ---- reversal


def test_crossover_interpolates_on_log_m() -> None:
    assert reversal.crossover_m([(10, -0.5), (1000, 0.5)]) == pytest.approx(100.0)


def test_crossover_absent_when_no_sign_change_and_phrase_says_so() -> None:
    all_old = [(10, -0.5), (100, -0.2)]
    all_new = [(10, 0.5), (100, 0.2)]
    assert reversal.crossover_m(all_old) is None
    assert reversal.crossover_m(all_new) is None
    assert "old field" in reversal.describe_crossing(all_old)
    assert "new field" in reversal.describe_crossing(all_new)


def test_crossover_uses_last_negative_point_under_noise() -> None:
    noisy = [(10, -0.5), (100, 0.1), (1000, -0.1), (10000, 0.5)]
    assert reversal.crossover_m(noisy) == pytest.approx(math.exp(np.log(1000) + np.log(10) / 6))


# ---- effective evidence


def test_beta_curve_matches_spec_ceilings() -> None:
    lookup = lambda contrast, days: float(
        np.interp(np.log(days), np.log(GRID_DAYS), beta_curve(contrast))
    )
    assert lookup("7pt", 2_000) == pytest.approx(0.69, abs=0.05)
    assert lookup("7pt", 7_000) == pytest.approx(0.92, abs=0.05)
    assert lookup("2pt", 32_000) == pytest.approx(0.75, abs=0.05)


def test_effective_evidence_is_a_share_and_null_beyond_grid() -> None:
    assert effective_days(0.1, "7pt") == 0.0
    assert effective_evidence(0.69, 4_000, "7pt") == pytest.approx(0.5, abs=0.2)
    assert effective_days(1.01, "7pt") is None


# ---- hypotheses


def _h1_rows(raw: float, window: float, seeds: int = 30) -> list[ResultRow]:
    rng = np.random.default_rng(5)
    rows: list[ResultRow] = []
    for s in range(seeds):
        noise = float(rng.normal(0, 0.02))
        rows.append(steady_row(s, raw + noise, 0.8))
        rows.append(steady_row(s, window + noise + float(rng.normal(0, 0.02)), 0.8, policy="w1000"))
    return rows


def test_h1_supported_when_effect_clears_floor_and_correction() -> None:
    h1 = hypotheses.evaluate(_h1_rows(0.6, 0.4), RESAMPLES, False)[0]
    assert h1.verdict == "supported"
    assert h1.effect == pytest.approx(0.2, abs=0.02)


def test_h1_not_supported_below_the_005_floor_even_when_significant() -> None:
    assert hypotheses.evaluate(_h1_rows(0.43, 0.40), RESAMPLES, False)[0].verdict == "not supported"


def test_untestable_hypotheses_have_null_effect_and_p() -> None:
    results = hypotheses.evaluate([steady_row(0, 0.5, 0.8)], RESAMPLES, False)
    assert [h.verdict for h in results] == ["untestable"] * 3
    assert results[0].effect is None and results[0].p_holm is None


def _h2_rows(
    report_short: float, report_old: float, decide_short: float, decide_old: float, n9: float = 0.5
) -> list[ResultRow]:
    """The two answers at the statistical rung, and at n9 for the saturation precondition."""
    rows = _ladder_rows(report_short, report_old, "report", seeds=20)
    rows += _ladder_rows(decide_short, decide_old, "decide", seeds=20)
    for question, short in (("report", report_short), ("decide", decide_short)):
        for seed in range(20):
            for lag in ladder.SHORT_LAGS:
                rows += ladder_pair(seed, lag, short * n9, question, rung="n9")
    return rows


def test_h2_supported_only_above_margin_and_untestable_for_verbalized() -> None:
    gap = _h2_rows(1.0, 0.9, 1.0, 0.2)
    no_gap = _h2_rows(1.0, 0.5, 1.0, 0.45)
    assert hypotheses.evaluate(gap, RESAMPLES, False)[1].verdict == "supported"
    assert hypotheses.evaluate(no_gap, RESAMPLES, False)[1].verdict == "not supported"
    assert hypotheses.evaluate(gap, RESAMPLES, True)[1].verdict == "untestable"


def test_h2_is_untestable_when_a_response_has_saturated() -> None:
    saturated = _h2_rows(1.0, 0.9, 1.0, 0.2, n9=1.0)
    result = hypotheses.evaluate(saturated, RESAMPLES, False)[1]
    assert result.verdict == "untestable"
    assert result.note is not None and "saturated" in result.note


def test_h2_is_untestable_without_the_weaker_rung() -> None:
    rows = _ladder_rows(1.0, 0.9, "report", seeds=20) + _ladder_rows(1.0, 0.2, "decide", seeds=20)
    assert hypotheses.evaluate(rows, RESAMPLES, False)[1].verdict == "untestable"


def _h3_cell(m: int, seeds: int = 30) -> list[ResultRow]:
    rows = []
    for s in range(seeds):
        rows.append(reversal_row(s, m, 0.2, 0.5))
        rows.append(reversal_row(s, m, 0.5 + 0.001 * s, 0.2, policy="w1000"))
    return rows


def test_h3_needs_exactly_the_registered_swap_age() -> None:
    assert hypotheses.evaluate(_h3_cell(2000), RESAMPLES, False)[2].verdict == "supported"
    assert hypotheses.evaluate(_h3_cell(2866), RESAMPLES, False)[2].verdict == "untestable"


def test_partial_run_is_untestable_and_says_how_many_seeds_ran() -> None:
    result = hypotheses.evaluate(_h1_rows(0.6, 0.4, seeds=3), RESAMPLES, False)[0]
    assert result.verdict == "untestable"
    assert (result.seeds_used, result.seeds_expected) == (3, 30)
    assert result.note is not None and "3 of the 30" in result.note


def test_one_policy_short_of_seeds_makes_the_cell_short() -> None:
    rows = [r for r in _h1_rows(0.6, 0.4) if r.policy == "raw" or r.seed < 25]
    assert hypotheses.evaluate(rows, RESAMPLES, False)[0].seeds_used == 25


def test_complete_run_reports_seeds_used() -> None:
    result = hypotheses.evaluate(_h1_rows(0.6, 0.4), RESAMPLES, False)[0]
    assert (result.seeds_used, result.seeds_expected) == (30, 30)
    assert result.note is None


# ---- harness and cost


def test_cost_per_life_matches_spec_table() -> None:
    assert harness.usd_per_life("raw", 0.04) == pytest.approx(163.84)
    assert harness.usd_per_life("w1000", 0.04) == pytest.approx(10.24)
    assert harness.usd_per_life("e700", 0.04) == pytest.approx(0.128)


def test_rescue_and_value_added_are_paired_and_separate() -> None:
    rows = [
        steady_row(0, 0.4, 0.8),
        row(
            seed=0,
            length_tokens_target=256_000,
            contrast="2pt",
            policy="w1000",
            probabilities=probs(0.7),
            baseline_scores={"w1000": probs(0.5)},
        ),
    ]
    results = harness.harness_results(rows, 0.04)
    assert results[0].policy == "w1000"
    assert results[0].rescue == pytest.approx(0.3)
    assert results[0].value_added == pytest.approx(0.2)


def test_no_code_baseline_gives_null_value_added() -> None:
    rows = [row(seed=0, policy="shuffled"), row(seed=0)]
    assert harness.harness_results(rows, 0.04)[0].value_added is None


def test_oracle_value_added_is_against_code_that_reads_the_answer() -> None:
    rows = [row(seed=0, policy="oracle", probabilities=probs(0.9)), row(seed=0)]
    assert harness.harness_results(rows, 0.04)[0].value_added == pytest.approx(-0.1)


def test_matched_rows_keep_only_diaries_every_policy_answered() -> None:
    both = [steady_row(0, 0.5, 0.8), steady_row(0, 0.6, 0.8, policy="w1000")]
    raw_only = steady_row(1, 0.9, 0.8)
    assert harness.matched_rows([*both, raw_only]) == both


def test_how_says_below_guessing_and_capped_in_plain_words() -> None:
    below = scores.uses_history([steady_row(s, 0.2, 0.8) for s in range(3)], RESAMPLES)
    assert below.score == 0.0
    assert "below guessing" in below.how and "shown as 0" in below.how
    above = scores.uses_history([steady_row(s, 0.9, 0.5) for s in range(3)], RESAMPLES)
    assert "before capping at 100" in above.how


def test_curve_intervals_stay_inside_the_possible_range() -> None:
    rows = [steady_row(s, v, 0.8) for s, v in enumerate([0.02, 0.98, 0.5])]
    curve = charts.steady_curves(rows, RESAMPLES)[0]
    assert all(0.0 <= p.lo and p.hi <= 1.0 for p in curve.points)


# ---- site


def _site_rows(model: str, mock: bool) -> list[ResultRow]:
    rows: list[ResultRow] = [
        steady_row(s, 0.6, 0.8, length=16_000, contrast="7pt", model=model, is_mock=mock)
        for s in range(5)
    ]
    rows += [
        steady_row(
            s, 0.5, 0.8, length=16_000, contrast="7pt", policy="w1000", model=model, is_mock=mock
        )
        for s in range(5)
    ]
    for s in range(5):
        rows.append(
            reversal_row(s, 100, 0.6, 0.2, n_days=2_000, model=model).model_copy(
                update={"is_mock": mock}
            )
        )
        rows += ladder_pair(s, 1, 1.0 + 0.01 * s, model=model, length=16_000, is_mock=mock)
        rows += ladder_pair(s, 3, 1.0 + 0.01 * s, model=model, length=16_000, is_mock=mock)
        rows += ladder_pair(s, 10, 1.0 + 0.01 * s, model=model, length=16_000, is_mock=mock)
        rows += ladder_pair(s, 100, 0.5 + 0.01 * s, model=model, length=16_000, is_mock=mock)
        rows += ladder_pair(
            s, 100, 0.4 + 0.01 * s, "decide", model=model, length=16_000, is_mock=mock
        )
        for lag in ladder.SHORT_LAGS:
            rows += ladder_pair(
                s, lag, 1.0 + 0.01 * s, "decide", model=model, length=16_000, is_mock=mock
            )
    return rows


def _load(out: Path) -> tuple[SiteIndex, dict[str, ModelCard]]:
    index = SiteIndex.model_validate_json((out / "index.json").read_text(encoding="utf-8"))
    built = {
        e["model_id"]: ModelCard.model_validate_json(
            (out / "models" / f"{e['model_id']}.json").read_text(encoding="utf-8")
        )
        for e in index.models
    }
    return index, built


def test_demo_flag_propagates_to_every_card_and_figure(tmp_path: Path) -> None:
    rows = _site_rows("m1", True) + _site_rows("m2", False)
    cards.build_site(rows, tmp_path, is_demo=False, models=[])
    index, built = _load(tmp_path)
    assert index.is_demo and len(built) == 2
    for card in built.values():
        assert card.is_demo
        assert card.verdict_line.startswith(metrics.DEMO_PREFIX)
        assert all(c.takeaway.startswith(metrics.DEMO_PREFIX) for c in card.charts)
        assert all(s.how.startswith(metrics.DEMO_PREFIX) for s in card.subscores)
    assert (
        json.loads((tmp_path / "figures" / "m2" / "fig1_steady.json").read_text())["is_demo"]
        is True
    )
    assert any("mock" in note for note in index.disclaimers)


def test_verbalized_ladder_figure_has_no_curves_rk_or_log_loss(tmp_path: Path) -> None:
    rows = _ladder_rows(1.0, 0.5, "report", probabilities_source="verbalized")
    cards.build_site(rows, tmp_path, is_demo=False, models=[])
    figure = json.loads((tmp_path / "figures" / "m1" / "fig3_ladder.json").read_text())
    assert figure["panels"]
    for panel in figure["panels"]:
        assert panel["curves"] == [] and panel["rk"] == {}
    summary = json.loads((tmp_path / "figures" / "m1" / "question_metrics.json").read_text())
    assert all(entry["log_loss"] is None for entry in summary["metrics"])


def test_card_carries_shared_score_and_share_images(tmp_path: Path) -> None:
    rows = _site_rows("m1", False) + _site_rows("m2", False)
    cards.build_site(rows, tmp_path, is_demo=False, models=[])
    index, built = _load(tmp_path)
    entry = next(e for e in index.models if e["model_id"] == "m1")
    assert built["m1"].flock_shared == entry["flock_score"]
    assert built["m1"].shared_length_tokens == index.shared_length_tokens
    assert (tmp_path / "og" / "m1.png").stat().st_size > 1000
    assert (tmp_path / "og" / "site.png").stat().st_size > 1000


def test_registration_link_is_read_only_when_filled_in(tmp_path: Path) -> None:
    doc = tmp_path / "PREREGISTRATION.md"
    doc.write_text("| OSF registration link | |\n", encoding="utf-8")
    assert cards.registration_url(doc) is None
    doc.write_text("| OSF registration link | https://osf.io/abc12 |\n", encoding="utf-8")
    assert cards.registration_url(doc) == "https://osf.io/abc12"
    assert cards.registration_url(tmp_path / "missing.md") is None


def test_real_run_is_not_marked_demo(tmp_path: Path) -> None:
    cards.build_site(_site_rows("m1", False), tmp_path, is_demo=False, models=[])
    index, built = _load(tmp_path)
    assert not index.is_demo and not built["m1"].is_demo
    assert metrics.DEMO_PREFIX not in built["m1"].verdict_line


def test_site_writes_contract_shapes_five_figures_and_uses_registry(tmp_path: Path) -> None:
    entry = ModelEntry(
        id="m1",
        display="Model One",
        adapter="mock",
        model_id="m-one",
        window=100_000,
        price_input_per_m=0.5,
    )
    cards.build_site(_site_rows("m1", False), tmp_path, is_demo=False, models=[entry])
    index, built = _load(tmp_path)
    card = built["m1"]
    assert card.display == "Model One"
    assert [h.id for h in card.hypotheses] == ["H1", "H2", "H3"]
    assert {c.id for c in card.charts} == {"steady", "reversal", "ladder"}
    assert card.harness[0].usd_per_life == pytest.approx(128.0)
    assert card.max_tokens_tested == 16_000
    assert index.shared_length_tokens == 16_000
    assert index.models[0]["subscores"]["history"] is not None
    for name in ("fig1_steady", "fig2_reversal", "fig3_ladder", "fig4_harness", "fig5_cost"):
        assert (tmp_path / "figures" / "m1" / f"{name}.png").stat().st_size > 1000
        assert (tmp_path / "figures" / "m1" / f"{name}.json").exists()


def test_takeaway_and_verdict_report_the_actual_numbers(tmp_path: Path) -> None:
    cards.build_site(_site_rows("m1", False), tmp_path, is_demo=False, models=[])
    _, built = _load(tmp_path)
    card = built["m1"]
    steady = next(c for c in card.charts if c.id == "steady")
    assert "60%" in steady.takeaway and "80%" in steady.takeaway
    history = next(s for s in card.subscores if s.id == "history")
    assert f"{history.score:.0f}/100" in card.verdict_line
    assert "0.350" in history.how and "0.550" in history.how


def test_token_and_call_totals_count_each_request_once(tmp_path: Path) -> None:
    rows = [
        row(call_id="same", question_key="risk", input_tokens=1000, contrast="7pt"),
        row(call_id="same", question_key="act", input_tokens=1000, contrast="7pt"),
    ]
    cards.build_site(rows, tmp_path, is_demo=False, models=[])
    _, built = _load(tmp_path)
    assert built["m1"].calls == 1 and built["m1"].input_tokens == 1000


def test_empty_input_writes_an_empty_site(tmp_path: Path) -> None:
    cards.build_site([], tmp_path, is_demo=True, models=[])
    index, built = _load(tmp_path)
    assert index.models == [] and built == {} and index.shared_length_tokens == 0


def test_unmeasurable_flock_stays_null_on_card(tmp_path: Path) -> None:
    rows = [steady_row(s, 0.6, 0.8, length=16_000, contrast="7pt") for s in range(5)]
    cards.build_site(rows, tmp_path, is_demo=False, models=[])
    _, built = _load(tmp_path)
    card = built["m1"]
    assert card.flock_score is None
    assert next(s for s in card.subscores if s.id == "use").score is None
    assert "Not enough testable results" in card.verdict_line
