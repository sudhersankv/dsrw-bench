"""Link-preview images: one 1200x675 PNG per model and one for the site, for X and Open Graph."""

from __future__ import annotations

from pathlib import Path

from matplotlib.axes import Axes
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

from swb.contracts import ModelCard, SiteIndex, SubScore

_WIDTH_IN, _HEIGHT_IN, _DPI = 12.0, 6.75, 100
_PAPER = "#e9f0e4"
_INK = "#1d4238"
_MUTED = "#4d6b60"
_METER = "#7fa65a"
_GROUND = "#dfe6cf"
_WOLF = "#c0267a"
_PREMISE = "An AI reads a sheep's diary and must pick the safe field."
_TITLE = "Does the Sheep Remember the Wolf?"
_DEMO_TEXT = "DEMO DATA, NOT A MODEL RESULT"
_MAX_NAME_CHARS = 42
_MAX_BOARD_ROWS = 6
_GLOSS = {
    "history": "Steady wolf, compared with a simple counter",
    "adapt": "The wolf moves, compared with a change detector",
    "recall": "Old clue reported, compared with a fresh clue",
    "use": "Old clue acted on, compared with a fresh clue",
}


def _canvas() -> tuple[Figure, Axes]:
    figure = Figure(figsize=(_WIDTH_IN, _HEIGHT_IN), dpi=_DPI, facecolor=_PAPER)
    FigureCanvasAgg(figure)
    ax = figure.add_axes((0.0, 0.0, 1.0, 1.0))
    ax.set_xlim(0, 1200)
    ax.set_ylim(675, 0)
    ax.axis("off")
    ax.add_patch(Rectangle((24, 24), 1152, 627, fill=False, edgecolor=_INK, linewidth=3))
    return figure, ax


def _header(ax: Axes) -> None:
    ax.text(58, 76, _TITLE, fontsize=23, fontweight="bold", color=_INK)
    ax.text(58, 112, _PREMISE, fontsize=15, color=_MUTED)


def _short(name: str) -> str:
    return name if len(name) <= _MAX_NAME_CHARS else f"{name[: _MAX_NAME_CHARS - 1]}..."


def _demo(ax: Axes, is_demo: bool) -> None:
    if not is_demo:
        return
    ax.text(
        600,
        360,
        _DEMO_TEXT,
        fontsize=40,
        fontweight="bold",
        color=_WOLF,
        ha="center",
        va="center",
        rotation=8,
        bbox={"facecolor": _PAPER, "edgecolor": _WOLF, "linewidth": 4, "alpha": 0.95, "pad": 14},
    )


def _meter(ax: Axes, sub: SubScore, y: float) -> None:
    ax.text(620, y, sub.label, fontsize=15.5, fontweight="bold", color=_INK)
    ax.text(620, y + 24, _GLOSS[sub.id], fontsize=11.5, color=_MUTED)
    if sub.score is None:
        ax.text(1140, y, "Not testable", fontsize=14, color=_MUTED, ha="right")
        return
    ax.add_patch(
        Rectangle((890, y - 16), 165, 22, facecolor=_GROUND, edgecolor=_INK, linewidth=1.5)
    )
    ax.add_patch(Rectangle((890, y - 16), 165 * sub.score / 100, 22, facecolor=_METER))
    ax.text(1140, y, f"{sub.score:.0f}", fontsize=22, fontweight="bold", color=_INK, ha="right")


def _flock_text(card: ModelCard) -> str:
    if card.flock_score is None:
        return "Not testable"
    return f"{card.flock_score:.0f}"


def _scope_line(card: ModelCard) -> str:
    shared = card.flock_shared
    if shared is None or card.shared_length_tokens >= card.max_tokens_tested:
        return f"Longest diary tested: {card.max_tokens_tested / 1000:g}K tokens"
    return f"{shared:.0f} on the shared {card.shared_length_tokens / 1000:g}K-token diaries used to rank models"


def write_share_card(card: ModelCard, out_dir: Path) -> None:
    figure, ax = _canvas()
    _header(ax)
    ax.text(58, 190, _short(card.display), fontsize=28, fontweight="bold", color=_INK)
    ax.text(58, 250, "Flock score", fontsize=19, fontweight="bold", color=_INK)
    big = card.flock_score is not None
    ax.text(58, 420, _flock_text(card), fontsize=130 if big else 44, fontweight="bold", color=_INK)
    ax.text(
        58, 465, "out of 100, the mean of Uses history, Adapts and Acts", fontsize=13, color=_MUTED
    )
    ax.text(58, 495, _scope_line(card), fontsize=13, color=_MUTED)
    for index, sub in enumerate(card.subscores[:4]):
        _meter(ax, sub, 215 + index * 90)
    if card.probabilities_source == "verbalized":
        ax.text(
            620,
            580,
            "Top-1 only: this model gives one answer, not probabilities.",
            fontsize=13,
            color=_MUTED,
        )
    _demo(ax, card.is_demo)
    directory = out_dir / "og"
    directory.mkdir(parents=True, exist_ok=True)
    figure.savefig(directory / f"{card.model_id}.png", dpi=_DPI, facecolor=_PAPER)


def _board_line(ax: Axes, rank: int, entry: dict[str, object], y: float) -> None:
    flock = entry.get("flock_score")
    score = f"{flock:.0f}" if isinstance(flock, (int, float)) else "Not testable"
    ax.text(58, y, f"{rank}.", fontsize=22, fontweight="bold", color=_INK)
    ax.text(105, y, _short(str(entry["display"])), fontsize=22, color=_INK)
    ax.text(1140, y, score, fontsize=26, fontweight="bold", color=_INK, ha="right")


def _ranked(entries: list[dict[str, object]]) -> list[dict[str, object]]:
    def key(entry: dict[str, object]) -> tuple[int, float]:
        flock = entry.get("flock_score")
        return (0, -float(flock)) if isinstance(flock, (int, float)) else (1, 0.0)

    return sorted(entries, key=key)


def write_site_card(index: SiteIndex, out_dir: Path) -> None:
    figure, ax = _canvas()
    _header(ax)
    ax.text(58, 175, "Flock score leaderboard", fontsize=19, fontweight="bold", color=_INK)
    for rank, entry in enumerate(_ranked(index.models)[:_MAX_BOARD_ROWS], start=1):
        _board_line(ax, rank, entry, 180 + rank * 62)
    if not index.models:
        ax.text(58, 330, "No results yet.", fontsize=26, color=_MUTED)
    _demo(ax, index.is_demo)
    directory = out_dir / "og"
    directory.mkdir(parents=True, exist_ok=True)
    figure.savefig(directory / "site.png", dpi=_DPI, facecolor=_PAPER)
