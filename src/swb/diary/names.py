"""Pronounceable non-word pasture names."""

from __future__ import annotations

from itertools import product

import numpy as np

# Each name is onset + vowel + medial cluster + ending. The medial clusters almost never occur
# inside English words, which is what keeps every combination a non-word. The inventories exclude
# h, w and f, so no name can spell "hot", "wolf", "fog" or any harmless item.
ONSETS = tuple("bdgklmnprstvz")
VOWELS = tuple("aeiou")
MEDIALS = ("kv", "zb", "mz", "vk", "zk", "bz")
ENDINGS = ("or", "el", "im", "ot", "un", "ek", "ar", "in", "ul")

NAME_POOL: tuple[str, ...] = tuple(
    (onset + vowel + medial + ending).capitalize()
    for onset, vowel, medial, ending in product(ONSETS, VOWELS, MEDIALS, ENDINGS)
)

N_PASTURES = 4


def pasture_names(rng: np.random.Generator) -> list[str]:
    """Four distinct non-words, drawn uniformly from the pool."""
    picks = rng.choice(len(NAME_POOL), size=N_PASTURES, replace=False)
    return [NAME_POOL[int(i)] for i in picks]
