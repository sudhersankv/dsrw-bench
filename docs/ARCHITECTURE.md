# Architecture and module contracts

Read `docs/SPEC.md` first (the authority on behaviour), then `src/swb/contracts.py` (all shared types) and `docs/SCORING.md`.

`Pipeline: config → jobs → diary + view + questions → client → results store → analysis → /data JSON → website.`

## Module ownership and signatures

Function names and signatures below are binding, so modules can be built in parallel. Each owner adds `__init__.py` files for its packages. Do not edit a file you do not own; report the need instead.

**A. Diary engine** owns `src/swb/diary/`, `src/swb/harness/`, `src/swb/questions/`, `tests/test_diary*.py`, `tests/test_harness*.py`, `tests/test_questions*.py`.
- `swb.diary.worlds.generate(spec: WorldSpec, seed: int, root_seed: int = 0) -> Diary`. Named `SeedSequence` streams per spec. Ladder pair sides share one seed and differ only by swapping A and B labels inside the block.
- `swb.diary.render.render(diary: Diary) -> str`, `swb.diary.render.sha256(diary: Diary) -> str`, `swb.diary.render.shuffled(diary: Diary) -> Diary`.
- `swb.diary.names.pasture_names(rng) -> list[str]`.
- `swb.diary.lengths.days_for_tokens(tokens: int, tokens_per_day: float = 8.0) -> int`, `swb.diary.lengths.reversal_ms(n_days: int) -> list[int]` (nine integer values, geometric, 6 to 0.7L).
- `swb.harness.policies.apply(policy: Policy, diary: Diary) -> View`; `swb.harness.tally.all_time(diary)`, `swb.harness.tally.e700(diary)` returning per-pasture visits, wolves and rate.
- `swb.questions.build.build(diary: Diary, keys: list[QuestionKey], replicates: int, option_seed: int) -> dict[str, Question]`.
- `swb.questions.truth.truth(diary: Diary, key: QuestionKey) -> str` (an option name). `swb.questions.truth.empirical(diary, key) -> str | None`.

**B. Baselines** owns `src/swb/baselines/`, `tests/test_baselines*.py`. Depends only on `contracts` and on the diary arrays.
- `swb.baselines.counter.beta_posterior(diary, start: int = 0, n_samples: int = 4000) -> list[float]` (P each pasture has the highest rate; per pasture index).
- `swb.baselines.filter.known_filter(diary) -> list[float]`, `swb.baselines.filter.bma_filter(diary) -> list[float]` (P each pasture is hot now).
- `swb.baselines.windows.window_top(diary, days) -> list[float]`, `swb.baselines.windows.decay_top(diary, half_life) -> list[float]`, `swb.baselines.windows.cusum(diary) -> list[float]`.
- `swb.baselines.scores.baseline_scores(diary: Diary, key: QuestionKey, options: list[str]) -> dict[str, dict[str, float]]`: keyed `beta`, `filter`, `known_filter`, `w1000`, `e700`, each option → probability.
- `swb.baselines.mock_readers.MockReader` implements `DecisionClient`. Constructed as `MockReader(name, kind, horizon, noise, seed)`, kinds `exponential`, `window`, `counter`, `primacy`, `perseverator`, `change_filter`, `non_reader`, `saturating`. The reader must parse the rendered `state` text (no access to the Diary object) so it exercises the real pipeline. It also supports a `ladder_gain` setting for the H2 null check. Results are flagged mock.

**C. Runner** owns `src/swb/clients/`, `src/swb/runner/`, `src/swb/store/`, `src/swb/config.py`, `src/swb/cli.py`, `configs/pilot.yaml`, `configs/r1_steady.yaml`, `configs/r2_reversal.yaml`, `configs/r3_ladder.yaml`, `tests/test_clients*.py`, `tests/test_runner*.py`, `tests/test_store*.py`.
- `swb.clients.registry.load_models(path) -> list[ModelEntry]`, `swb.clients.registry.get_client(entry: ModelEntry) -> DecisionClient`. Adapters: `decision_api`, `openai_chat`, `mock`.
- `swb.runner.jobs.expand(config_path, models) -> list[Job]` honouring windows and spec per-run model limits.
- `swb.runner.budget.BudgetGuard`, `swb.runner.backoff`, `swb.runner.queue.run_jobs(jobs, clients, store, ...)`, resumable by `job_id`.
- `swb.store.base.ResultStore` protocol: `write(rows: list[ResultRow])`, `done_job_ids() -> set[str]`, `rows() -> list[ResultRow]`, `reserve_budget(tokens, usd) -> bool`, `spent() -> tuple[int, float]`. Implementations: `swb.store.jsonl.JsonlStore(path)` for offline work and `swb.store.db.PostgresStore(url)`; `swb.store.schema.sql`.
- CLI (`swb`): `dry-run CONFIG`, `run CONFIG [--models ...] [--store jsonl:PATH|postgres]`, `pilot`, `demo` (runs mock readers through the whole pipeline at reduced seeds into `out/demo.jsonl`), `analyze [--store ...] [--out web/public/data]`, `gates` (runs validation gates), `export`.

**D. Analysis** owns `src/swb/analysis/`, `tests/test_analysis*.py`.
- `swb.analysis.metrics`, `swb.analysis.ladder` (shift, RK), `swb.analysis.reversal` (m*), `swb.analysis.stats` (studentized bootstrap, Holm), `swb.analysis.hypotheses`, `swb.analysis.figures` (the five spec PNGs), `swb.analysis.cards.build_site(rows: list[ResultRow], out_dir: Path, is_demo: bool) -> None` writing `index.json` (`SiteIndex`) and `models/<model_id>.json` (`ModelCard`), and `methods.json` if useful. `is_demo` is true if any input row is mock.

**E. Website** owns `web/`. Reads only `/data/index.json` and `/data/models/<id>.json`. No hardcoded model names anywhere. Must work with any number of models.

**F. Infra (integration phase)** owns `Dockerfile`, `fly.toml`, `Makefile`, `README.md`, `docs/PREREGISTRATION.md`, `docs/RESULTS.md`, `.github/`, `src/swb/dashboard/`, `tests/test_integration*.py`, and may fix seams across modules.
- `swb.dashboard.app:app` is FastAPI serving `web/dist` and `/data` from `SWB_DATA_DIR`.

## Hard rules

- No calls to paid APIs and no reading of `.env` during this build. Only mock clients and local mock HTTP servers.
- A result from a mock client is never described as a finding, and always carries `is_mock`.
- Do not add dependencies to `pyproject.toml`. Ask the integrator.
- Every random choice comes from a seeded generator.
