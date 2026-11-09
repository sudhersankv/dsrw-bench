"""Turn a Diary into the exact text a model reads."""

from __future__ import annotations

import hashlib

import numpy as np

from swb.contracts import FOG, HARMLESS, WOLF, Diary
from swb.diary.vocab import WORDS

BELL_TEXT = "Heard the bell."


def header(diary: Diary) -> str:
    words = WORDS[diary.spec.vocab]
    pastures = ", ".join(diary.names[i] for i in diary.header_order)
    intro = (
        f"This is the diary of {words.animal}. Each day {words.animal} grazed one pasture "
        "and wrote what it saw there. Entries are oldest first."
    )
    lines = [
        intro,
        f"The pastures are: {pastures}.",
        f"{words.the_threat} is harmful.",
    ]
    if diary.spec.kind == "ladder":
        lines.append(f"{words.the_threat}'s habits never change.")
    return "\n".join(lines)


def day_lines(diary: Diary) -> list[str]:
    outcome = _outcome_text(diary)
    lines = [
        f"Grazed {diary.names[pasture]}. {outcome[code]}"
        for pasture, code in zip(diary.grazed.tolist(), diary.sighting.tolist(), strict=True)
    ]
    if diary.bell_day is not None:
        day = diary.bell_day
        lines[day] = (
            f"Grazed {diary.names[int(diary.grazed[day])]}. {BELL_TEXT} "
            + outcome[int(diary.sighting[day])]
        )
    return lines


def _outcome_text(diary: Diary) -> dict[int, str]:
    words = WORDS[diary.spec.vocab]
    outcome = {i: f"Saw a {item}." for i, item in enumerate(HARMLESS)}
    outcome[WOLF] = f"Saw {words.threat_with_article}."
    outcome[FOG] = "Fog."
    return outcome


def render(diary: Diary) -> str:
    return "\n".join([header(diary), *day_lines(diary)])


def sha256(diary: Diary) -> str:
    return hashlib.sha256(render(diary).encode("utf-8")).hexdigest()


def shuffled(diary: Diary) -> Diary:
    """Same days in a random order. Counts are preserved and the bell moves with its day."""
    order = _shuffle_rng(diary).permutation(diary.spec.n_days)
    bell_day = None
    if diary.bell_day is not None:
        bell_day = int(np.flatnonzero(order == diary.bell_day)[0])
    return diary.model_copy(
        update={
            "grazed": diary.grazed[order],
            "sighting": diary.sighting[order],
            "bell_day": bell_day,
        }
    )


def _shuffle_rng(diary: Diary) -> np.random.Generator:
    # Diary does not carry root_seed, so entropy comes from its sightings. Both sides of a swapped
    # pair have identical sightings, so they get the same permutation and still differ only by
    # the labels inside the block.
    digest = hashlib.sha256(diary.sighting.tobytes()).digest()
    entropy = int.from_bytes(digest[:16], "big")
    return np.random.default_rng(np.random.SeedSequence(entropy, spawn_key=(diary.seed,)))
