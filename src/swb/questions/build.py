"""Questions in the spec's wording, rendered per vocabulary, with shuffled option order."""

from __future__ import annotations

import numpy as np

from swb.contracts import HARMLESS, Diary, Question, QuestionKey
from swb.diary.vocab import WORDS, Words
from swb.questions.truth import USED_IN, check_used_in

KEY_ORDER: tuple[QuestionKey, ...] = tuple(USED_IN)


def instructions(key: QuestionKey, words: Words) -> str:
    return {
        "risk": f"Which pasture carries the highest underlying {words.threat} risk?",
        "current": "Which pasture is most dangerous right now?",
        "act": f"Which pasture should {words.animal} graze tomorrow to stay safest?",
        "report": f"On which pasture were {words.threat_plural} seen most?",
        "decide": f"Which pasture should {words.animal} avoid tomorrow?",
        "find": "On the day you heard the bell, what did you see?",
    }[key]


def build(
    diary: Diary, keys: list[QuestionKey], replicates: int, option_seed: int
) -> dict[str, Question]:
    if replicates < 1:
        raise ValueError("replicates must be at least 1")
    questions = [
        _question(diary, key, replicate, option_seed)
        for key in keys
        for replicate in range(replicates)
    ]
    return {question.name: question for question in questions}


def _question(diary: Diary, key: QuestionKey, replicate: int, option_seed: int) -> Question:
    check_used_in(diary, key)
    base = HARMLESS if key == "find" else diary.names
    rng = np.random.default_rng(
        np.random.SeedSequence(option_seed, spawn_key=(KEY_ORDER.index(key), replicate))
    )
    return Question(
        key=key,
        replicate=replicate,
        instructions=instructions(key, WORDS[diary.spec.vocab]),
        options=[base[int(i)] for i in rng.permutation(len(base))],
    )
