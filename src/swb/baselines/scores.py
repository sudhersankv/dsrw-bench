"""Baseline answers on one diary and question, stored beside each model's answer."""

from __future__ import annotations

from swb.baselines.counter import beta_posterior
from swb.baselines.filter import bma_filter, known_filter
from swb.baselines.windows import decay_top, window_top
from swb.contracts import Diary, QuestionKey

_BASELINES = ("beta", "filter", "known_filter", "w1000", "e700")
_WINDOW_DAYS = 1000
_HALF_LIFE_DAYS = 700


def baseline_scores(
    diary: Diary, key: QuestionKey, options: list[str]
) -> dict[str, dict[str, float]]:
    """Each baseline's probability per option. `find` is not a tally question, so it is chance."""
    if key == "find":
        chance = {option: 1.0 / len(options) for option in options}
        return {name: dict(chance) for name in _BASELINES}
    safest = key == "act"
    beliefs = {
        "beta": beta_posterior(diary, lowest=safest),
        "filter": bma_filter(diary, safe=safest),
        "known_filter": known_filter(diary, safe=safest),
        "w1000": window_top(diary, _WINDOW_DAYS, lowest=safest),
        "e700": decay_top(diary, _HALF_LIFE_DAYS, lowest=safest),
    }
    index = {name: i for i, name in enumerate(diary.names)}
    return {
        name: {option: probs[index[option]] for option in options}
        for name, probs in beliefs.items()
    }
