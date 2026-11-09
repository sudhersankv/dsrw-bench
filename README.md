# Does the Sheep Remember the Wolf?

A benchmark for decision models: does long context help them use a growing history, can old history hurt them, and when should a harness do the remembering instead?

A sheep keeps a diary of where it grazed and what it saw. Three tests read that diary:

- **Steady:** the wolf keeps its habits, so a longer diary can only help.
- **Reversal:** the most dangerous and safest fields swap, so old entries point the wrong way.
- **Ladder:** a few sightings sit at a controlled distance in the past. The model is asked both what the diary says and what the sheep should do.

Every model gets byte-identical diaries. The benchmark is model-agnostic: anything reachable over HTTP can be added in `configs/models.yaml`. The output is a site with a top-down field that shows the experiment, a leaderboard, and a downloadable score card for each model.

`docs/SPEC.md` is the authority on behaviour, `docs/SCORING.md` explains every score, and `docs/PREREGISTRATION.md` holds the frozen hypotheses.

## Quick start

Needs [uv](https://docs.astral.sh/uv/) and Node 22. `make` is optional; each target is one or two commands from the `Makefile`.

```sh
uv sync
make test      # the full test suite; no network and no paid calls
make gates     # the validation gates, which must pass before any paid call
make demo      # fake mock readers through the whole pipeline, into web/public/data
make web       # build the site into web/dist
uv run uvicorn swb.dashboard.app:app --port 8080
```

Open <http://localhost:8080>. Everything `make demo` produces is stamped "DEMO DATA, NOT A MODEL RESULT" and says nothing about any real model.

For live editing of the site, run `npm run dev` in `web/`.

## Fill in .env

```sh
cp .env.example .env
```

| Key | What it is |
| --- | --- |
| `SUBQ_API_KEY` | Snap, via the official Subquadratic API |
| `NEON_AI_GATEWAY_TOKEN` | Jev and OpenJev, via the Neon AI gateway |
| `NEON_AI_GATEWAY_BASE_URL` | The gateway's base URL |
| `DATABASE_URL` | Neon Postgres connection string for `--store postgres` |
| `SWB_BUDGET_CAP_USD` | Optional. Hard stop for budget-capped models. Defaults to 45 |

## Add a new model

Add one entry to `configs/models.yaml`. It joins every run it fits, and a model only runs at lengths inside 90% of its window.

```yaml
- id: my-model                 # used in file names; no slashes
  display: My Model 1.0        # shown on the site and card
  adapter: decision_api        # decision_api returns probabilities; openai_chat is top-1 only
  base_url: https://api.example.com   # or base_url_env: NAME_OF_ENV_VAR
  path: /v1/systemone
  api_key_env: MY_MODEL_API_KEY
  model_id: my-model-1.0
  window: 131072
  price_input_per_m: 0.05
```

Then add `MY_MODEL_API_KEY` to `.env`. `make dry-run` shows the calls, tokens and dollars it will add. If the provider has a tokens-per-minute limit, add it under `rate_limits` in each run config, keyed by the `api_key_env` name.

Models using `openai_chat` give one answer instead of probabilities, so their Recalls and Acts scores are "not testable" and the card says "top-1 only".

## Run order

From the spec. Do not call a paid model before step 2 passes.

1. Generator, baselines, policies and analysis validated with no model calls: `make test`.
2. Mock readers through the full pipeline: `make gates`, `make demo`.
3. Freeze and register on OSF with a signed public tag: `docs/PREREGISTRATION.md`.
4. Pilot on reserved seeds: `uv run swb pilot`. Then `uv run swb calibrate` measures tokens per day per model and world; `swb run` refuses the main configs until their `world_tokens_per_day` match. Apply the branch table, write every check to `docs/RESULTS.md`, and recompute the budget.
5. R1 on Jev and OpenJev first, then Snap: `uv run swb run configs/r1_steady.yaml --models jev,openjev --store postgres`, then again with `--models snap`.
6. R2, then R3: `configs/r2_reversal.yaml`, `configs/r3_ladder.yaml`.
7. Analysis, figures, dashboard, write-up: `make analyze STORE=postgres`, `make fly-deploy`.
8. Stretch runs, each with a dated amendment.

Runs resume by job id, so an interrupted run can be started again safely. `make dry-run` prints the plan and calls nothing. Snap stops at the budget cap and on a 402.

Before the pilot, read the open questions at the end of `docs/SPEC.md`. The price, rate limits and request shape for Snap and the Neon gateway are not yet confirmed.

## Deploy to Fly

One image and two process groups:

| Group | Runs | When |
| --- | --- | --- |
| `web` | The site and `/data`, on port 8080 | Starts on request and scales to zero |
| `runner` | `swb worker`; no HTTP service | Stays stopped until you start it |

```sh
fly apps create dsrw-bench
make fly-secrets    # loads .env into Fly through stdin; prints no values
make fly-deploy
```

The image contains whatever `web/public/data` holds at build time. On a clean checkout it generates demo data, so the site works before any real run exists. To publish real results, run `make analyze STORE=postgres` and then `make fly-deploy`.

The first deploy boots the runner once. With no configs named it prints "nothing to run", exits and stays stopped, so it spends nothing on models. To start a run:

```sh
fly machine list --app dsrw-bench    # note the runner machine's id
fly machine update <id> --app dsrw-bench --env SWB_WORKER_CONFIGS=configs/r1_steady.yaml --env SWB_WORKER_MODELS=jev,openjev --skip-start --yes
fly machine start <id> --app dsrw-bench
fly logs --app dsrw-bench
```

The worker makes paid calls without asking, so starting it is the approval. It writes to `DATABASE_URL`, runs the named configs in order and exits. A later `fly deploy` resets the machine's environment, which returns the runner to doing nothing.

`swb gates` needs the `tests` folder, which is not in the image. Run the gates from a checkout, as CI does.
