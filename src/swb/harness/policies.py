"""What the model sees under each harness policy. Tables always follow any diary portion."""

from __future__ import annotations

from swb.contracts import Diary, Policy, View
from swb.diary.lengths import TOKENS_PER_DAY
from swb.diary.render import day_lines, header, render, shuffled
from swb.diary.vocab import WORDS
from swb.harness.tally import E700_HALF_LIFE, PastureTally, all_time, e700

WINDOW_DAYS = 1000
CHARS_PER_TOKEN = 4


def apply(policy: Policy, diary: Diary) -> View:
    if policy == "raw":
        return _diary_view(policy, render(diary), diary, diary.spec.n_days)
    if policy == "w1000":
        return _window_view(diary)
    if policy == "e700":
        return _table_view(policy, diary, e700(diary), _e700_title(diary), decimals=1)
    if policy == "table":
        return _table_view(policy, diary, all_time(diary), _all_time_title(diary), decimals=0)
    if policy == "oracle":
        return _text_view(policy, f"Current highest-risk pasture: {diary.names[diary.hot]}.")
    if policy == "shuffled":
        return _shuffled_view(diary)
    raise ValueError(f"unknown policy {policy!r}")


def _window_view(diary: Diary) -> View:
    if diary.spec.n_days <= WINDOW_DAYS:
        raise ValueError(f"w1000 is omitted for diaries of {WINDOW_DAYS} days or fewer")
    lines = day_lines(diary)[-WINDOW_DAYS:]
    return _diary_view("w1000", "\n".join([header(diary), *lines]), diary, WINDOW_DAYS)


def _shuffled_view(diary: Diary) -> View:
    if diary.spec.kind != "ladder":
        raise ValueError("the shuffled policy applies only to ladder diaries")
    return _diary_view("shuffled", render(shuffled(diary)), diary, diary.spec.n_days)


def _diary_view(policy: Policy, text: str, diary: Diary, days: int) -> View:
    est = int(days * TOKENS_PER_DAY) + len(header(diary)) // CHARS_PER_TOKEN
    return View(policy=policy, text=text, est_tokens=est)


def _text_view(policy: Policy, text: str) -> View:
    return View(policy=policy, text=text, est_tokens=len(text) // CHARS_PER_TOKEN)


def _table_view(
    policy: Policy, diary: Diary, tallies: list[PastureTally], title: str, decimals: int
) -> View:
    rows = [_table_row(tallies[i], decimals) for i in diary.header_order]
    return _text_view(policy, "\n".join([header(diary), "", title, *rows]))


def _table_row(tally: PastureTally, decimals: int) -> str:
    return (
        f"{tally.name}: visits {tally.visits:.{decimals}f}, "
        f"sightings {tally.wolves:.{decimals}f}, rate {tally.rate:.4f}"
    )


def _all_time_title(diary: Diary) -> str:
    return (
        f"All days so far, per pasture: visits, {WORDS[diary.spec.vocab].threat} sightings, rate."
    )


def _e700_title(diary: Diary) -> str:
    threat = WORDS[diary.spec.vocab].threat
    return (
        f"Discounted per pasture: visits, {threat} sightings, rate. "
        f"Each day's weight halves every {E700_HALF_LIFE:.0f} days back."
    )
