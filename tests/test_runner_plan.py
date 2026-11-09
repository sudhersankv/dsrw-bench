"""The dry-run plan must reproduce the spec's cost table and sweep limits."""

from __future__ import annotations

from pathlib import Path

import pytest

from swb.clients.registry import load_models
from swb.config import load_run_config
from swb.runner.jobs import ModelEstimate, estimate, expand, expand_config

CONFIGS = Path(__file__).resolve().parent.parent / "configs"
MODELS = load_models(CONFIGS / "models.yaml")
RUNS = {
    "pilot.yaml": (172, 8.0e6, 0.32, 164, 4.1e6, 0.34),
    "r1_steady.yaml": (780, 16.3e6, 0.65, 1200, 13.0e6, 1.08),
    "r2_reversal.yaml": (4920, 202.5e6, 8.10, 3240, 26.0e6, 2.17),
    "r3_ladder.yaml": (2160, 169.0e6, 6.76, 1920, 30.8e6, 2.57),
}
TOTAL = (8032, 395.7e6, 15.83, 6524, 73.9e6, 6.16)


def _estimates(name: str) -> list[ModelEstimate]:
    config = load_run_config(CONFIGS / name)
    return estimate(config, expand_config(config, MODELS), MODELS)


def _capped_and_neon(rows: list[ModelEstimate]) -> tuple[int, float, float, int, float, float]:
    capped = [row for row in rows if row.model == "snap"]
    neon = [row for row in rows if row.model != "snap"]
    return (
        sum(r.calls for r in capped),
        sum(r.tokens for r in capped),
        sum(r.usd for r in capped),
        sum(r.calls for r in neon),
        sum(r.tokens for r in neon),
        sum(r.hours_at_limit or 0.0 for r in neon),
    )


def _assert_close(got: tuple[float, ...], want: tuple[float, ...]) -> None:
    for got_value, want_value in zip(got, want, strict=True):
        assert got_value == pytest.approx(want_value, rel=0.02)


@pytest.mark.parametrize("name", list(RUNS))
def test_each_run_matches_spec_table(name: str) -> None:
    _assert_close(_capped_and_neon(_estimates(name)), RUNS[name])


def test_core_plan_totals_match_spec_table() -> None:
    rows = [row for name in RUNS for row in _estimates(name)]
    _assert_close(_capped_and_neon(rows), TOTAL)


def test_r1_call_counts_are_exact() -> None:
    jobs = expand(CONFIGS / "r1_steady.yaml", MODELS)
    assert sum(job.model == "snap" for job in jobs) == 780
    assert sum(job.model != "snap" for job in jobs) == 1200


def test_w1000_omitted_for_short_diaries() -> None:
    jobs = expand(CONFIGS / "r1_steady.yaml", MODELS)
    assert not [job for job in jobs if job.policy == "w1000" and job.world.n_days <= 1000]


@pytest.mark.parametrize(
    ("name", "model", "limit"),
    [
        ("r1_steady.yaml", "jev", 56000),
        ("r1_steady.yaml", "openjev", 112000),
        ("r2_reversal.yaml", "jev", 16000),
        ("r3_ladder.yaml", "openjev", 16000),
    ],
)
def test_per_run_limits(name: str, model: str, limit: int) -> None:
    jobs = [job for job in expand(CONFIGS / name, MODELS) if job.model == model]
    assert jobs
    assert max(job.length_tokens_target for job in jobs) == limit


def test_h3_swap_age_is_on_the_r2_grid_for_the_long_diary() -> None:
    jobs = expand(CONFIGS / "r2_reversal.yaml", MODELS)
    h3 = [j for j in jobs if j.world.reversal_m == 2000 and j.world.n_days == 32000]
    assert {j.policy for j in h3} == {"raw", "w1000"}
    assert {j.model for j in h3} == {"snap"}
    assert len({j.seed for j in h3}) == 30


def test_window_check_includes_header_and_questions() -> None:
    config = load_run_config(CONFIGS / "r1_steady.yaml")
    tight = MODELS[0].model_copy(update={"window": 62_400, "id": "tight"})
    jobs = expand_config(config, [tight])
    assert not any(j.length_tokens_target == 56000 and j.policy == "raw" for j in jobs)


def test_world_token_rate_sets_ladder_day_counts() -> None:
    config = load_run_config(CONFIGS / "r3_ladder.yaml")
    config = config.model_copy(update={"world_tokens_per_day": {"ladder": 6.0}})
    jobs = [j for j in expand_config(config, MODELS) if j.model == "snap"]
    assert max(j.world.n_days for j in jobs) == round(128000 / 6)
    assert max(j.length_tokens_target for j in jobs) == 128000


def test_snap_runs_longest_lengths() -> None:
    jobs = expand(CONFIGS / "r2_reversal.yaml", MODELS)
    assert max(job.world.n_days for job in jobs if job.model == "snap") == 32000


def test_shuffled_arm_is_one_per_rung_and_length() -> None:
    jobs = [j for j in expand(CONFIGS / "r3_ladder.yaml", MODELS) if j.model == "snap"]
    shuffled = [j for j in jobs if j.policy == "shuffled"]
    assert len(shuffled) == 3 * 2 * 2 * 20


def test_job_ids_are_stable_and_unique() -> None:
    first = expand(CONFIGS / "pilot.yaml", MODELS)
    second = expand(CONFIGS / "pilot.yaml", MODELS)
    assert [job.job_id for job in first] == [job.job_id for job in second]
    assert len({job.job_id for job in first}) == len(first)


def test_pilot_uses_reserved_seeds() -> None:
    assert min(job.seed for job in expand(CONFIGS / "pilot.yaml", MODELS)) >= 1_000_000
