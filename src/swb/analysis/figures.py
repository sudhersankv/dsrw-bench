"""The five spec figures, one PNG plus the data behind it, per model."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from matplotlib.axes import Axes
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from swb.analysis.charts import (
    CONTRAST_LABELS,
    curve_points,
    ladder_curves,
    reversal_curves,
    steady_curves,
    steady_days,
)
from swb.analysis.effective import effective_evidence
from swb.analysis.harness import (
    POLICY_LABELS,
    POLICY_ORDER,
    by_world,
    matched_rows,
    score_of,
    tokens_per_decision,
    usd_per_life,
)
from swb.analysis.ladder import rk_at, shift_table
from swb.analysis.metrics import (
    CHANCE_FIND,
    DEMO_PREFIX,
    format_tokens,
    is_verbalized,
    p_correct,
    question_summary,
    seed_means,
)
from swb.analysis.reversal import crossover_m
from swb.contracts import Curve, Policy, ResultRow, Rung

FigureData = dict[str, Any]
Builder = Callable[[list[ResultRow], int, float], tuple[Figure, FigureData]]

_INK = "#0b0b0b"
_SECONDARY = "#52514e"
_MUTED = "#898781"
_GRID = "#e1e0d9"
_AXIS = "#c3c2b7"
_SURFACE = "#fcfcfb"
_CRITICAL = "#d03b3b"
_POLICY_COLORS: dict[str, str] = {
    "raw": "#2a78d6",
    "w1000": "#eb6834",
    "table": "#1baf7a",
    "e700": "#eda100",
    "oracle": "#e87ba4",
    "shuffled": "#6250d6",
}
_ALL_POLICIES: tuple[Policy, ...] = ("raw", *POLICY_ORDER)
_QUESTION_COLORS = {"report": "#2a78d6", "decide": "#eb6834"}
_RESCUE_COLOR = "#2a78d6"
_VALUE_ADDED_COLOR = "#eb6834"
_RUNGS: tuple[Rung, ...] = ("n1", "n9", "statistical")
_RUNG_LABELS = {"n1": "1 wolf", "n9": "9 wolves", "statistical": "About 30 wolves"}
_REFERENCE_STYLES = {"ref_filter": ("--", _SECONDARY), "ref_w1000": (":", _MUTED)}


def _new_figure(width: float, height: float) -> Figure:
    figure = Figure(figsize=(width, height), facecolor=_SURFACE, layout="constrained")
    FigureCanvasAgg(figure)
    return figure


def _style(ax: Axes, x_label: str, y_label: str, title: str) -> None:
    ax.set_facecolor(_SURFACE)
    ax.set_title(title, fontsize=11, color=_INK, loc="left")
    ax.set_xlabel(x_label, fontsize=9, color=_SECONDARY)
    ax.set_ylabel(y_label, fontsize=9, color=_SECONDARY)
    ax.tick_params(colors=_MUTED, labelsize=8)
    ax.grid(True, color=_GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(_AXIS)


def _no_data(ax: Axes, message: str) -> None:
    ax.text(
        0.5,
        0.5,
        message,
        ha="center",
        va="center",
        transform=ax.transAxes,
        color=_MUTED,
        fontsize=9,
    )


def _legend(ax: Axes) -> None:
    if ax.get_legend_handles_labels()[0]:
        ax.legend(frameon=False, fontsize=8, labelcolor=_SECONDARY)


def _line(ax: Axes, curve: Curve, color: str, style: str = "-") -> None:
    x = [p.x for p in curve.points]
    y = [p.y for p in curve.points]
    ax.plot(
        x,
        y,
        linestyle=style,
        color=color,
        linewidth=2,
        marker="o" if style == "-" else None,
        markersize=4.5,
        label=curve.label,
    )
    bounded = [p for p in curve.points if p.lo is not None and p.hi is not None]
    if bounded:
        ax.fill_between(
            [p.x for p in bounded],
            [p.lo for p in bounded],
            [p.hi for p in bounded],
            color=color,
            alpha=0.15,
            linewidth=0,
        )


def _curves_data(curves: list[Curve]) -> list[dict[str, Any]]:
    return [curve.model_dump() for curve in curves]


def _effective_points(
    curves: list[Curve], contrast: str, days: dict[float, int]
) -> list[tuple[float, float]]:
    raw = next((c for c in curves if c.id == f"raw_{contrast}"), None)
    if raw is None:
        return []
    points = []
    for point in raw.points:
        share = effective_evidence(point.y, days[point.x], contrast) if point.x in days else None
        if share is not None:
            points.append((point.x, share))
    return points


def _fig1_steady(rows: list[ResultRow], resamples: int, _: float) -> tuple[Figure, FigureData]:
    curves = steady_curves(rows, resamples)
    days = steady_days(rows)
    contrasts = sorted({c.id.rsplit("_", 1)[1] for c in curves}, reverse=True) or ["7pt"]
    figure = _new_figure(4.2 * len(contrasts) + 4.2, 4.0)
    axes = figure.subplots(1, len(contrasts) + 1, squeeze=False)[0]
    effective: dict[str, list[tuple[float, float]]] = {}
    for ax, contrast in zip(axes, contrasts):
        chosen = [c for c in curves if c.id.endswith(contrast)]
        _style(
            ax,
            "Diary length (tokens)",
            "Probability on the true favorite field",
            CONTRAST_LABELS.get(contrast, contrast),
        )
        for curve in chosen:
            if curve.kind == "baseline":
                _line(ax, curve, _SECONDARY, "--")
            else:
                _line(ax, curve, _POLICY_COLORS[curve.id.split("_")[0]])
        if chosen:
            ax.set_xscale("log")
            ax.set_ylim(0, 1)
            _legend(ax)
        else:
            _no_data(ax, "No steady runs")
        effective[contrast] = _effective_points(curves, contrast, days)
    panel = axes[-1]
    _style(
        panel, "Diary length (tokens)", "Share of days a counter would need", "Effective evidence"
    )
    for contrast, points in effective.items():
        if points:
            panel.plot(
                [p[0] for p in points],
                [p[1] for p in points],
                marker="o",
                markersize=4.5,
                linewidth=2,
                color=_POLICY_COLORS["raw"],
                linestyle="-" if contrast == "7pt" else "--",
                label=f"Whole diary, {CONTRAST_LABELS.get(contrast, contrast)}",
            )
    if any(effective.values()):
        panel.set_xscale("log")
        _legend(panel)
    else:
        _no_data(panel, "No effective evidence measured")
    return figure, {"curves": _curves_data(curves), "effective_evidence": effective}


def _fig2_reversal(rows: list[ResultRow], resamples: int, _: float) -> tuple[Figure, FigureData]:
    curves = reversal_curves(rows, resamples)
    contrasts = sorted({c.id.rsplit("_", 1)[1] for c in curves}, reverse=True) or ["7pt"]
    figure = _new_figure(5.0 * len(contrasts), 4.0)
    axes = figure.subplots(1, len(contrasts), squeeze=False)[0]
    crossings: dict[str, float | None] = {}
    for ax, contrast in zip(axes, contrasts):
        _style(
            ax,
            "Days since the swap",
            "New danger field minus old",
            CONTRAST_LABELS.get(contrast, contrast),
        )
        chosen = [c for c in curves if c.id.endswith(contrast)]
        if not chosen:
            _no_data(ax, "No reversal runs")
            continue
        crossings[contrast] = _draw_reversal(ax, chosen)
    return figure, {"curves": _curves_data(curves), "crossover_m": crossings}


def _draw_reversal(ax: Axes, curves: list[Curve]) -> float | None:
    crossing = None
    for curve in curves:
        prefix = "_".join(curve.id.split("_")[:2])
        if curve.kind == "baseline":
            style, color = _REFERENCE_STYLES.get(prefix, ("--", _SECONDARY))
            _line(ax, curve, color, style)
            continue
        policy = curve.id.split("_")[0]
        _line(ax, curve, _POLICY_COLORS[policy])
        if policy == "raw":
            crossing = crossover_m(curve_points(curve))
    ax.axhline(0, color=_AXIS, linewidth=1)
    ax.set_xscale("log")
    ax.set_ylim(-1, 1)
    if crossing is not None:
        ax.axvline(crossing, color=_POLICY_COLORS["raw"], linestyle=":", linewidth=1)
        ax.annotate(f"m* about {crossing:,.0f}", (crossing, -0.92), fontsize=8, color=_SECONDARY)
    _legend(ax)
    return crossing


def _find_points(rows: list[ResultRow], rung: Rung, length: int) -> list[tuple[float, float]]:
    cells: dict[int, list[ResultRow]] = {}
    for row in rows:
        if (
            row.world == "ladder"
            and row.question_key == "find"
            and row.rung == rung
            and row.length_tokens_target == length
            and row.policy == "raw"
            and row.lag_days is not None
        ):
            cells.setdefault(row.lag_days, []).append(row)
    points = []
    for lag in sorted(cells):
        means = seed_means(cells[lag], p_correct)
        points.append((float(lag), sum(means.values()) / len(means)))
    return points


def _rk_series(
    rows: list[ResultRow], rung: Rung, length: int
) -> dict[str, dict[int, float | None]]:
    series: dict[str, dict[int, float | None]] = {}
    for question in ("report", "decide"):
        table = shift_table(rows, question, rung, length)
        series[question] = {lag: rk_at(table, lag) for lag in sorted(table)}
    return series


def _ladder_panel(
    top: Axes, bottom: Axes, rows: list[ResultRow], rung: Rung, length: int, resamples: int
) -> dict[str, Any]:
    verbalized = is_verbalized(rows)
    curves = [] if verbalized else ladder_curves(rows, rung, length, resamples)
    title = f"{_RUNG_LABELS[rung]}, {format_tokens(length)} tokens"
    _style(top, "", "How much the clue changed the answer", title)
    for curve in curves:
        _line(top, curve, _QUESTION_COLORS[curve.id])
    top.axhline(0, color=_AXIS, linewidth=1)
    if curves:
        top.set_xscale("log")
        _legend(top)
    else:
        _no_data(top, "No probabilities to read here")
    find = _find_points(rows, rung, length)
    _style(bottom, "Days since the clue", "P(find)", "")
    if find:
        bottom.plot(
            [p[0] for p in find],
            [p[1] for p in find],
            color=_SECONDARY,
            linewidth=2,
            marker="o",
            markersize=4.5,
        )
        bottom.axhline(CHANCE_FIND, color=_MUTED, linestyle=":", linewidth=1)
        bottom.set_xscale("log")
        bottom.set_ylim(0, 1)
    else:
        _no_data(bottom, "No find answers")
    return {
        "rung": rung,
        "length_tokens": length,
        "curves": _curves_data(curves),
        "find": find,
        "rk": {} if verbalized else _rk_series(rows, rung, length),
    }


def _fig3_ladder(rows: list[ResultRow], resamples: int, _: float) -> tuple[Figure, FigureData]:
    ladder = [r for r in rows if r.world == "ladder" and r.policy == "raw"]
    lengths = sorted({r.length_tokens_target for r in ladder})
    rungs = [rung for rung in _RUNGS if any(r.rung == rung for r in ladder)]
    if not lengths or not rungs:
        figure = _new_figure(5, 3)
        ax = figure.subplots()
        _style(ax, "", "", "Old-clue test")
        _no_data(ax, "No old-clue runs")
        return figure, {"panels": []}
    figure = _new_figure(4.4 * len(lengths), 3.6 * len(rungs))
    grid = figure.add_gridspec(2 * len(rungs), len(lengths), height_ratios=[3, 1] * len(rungs))
    panels = []
    for r_index, rung in enumerate(rungs):
        for l_index, length in enumerate(lengths):
            top = figure.add_subplot(grid[2 * r_index, l_index])
            bottom = figure.add_subplot(grid[2 * r_index + 1, l_index], sharex=top)
            panels.append(_ladder_panel(top, bottom, ladder, rung, length, resamples))
    return figure, {"panels": panels}


def _draw_harness(ax: Axes, entries: dict[Policy, tuple[float | None, float | None]]) -> None:
    width = 0.36
    for index, (policy, (rescue, added)) in enumerate(entries.items()):
        for offset, value, color, name in (
            (-width / 2, rescue, _RESCUE_COLOR, "Rescue"),
            (width / 2, added, _VALUE_ADDED_COLOR, "Value added"),
        ):
            if value is None:
                ax.text(
                    index + offset, 0, "n/a", ha="center", va="bottom", fontsize=7, color=_MUTED
                )
            else:
                label = name if name not in ax.get_legend_handles_labels()[1] else None
                ax.bar(index + offset, value, width, color=color, label=label)
    ax.axhline(0, color=_AXIS, linewidth=1)
    ax.set_xlim(-0.75, len(entries) - 0.25)
    ax.set_xticks(
        range(len(entries)),
        [POLICY_LABELS[p] for p in entries],
        rotation=20,
        ha="right",
        fontsize=8,
    )


def _fig4_harness(rows: list[ResultRow], _: int, __: float) -> tuple[Figure, FigureData]:
    worlds = by_world(rows)
    figure = _new_figure(max(4.6 * len(worlds), 4.6), 4.0)
    axes = figure.subplots(1, max(len(worlds), 1), squeeze=False)[0]
    if not worlds:
        _style(axes[0], "", "", "Harness policies")
        _no_data(axes[0], "No harness policies run")
    for ax, (world, entries) in zip(axes, worlds.items()):
        _style(ax, "", "Change in probability on the truth", world.capitalize())
        _draw_harness(ax, entries)
        _legend(ax)
    data = {
        w: {p: {"rescue": r, "value_added": v} for p, (r, v) in e.items()}
        for w, e in worlds.items()
    }
    return figure, {"worlds": data}


def _matched_scores(rows: list[ResultRow]) -> list[dict[str, Any]]:
    """Score and tokens per policy, on the diaries that every policy in this world answered."""
    matched = matched_rows(rows)
    return [
        {
            "policy": policy,
            "label": POLICY_LABELS[policy],
            "score": score_of(matched, policy),
            "tokens_per_decision": tokens_per_decision(matched, policy),
        }
        for policy in _ALL_POLICIES
        if any(row.policy == policy for row in matched)
    ]


def _draw_scores(ax: Axes, entries: list[dict[str, Any]]) -> None:
    plotted = [e for e in entries if e["score"] is not None and e["tokens_per_decision"] > 0]
    for index, entry in enumerate(plotted):
        point = (entry["tokens_per_decision"], entry["score"])
        ax.scatter(*point, s=70, color=_POLICY_COLORS[entry["policy"]], zorder=3)
        # Alternating sides keeps labels readable when two policies land on the same spot.
        ax.annotate(
            entry["label"],
            point,
            fontsize=8,
            color=_SECONDARY,
            xytext=(5, 5 if index % 2 == 0 else -13),
            textcoords="offset points",
        )
    if plotted:
        ax.set_xscale("log")
        ax.set_ylim(0, 1.08)
        ax.margins(x=0.3)
    else:
        _no_data(ax, "No policies answered the same diaries")


def _fig5_cost(rows: list[ResultRow], _: int, price: float) -> tuple[Figure, FigureData]:
    worlds = sorted({row.world for row in rows})
    figure = _new_figure(4.4 * (len(worlds) + 1), 4.0)
    axes = figure.subplots(1, len(worlds) + 1, squeeze=False)[0]
    scores: dict[str, list[dict[str, Any]]] = {}
    for ax, world in zip(axes, worlds):
        _style(ax, "Tokens per decision", "Mean probability on the truth", world.capitalize())
        scores[world] = _matched_scores([row for row in rows if row.world == world])
        _draw_scores(ax, scores[world])
    panel = axes[-1]
    _style(panel, "Dollars per 32,000-day sheep life", "", "Cost of a life")
    costs = [
        {"policy": p, "label": POLICY_LABELS[p], "usd_per_life": usd_per_life(p, price)}
        for p in _ALL_POLICIES
        if any(row.policy == p for row in rows)
    ]
    if any(entry["usd_per_life"] > 0 for entry in costs):
        _draw_costs(panel, [entry for entry in costs if entry["usd_per_life"] > 0])
    else:
        _no_data(panel, "No price known")
    return figure, {
        "price_per_million_input_tokens": price,
        "scores_on_matched_diaries": scores,
        "costs": costs,
        "code_alone_usd_per_life": 0.0,
    }


def _draw_costs(ax: Axes, entries: list[dict[str, Any]]) -> None:
    ordered = sorted(entries, key=lambda e: e["usd_per_life"])
    for index, entry in enumerate(ordered):
        ax.scatter(
            entry["usd_per_life"], index, s=70, color=_POLICY_COLORS[entry["policy"]], zorder=3
        )
        ax.annotate(
            f"${entry['usd_per_life']:,.2f}",
            (entry["usd_per_life"], index),
            fontsize=8,
            color=_SECONDARY,
            xytext=(7, -3),
            textcoords="offset points",
        )
    ax.set_yticks(range(len(ordered)), [e["label"] for e in ordered], fontsize=8)
    ax.set_xscale("log")
    ax.margins(x=0.25)


def _save(figure: Figure, data: FigureData, base: Path, is_demo: bool, resamples: int) -> None:
    if is_demo:
        figure.suptitle(DEMO_PREFIX.strip(), color=_CRITICAL, fontsize=12, fontweight="bold")
    figure.savefig(base.with_suffix(".png"), dpi=150, facecolor=_SURFACE)
    payload = {"is_demo": is_demo, "resamples": resamples, **data}
    base.with_suffix(".json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


_BUILDERS: dict[str, Builder] = {
    "fig1_steady": _fig1_steady,
    "fig2_reversal": _fig2_reversal,
    "fig3_ladder": _fig3_ladder,
    "fig4_harness": _fig4_harness,
    "fig5_cost": _fig5_cost,
}


def write_figures(
    rows: list[ResultRow],
    model: str,
    out_dir: Path,
    is_demo: bool,
    resamples: int,
    price_per_m: float,
) -> None:
    """Write the five PNG and JSON pairs, plus per-question metric means, for one model."""
    directory = out_dir / "figures" / model
    directory.mkdir(parents=True, exist_ok=True)
    for name, builder in _BUILDERS.items():
        figure, data = builder(rows, resamples, price_per_m)
        _save(figure, data, directory / name, is_demo, resamples)
    summary = {"is_demo": is_demo, "metrics": question_summary(rows)}
    (directory / "question_metrics.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
