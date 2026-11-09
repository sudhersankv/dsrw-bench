"""Ceilings, reversal crossovers and baseline_scores, on small diaries built here."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pytest

from swb.baselines.counter import beta_posterior, prob_extreme, tally
from swb.baselines.filter import bma_filter, known_filter
from swb.baselines.scores import baseline_scores
from swb.baselines.windows import cusum, decay_top, window_top
from swb.contracts import CONTRASTS, FOG, WOLF, Contrast, Diary, LadderSpec, WorldSpec

Reader = Callable[[Diary], list[float]]
NAMES = ["Darro", "Kell", "Mib", "Sule"]
HOT, SAFE = 0, 1


def steady(contrast: Contrast, n_days: int, seed: int) -> Diary:
    return _world(contrast, n_days, seed, None)


def reversal(contrast: Contrast, n_days: int, seed: int, m: int) -> Diary:
    return _world(contrast, n_days, seed, m)


def _world(contrast: Contrast, n_days: int, seed: int, m: int | None) -> Diary:
    rng = np.random.default_rng([seed, n_days, m or 0, len(contrast), int(contrast == "high")])
    hot, middle, safe = CONTRASTS[contrast]
    old = np.array([hot, safe, middle, middle])
    new = np.array([safe, hot, middle, middle])
    grazed = rng.integers(0, 4, n_days)
    rate = old[grazed]
    if m is not None:
        rate[n_days - m :] = new[grazed[n_days - m :]]
    harmless = rng.integers(0, 7, n_days)
    sighting = np.where(rng.random(n_days) < rate, WOLF, harmless).astype(np.int8)
    spec = WorldSpec(
        kind="steady" if m is None else "reversal", n_days=n_days, contrast=contrast, reversal_m=m
    )
    return Diary(
        spec=spec,
        seed=seed,
        names=NAMES,
        header_order=[0, 1, 2, 3],
        grazed=grazed.astype(np.int8),
        sighting=sighting,
        hot=HOT if m is None else SAFE,
        safe=SAFE if m is None else HOT,
        old_hot=None if m is None else HOT,
        tomorrow_rates=(old if m is None else new).tolist(),
    )


def ladder(lag: int, side: str, seed: int, n_days: int = 2000) -> Diary:
    """Statistical rung: the target is pasture 0 on side A and pasture 1 on side B."""
    rng = np.random.default_rng([seed, lag, n_days])
    grazed = rng.integers(0, 4, n_days)
    sighting = np.full(n_days, FOG, dtype=np.int8)
    block = np.arange(n_days - lag - 100, n_days - lag)
    target = 0 if side == "A" else 1
    rate = np.where(grazed[block] == 0, 0.6, 0.2)
    if side == "B":
        grazed[block] = np.select([grazed[block] == 0, grazed[block] == 1], [1, 0], grazed[block])
    sighting[block] = np.where(rng.random(block.size) < rate, WOLF, rng.integers(0, 7, block.size))
    spec = WorldSpec(
        kind="ladder",
        n_days=n_days,
        ladder=LadderSpec(rung="statistical", lag_days=lag, pair_side=side),
    )
    return Diary(
        spec=spec,
        seed=seed,
        names=NAMES,
        header_order=[0, 1, 2, 3],
        grazed=grazed.astype(np.int8),
        sighting=sighting,
        hot=target,
    )


def reversal_ms(n_days: int) -> list[int]:
    return np.unique(np.geomspace(6, 0.7 * n_days, 9).round().astype(int)).tolist()


def crossover(reader: Reader, contrast: Contrast, n_days: int, seeds: int) -> float | None:
    """The m where mean P(new) - P(old) crosses zero, interpolated in log m."""
    ms = reversal_ms(n_days)
    gaps = []
    for m in ms:
        beliefs = np.array([reader(reversal(contrast, n_days, seed, m)) for seed in range(seeds)])
        gaps.append(float(np.mean(beliefs[:, SAFE] - beliefs[:, HOT])))
    for i in range(len(ms) - 1):
        if gaps[i] < 0 <= gaps[i + 1]:
            fraction = -gaps[i] / (gaps[i + 1] - gaps[i])
            return float(np.exp(np.log(ms[i]) + fraction * np.log(ms[i + 1] / ms[i])))
    return None


@pytest.mark.parametrize(
    ("contrast", "n_days", "expected"),
    [
        ("7pt", 125, 0.31),
        ("7pt", 500, 0.46),
        ("7pt", 2000, 0.75),
        ("7pt", 7000, 0.97),
        ("2pt", 7000, 0.48),
        ("2pt", 14000, 0.62),
        ("2pt", 32000, 0.82),
    ],
)
def test_known_structure_ceiling_matches_spec_table(
    contrast: Contrast, n_days: int, expected: float
) -> None:
    mean = np.mean([known_filter(steady(contrast, n_days, s))[HOT] for s in range(600)])
    assert mean == pytest.approx(expected, abs=0.05)


@pytest.mark.parametrize(
    ("contrast", "n_days", "expected"),
    [
        ("7pt", 2000, 0.69),
        ("7pt", 7000, 0.92),
        ("2pt", 7000, 0.50),
        ("2pt", 14000, 0.61),
        ("2pt", 32000, 0.75),
    ],
)
def test_beta_counter_matches_spec(contrast: Contrast, n_days: int, expected: float) -> None:
    mean = np.mean([beta_posterior(steady(contrast, n_days, s))[HOT] for s in range(600)])
    assert mean == pytest.approx(expected, abs=0.05)


@pytest.mark.parametrize(
    ("reader", "expected_m"),
    [(lambda d: window_top(d, 1000), 500.0), (lambda d: decay_top(d, 700), 700.0)],
)
def test_fixed_horizon_readers_cross_at_the_same_m_at_both_contrasts(
    reader: Reader, expected_m: float
) -> None:
    low = crossover(reader, "7pt", 8000, 100)
    high = crossover(reader, "high", 8000, 40)
    assert low is not None and high is not None
    assert 1 / 1.6 < low / high < 1.6
    assert 0.6 * expected_m < high < 1.6 * expected_m


def test_known_filter_crossover_moves_at_least_tenfold() -> None:
    low = crossover(known_filter, "7pt", 8000, 40)
    high = crossover(known_filter, "high", 8000, 40)
    assert low is not None and high is not None
    assert low / high >= 10


def test_full_memory_reader_crosses_below_seventy_percent_of_length() -> None:
    n_days = 8000
    m_star = crossover(beta_posterior, "high", n_days, 30)
    assert m_star is not None
    assert m_star < 0.7 * n_days


def test_bma_tracks_a_clear_reversal_and_stays_put_when_steady() -> None:
    assert bma_filter(reversal("high", 8000, 3, 2000))[SAFE] > 0.9
    assert bma_filter(steady("high", 8000, 3))[HOT] > 0.9


def test_cusum_counts_only_since_the_change() -> None:
    wins = [int(np.argmax(cusum(reversal("high", 8000, s, 1500))) == SAFE) for s in range(20)]
    assert sum(wins) >= 18
    assert np.argmax(beta_posterior(reversal("high", 8000, 0, 1500))) == HOT


def test_cusum_ignores_a_steady_world() -> None:
    diary = steady("7pt", 8000, 5)
    assert cusum(diary) == pytest.approx(beta_posterior(diary), abs=0.25)


def test_beta_report_shift_is_flat_across_lags() -> None:
    def shift(lag: int, seed: int) -> float:
        a = beta_posterior(ladder(lag, "A", seed))
        b = beta_posterior(ladder(lag, "B", seed))
        return 0.5 * (np.log(a[0] / a[1]) - np.log(b[0] / b[1]))

    near = np.mean([shift(1, seed) for seed in range(60)])
    far = np.mean([shift(1500, seed) for seed in range(60)])
    assert near > 1.0
    assert far == pytest.approx(near, rel=0.15)


def test_window_ignores_days_before_it() -> None:
    diary = reversal("high", 4000, 1, 400)
    recent_only = beta_posterior(diary, start=3600)
    assert window_top(diary, 400) == pytest.approx(recent_only)


def test_decay_with_huge_half_life_matches_the_full_counter() -> None:
    diary = steady("high", 3000, 2)
    assert decay_top(diary, 1e12) == pytest.approx(beta_posterior(diary), abs=1e-6)


def test_tally_excludes_fog() -> None:
    diary = ladder(10, "A", 0)
    visits, wolves = tally(diary)
    assert visits.sum() == 100
    assert wolves.sum() == (diary.sighting == WOLF).sum()


def test_prob_extreme_is_a_distribution_and_symmetric() -> None:
    alpha = np.array([11.0, 11.0, 2.0, 2.0])
    beta = np.array([3.0, 3.0, 8.0, 8.0])
    top = prob_extreme(alpha, beta)
    assert sum(top) == pytest.approx(1.0)
    assert top[0] == pytest.approx(top[1])
    assert prob_extreme(beta, alpha, lowest=True) == pytest.approx(top, abs=1e-9)


def test_baseline_scores_are_keyed_by_option_and_follow_the_question() -> None:
    diary = reversal("high", 4000, 7, 1500)
    options = ["Sule", "Kell", "Darro", "Mib"]
    current = baseline_scores(diary, "current", options)
    assert set(current) == {"beta", "filter", "known_filter", "w1000", "e700"}
    for probs in current.values():
        assert list(probs) == options
        assert sum(probs.values()) == pytest.approx(1.0)
    assert max(current["filter"], key=current["filter"].__getitem__) == "Kell"
    act = baseline_scores(diary, "act", options)
    assert max(act["filter"], key=act["filter"].__getitem__) == "Darro"


def test_baseline_scores_find_is_chance_over_items() -> None:
    options = ["crow", "deer", "heron", "hawk", "rabbit", "beetle", "butterfly"]
    scores = baseline_scores(ladder(10, "A", 1), "find", options)
    assert scores["beta"]["crow"] == pytest.approx(1 / 7)


def test_filters_run_on_a_ladder_with_fog() -> None:
    probs = known_filter(ladder(10, "A", 4))
    assert sum(probs) == pytest.approx(1.0)
    assert int(np.argmax(probs)) == 0
