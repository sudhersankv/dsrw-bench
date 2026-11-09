"""Mock readers: they get only rendered text, and their horizon must be recoverable."""

from __future__ import annotations

import asyncio
import time

import numpy as np
import pytest

from swb.baselines.mock_readers import KINDS, MockReader, parse_diary
from swb.contracts import CONTRASTS, HARMLESS, Question

NAMES = ["Darro", "Kell", "Mib", "Sule"]
HEADER = "Pastures: Sule, Mib, Kell, Darro.\nEntries are oldest first. X is harmful.\n"


def entry(pasture: int, text: str) -> str:
    return f"Grazed {NAMES[pasture]}. {text}"


def world_text(rates: np.ndarray, rng: np.random.Generator) -> str:
    """Diary text where `rates` is (days, 4), in the neutral vocabulary."""
    n_days = rates.shape[0]
    grazed = rng.integers(0, 4, n_days)
    wolf = rng.random(n_days) < rates[np.arange(n_days), grazed]
    items = rng.integers(0, 7, n_days)
    lines = [
        entry(int(p), "Saw X." if w else f"Saw a {HARMLESS[i]}.")
        for p, w, i in zip(grazed, wolf, items, strict=True)
    ]
    return HEADER + "\n".join(lines) + "\n"


def steady_text(contrast: str, n_days: int, seed: int) -> str:
    hot, middle, safe = CONTRASTS[contrast]
    rates = np.tile([hot, safe, middle, middle], (n_days, 1))
    return world_text(rates, np.random.default_rng(seed))


def reversal_text(contrast: str, n_days: int, m: int, seed: int) -> str:
    hot, middle, safe = CONTRASTS[contrast]
    rates = np.tile([hot, safe, middle, middle], (n_days, 1))
    rates[n_days - m :] = [safe, hot, middle, middle]
    return world_text(rates, np.random.default_rng([seed, m]))


def ladder_text(lag: int, side: str, seed: int, n_days: int = 2000) -> str:
    """Statistical rung with a bell at mid-block; side B swaps pastures 0 and 1 in the block."""
    rng = np.random.default_rng([seed, lag])
    grazed = rng.integers(0, 4, n_days)
    start = n_days - lag - 100
    block = np.arange(start, n_days - lag)
    wolf = rng.random(block.size) < np.where(grazed[block] == 0, 0.6, 0.2)
    items = rng.integers(0, 7, block.size)
    bell = start + 50
    wolf[50] = False
    if side == "B":
        grazed[block] = np.select([grazed[block] == 0, grazed[block] == 1], [1, 0], grazed[block])
    lines = [entry(int(p), "Fog.") for p in grazed]
    for offset, day in enumerate(block):
        text = "Saw X." if wolf[offset] else f"Saw a {HARMLESS[items[offset]]}."
        lines[day] = entry(int(grazed[day]), f"Heard the bell. {text}" if day == bell else text)
    return HEADER + "\n".join(lines) + "\n"


def question(key: str, options: list[str] | None = None) -> dict[str, Question]:
    q = Question(key=key, instructions="Pick one.", options=options or NAMES)  # type: ignore[arg-type]
    return {q.name: q}


def answer(
    reader: MockReader, state: str, key: str, options: list[str] | None = None
) -> dict[str, float]:
    questions = question(key, options)
    result = asyncio.run(reader.decide(state, questions))
    return result.probabilities[next(iter(questions))]


def shift(reader: MockReader, key: str, lag: int, seed: int) -> float:
    a = answer(reader, ladder_text(lag, "A", seed), key)
    b = answer(reader, ladder_text(lag, "B", seed), key)
    return 0.5 * (
        (np.log(a["Darro"]) - np.log(a["Kell"])) - (np.log(b["Darro"]) - np.log(b["Kell"]))
    )


def mean_shift(reader: MockReader, key: str, lag: int, seeds: int = 30) -> float:
    return float(np.mean([shift(reader, key, lag, seed) for seed in range(seeds)]))


def test_parse_diary_reads_days_wolves_fog_and_bell() -> None:
    state = HEADER + "\n".join(
        [
            entry(0, "Saw X."),
            entry(1, "Fog."),
            entry(2, "Heard the bell. Saw a heron."),
            entry(3, "Saw a wolf."),
        ]
    )
    parsed = parse_diary(state)
    assert parsed.n_days == 4
    assert parsed.wolf.tolist() == [True, False, False, True]
    assert parsed.seen.tolist() == [True, False, True, True]
    assert parsed.bell_day == 2
    assert parsed.bell_item == "heron"


@pytest.mark.parametrize("kind", KINDS)
def test_every_kind_returns_a_distribution_over_the_options(kind: str) -> None:
    reader = MockReader("m", kind, 300, 0.1, 1)
    probs = answer(reader, steady_text("high", 1200, 1), "risk")
    assert list(probs) == NAMES
    assert sum(probs.values()) == pytest.approx(1.0)
    assert all(p > 0 for p in probs.values())


def test_results_are_flagged_as_mock() -> None:
    reader = MockReader("m", "counter", 100, 0.0, 1)
    result = asyncio.run(reader.decide(steady_text("high", 50, 1), question("risk")))
    assert result.raw["is_mock"] is True
    assert reader.is_mock
    assert result.input_tokens == 400


def test_unknown_kind_is_rejected() -> None:
    with pytest.raises(ValueError):
        MockReader("m", "psychic", 1, 0.0, 0)


def test_counter_picks_the_hot_pasture_and_act_picks_the_safe_one() -> None:
    reader = MockReader("m", "counter", 1000, 0.0, 1)
    state = steady_text("high", 2000, 2)
    risk = answer(reader, state, "risk")
    act = answer(reader, state, "act")
    assert max(risk, key=risk.__getitem__) == "Darro"
    assert max(act, key=act.__getitem__) == "Kell"


def test_non_reader_is_uniform() -> None:
    probs = answer(MockReader("m", "non_reader", 1, 0.0, 0), steady_text("high", 800, 1), "risk")
    assert all(p == pytest.approx(0.25) for p in probs.values())


def test_noise_is_seeded_and_changes_with_the_seed() -> None:
    state = steady_text("7pt", 300, 1)
    first = answer(MockReader("m", "counter", 1, 0.5, 11), state, "risk")
    again = answer(MockReader("m", "counter", 1, 0.5, 11), state, "risk")
    other = answer(MockReader("m", "counter", 1, 0.5, 12), state, "risk")
    assert first == again
    assert first != other


def crossover(reader: MockReader, contrast: str, n_days: int, seeds: int) -> float | None:
    ms = np.unique(np.geomspace(6, 0.7 * n_days, 9).round().astype(int)).tolist()
    gaps = []
    for m in ms:
        diffs = []
        for seed in range(seeds):
            probs = answer(reader, reversal_text(contrast, n_days, m, seed), "current")
            diffs.append(probs["Kell"] - probs["Darro"])
        gaps.append(float(np.mean(diffs)))
    for i in range(len(ms) - 1):
        if gaps[i] < 0 <= gaps[i + 1]:
            fraction = -gaps[i] / (gaps[i + 1] - gaps[i])
            return float(np.exp(np.log(ms[i]) + fraction * np.log(ms[i + 1] / ms[i])))
    return None


def test_window_reader_crossover_recovers_half_its_horizon_at_both_contrasts() -> None:
    reader = MockReader("w", "window", 1000, 0.0, 1)
    low = crossover(reader, "7pt", 4000, 40)
    high = crossover(reader, "high", 4000, 12)
    assert low is not None and high is not None
    assert 300 < high < 800
    assert 1 / 1.6 < low / high < 1.6


def test_full_memory_reader_crosses_below_seventy_percent_of_length() -> None:
    n_days = 4000
    m_star = crossover(MockReader("c", "counter", 1, 0.0, 1), "high", n_days, 12)
    assert m_star is not None
    assert m_star < 0.7 * n_days


def test_perseverator_never_crosses() -> None:
    assert crossover(MockReader("p", "perseverator", 500, 0.0, 1), "high", 4000, 10) is None


def test_change_filter_adapts_quickly_at_high_contrast() -> None:
    reader = MockReader("f", "change_filter", 1, 0.0, 1)
    probs = answer(reader, reversal_text("high", 4000, 200, 3), "current")
    assert probs["Kell"] > 0.9


def test_window_reader_ladder_shift_stops_at_its_horizon() -> None:
    reader = MockReader("w", "window", 500, 0.0, 1)
    assert mean_shift(reader, "report", 10) > 1.0
    assert mean_shift(reader, "report", 300) == pytest.approx(
        mean_shift(reader, "report", 10), rel=0.25
    )
    assert mean_shift(reader, "report", 600) == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize("half_life", [150.0, 600.0])
def test_exponential_reader_ladder_shift_recovers_its_half_life(half_life: float) -> None:
    reader = MockReader("e", "exponential", half_life, 0.0, 1)
    near = mean_shift(reader, "report", 1, 60)
    at_half_life = mean_shift(reader, "report", int(half_life), 60)
    assert at_half_life / near == pytest.approx(0.5, abs=0.12)


def test_primacy_reader_only_sees_the_earliest_days() -> None:
    reader = MockReader("p", "primacy", 400, 0.0, 1)
    early = shift(reader, "report", 1890, 2)
    assert abs(early) > 0.5
    assert shift(reader, "report", 10, 2) == pytest.approx(0.0, abs=1e-9)


def test_find_is_recalled_inside_the_horizon_and_chance_outside() -> None:
    reader = MockReader("w", "window", 400, 0.0, 1)
    near_state = ladder_text(10, "A", 3)
    far_state = ladder_text(1500, "A", 3)
    near = answer(reader, near_state, "find", HARMLESS)
    far = answer(reader, far_state, "find", HARMLESS)
    assert max(near.values()) == pytest.approx(0.9, abs=1e-6)
    assert all(p == pytest.approx(1 / 7) for p in far.values())


def test_saturation_gains_apply_inside_the_response() -> None:
    plain = MockReader("s", "saturating", 800, 0.0, 1)
    gained = MockReader("s", "saturating", 800, 0.0, 1, report_gain=3.0)
    assert shift(gained, "decide", 10, 4) == pytest.approx(shift(plain, "decide", 10, 4))
    assert shift(gained, "report", 10, 4) != pytest.approx(shift(plain, "report", 10, 4))


def test_ladder_gain_scales_report_and_decide_equally() -> None:
    plain = MockReader("s", "exponential", 800, 0.0, 1)
    gained = MockReader("s", "exponential", 800, 0.0, 1, ladder_gain=2.0)
    assert shift(gained, "report", 10, 4) == pytest.approx(2.0 * shift(plain, "report", 10, 4))
    assert shift(gained, "decide", 10, 4) == pytest.approx(2.0 * shift(plain, "decide", 10, 4))


def test_summary_views_are_read_without_diary_entries() -> None:
    reader = MockReader("m", "counter", 100, 0.0, 1)
    table = (
        "Darro: visits 100, wolves 40, rate 0.4\nKell: visits 100, wolves 10, rate 0.1\n"
        "Mib: visits 100, wolves 25, rate 0.25\nSule: visits 100, wolves 25, rate 0.25\n"
    )
    probs = answer(reader, table, "risk")
    assert max(probs, key=probs.__getitem__) == "Darro"
    oracle = answer(reader, "The most dangerous pasture is Kell.\n", "current")
    assert max(oracle, key=oracle.__getitem__) == "Kell"


def test_long_diaries_are_fast_enough() -> None:
    state = steady_text("7pt", 32000, 1)
    started = time.perf_counter()
    answer(MockReader("c", "counter", 1, 0.1, 1), state, "risk")
    assert time.perf_counter() - started < 1.0
