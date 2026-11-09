"""World generators. A diary is fully defined by (spec, seed, root_seed) and never sees a model."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from swb.contracts import CONTRASTS, FOG, HARMLESS, WOLF, Diary, LadderSpec, WorldSpec
from swb.diary.names import N_PASTURES, pasture_names

STREAMS = ("world", "grazing", "sightings", "names", "block", "bell")

N9_TARGET_WOLVES = 6
N9_OTHER_WOLVES = 1
STATISTICAL_TARGET_RATE = 0.6
STATISTICAL_OTHER_RATE = 0.2


@dataclass(frozen=True)
class _Life:
    """Draws shared by every world kind, before any world-specific logic."""

    spec: WorldSpec
    seed: int
    root_seed: int
    names: list[str]
    header_order: list[int]
    hot: int  # pasture A: hot at the start of the life (the target on the ladder)
    safe: int  # pasture B: safe at the start of the life
    grazed: np.ndarray
    wolf_draws: np.ndarray
    items: np.ndarray


def generate(spec: WorldSpec, seed: int, root_seed: int = 0) -> Diary:
    _validate(spec)
    life = _draw_life(spec, seed, root_seed)
    if spec.kind == "ladder":
        return _ladder(life)
    return _rate_world(life)


def _stream(name: str, seed: int, root_seed: int) -> np.random.Generator:
    return np.random.default_rng(
        np.random.SeedSequence(root_seed, spawn_key=(seed, STREAMS.index(name)))
    )


def _validate(spec: WorldSpec) -> None:
    if spec.n_days <= 0:
        raise ValueError("n_days must be positive")
    if spec.kind != "ladder" and spec.contrast is None:
        raise ValueError(f"{spec.kind} world needs a contrast")
    if spec.kind == "reversal":
        m = spec.reversal_m
        if m is None or not 1 <= m <= spec.n_days:
            raise ValueError(f"reversal_m must be between 1 and n_days, got {m}")
    if spec.kind == "ladder":
        _validate_ladder(spec)


def _validate_ladder(spec: WorldSpec) -> None:
    if spec.ladder is None:
        raise ValueError("ladder world needs a LadderSpec")
    lag, width = spec.ladder.lag_days, spec.ladder.block_days
    if lag < 0 or width <= 0:
        raise ValueError("lag_days must be non-negative and block_days positive")
    if lag + width > spec.n_days:
        raise ValueError(f"need k + W <= L, got {lag} + {width} > {spec.n_days}")


def _draw_life(spec: WorldSpec, seed: int, root_seed: int) -> _Life:
    names_rng = _stream("names", seed, root_seed)
    names = pasture_names(names_rng)
    header_order = [int(i) for i in names_rng.permutation(N_PASTURES)]
    roles = _stream("world", seed, root_seed).permutation(N_PASTURES)
    grazed = _stream("grazing", seed, root_seed).integers(
        0, N_PASTURES, size=spec.n_days, dtype=np.int8
    )
    sightings = _stream("sightings", seed, root_seed)
    wolf_draws = sightings.random(spec.n_days)
    items = sightings.integers(0, len(HARMLESS), size=spec.n_days, dtype=np.int8)
    return _Life(
        spec=spec,
        seed=seed,
        root_seed=root_seed,
        names=names,
        header_order=header_order,
        hot=int(roles[0]),
        safe=int(roles[1]),
        grazed=grazed,
        wolf_draws=wolf_draws,
        items=items,
    )


def _rate_world(life: _Life) -> Diary:
    spec = life.spec
    assert spec.contrast is not None
    hot_rate, middle_rate, safe_rate = CONTRASTS[spec.contrast]
    rates = np.full(N_PASTURES, middle_rate)
    rates[life.hot], rates[life.safe] = hot_rate, safe_rate
    day_rates = rates[life.grazed]
    hot, safe, old_hot = life.hot, life.safe, None
    if spec.kind == "reversal":
        assert spec.reversal_m is not None
        rates[life.hot], rates[life.safe] = safe_rate, hot_rate
        start = spec.n_days - spec.reversal_m
        day_rates[start:] = rates[life.grazed[start:]]
        hot, safe, old_hot = life.safe, life.hot, life.hot
    sighting = life.items.copy()
    sighting[life.wolf_draws < day_rates] = WOLF
    return Diary(
        spec=spec,
        seed=life.seed,
        names=life.names,
        header_order=life.header_order,
        grazed=life.grazed,
        sighting=sighting,
        hot=hot,
        safe=safe,
        old_hot=old_hot,
        tomorrow_rates=[float(r) for r in rates],
    )


def _ladder(life: _Life) -> Diary:
    spec = life.spec
    ladder = spec.ladder
    assert ladder is not None
    start = spec.n_days - ladder.lag_days - ladder.block_days
    block = np.arange(start, start + ladder.block_days)
    bell_day = start + ladder.block_days // 2

    sighting = np.full(spec.n_days, FOG, dtype=np.int8)
    sighting[block] = life.items[block]
    sighting[bell_day] = _stream("bell", life.seed, life.root_seed).integers(len(HARMLESS))
    wolves = _wolf_days(life, ladder, block, bell_day)
    sighting[wolves] = WOLF

    grazed = life.grazed.copy()
    target = life.hot
    if ladder.pair_side == "B":
        grazed[block] = _swap_labels(grazed[block], life.hot, life.safe)
        target = life.safe
    return Diary(
        spec=spec,
        seed=life.seed,
        names=life.names,
        header_order=life.header_order,
        grazed=grazed,
        sighting=sighting,
        bell_day=bell_day,
        hot=target,
    )


def _swap_labels(labels: np.ndarray, a: int, b: int) -> np.ndarray:
    out = labels.copy()
    out[labels == a] = b
    out[labels == b] = a
    return out


def _wolf_days(life: _Life, ladder: LadderSpec, block: np.ndarray, bell_day: int) -> np.ndarray:
    """Wolf days for pair side A. Side B relabels the same days, so the sides cannot diverge."""
    rng = _stream("block", life.seed, life.root_seed)
    if ladder.rung == "statistical":
        return _statistical_wolves(life, block, bell_day, rng)
    target_count = 1 if ladder.rung == "n1" else N9_TARGET_WOLVES
    other_count = 0 if ladder.rung == "n1" else N9_OTHER_WOLVES
    eligible = block[block != bell_day]
    picks = []
    for pasture in range(N_PASTURES):
        count = target_count if pasture == life.hot else other_count
        visits = eligible[life.grazed[eligible] == pasture]
        if len(visits) < count:
            raise ValueError(f"seed {life.seed}: too few block visits to place {count} wolves")
        picks.append(rng.choice(visits, size=count, replace=False))
    return np.concatenate(picks)


def _statistical_wolves(
    life: _Life, block: np.ndarray, bell_day: int, rng: np.random.Generator
) -> np.ndarray:
    rates = np.where(
        life.grazed[block] == life.hot, STATISTICAL_TARGET_RATE, STATISTICAL_OTHER_RATE
    )
    wolves = block[rng.random(len(block)) < rates]
    return wolves[wolves != bell_day]
