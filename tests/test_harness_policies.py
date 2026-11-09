"""Harness views: what each policy hands the model, and the code-made tallies."""

from __future__ import annotations

import numpy as np
import pytest

from swb.contracts import FOG, WOLF, LadderSpec, Policy, WorldSpec
from swb.diary.render import day_lines, header, render, shuffled
from swb.diary.worlds import generate
from swb.harness.policies import apply
from swb.harness.tally import all_time, e700


def steady(n_days: int = 3000, seed: int = 1):
    return generate(WorldSpec(kind="steady", n_days=n_days, contrast="7pt"), seed)


def ladder(seed: int = 1):
    spec = WorldSpec(kind="ladder", n_days=2000, ladder=LadderSpec(rung="n9", lag_days=100))
    return generate(spec, seed)


def test_raw_is_the_rendered_diary() -> None:
    diary = steady()
    view = apply("raw", diary)
    assert view.policy == "raw"
    assert view.text == render(diary)
    assert view.est_tokens == pytest.approx(3000 * 8, rel=0.02)


def test_w1000_keeps_the_header_and_the_last_thousand_days() -> None:
    diary = steady()
    view = apply("w1000", diary)
    lines = view.text.split("\n")
    head_len = len(header(diary).split("\n"))
    assert lines[:head_len] == header(diary).split("\n")
    assert lines[head_len:] == day_lines(diary)[-1000:]
    assert view.est_tokens == pytest.approx(8000, rel=0.02)


@pytest.mark.parametrize("n_days", [125, 1000])
def test_w1000_is_omitted_for_short_diaries(n_days: int) -> None:
    with pytest.raises(ValueError, match="omitted"):
        apply("w1000", steady(n_days))


def test_w1000_applies_just_above_the_threshold() -> None:
    assert len(apply("w1000", steady(1001)).text.split("\n")) == 1000 + len(
        header(steady(1001)).split("\n")
    )


def test_table_counts_match_the_arrays() -> None:
    diary = steady()
    tallies = all_time(diary)
    assert sum(t.visits for t in tallies) == 3000
    for pasture, tally in enumerate(tallies):
        here = diary.grazed == pasture
        assert tally.name == diary.names[pasture]
        assert tally.visits == here.sum()
        assert tally.wolves == (diary.sighting[here] == WOLF).sum()
        assert tally.rate == pytest.approx(tally.wolves / tally.visits)


def test_fog_days_are_not_visits() -> None:
    tallies = all_time(ladder())
    assert sum(t.visits for t in tallies) == 100
    assert sum(t.wolves for t in tallies) == 9


def test_e700_weights_halve_every_700_days() -> None:
    diary = steady(n_days=1401)
    diary.grazed[:] = 0
    diary.sighting[:] = 0
    diary.grazed[0] = 1  # 1,400 days before the end: two half-lives
    diary.grazed[700] = 2  # one half-life
    diary.grazed[-1] = 3  # today
    tallies = e700(diary)
    assert tallies[1].visits == pytest.approx(0.25)
    assert tallies[2].visits == pytest.approx(0.5)
    assert tallies[3].visits == pytest.approx(1.0)


def test_e700_counts_recent_wolves_more_than_all_time() -> None:
    diary = steady(n_days=4000)
    diary.sighting[:] = 0
    diary.sighting[-1] = WOLF
    pasture = int(diary.grazed[-1])
    assert e700(diary)[pasture].wolves == pytest.approx(1.0)
    assert e700(diary)[pasture].rate > all_time(diary)[pasture].rate


@pytest.mark.parametrize("policy", ["table", "e700"])
def test_tables_follow_the_header_in_header_order(policy: Policy) -> None:
    diary = steady()
    text = apply(policy, diary).text
    assert text.startswith(header(diary))
    table = text[len(header(diary)) :]
    positions = [table.index(diary.names[i]) for i in diary.header_order]
    assert positions == sorted(positions)
    assert "Grazed" not in text


def test_table_view_prints_the_real_counts() -> None:
    diary = steady()
    text = apply("table", diary).text
    for tally in all_time(diary):
        assert f"{tally.name}: visits {tally.visits:.0f}, sightings {tally.wolves:.0f}" in text


def test_tables_are_about_a_hundred_tokens() -> None:
    diary = steady()
    assert 30 <= apply("table", diary).est_tokens <= 150
    assert 30 <= apply("e700", diary).est_tokens <= 150


def test_oracle_is_one_line_naming_the_current_hot_pasture() -> None:
    diary = generate(
        WorldSpec(kind="reversal", n_days=2000, contrast="high", reversal_m=50), seed=2
    )
    view = apply("oracle", diary)
    assert "\n" not in view.text
    assert diary.names[diary.hot] in view.text
    assert not any(diary.names[i] in view.text for i in range(4) if i != diary.hot)
    assert view.est_tokens <= 20


def test_shuffled_view_is_the_shuffled_diary() -> None:
    diary = ladder()
    view = apply("shuffled", diary)
    assert view.text == render(shuffled(diary))
    assert view.text != render(diary)


def test_shuffled_policy_is_ladder_only() -> None:
    with pytest.raises(ValueError, match="ladder"):
        apply("shuffled", steady())


@pytest.mark.parametrize("policy", ["raw", "table", "e700"])
def test_views_on_ladder_do_not_leak_or_crash(policy: Policy) -> None:
    text = apply(policy, ladder()).text
    assert "hot" not in text.lower()
    assert "dangerous" not in text.lower()


def test_views_preserve_fog_in_raw_ladder_text() -> None:
    diary = ladder()
    fog_days = int((diary.sighting == FOG).sum())
    assert apply("raw", diary).text.count(" Fog.") == fog_days
    assert np.sum(diary.sighting == WOLF) == 9
