"""Rescue, value added and cost per sheep life (spec "Harness policies" and "Metrics")."""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from swb.analysis.metrics import baseline_p, p_correct
from swb.contracts import HarnessResult, Policy, ResultRow, WorldKind

LIFE_DAYS = 32_000
TOKENS_PER_DAY = 8
WINDOW_DAYS = 1_000
TALLY_TOKENS = 100
ORACLE_TOKENS = 20
POLICY_ORDER: tuple[Policy, ...] = ("w1000", "e700", "table", "oracle", "shuffled")
POLICY_LABELS: dict[Policy, str] = {
    "raw": "Whole diary",
    "w1000": "Last 1,000 days",
    "e700": "Recency-weighted tally",
    "table": "All-time tally",
    "oracle": "Told the answer",
    "shuffled": "Shuffled diary (control)",
}
PRIMARY_QUESTION: dict[WorldKind, str] = {
    "steady": "risk",
    "reversal": "current",
    "ladder": "report",
}
CODE_FOR_VIEW: dict[Policy, str] = {"w1000": "w1000", "e700": "e700", "table": "beta"}


def tokens_per_life(policy: Policy) -> int:
    """Total input tokens for a 32,000-day life queried once a day.

    The growing diary uses L^2 / 2 days read in total, the form behind the spec's $163.84.
    """
    if policy in ("raw", "shuffled"):
        return TOKENS_PER_DAY * LIFE_DAYS * LIFE_DAYS // 2
    if policy == "w1000":
        return LIFE_DAYS * WINDOW_DAYS * TOKENS_PER_DAY
    if policy in ("e700", "table"):
        return LIFE_DAYS * TALLY_TOKENS
    return LIFE_DAYS * ORACLE_TOKENS


def usd_per_life(policy: Policy, price_per_million: float) -> float:
    return tokens_per_life(policy) * price_per_million / 1_000_000


def _row_key(row: ResultRow) -> tuple[object, ...]:
    return (
        row.world,
        row.contrast,
        row.length_tokens_target,
        row.n_days,
        row.reversal_m,
        row.lag_days,
        row.rung,
        row.pair_side,
        row.question_key,
        row.seed,
        row.replicate,
    )


def _primary(rows: list[ResultRow]) -> list[ResultRow]:
    return [r for r in rows if PRIMARY_QUESTION.get(r.world) == r.question_key]


def _mean_by_seed(pairs: list[tuple[int, float]]) -> float | None:
    if not pairs:
        return None
    by_seed: dict[int, list[float]] = defaultdict(list)
    for seed, value in pairs:
        by_seed[seed].append(value)
    return float(np.mean([np.mean(values) for values in by_seed.values()]))


def rescue(rows: list[ResultRow], policy: Policy) -> float | None:
    """model(view) - model(raw), paired on the same diary and question."""
    primary = _primary(rows)
    raw = {_row_key(r): p_correct(r) for r in primary if r.policy == "raw"}
    diffs = [
        (r.seed, p_correct(r) - raw[_row_key(r)])
        for r in primary
        if r.policy == policy and _row_key(r) in raw
    ]
    return _mean_by_seed(diffs)


def _code_score(row: ResultRow, policy: Policy) -> float | None:
    """What code alone scores on this view. The oracle line names the answer outright."""
    if policy == "oracle":
        return 1.0
    code_name = CODE_FOR_VIEW.get(policy)
    return None if code_name is None else baseline_p(row, code_name)


def value_added(rows: list[ResultRow], policy: Policy) -> float | None:
    """model(view) - code(same view). None when no code baseline reads that view."""
    diffs = []
    for row in _primary(rows):
        code = _code_score(row, policy) if row.policy == policy else None
        if code is not None:
            diffs.append((row.seed, p_correct(row) - code))
    return _mean_by_seed(diffs)


def matched_rows(rows: list[ResultRow]) -> list[ResultRow]:
    """Primary rows for diaries answered under every policy here, so policies compare like for like."""
    primary = _primary(rows)
    keys_by_policy: dict[Policy, set[tuple[object, ...]]] = defaultdict(set)
    for row in primary:
        keys_by_policy[row.policy].add(_row_key(row))
    common = set.intersection(*keys_by_policy.values()) if keys_by_policy else set()
    return [row for row in primary if _row_key(row) in common]


def score_of(rows: list[ResultRow], policy: Policy) -> float | None:
    """Mean probability on the truth for one policy, across its primary questions."""
    return _mean_by_seed([(r.seed, p_correct(r)) for r in _primary(rows) if r.policy == policy])


def tokens_per_decision(rows: list[ResultRow], policy: Policy) -> int:
    per_call = {row.call_id: row.input_tokens for row in rows if row.policy == policy}
    return round(float(np.mean(list(per_call.values())))) if per_call else 0


def policies_present(rows: list[ResultRow]) -> list[Policy]:
    seen = {row.policy for row in rows}
    return [policy for policy in POLICY_ORDER if policy in seen]


def harness_results(rows: list[ResultRow], price_per_million: float) -> list[HarnessResult]:
    return [
        HarnessResult(
            policy=policy,
            label=POLICY_LABELS[policy],
            rescue=rescue(rows, policy),
            value_added=value_added(rows, policy),
            tokens_per_decision=tokens_per_decision(rows, policy),
            usd_per_life=usd_per_life(policy, price_per_million),
        )
        for policy in policies_present(rows)
    ]


def by_world(
    rows: list[ResultRow],
) -> dict[WorldKind, dict[Policy, tuple[float | None, float | None]]]:
    """(rescue, value added) for each policy, separately by world; figure 4's data."""
    worlds: dict[WorldKind, dict[Policy, tuple[float | None, float | None]]] = {}
    for world in sorted({row.world for row in rows}):
        in_world = [row for row in rows if row.world == world]
        entries = {
            p: (rescue(in_world, p), value_added(in_world, p)) for p in policies_present(in_world)
        }
        if entries:
            worlds[world] = entries
    return worlds
