"""Questions, truth, and the independent recount of the rendered diary."""

from __future__ import annotations

import re
from collections import Counter

import numpy as np
import pytest

from swb.contracts import HARMLESS, Diary, LadderSpec, QuestionKey, WorldSpec
from swb.diary.render import render
from swb.diary.worlds import generate
from swb.questions.build import build
from swb.questions.truth import empirical, truth

LINE = re.compile(r"^Grazed (\w+)\. (?:(Heard the bell\.) )?(?:Saw an? (\w+)\.|(Fog\.))$")


def parse(text: str) -> list[tuple[str, str | None, bool]]:
    """Read (pasture, what was seen, bell) straight from the text, sharing nothing with render."""
    days = []
    for line in text.split("\n"):
        match = LINE.match(line)
        if match:
            pasture, bell, seen, _fog = match.groups()
            days.append((pasture, seen, bell is not None))
    return days


def recount(diary: Diary, key: QuestionKey) -> str | None:
    days = parse(render(diary))
    threat = {"neutral": "X", "natural": "wolf"}[diary.spec.vocab]
    if key == "find":
        return next(seen for _, seen, bell in days if bell)
    wolves: Counter[str] = Counter(p for p, seen, _ in days if seen == threat)
    visits: Counter[str] = Counter(p for p, seen, _ in days if seen is not None)
    if key == "report":
        scores = {name: float(wolves[name]) for name in diary.names}
    else:
        sign = -1.0 if key == "act" else 1.0
        scores = {
            name: sign * (wolves[name] / visits[name] if visits[name] else 0.0)
            for name in diary.names
        }
    top = max(scores.values())
    winners = [name for name, score in scores.items() if score == top]
    return winners[0] if len(winners) == 1 else None


def steady(seed: int, n_days: int = 1500, vocab: str = "neutral") -> Diary:
    return generate(WorldSpec(kind="steady", n_days=n_days, contrast="high", vocab=vocab), seed)


def reversal(seed: int, m: int = 300) -> Diary:
    return generate(WorldSpec(kind="reversal", n_days=1500, contrast="high", reversal_m=m), seed)


def ladder(seed: int, rung: str = "statistical", side: str = "A", vocab: str = "neutral") -> Diary:
    spec = WorldSpec(
        kind="ladder",
        n_days=1500,
        vocab=vocab,
        ladder=LadderSpec(rung=rung, lag_days=100, pair_side=side),
    )
    return generate(spec, seed)


def test_parser_reads_every_day() -> None:
    assert len(parse(render(steady(1)))) == 1500
    assert len(parse(render(ladder(1)))) == 1500


@pytest.mark.parametrize("seed", range(20))
@pytest.mark.parametrize("key", ["risk", "act"])
def test_steady_empirical_matches_independent_recount(seed: int, key: QuestionKey) -> None:
    diary = steady(seed)
    assert empirical(diary, key) == recount(diary, key)


@pytest.mark.parametrize("seed", range(20))
@pytest.mark.parametrize("key", ["current", "act"])
def test_reversal_empirical_matches_independent_recount(seed: int, key: QuestionKey) -> None:
    diary = reversal(seed)
    assert empirical(diary, key) == recount(diary, key)


@pytest.mark.parametrize("seed", range(20))
@pytest.mark.parametrize("rung", ["n1", "n9", "statistical"])
@pytest.mark.parametrize("key", ["report", "decide", "find"])
def test_ladder_empirical_matches_independent_recount(
    seed: int, rung: str, key: QuestionKey
) -> None:
    diary = ladder(seed, rung)
    assert empirical(diary, key) == recount(diary, key)


def test_recount_works_on_the_natural_vocabulary() -> None:
    diary = ladder(3, vocab="natural")
    assert empirical(diary, "report") == recount(diary, "report")


@pytest.mark.parametrize("seed", range(30))
def test_truth_matches_generator_parameters(seed: int) -> None:
    diary = steady(seed)
    assert diary.tomorrow_rates is not None
    rates = np.array(diary.tomorrow_rates)
    assert truth(diary, "risk") == diary.names[int(rates.argmax())]
    assert truth(diary, "act") == diary.names[int(rates.argmin())]


@pytest.mark.parametrize("seed", range(30))
def test_reversal_truth_is_the_new_hot_pasture(seed: int) -> None:
    diary = reversal(seed)
    assert diary.tomorrow_rates is not None
    rates = np.array(diary.tomorrow_rates)
    assert truth(diary, "current") == diary.names[int(rates.argmax())]
    assert truth(diary, "act") == diary.names[int(rates.argmin())]
    assert truth(diary, "current") != diary.names[diary.old_hot]


@pytest.mark.parametrize("side", ["A", "B"])
def test_ladder_truth_is_the_target_of_that_side(side: str) -> None:
    diary = ladder(4, "n9", side)
    assert truth(diary, "report") == diary.names[diary.hot]
    assert truth(diary, "decide") == diary.names[diary.hot]
    assert empirical(diary, "report") == diary.names[diary.hot]


def test_swapped_sides_have_different_targets() -> None:
    assert truth(ladder(4, "n9", "A"), "report") != truth(ladder(4, "n9", "B"), "report")


def test_find_truth_is_the_bell_days_item() -> None:
    diary = ladder(7)
    assert diary.bell_day is not None
    assert truth(diary, "find") == HARMLESS[int(diary.sighting[diary.bell_day])]
    assert truth(diary, "find") in HARMLESS


@pytest.mark.parametrize(
    ("make", "key"),
    [
        (lambda: steady(1), "current"),
        (lambda: steady(1), "report"),
        (lambda: reversal(1), "risk"),
        (lambda: ladder(1), "act"),
    ],
)
def test_questions_outside_their_world_are_rejected(make, key: QuestionKey) -> None:
    diary = make()
    with pytest.raises(ValueError, match="not used"):
        truth(diary, key)
    with pytest.raises(ValueError, match="not used"):
        build(diary, [key], 1, 0)


def test_build_names_are_key_and_replicate() -> None:
    questions = build(steady(2), ["risk", "act"], 2, 0)
    assert set(questions) == {"risk__r0", "risk__r1", "act__r0", "act__r1"}
    assert questions["act__r1"].replicate == 1


def test_build_uses_spec_wording_in_the_neutral_vocabulary() -> None:
    questions = build(steady(2), ["risk", "act"], 1, 0)
    assert questions["risk__r0"].instructions == (
        "Which pasture carries the highest underlying X risk?"
    )
    assert questions["act__r0"].instructions == (
        "Which pasture should the agent graze tomorrow to stay safest?"
    )


def test_build_uses_spec_wording_in_the_natural_vocabulary() -> None:
    questions = build(steady(2, vocab="natural"), ["risk", "act"], 1, 0)
    assert questions["risk__r0"].instructions == (
        "Which pasture carries the highest underlying wolf risk?"
    )
    assert questions["act__r0"].instructions == (
        "Which pasture should the sheep graze tomorrow to stay safest?"
    )


def test_build_ladder_wording_and_options() -> None:
    natural = build(ladder(2, vocab="natural"), ["report", "decide", "find"], 1, 0)
    assert natural["report__r0"].instructions == "On which pasture were wolves seen most?"
    assert natural["decide__r0"].instructions == "Which pasture should the sheep avoid tomorrow?"
    assert natural["find__r0"].instructions == "On the day you heard the bell, what did you see?"
    assert sorted(natural["find__r0"].options) == sorted(HARMLESS)
    assert sorted(natural["report__r0"].options) == sorted(ladder(2).names)
    neutral = build(ladder(2), ["report", "decide"], 1, 0)
    assert neutral["report__r0"].instructions == "On which pasture were Xs seen most?"
    assert neutral["decide__r0"].instructions == "Which pasture should the agent avoid tomorrow?"


def test_current_question_is_the_only_most_dangerous_text() -> None:
    questions = build(reversal(2), ["current"], 1, 0)
    assert questions["current__r0"].instructions == "Which pasture is most dangerous right now?"


def test_option_order_differs_across_replicates_and_replays() -> None:
    diary = steady(5)
    first = build(diary, ["risk"], 5, option_seed=9)
    again = build(diary, ["risk"], 5, option_seed=9)
    assert {k: v.options for k, v in first.items()} == {k: v.options for k, v in again.items()}
    assert len({tuple(q.options) for q in first.values()}) > 1


def test_every_pasture_appears_first_across_option_seeds() -> None:
    diary = steady(5)
    firsts = {build(diary, ["risk"], 1, option_seed=s)["risk__r0"].options[0] for s in range(80)}
    assert firsts == set(diary.names)


def test_pair_sides_share_option_order() -> None:
    a = build(ladder(6, "n9", "A"), ["report"], 3, option_seed=4)
    b = build(ladder(6, "n9", "B"), ["report"], 3, option_seed=4)
    assert {k: v.options for k, v in a.items()} == {k: v.options for k, v in b.items()}


def test_build_requires_a_replicate() -> None:
    with pytest.raises(ValueError):
        build(steady(1), ["risk"], 0, 0)
