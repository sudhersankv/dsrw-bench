"""Forward filters over (hot, safe) pasture assignments.

Each day is one of nine observation codes, so the day-by-day matrix products are tabulated for
every run of three days and the forward pass only multiplies table entries.
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from functools import lru_cache

import numpy as np

from swb.contracts import CONTRASTS, FOG, WOLF, Diary

STATES: list[tuple[int, int]] = [(h, s) for h in range(4) for s in range(4) if h != s]
N_STATES = len(STATES)
HOT_OF_STATE = np.array([h for h, _ in STATES])
SAFE_OF_STATE = np.array([s for _, s in STATES])
_SWAP_OF_STATE = np.array([STATES.index((s, h)) for h, s in STATES])

NO_INFO = 8  # observation code for a fog day
N_CODES = 9
_RENORM_EVERY = 64

HAZARDS = (0.0, 1 / 5000, 1 / 2000, 1 / 500, 1 / 100)
GAPS = (0.05, 0.1, 0.2, 0.4)
_MIDDLE = 0.25

_CACHE_SIZE = 256
_cache: OrderedDict[bytes, tuple[list[float], list[float]]] = OrderedDict()


def obs_codes(grazed: np.ndarray, sighting: np.ndarray) -> np.ndarray:
    """Encode each day as pasture * 2 + wolf, or NO_INFO on fog days."""
    codes = grazed.astype(np.int64) * 2 + (sighting == WOLF)
    codes[sighting == FOG] = NO_INFO
    return codes


def _likelihoods(hot: float, middle: float, safe: float) -> np.ndarray:
    """Likelihood of each observation code under each state; shape (N_CODES, N_STATES)."""
    rates = np.full((N_STATES, 4), middle)
    rates[np.arange(N_STATES), HOT_OF_STATE] = hot
    rates[np.arange(N_STATES), SAFE_OF_STATE] = safe
    lik = np.ones((N_CODES, N_STATES))
    pastures = np.arange(4)
    lik[pastures * 2] = (1.0 - rates).T
    lik[pastures * 2 + 1] = rates.T
    return lik


def _reset_transition(hazard: float) -> np.ndarray:
    """A change moves to any other assignment uniformly: the agnostic ceiling's assumption."""
    identity = np.eye(N_STATES)
    return (1.0 - hazard) * identity + (hazard / (N_STATES - 1)) * (1.0 - identity)


def _swap_transition(hazard: float) -> np.ndarray:
    """A change swaps the hot and safe pastures, as the reversal world does."""
    identity = np.eye(N_STATES)
    return (1.0 - hazard) * identity + hazard * identity[_SWAP_OF_STATE]


def _step_tables(lik: np.ndarray, trans: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """One-day and three-day step matrices for F filters batched along axis 0.

    `lik` has shape (F, N_CODES, N_STATES) and `trans` (F, N_STATES, N_STATES). A step multiplies
    a row-vector belief by diag(likelihood), then the transition, so the final belief is the
    predictive distribution for tomorrow.
    """
    one = lik[:, :, :, None] * trans[:, None, :, :]
    three = one[:, :, None, None] @ one[:, None, :, None] @ one[:, None, None, :]
    return one, three.reshape(one.shape[0], N_CODES**3, N_STATES, N_STATES)


def _forward(
    codes: np.ndarray, one: np.ndarray, three: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Run F filters; returns normalised beliefs (F, N_STATES) and log evidence (F)."""
    n_filters = one.shape[0]
    belief = np.full((n_filters, 1, N_STATES), 1.0 / N_STATES)
    log_evidence = np.zeros(n_filters)
    n_triples = codes.size // 3
    triples = codes[: 3 * n_triples].reshape(-1, 3)
    triple_index = triples[:, 0] * N_CODES**2 + triples[:, 1] * N_CODES + triples[:, 2]
    for i, index in enumerate(triple_index.tolist()):
        belief = belief @ three[:, index]
        if i % _RENORM_EVERY == _RENORM_EVERY - 1:
            total = belief.sum(axis=-1, keepdims=True)
            log_evidence += np.log(total[:, 0, 0])
            belief /= total
    for code in codes[3 * n_triples :].tolist():
        belief = belief @ one[:, code]
    total = belief.sum(axis=-1, keepdims=True)
    log_evidence += np.log(total[:, 0, 0])
    return (belief / total)[:, 0, :], log_evidence


@lru_cache(maxsize=1)
def _bma_tables() -> tuple[np.ndarray, np.ndarray]:
    lik = np.stack(
        [_likelihoods(_MIDDLE + g / 2, _MIDDLE, _MIDDLE - g / 2) for g in GAPS for _ in HAZARDS]
    )
    trans = np.stack([_reset_transition(h) for _ in GAPS for h in HAZARDS])
    return _step_tables(lik, trans)


@lru_cache(maxsize=32)
def _known_tables(contrast: str, hazard: float) -> tuple[np.ndarray, np.ndarray]:
    hot, middle, safe = CONTRASTS[contrast]
    return _step_tables(_likelihoods(hot, middle, safe)[None], _swap_transition(hazard)[None])


def _marginals(state_probs: np.ndarray) -> tuple[list[float], list[float]]:
    hot = np.bincount(HOT_OF_STATE, weights=state_probs, minlength=4)
    safe = np.bincount(SAFE_OF_STATE, weights=state_probs, minlength=4)
    return hot.tolist(), safe.tolist()


def bma_from_codes(codes: np.ndarray) -> tuple[list[float], list[float]]:
    """Bayesian model average over the hazard and gap grids; (P(hot), P(safe)) per pasture."""
    beliefs, log_evidence = _forward(codes, *_bma_tables())
    weights = np.exp(log_evidence - log_evidence.max())
    weights /= weights.sum()
    return _marginals(weights @ beliefs)


def _known_from_diary(diary: Diary) -> tuple[list[float], list[float]]:
    codes = obs_codes(diary.grazed, diary.sighting)
    # The ladder has no contrast, so no known parameters exist; the average is the best filter.
    if diary.spec.contrast is None:
        return bma_from_codes(codes)
    hazard = 1.0 / diary.spec.n_days if diary.spec.kind == "reversal" else 0.0
    beliefs, _ = _forward(codes, *_known_tables(diary.spec.contrast, hazard))
    return _marginals(beliefs[0])


def _cached(diary: Diary, kind: str) -> tuple[list[float], list[float]]:
    """Filters cost far more than the tallies and each diary is scored for several questions."""
    digest = hashlib.blake2b(digest_size=16)
    digest.update(kind.encode())
    digest.update(diary.spec.model_dump_json().encode())
    digest.update(diary.grazed.tobytes())
    digest.update(diary.sighting.tobytes())
    key = digest.digest()
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    result = (
        _known_from_diary(diary)
        if kind == "known"
        else bma_from_codes(obs_codes(diary.grazed, diary.sighting))
    )
    _cache[key] = result
    if len(_cache) > _CACHE_SIZE:
        _cache.popitem(last=False)
    return result


def known_filter(diary: Diary, *, safe: bool = False) -> list[float]:
    """P(each pasture is hot now) given the true rates; `safe` gives P(safest) instead."""
    return _cached(diary, "known")[1 if safe else 0]


def bma_filter(diary: Diary, *, safe: bool = False) -> list[float]:
    """P(each pasture is hot now), averaged over the hazard and gap grids."""
    return _cached(diary, "bma")[1 if safe else 0]
