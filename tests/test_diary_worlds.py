"""Generator behaviour: rates, reversal swap, ladder block and bell, swapped pairs."""

from __future__ import annotations

import numpy as np
import pytest

from swb.contracts import CONTRASTS, FOG, HARMLESS, WOLF, Contrast, LadderSpec, Rung, WorldSpec
from swb.diary.lengths import days_for_tokens, reversal_ms
from swb.diary.render import render
from swb.diary.worlds import generate


def steady_spec(n_days: int = 2000, contrast: Contrast = "7pt") -> WorldSpec:
    return WorldSpec(kind="steady", n_days=n_days, contrast=contrast)


def reversal_spec(m: int, n_days: int = 2000, contrast: Contrast = "high") -> WorldSpec:
    return WorldSpec(kind="reversal", n_days=n_days, contrast=contrast, reversal_m=m)


def ladder_spec(
    rung: Rung = "n9", lag: int = 100, n_days: int = 2000, side: str = "A"
) -> WorldSpec:
    return WorldSpec(
        kind="ladder",
        n_days=n_days,
        ladder=LadderSpec(rung=rung, lag_days=lag, pair_side=side),
    )


def block_range(spec: WorldSpec) -> range:
    assert spec.ladder is not None
    start = spec.n_days - spec.ladder.lag_days - spec.ladder.block_days
    return range(start, start + spec.ladder.block_days)


@pytest.mark.parametrize("contrast", ["7pt", "2pt", "high"])
def test_rates_have_the_spec_mean(contrast: Contrast) -> None:
    hot, middle, safe = CONTRASTS[contrast]
    assert (hot + 2 * middle + safe) / 4 == pytest.approx(0.25)


@pytest.mark.parametrize("contrast", ["7pt", "2pt", "high"])
def test_steady_truth_matches_generator_rates(contrast: Contrast) -> None:
    hot_rate, middle_rate, safe_rate = CONTRASTS[contrast]
    diary = generate(steady_spec(4000, contrast), seed=3)
    assert diary.safe is not None
    assert diary.tomorrow_rates is not None
    assert diary.tomorrow_rates[diary.hot] == hot_rate
    assert diary.tomorrow_rates[diary.safe] == safe_rate
    others = {0, 1, 2, 3} - {diary.hot, diary.safe}
    assert all(diary.tomorrow_rates[i] == middle_rate for i in others)
    assert diary.old_hot is None
    assert diary.bell_day is None


def test_steady_sighting_frequencies_converge_to_the_rates() -> None:
    diary = generate(steady_spec(200_000, "high"), seed=1)
    assert diary.tomorrow_rates is not None
    for pasture, rate in enumerate(diary.tomorrow_rates):
        here = diary.sighting[diary.grazed == pasture]
        assert np.mean(here == WOLF) == pytest.approx(rate, abs=0.01)


def test_grazing_is_uniform_and_items_cover_all_harmless() -> None:
    diary = generate(steady_spec(100_000), seed=2)
    assert np.bincount(diary.grazed, minlength=4) / 100_000 == pytest.approx(0.25, abs=0.01)
    items = diary.sighting[diary.sighting != WOLF]
    assert np.bincount(items, minlength=7) / len(items) == pytest.approx(1 / 7, abs=0.01)


def test_reversal_swaps_only_a_and_b_only_in_the_last_m_days() -> None:
    n, m = 4000, 500
    steady = generate(steady_spec(n, "high"), seed=7)
    swapped = generate(reversal_spec(m, n, "high"), seed=7)
    assert (steady.grazed == swapped.grazed).all()
    assert (steady.sighting[: n - m] == swapped.sighting[: n - m]).all()
    assert steady.safe is not None
    a, b = steady.hot, steady.safe
    differs = np.flatnonzero(steady.sighting != swapped.sighting)
    assert differs.size > 0
    assert differs.min() >= n - m
    assert set(steady.grazed[differs].tolist()) <= {a, b}


def test_reversal_truth_points_at_the_new_hot_pasture() -> None:
    hot_rate, _, safe_rate = CONTRASTS["high"]
    diary = generate(reversal_spec(100), seed=11)
    steady = generate(steady_spec(2000, "high"), seed=11)
    assert diary.old_hot == steady.hot
    assert diary.hot == steady.safe
    assert diary.safe == steady.hot
    assert diary.tomorrow_rates is not None
    assert diary.tomorrow_rates[diary.hot] == hot_rate
    assert diary.tomorrow_rates[diary.safe] == safe_rate


def test_reversal_rates_flip_in_the_last_m_days() -> None:
    n, m = 300_000, 150_000
    diary = generate(reversal_spec(m, n, "high"), seed=5)
    assert diary.safe is not None and diary.old_hot is not None
    hot_rate, _, safe_rate = CONTRASTS["high"]
    old, new = diary.grazed[: n - m], diary.grazed[n - m :]
    old_s, new_s = diary.sighting[: n - m], diary.sighting[n - m :]
    assert np.mean(old_s[old == diary.old_hot] == WOLF) == pytest.approx(hot_rate, abs=0.01)
    assert np.mean(new_s[new == diary.old_hot] == WOLF) == pytest.approx(safe_rate, abs=0.01)
    assert np.mean(new_s[new == diary.hot] == WOLF) == pytest.approx(hot_rate, abs=0.01)


@pytest.mark.parametrize("m", [0, 2001, None])
def test_reversal_rejects_invalid_m(m: int | None) -> None:
    with pytest.raises(ValueError):
        generate(WorldSpec(kind="reversal", n_days=2000, contrast="7pt", reversal_m=m), seed=0)


def test_rate_worlds_need_a_contrast() -> None:
    with pytest.raises(ValueError):
        generate(WorldSpec(kind="steady", n_days=100), seed=0)


@pytest.mark.parametrize("k", [1, 3, 10, 100, 300, 1000, 1900])
def test_block_sits_k_days_before_the_end(k: int) -> None:
    spec = ladder_spec(lag=k)
    diary = generate(spec, seed=2)
    outside_fog = np.flatnonzero(diary.sighting != FOG)
    assert outside_fog.min() == block_range(spec).start
    assert outside_fog.max() == 2000 - 1 - k
    assert len(outside_fog) == 100


def test_largest_legal_lag_starts_at_day_zero() -> None:
    spec = ladder_spec(lag=1900)
    diary = generate(spec, seed=4)
    assert (diary.sighting[:100] != FOG).all()
    assert (diary.sighting[100:] == FOG).all()


def test_block_outside_the_diary_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"k \+ W <= L"):
        generate(ladder_spec(lag=1901), seed=0)


@pytest.mark.parametrize("seed", range(25))
def test_n1_has_exactly_one_wolf_on_the_target(seed: int) -> None:
    diary = generate(ladder_spec("n1"), seed=seed)
    wolves = np.flatnonzero(diary.sighting == WOLF)
    assert len(wolves) == 1
    assert diary.grazed[wolves[0]] == diary.hot


@pytest.mark.parametrize("side", ["A", "B"])
@pytest.mark.parametrize("seed", range(25))
def test_n9_counts_by_pasture(seed: int, side: str) -> None:
    diary = generate(ladder_spec("n9", side=side), seed=seed)
    wolves = diary.grazed[diary.sighting == WOLF]
    counts = np.bincount(wolves, minlength=4)
    assert counts[diary.hot] == 6
    assert sorted(np.delete(counts, diary.hot).tolist()) == [1, 1, 1]


def test_statistical_rung_rates() -> None:
    target_hits, target_days, other_hits, other_days = 0, 0, 0, 0
    totals = []
    for seed in range(300):
        diary = generate(ladder_spec("statistical"), seed=seed)
        spec_range = block_range(diary.spec)
        grazed = diary.grazed[spec_range.start : spec_range.stop]
        sighting = diary.sighting[spec_range.start : spec_range.stop]
        on_target = grazed == diary.hot
        target_hits += int((sighting[on_target] == WOLF).sum())
        target_days += int(on_target.sum())
        other_hits += int((sighting[~on_target] == WOLF).sum())
        other_days += int((~on_target).sum())
        totals.append(int((sighting == WOLF).sum()))
    assert target_hits / target_days == pytest.approx(0.6, abs=0.02)
    assert other_hits / other_days == pytest.approx(0.2, abs=0.02)
    assert np.mean(totals) == pytest.approx(30, abs=1.5)


@pytest.mark.parametrize("rung", ["n1", "n9", "statistical"])
def test_bell_is_on_the_middle_day_and_is_never_a_wolf(rung: Rung) -> None:
    spec = ladder_spec(rung)
    for seed in range(200):
        diary = generate(spec, seed=seed)
        block = block_range(spec)
        assert diary.bell_day == block.start + 50
        assert 0 <= diary.sighting[diary.bell_day] < len(HARMLESS)


def test_bell_item_is_uniform_over_the_seven_items() -> None:
    items = []
    for seed in range(2100):
        diary = generate(ladder_spec("n1"), seed=seed)
        items.append(int(diary.sighting[diary.bell_day]))
    assert np.bincount(items, minlength=7) / 2100 == pytest.approx(1 / 7, abs=0.035)


def test_exactly_one_bell_on_the_ladder_and_none_elsewhere() -> None:
    assert render(generate(ladder_spec(), seed=1)).count("Heard the bell.") == 1
    assert "Heard the bell." not in render(generate(steady_spec(), seed=1))
    assert "Heard the bell." not in render(generate(reversal_spec(100), seed=1))


@pytest.mark.parametrize("rung", ["n1", "n9", "statistical"])
@pytest.mark.parametrize("seed", range(20))
def test_swap_property_sides_differ_only_by_labels_inside_the_block(rung: Rung, seed: int) -> None:
    side_a = generate(ladder_spec(rung, side="A"), seed=seed)
    side_b = generate(ladder_spec(rung, side="B"), seed=seed)
    assert side_a.names == side_b.names
    assert side_a.header_order == side_b.header_order
    assert side_a.bell_day == side_b.bell_day
    assert (side_a.sighting == side_b.sighting).all()
    assert side_a.hot != side_b.hot

    block = block_range(side_a.spec)
    a_label, b_label = side_a.hot, side_b.hot
    outside = np.ones(2000, dtype=bool)
    outside[block.start : block.stop] = False
    assert (side_a.grazed[outside] == side_b.grazed[outside]).all()

    swap = {a_label: b_label, b_label: a_label}
    expected = [swap.get(int(g), int(g)) for g in side_a.grazed[block.start : block.stop]]
    assert side_b.grazed[block.start : block.stop].tolist() == expected


def test_ladder_has_no_hot_rate_fields_and_only_fog_outside_the_block() -> None:
    spec = ladder_spec("n9")
    diary = generate(spec, seed=9)
    assert diary.safe is None
    assert diary.tomorrow_rates is None
    block = block_range(spec)
    mask = np.ones(2000, dtype=bool)
    mask[block.start : block.stop] = False
    assert (diary.sighting[mask] == FOG).all()
    assert (diary.sighting[~mask] != FOG).all()


def test_days_for_tokens() -> None:
    assert days_for_tokens(16_000) == 2000
    assert days_for_tokens(256_000) == 32_000
    assert days_for_tokens(1000, tokens_per_day=10.0) == 100
    with pytest.raises(ValueError):
        days_for_tokens(0)


@pytest.mark.parametrize("n_days", [2000, 8000, 32_000])
def test_reversal_ms_are_nine_geometric_integers(n_days: int) -> None:
    ms = reversal_ms(n_days)
    assert len(ms) == 9
    assert ms == sorted(set(ms))
    assert ms[0] == 6
    assert ms[-1] == round(0.7 * n_days)
    ratios = np.diff(np.log(ms))
    assert ratios == pytest.approx(ratios[0], abs=0.15)


def test_reversal_ms_rejects_short_diaries() -> None:
    with pytest.raises(ValueError):
        reversal_ms(5)
