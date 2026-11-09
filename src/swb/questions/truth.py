"""Generating truth and the diary-computed diagnostic for each question."""

from __future__ import annotations

import numpy as np

from swb.contracts import FOG, HARMLESS, WOLF, Diary, QuestionKey, WorldKind

USED_IN: dict[QuestionKey, frozenset[WorldKind]] = {
    "risk": frozenset({"steady"}),
    "current": frozenset({"reversal"}),
    "act": frozenset({"steady", "reversal"}),
    "report": frozenset({"ladder"}),
    "decide": frozenset({"ladder"}),
    "find": frozenset({"ladder"}),
}


def check_used_in(diary: Diary, key: QuestionKey) -> None:
    if diary.spec.kind not in USED_IN[key]:
        raise ValueError(f"question {key!r} is not used in {diary.spec.kind} worlds")


def truth(diary: Diary, key: QuestionKey) -> str:
    check_used_in(diary, key)
    if key == "find":
        return _bell_item(diary)
    if key == "act":
        assert diary.safe is not None
        return diary.names[diary.safe]
    return diary.names[diary.hot]


def empirical(diary: Diary, key: QuestionKey) -> str | None:
    """What the diary's own counts say. None when the counts tie and name no single answer."""
    check_used_in(diary, key)
    if key == "find":
        return _bell_item(diary)
    wolves, visits = _counts(diary)
    if key == "report":
        return _unique_top(diary, wolves)
    rates = np.divide(wolves, visits, out=np.zeros(len(wolves)), where=visits > 0)
    return _unique_top(diary, -rates if key == "act" else rates)


def _bell_item(diary: Diary) -> str:
    assert diary.bell_day is not None
    return HARMLESS[int(diary.sighting[diary.bell_day])]


def _counts(diary: Diary) -> tuple[np.ndarray, np.ndarray]:
    n = len(diary.names)
    observed = diary.sighting != FOG
    visits = np.bincount(diary.grazed[observed], minlength=n).astype(float)
    wolves = np.bincount(diary.grazed[diary.sighting == WOLF], minlength=n).astype(float)
    return wolves, visits


def _unique_top(diary: Diary, values: np.ndarray) -> str | None:
    tops = np.flatnonzero(values == values.max())
    return diary.names[int(tops[0])] if len(tops) == 1 else None
