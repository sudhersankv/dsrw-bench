"""Mock readers of known horizon. They see only the rendered state text, like a real model."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

import numpy as np

from swb.baselines.filter import NO_INFO, bma_from_codes
from swb.contracts import HARMLESS, DecisionResult, Question

KINDS = (
    "exponential",
    "window",
    "counter",
    "primacy",
    "perseverator",
    "change_filter",
    "non_reader",
    "saturating",
)

_TOKENS_PER_DAY = 8
_MOCK_WINDOW = 1 << 24
_BASE_RATE = 0.25
# Log-odds per unit of excess wolf count: the slope of a small-contrast likelihood ratio.
_LOG_ODDS_PER_WOLF = 0.5
_ORACLE_LOG_ODDS = 6.0
_PERSEVERATOR_BOOST = 5.0
_RECALL_PROBABILITY = 0.9
_RECALL_MIN_WEIGHT = 0.5
_SATURATION_WOLVES = 5.0
_SATURATION_LOG_ODDS = 4.0
_MIN_PROBABILITY = 1e-12
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_WOLF_TEXT = re.compile(r"\bwolf\b|\bX\b")


@dataclass(frozen=True)
class ParsedDiary:
    """Day arrays recovered from text, oldest first."""

    names: list[str]
    grazed: np.ndarray
    wolf: np.ndarray
    seen: np.ndarray
    bell_day: int | None
    bell_item: str | None

    @property
    def n_days(self) -> int:
        return int(self.grazed.size)


def _item_in(text: str) -> str | None:
    return next((item for item in HARMLESS if item in text), None)


def parse_diary(state: str) -> ParsedDiary:
    """Read every 'Grazed ...' entry, and the bell if one was heard."""
    names: dict[str, int] = {}
    grazed: list[int] = []
    wolf: list[bool] = []
    seen: list[bool] = []
    bell_day: int | None = None
    bell_item: str | None = None
    entry_text = ""
    for line in state.splitlines():
        if line.startswith("Grazed "):
            name, _, entry_text = line[len("Grazed ") :].partition(".")
            grazed.append(names.setdefault(name.strip(), len(names)))
            wolf.append(_WOLF_TEXT.search(entry_text) is not None)
            seen.append("Fog" not in entry_text)
        if "bell" in line and grazed:
            bell_day = len(grazed) - 1
            bell_item = _item_in(entry_text) or _item_in(line)
    return ParsedDiary(
        names=list(names),
        grazed=np.array(grazed, dtype=np.int64),
        wolf=np.array(wolf, dtype=bool),
        seen=np.array(seen, dtype=bool),
        bell_day=bell_day,
        bell_item=bell_item,
    )


def _summary_counts(state: str, options: list[str]) -> dict[str, tuple[float, float]]:
    """Visits and wolves per option from a table or tally view."""
    counts: dict[str, tuple[float, float]] = {}
    for line in state.splitlines():
        mentioned = [option for option in options if option in line]
        numbers = _NUMBER.findall(line)
        if len(mentioned) == 1 and len(numbers) >= 2:
            counts[mentioned[0]] = (float(numbers[0]), float(numbers[1]))
    return counts


def _oracle_option(state: str, options: list[str]) -> str | None:
    """The single option named by a one-line oracle view, if that is what this is."""
    for line in state.splitlines():
        mentioned = [option for option in options if option in line]
        if len(mentioned) == 1 and not _NUMBER.search(line):
            return mentioned[0]
    return None


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = np.exp(logits - logits.max())
    return shifted / shifted.sum()


class MockReader:
    """A reader whose memory is a known kernel over days; implements DecisionClient."""

    is_mock = True

    def __init__(
        self,
        name: str,
        kind: str,
        horizon: float = 1000,
        noise: float = 0.0,
        seed: int = 0,
        *,
        ladder_gain: float = 1.0,
        report_gain: float = 1.0,
        decide_gain: float = 1.0,
        window: int = _MOCK_WINDOW,
    ) -> None:
        if kind not in KINDS:
            raise ValueError(f"unknown mock kind: {kind}")
        self.name = name
        self.kind = kind
        self.horizon = horizon
        self.noise = noise
        self.seed = seed
        self.ladder_gain = ladder_gain
        # Read inside the saturating response, so one memory trace can compress differently per
        # question. `ladder_gain` acts after saturation and cancels out of any ratio.
        self.saturation_gains = {"report": report_gain, "decide": decide_gain}
        self.model_id = f"mock-{kind}"
        self.window = window

    async def decide(self, state: str, questions: dict[str, Question]) -> DecisionResult:
        diary = parse_diary(state)
        tokens = _TOKENS_PER_DAY * diary.n_days if diary.n_days else len(state) // 4 + 1
        return DecisionResult(
            probabilities={
                name: self._answer(state, diary, question) for name, question in questions.items()
            },
            input_tokens=tokens,
            latency_ms=1,
            http_status=200,
            model_version=self.model_id,
            raw={"is_mock": True, "kind": self.kind, "horizon": self.horizon},
        )

    def _answer(self, state: str, diary: ParsedDiary, question: Question) -> dict[str, float]:
        logits = (
            self._find_logits(diary, question)
            if question.key == "find"
            else self._pasture_logits(state, diary, question)
        )
        if self.noise > 0.0:
            draw = self._noise_rng(state, question).standard_normal(logits.size)
            logits = logits + self.noise * draw
        return dict(zip(question.options, _softmax(logits).tolist(), strict=True))

    def _noise_rng(self, state: str, question: Question) -> np.random.Generator:
        digest = hashlib.sha256(f"{question.name}\0{state}".encode()).digest()
        return np.random.default_rng([self.seed, int.from_bytes(digest[:8], "big")])

    def _kernel(self, n_days: int) -> np.ndarray:
        """Memory weight of each day, oldest first."""
        ages = np.arange(n_days - 1, -1, -1, dtype=float)
        match self.kind:
            case "window":
                return (ages < self.horizon).astype(float)
            case "exponential" | "saturating":
                return 0.5 ** (ages / self.horizon)
            case "primacy" | "perseverator":
                return (np.arange(n_days) < self.horizon).astype(float)
            case _:
                return np.ones(n_days)

    def _find_logits(self, diary: ParsedDiary, question: Question) -> np.ndarray:
        options = question.options
        recalled = (
            self.kind != "non_reader"
            and diary.bell_day is not None
            and diary.bell_item in options
            and self._kernel(diary.n_days)[diary.bell_day] >= _RECALL_MIN_WEIGHT
        )
        if not recalled:
            return np.zeros(len(options))
        probs = np.full(len(options), (1.0 - _RECALL_PROBABILITY) / (len(options) - 1))
        probs[options.index(diary.bell_item)] = _RECALL_PROBABILITY
        return np.log(probs)

    def _pasture_logits(self, state: str, diary: ParsedDiary, question: Question) -> np.ndarray:
        options = question.options
        lowest = question.key == "act"
        if self.kind == "non_reader":
            return np.zeros(len(options))
        if diary.n_days == 0:
            logits = (
                -self._view_logits(state, options) if lowest else self._view_logits(state, options)
            )
        elif self.kind == "change_filter":
            logits = self._filter_logits(diary, options, lowest=lowest)
        else:
            memory = self._memory_logits(
                diary, options, self.saturation_gains.get(question.key, 1.0)
            )
            logits = -memory if lowest else memory
        return logits * self.ladder_gain if question.key in ("report", "decide") else logits

    def _view_logits(self, state: str, options: list[str]) -> np.ndarray:
        """Answer from a table or oracle view, which has no diary entries to weigh."""
        counts = _summary_counts(state, options)
        if counts:
            pairs = [counts.get(option, (0.0, 0.0)) for option in options]
            return np.array([_LOG_ODDS_PER_WOLF * (w - _BASE_RATE * v) for v, w in pairs])
        named = _oracle_option(state, options)
        return np.array([_ORACLE_LOG_ODDS if option == named else 0.0 for option in options])

    def _filter_logits(self, diary: ParsedDiary, options: list[str], *, lowest: bool) -> np.ndarray:
        codes = diary.grazed * 2 + diary.wolf
        codes[~diary.seen] = NO_INFO
        hot, safe = bma_from_codes(codes)
        by_name = dict(zip(diary.names, safe if lowest else hot, strict=False))
        return np.log([max(by_name.get(option, 0.0), _MIN_PROBABILITY) for option in options])

    def _memory_logits(self, diary: ParsedDiary, options: list[str], gain: float) -> np.ndarray:
        kernel = self._kernel(diary.n_days)
        n_names = max(len(diary.names), 1)
        visits = np.bincount(
            diary.grazed[diary.seen], weights=kernel[diary.seen], minlength=n_names
        )
        wolves = np.bincount(
            diary.grazed[diary.wolf], weights=kernel[diary.wolf], minlength=n_names
        )
        by_name = dict(
            zip(diary.names, self._response(visits, wolves, gain).tolist(), strict=False)
        )
        return np.array([by_name.get(option, 0.0) for option in options])

    def _response(self, visits: np.ndarray, wolves: np.ndarray, gain: float) -> np.ndarray:
        """Log-odds per pasture; linear in the kernel so that shifts recover the horizon."""
        if self.kind == "saturating":
            return _SATURATION_LOG_ODDS * (1.0 - np.exp(-gain * wolves / _SATURATION_WOLVES))
        logits = _LOG_ODDS_PER_WOLF * (wolves - _BASE_RATE * visits)
        return logits * _PERSEVERATOR_BOOST if self.kind == "perseverator" else logits
