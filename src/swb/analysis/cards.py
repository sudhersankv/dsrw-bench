"""Builds the website data: index.json and one models/<id>.json per model."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import yaml

from swb.analysis.charts import ladder_chart, reversal_chart, steady_chart
from swb.analysis.figures import write_figures
from swb.analysis.harness import LIFE_DAYS, TOKENS_PER_DAY, harness_results
from swb.analysis.hypotheses import evaluate
from swb.analysis.metrics import DEMO_PREFIX, core_rows, format_tokens, is_verbalized
from swb.analysis.scores import flock_score, subscores
from swb.analysis.share import write_share_card, write_site_card
from swb.analysis.stats import RESAMPLES_DEMO, RESAMPLES_FINAL
from swb.contracts import Chart, ModelCard, ModelEntry, ResultRow, SiteIndex, SubScore, WorldKind

FALLBACK_PRICE_PER_M = 0.04
_ROOT = Path(__file__).resolve().parents[3]
_REGISTRY = _ROOT / "configs" / "models.yaml"
_PREREGISTRATION = _ROOT / "docs" / "PREREGISTRATION.md"
_REGISTRATION_LINK = re.compile(r"OSF registration link \| (https?://\S+) \|")


def registration_url(path: Path = _PREREGISTRATION) -> str | None:
    """The public registration link, once one has been filled in."""
    if not path.exists():
        return None
    match = _REGISTRATION_LINK.search(path.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def _load_registry() -> list[ModelEntry]:
    if not _REGISTRY.exists():
        return []
    data = yaml.safe_load(_REGISTRY.read_text(encoding="utf-8")) or {}
    return [ModelEntry.model_validate(entry) for entry in data.get("models", [])]


def _entry_lookup(models: Sequence[ModelEntry]) -> dict[str, ModelEntry]:
    entries = list(models) or _load_registry()
    return {name: entry for entry in entries for name in (entry.id, entry.model_id)}


def _per_call(rows: list[ResultRow]) -> dict[str, ResultRow]:
    """Tokens and cost belong to the request, so each call is counted once however many rows it wrote."""
    return {row.call_id: row for row in rows}


def _implied_price(calls: dict[str, ResultRow]) -> float | None:
    billed = [row for row in calls.values() if row.cost_usd is not None and row.input_tokens > 0]
    if not billed:
        return None
    return (
        sum(row.cost_usd or 0.0 for row in billed) / sum(row.input_tokens for row in billed) * 1e6
    )


def _price_per_m(entry: ModelEntry | None, calls: dict[str, ResultRow]) -> float:
    if entry is not None:
        return entry.price_input_per_m
    implied = _implied_price(calls)
    return FALLBACK_PRICE_PER_M if implied is None else implied


def _usd_spent(calls: dict[str, ResultRow], price_per_m: float) -> float:
    total = 0.0
    for row in calls.values():
        if row.cost_usd is not None:
            total += row.cost_usd
        elif not row.is_mock:
            total += row.input_tokens * price_per_m / 1_000_000
    return total


def _sentence(score: SubScore, phrase: str) -> str:
    return (
        f"{phrase}: {score.score:.0f}/100" if score.score is not None else f"{phrase}: not testable"
    )


def verdict_line(scores: list[SubScore], flock: float | None, verbalized: bool) -> str:
    """One plain line built only from the scores that exist."""
    by_id = {score.id: score for score in scores}
    parts = [
        _sentence(by_id["history"], "reads a long diary"),
        _sentence(by_id["adapt"], "follows the wolf when it moves"),
        _sentence(by_id["use"], "still acts on old clues"),
    ]
    summary = (
        "Not enough testable results for an overall score; "
        if flock is None
        else f"Overall {flock:.0f}/100; "
    )
    suffix = " Top-1 only: this model's probabilities cannot be scored finely." if verbalized else ""
    use = by_id["use"]
    if use.score is not None and use.score >= 100:
        suffix += " Old-clue score capped: no fading with distance, but the effect is small."
    return summary + "; ".join(parts) + "." + suffix


def _mark_demo(card: ModelCard) -> ModelCard:
    """A mock result is never a finding, so every sentence on a demo card says what it is."""
    subs = [s.model_copy(update={"how": DEMO_PREFIX + s.how}) for s in card.subscores]
    charts: list[Chart] = [
        c.model_copy(update={"takeaway": DEMO_PREFIX + c.takeaway}) for c in card.charts
    ]
    return card.model_copy(
        update={
            "subscores": subs,
            "charts": charts,
            "verdict_line": DEMO_PREFIX + card.verdict_line,
        }
    )


def build_card(
    rows: list[ResultRow],
    model: str,
    entry: ModelEntry | None,
    demo: bool,
    stamp: str,
    resamples: int,
) -> ModelCard:
    calls = _per_call(rows)
    verbalized = is_verbalized(rows)
    price = _price_per_m(entry, calls)
    scores = subscores(rows, resamples, verbalized)
    flock = flock_score(scores)
    card = ModelCard(
        model_id=model,
        display=entry.display if entry else model,
        is_demo=demo,
        flock_score=flock,
        subscores=scores,
        charts=[
            steady_chart(rows, resamples),
            reversal_chart(rows, resamples),
            ladder_chart(rows, resamples, verbalized),
        ],
        harness=harness_results(rows, price),
        hypotheses=evaluate(rows, resamples, verbalized),
        max_tokens_tested=max((row.length_tokens_target for row in rows), default=0),
        probabilities_source="verbalized" if verbalized else "model",
        calls=len(calls),
        input_tokens=sum(row.input_tokens for row in calls.values()),
        usd_spent=_usd_spent(calls, price),
        seeds=len({row.seed for row in rows}),
        verdict_line=verdict_line(scores, flock, verbalized),
        generated_at=stamp,
    )
    return _mark_demo(card) if demo else card


def _lengths(rows: list[ResultRow], world: WorldKind) -> set[int]:
    return {r.length_tokens_target for r in rows if r.world == world and r.policy == "raw"}


def shared_lengths(by_model: dict[str, list[ResultRow]]) -> tuple[int, dict[WorldKind, set[int]]]:
    """Largest length every model ran in every world they all ran, and each world's common set."""
    worlds: tuple[WorldKind, ...] = ("steady", "reversal", "ladder")
    common: dict[WorldKind, set[int]] = {}
    for world in worlds:
        per_model = [_lengths(rows, world) for rows in by_model.values()]
        if per_model and all(per_model):
            common[world] = set.intersection(*per_model)
    populated = [lengths for lengths in common.values() if lengths]
    shared = set.intersection(*populated) if populated else set()
    return (max(shared) if shared else 0), common


def _restricted(
    rows: list[ResultRow], shared: int, common: dict[WorldKind, set[int]]
) -> list[ResultRow]:
    return [
        r
        for r in rows
        if r.length_tokens_target <= shared and r.length_tokens_target in common.get(r.world, set())
    ]


def _index_entry(
    card: ModelCard, rows: list[ResultRow], shared: int, common: dict[WorldKind, set[int]]
) -> dict[str, object]:
    """Leaderboard numbers use the shared lengths only, so wider windows gain no extra credit."""
    scores = subscores(
        _restricted(rows, shared, common), 0, card.probabilities_source == "verbalized"
    )
    return {
        "model_id": card.model_id,
        "display": card.display,
        "flock_score": flock_score(scores),
        "subscores": {score.id: score.score for score in scores},
        "max_tokens_tested": card.max_tokens_tested,
    }


def _disclaimers(demo: bool, shared: int, unpriced: list[str]) -> list[str]:
    notes = [
        "Scores are descriptive and support no hypothesis; the confirmatory tests H1 to H3 are reported separately.",
        f"The leaderboard ranks models on shared lengths up to {format_tokens(shared)} tokens; each card scores every length that model fits, so card and leaderboard scores can differ.",
        f"Cost per life is computed for a {LIFE_DAYS:,}-day life queried daily at {TOKENS_PER_DAY} tokens per diary day.",
    ]
    if demo:
        notes.insert(
            0,
            f"{DEMO_PREFIX}These numbers come from mock readers and say nothing about any real model.",
        )
    if unpriced:
        notes.append(
            f"No price is known for {', '.join(unpriced)}; per-life costs there assume ${FALLBACK_PRICE_PER_M} per 1M input tokens."
        )
    return notes


def _safe_id(model: str) -> str:
    if not model or any(part in model for part in ("/", "\\", "..")):
        raise ValueError(f"model id is not usable as a file name: {model!r}")
    return model


def build_site(
    rows: list[ResultRow], out_dir: Path, is_demo: bool, models: Sequence[ModelEntry] = ()
) -> None:
    """Write index.json, models/<id>.json and figures/<id>/ from stored results."""
    demo = is_demo or any(row.is_mock for row in rows)
    resamples = RESAMPLES_DEMO if demo else RESAMPLES_FINAL
    usable = core_rows(rows)
    entries = _entry_lookup(models)
    by_model: dict[str, list[ResultRow]] = {}
    for row in usable:
        by_model.setdefault(_safe_id(row.model), []).append(row)
    stamp = datetime.now(UTC).isoformat()
    shared, common = shared_lengths(by_model)
    (out_dir / "models").mkdir(parents=True, exist_ok=True)
    registered = registration_url()
    listing: list[dict[str, object]] = []
    for model in sorted(by_model):
        model_rows = by_model[model]
        built = build_card(model_rows, model, entries.get(model), demo, stamp, resamples)
        entry = _index_entry(built, model_rows, shared, common)
        card = built.model_copy(
            update={
                "flock_shared": entry["flock_score"],
                "shared_length_tokens": shared,
                "registration_url": registered,
            }
        )
        (out_dir / "models" / f"{model}.json").write_text(
            card.model_dump_json(indent=2), encoding="utf-8"
        )
        price = _price_per_m(entries.get(model), _per_call(model_rows))
        write_figures(model_rows, model, out_dir, demo, resamples, price)
        write_share_card(card, out_dir)
        listing.append(entry)
    unpriced = [
        m
        for m in sorted(by_model)
        if entries.get(m) is None and _implied_price(_per_call(by_model[m])) is None
    ]
    index = SiteIndex(
        is_demo=demo,
        generated_at=stamp,
        models=listing,
        shared_length_tokens=shared,
        disclaimers=_disclaimers(demo, shared, unpriced),
        registration_url=registered,
    )
    (out_dir / "index.json").write_text(index.model_dump_json(indent=2), encoding="utf-8")
    write_site_card(index, out_dir)
