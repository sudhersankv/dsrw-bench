"""Run vocabularies. Neutral removes the prior meaning carried by "sheep" and "wolf"."""

from __future__ import annotations

from dataclasses import dataclass

from swb.contracts import Vocab


@dataclass(frozen=True)
class Words:
    animal: str  # "the sheep"
    threat: str  # bare noun, used in "wolf risk"
    threat_plural: str
    threat_with_article: str  # as written after "Saw"
    the_threat: str  # capitalised, starts a sentence


WORDS: dict[Vocab, Words] = {
    "neutral": Words("the agent", "X", "Xs", "an X", "The X"),
    "natural": Words("the sheep", "wolf", "wolves", "a wolf", "The wolf"),
}
