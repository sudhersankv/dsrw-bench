"""Spec validation gates owned by the diary engine, plus rendering and name rules."""

from __future__ import annotations

import re

import numpy as np
import pytest

from swb.contracts import FOG, HARMLESS, WOLF, Diary, LadderSpec, Rung, WorldSpec
from swb.diary.names import ENDINGS, MEDIALS, NAME_POOL, ONSETS, VOWELS, pasture_names
from swb.diary.render import day_lines, header, render, sha256, shuffled
from swb.diary.worlds import generate


def steady(seed: int = 0, n_days: int = 2000, vocab: str = "neutral") -> Diary:
    return generate(WorldSpec(kind="steady", n_days=n_days, contrast="7pt", vocab=vocab), seed)


def reversal(seed: int = 0, n_days: int = 2000) -> Diary:
    return generate(
        WorldSpec(kind="reversal", n_days=n_days, contrast="high", reversal_m=200), seed
    )


def ladder(
    seed: int = 0, rung: Rung = "n9", side: str = "A", lag: int = 100, vocab: str = "neutral"
) -> Diary:
    spec = WorldSpec(
        kind="ladder",
        n_days=2000,
        vocab=vocab,
        ladder=LadderSpec(rung=rung, lag_days=lag, pair_side=side),
    )
    return generate(spec, seed)


ALL_WORLDS = [steady, reversal, ladder]


def test_name_check_each_slot_is_hot_about_a_quarter_of_the_time() -> None:
    counts = np.zeros(4)
    for seed in range(1000):
        diary = steady(seed, n_days=8)
        counts[diary.hot] += 1
    # Binomial(1000, 0.25) has sd 13.7; 4 sd keeps the gate from being flaky.
    assert np.abs(counts - 250).max() < 55


def test_header_slot_is_uniform_too() -> None:
    counts = np.zeros(4)
    for seed in range(1000):
        diary = steady(seed, n_days=8)
        counts[diary.header_order.index(diary.hot)] += 1
    assert np.abs(counts - 250).max() < 55


def test_name_pool_is_distinct_and_structural() -> None:
    assert len(NAME_POOL) == len(set(NAME_POOL)) == 3510
    forbidden = ("hot", "wolf", "fog", "bell", "favorite", "safe", "sheep", *HARMLESS)
    shape = re.compile(
        f"[{''.join(ONSETS)}][{''.join(VOWELS)}]({'|'.join(MEDIALS)})({'|'.join(ENDINGS)})"
    )
    for name in NAME_POOL:
        lowered = name.lower()
        assert shape.fullmatch(lowered)
        assert not any(word in lowered for word in forbidden)


def test_pasture_names_are_four_distinct_pool_members() -> None:
    names = pasture_names(np.random.default_rng(0))
    assert len(set(names)) == 4
    assert set(names) <= set(NAME_POOL)


def test_seeds_get_different_names() -> None:
    assert len({tuple(steady(seed, n_days=8).names) for seed in range(200)}) > 195


@pytest.mark.parametrize("make", ALL_WORLDS)
def test_replay_gives_the_same_sha(make) -> None:
    assert sha256(make(seed=42)) == sha256(make(seed=42))
    assert sha256(make(seed=42)) != sha256(make(seed=43))


def test_root_seed_changes_the_diary_and_replays() -> None:
    spec = WorldSpec(kind="steady", n_days=300, contrast="7pt")
    assert sha256(generate(spec, 1, root_seed=9)) == sha256(generate(spec, 1, root_seed=9))
    assert sha256(generate(spec, 1, root_seed=9)) != sha256(generate(spec, 1, root_seed=10))


def test_shuffle_preserves_counts_and_changes_order() -> None:
    diary = ladder(seed=3, rung="statistical")
    mixed = shuffled(diary)
    assert not (diary.grazed == mixed.grazed).all() or not (diary.sighting == mixed.sighting).all()
    pairs = sorted(zip(diary.grazed.tolist(), diary.sighting.tolist(), strict=True))
    assert pairs == sorted(zip(mixed.grazed.tolist(), mixed.sighting.tolist(), strict=True))


def test_shuffle_keeps_the_bell_with_its_day() -> None:
    diary = ladder(seed=4)
    mixed = shuffled(diary)
    assert diary.bell_day is not None and mixed.bell_day is not None
    assert mixed.sighting[mixed.bell_day] == diary.sighting[diary.bell_day]
    assert mixed.grazed[mixed.bell_day] == diary.grazed[diary.bell_day]
    assert render(mixed).count("Heard the bell.") == 1


def test_shuffle_is_deterministic_and_seed_dependent() -> None:
    diary = ladder(seed=5)
    assert sha256(shuffled(diary)) == sha256(shuffled(ladder(seed=5)))
    assert sha256(shuffled(diary)) != sha256(shuffled(ladder(seed=6)))


def test_shuffle_uses_the_same_permutation_on_both_pair_sides() -> None:
    a, b = ladder(seed=8, side="A"), ladder(seed=8, side="B")
    mixed_a, mixed_b = shuffled(a), shuffled(b)
    assert (mixed_a.sighting == mixed_b.sighting).all()
    assert mixed_a.bell_day == mixed_b.bell_day
    differing = np.flatnonzero(mixed_a.grazed != mixed_b.grazed)
    assert differing.size > 0
    assert set(mixed_a.grazed[differing].tolist()) == {a.hot, b.hot}
    assert (mixed_a.sighting[differing] != FOG).all()


@pytest.mark.parametrize("make", ALL_WORLDS)
@pytest.mark.parametrize("seed", range(10))
def test_leak_scan(make, seed: int) -> None:
    text = render(make(seed=seed))
    assert not re.search(r"\d", text)
    lowered = text.lower()
    assert "favorite" not in lowered
    assert "hot" not in lowered
    assert "most dangerous" not in lowered
    assert "dangerous" not in lowered
    assert "risk" not in lowered
    assert "safe" not in lowered


def test_leak_scan_on_natural_vocabulary() -> None:
    for make in [lambda s: steady(s, vocab="natural"), lambda s: ladder(s, vocab="natural")]:
        text = render(make(1)).lower()
        assert "hot" not in text and "favorite" not in text and not re.search(r"\d", text)


def test_header_names_every_pasture_exactly_once() -> None:
    diary = steady(seed=12)
    head = header(diary)
    counts = [head.count(name) for name in diary.names]
    assert counts == [1, 1, 1, 1]


def test_header_lists_all_pastures_in_header_order_and_says_oldest_first() -> None:
    diary = steady(seed=21)
    head = header(diary)
    positions = [head.index(diary.names[i]) for i in diary.header_order]
    assert positions == sorted(positions)
    assert "oldest first" in head
    assert "harmful" in head


def test_ladder_header_says_habits_never_change_and_others_do_not() -> None:
    assert "The X's habits never change." in header(ladder())
    assert "The wolf's habits never change." in header(ladder(vocab="natural"))
    assert "habits" not in header(steady())
    assert "habits" not in header(reversal())


def test_neutral_vocabulary_has_no_animal_words() -> None:
    text = render(steady(seed=2)).lower()
    assert "wolf" not in text and "sheep" not in text
    assert "the agent" in text
    assert "saw an x." in text


def test_natural_vocabulary_uses_sheep_and_wolf() -> None:
    text = render(steady(seed=2, vocab="natural"))
    assert "the sheep" in text
    assert "Saw a wolf." in text
    assert " X." not in text


def test_fog_days_read_exactly_as_the_spec() -> None:
    diary = ladder(seed=3)
    lines = day_lines(diary)
    fog_day = int(np.flatnonzero(diary.sighting == FOG)[0])
    assert lines[fog_day] == f"Grazed {diary.names[int(diary.grazed[fog_day])]}. Fog."


def test_bell_day_line_carries_the_item() -> None:
    diary = ladder(seed=3)
    assert diary.bell_day is not None
    item = HARMLESS[int(diary.sighting[diary.bell_day])]
    pasture = diary.names[int(diary.grazed[diary.bell_day])]
    assert day_lines(diary)[diary.bell_day] == f"Grazed {pasture}. Heard the bell. Saw a {item}."


def test_day_lines_match_the_arrays() -> None:
    diary = steady(seed=6, n_days=500)
    lines = day_lines(diary)
    assert len(lines) == 500
    for day, line in enumerate(lines):
        code = int(diary.sighting[day])
        word = "an X" if code == WOLF else f"a {HARMLESS[code]}"
        assert line == f"Grazed {diary.names[int(diary.grazed[day])]}. Saw {word}."
