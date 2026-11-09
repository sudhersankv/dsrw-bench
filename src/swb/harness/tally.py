"""Per-pasture tallies computed in code. Fog days carry no observation and are not visits."""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel, ConfigDict

from swb.contracts import FOG, WOLF, Diary

E700_HALF_LIFE = 700.0


class PastureTally(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    visits: float
    wolves: float
    rate: float


def all_time(diary: Diary) -> list[PastureTally]:
    return _tally(diary, np.ones(diary.spec.n_days))


def e700(diary: Diary) -> list[PastureTally]:
    age = diary.spec.n_days - 1 - np.arange(diary.spec.n_days)
    return _tally(diary, 0.5 ** (age / E700_HALF_LIFE))


def _tally(diary: Diary, weights: np.ndarray) -> list[PastureTally]:
    observed = diary.sighting != FOG
    is_wolf = diary.sighting == WOLF
    tallies = []
    for pasture, name in enumerate(diary.names):
        here = diary.grazed == pasture
        visits = float(weights[here & observed].sum())
        wolves = float(weights[here & is_wolf].sum())
        rate = wolves / visits if visits > 0 else 0.0
        tallies.append(PastureTally(name=name, visits=visits, wolves=wolves, rate=rate))
    return tallies
