"""Per-question metrics (spec "Metrics") and the row selection shared by every analysis."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable, Iterable

import numpy as np

from swb.contracts import HARMLESS, ResultRow

CLIP = 1e-6
CHANCE_PASTURE = 0.25
CHANCE_FIND = 1 / len(HARMLESS)
BELIEF_KEYS: frozenset[str] = frozenset({"risk", "current", "report", "decide", "find"})
DEMO_PREFIX = "DEMO DATA, NOT A MODEL RESULT. "

Value = Callable[[ResultRow], float | None]


def p_correct(row: ResultRow) -> float:
    return row.probabilities.get(row.truth, 0.0)


def is_verbalized(rows: Iterable[ResultRow]) -> bool:
    return any(row.probabilities_source == "verbalized" for row in rows)


def log_loss(row: ResultRow) -> float | None:
    """None for one-hot answers, whose loss would only measure the clip."""
    if row.question_key not in BELIEF_KEYS or row.probabilities_source == "verbalized":
        return None
    return -math.log(max(p_correct(row), CLIP))


def top1(row: ResultRow) -> float:
    top = max(row.option_order, key=lambda option: row.probabilities.get(option, 0.0))
    return 1.0 if top == row.truth else 0.0


def avoidance(row: ResultRow) -> float | None:
    """1 at the safest pasture, 0 at chance. None off `act` or when every pasture is equally risky."""
    if row.question_key != "act" or not row.true_rates:
        return None
    floor = min(row.true_rates.values())
    excess = {option: rate - floor for option, rate in row.true_rates.items()}
    mean_excess = sum(excess.values()) / len(excess)
    if mean_excess <= 0:
        return None
    regret = sum(row.probabilities.get(option, 0.0) * gap for option, gap in excess.items())
    return 1.0 - regret / mean_excess


def margin_new_old(row: ResultRow) -> float | None:
    """P(new) - P(old) on a reversal question."""
    if row.old_truth is None:
        return None
    return p_correct(row) - row.probabilities.get(row.old_truth, 0.0)


def baseline_p(row: ResultRow, name: str) -> float | None:
    return row.baseline_scores.get(name, {}).get(row.truth)


def baseline_margin(row: ResultRow, name: str) -> float | None:
    scores = row.baseline_scores.get(name)
    if not scores or row.old_truth is None or row.truth not in scores:
        return None
    return scores[row.truth] - scores.get(row.old_truth, 0.0)


def core_rows(rows: Iterable[ResultRow]) -> list[ResultRow]:
    """Rows eligible for scoring: answered, core format and vocabulary, pilot seeds excluded."""
    return [
        row
        for row in rows
        if row.http_status == 200
        and row.vocab == "neutral"
        and row.format == "compact"
        and not row.run_id.lower().startswith("pilot")
    ]


def seed_means(rows: Iterable[ResultRow], value: Value) -> dict[int, float]:
    """Mean of `value` per seed, so replicates of one diary never count as extra evidence."""
    collected: dict[int, list[float]] = defaultdict(list)
    for row in rows:
        result = value(row)
        if result is not None:
            collected[row.seed].append(result)
    return {seed: float(np.mean(values)) for seed, values in collected.items()}


def _mean_or_none(rows: list[ResultRow], value: Value) -> float | None:
    means = seed_means(rows, value)
    return float(np.mean(list(means.values()))) if means else None


def question_summary(rows: list[ResultRow]) -> list[dict[str, object]]:
    """Mean of each per-question metric by world, policy and question, seed-weighted."""
    groups: dict[tuple[str, str, str], list[ResultRow]] = defaultdict(list)
    for row in rows:
        groups[(row.world, row.policy, row.question_key)].append(row)
    return [
        {
            "world": world,
            "policy": policy,
            "question": question,
            "p_correct": _mean_or_none(group, p_correct) if question != "act" else None,
            "log_loss": _mean_or_none(group, log_loss),
            "avoidance": _mean_or_none(group, avoidance),
            "top1": _mean_or_none(group, top1) if question != "act" else None,
            "seeds": len({row.seed for row in group}),
        }
        for (world, policy, question), group in sorted(groups.items())
    ]


def format_tokens(tokens: float) -> str:
    return f"{tokens / 1000:g}K"
