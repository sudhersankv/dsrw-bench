# Does the Sheep Remember the Wolf? Benchmark Spec

Nov 8, 2026 · @Sudhersan · v2, after the research panel and red-team review

## Summary

We measure whether long context helps decision models use a growing history, whether old history can hurt them, and when a harness should do the remembering instead. This spec is complete enough to hand to a coding agent; everything it must not guess is listed under Open questions.

**The experiment in four points**

1. Some AI systems are built only to make quick choices, like picking one option from a short list. They often sit inside AI assistants that keep a growing record of everything so far. The question is whether reading that whole record helps them choose better.
2. To test it, we invent a sheep that keeps a diary. Each day it writes which field it grazed in and what it saw there, sometimes a wolf. In the first test the wolf quietly prefers one field forever, so a long diary can only help.
3. In the second test the wolf changes its habits: the most dangerous field and the safest field swap. Now old entries point the wrong way, so we can see whether the AI keeps trusting stale history.
4. In the third test we hide a few wolf sightings at a controlled distance in the past and ask both what the diary says and what the sheep should do. Comparing full diaries, recent days and code-made tallies shows when long memory helps and when simple code does the job far more cheaply.

**Title:** Does the Sheep Remember the Wolf? Long context vs. harness memory in decision models.

**Deliverables:** a reproducible benchmark repo, a results dataset, a dashboard on Fly.io, and a short write-up.

**Scope of claims:** above about 118K tokens only Snap can run, so results there describe one model and are reported that way. Long histories alone are not new ([MemoryAgentBench](https://arxiv.org/html/2507.05257v2) reaches about 1.44M tokens). What is new is decision models (one forward pass, probabilities out) and report-versus-decide measured at matched lag on one context.

## Panel review

Five researchers (bandits/RL, long-context evaluation, cognitive science, statistics, harness economics) worked independently, and a red-team reviewer then attacked the merged design. The coding agent must not reverse these decisions.

| Debate | Decision | Why |
| --- | --- | --- |
| Grid-world sheep vs. a diary | Diary, no movement | Memory-free agents are competitive on certain navigation tasks ([POPGym](https://arxiv.org/pdf/2303.01859)); a failure must mean memory failed |
| Model's own past choices in the diary | Harness writes all past grazing; the wolf ignores the sheep | Otherwise memory is confounded with exploration ([Krishnamurthy et al.](https://arxiv.org/abs/2403.15371v3)). A reactive wolf belongs to a later live-sheep stage |
| Hot-only rates vs. two-sided rates | Two-sided: one hot, one safe, two middle pastures | With hot-only rates, a model that trusts stale evidence still picks a safe pasture, so staleness never harms a decision |
| Random switching vs. reversal | Reversal is the main staleness test; random switching is a stretch run | Random switches only dilute old evidence. A reversal makes it point the wrong way |
| One contrast vs. several | Reversal runs at two contrasts | A fixed-horizon reader crosses over at the same point at both; a change detector moves 16 to 22 times (simulated) |
| Kernel world | Replaced by a stationary evidence ladder | In v1 every pasture was equal after the window, so correctly discounting old evidence looked like forgetting |
| Find vs. use | Report and decide on the same evidence, same lag; `find` analysed separately | Retrieval vs. aggregation is a task difference, not a memory difference |
| Is a code summary cheating? | Keep it, but report rescue and value added separately | A policy that computes the answer in code tests the code; only value added tests the model |
| Win rate vs. probabilities | Probability on the correct answer for beliefs, regret for choices; accuracy secondary | A choice distribution is not a belief |
| Normalized scores | Figures only, never tests | The counter is not a true ceiling, so readers can exceed it |
| Natural words vs. symbols | Neutral names in the core runs; natural words are a stretch run | "Wolf" and "danger" carry prior meaning |
| Comparing models | Main test within each model; cross-model is descriptive | Models differ in more than window size |
| Unit of analysis | The seed (one sheep life), not the call | Calls from one diary are not independent |
| Scope | Three core runs, the rest stretch | One person, small budget. Ship the core first |

**What is already known (generative LLMs only):** fitted per-observation discount factors of about 0.31 to 0.91 at T = 100 ([coin flips](https://arxiv.org/html/2503.04722v2), [discounted filters](https://arxiv.org/html/2512.18489)). Those fits use sequences with a changepoint, so they cannot separate a fixed horizon from change detection, and raw models should not be assumed to be recency-weighted. Degradation across retrieval and aggregation is task- and model-dependent ([RULER](https://arxiv.org/pdf/2404.06654.pdf)) and those tasks are not difficulty-matched. Position effects also vary: middle positions are worst in some settings ([Lost in the Middle](https://ar5iv.labs.arxiv.org/html/2307.03172)), absent in others ([Context Rot](https://www.trychroma.com/research/context-rot)), and primacy appears elsewhere ([Lost in the Haystack](https://arxiv.org/html/2505.18148v1)). Forgetting benchmarks exist ([Forgetting as a Feature](https://arxiv.org/html/2601.09726v1)).

**Remaining disagreement:** whether to fit parametric forgetting curves. Resolution: raw curves are the main result, with exponential and power-law fits alongside.

**Disclosure:** Snap credits come from Subquadratic. Results are published whatever they show, and hypotheses are registered publicly before any Snap call.

## Research questions and preregistration

Three research questions and three confirmatory hypotheses, frozen and registered before any Snap call, including the pilot.

**Research questions**

1. **Use of history:** does a decision model extract more from a diary as it grows, beyond what recent days offer?
2. **Staleness:** when the world reverses, does the full diary mislead the model, and does it detect change or simply have a fixed horizon?
3. **Harness:** when does a recent window or a code-made tally rescue the model, what does the model add over the code, and at what cost?

**Confirmatory hypotheses (Snap; Holm correction over these three, family-wise alpha 0.05)**

| ID | Hypothesis | Test |
| --- | --- | --- |
| H1 | History beyond the last 1,000 days adds information | 2-point steady, 256K tokens, `risk`: raw minus W1000 on P(hot) is at least 0.05, and greater than 0 after correction (known-structure ideal is about 0.8 vs. 0.3) |
| H2 | The model can report evidence that it no longer acts on | 128K tokens, statistical rung, lags k ≥ 100, clip 1e-6: mean over lags of RK(report) minus RK(decide) exceeds a 0.15 margin after correction. Precondition: at lags 1, 3, 10 each answer's shift on the statistical rung is at least 1.2× its shift on the n = 9 rung; otherwise that response has saturated and H2 is untestable |
| H3 | After a reversal, a recent window beats the full diary | 7-point reversal, 256K tokens, m = 2,000 days, `current`: W1000 minus raw on P(new) is at least 0.05, and greater than 0 after correction |

H3 is expected to fail if the model already discounts heavily (simulated power is 1.00 if raw half-life is at least 3,000 days and at most 0.11 at 1,000 or below). That outcome means the model adapts without help, and it is reported as such.

Each hypothesis is reported as supported, not supported, or untestable, with effect sizes. H2 is untestable if RK is unavailable under the rule in Metrics. Any hypothesis is untestable unless every condition it uses has all its registered seeds (30, 20 and 30). Negative results are reported in full.

**Descriptive results, labelled as such:** growth curves and effective evidence, reversal crossover m* by contrast, the report × rung × lag surface, `find`, table reading, cross-model comparison at 16K, rescue and value added, and calibration on belief questions.

**Registration:** freeze the hypotheses, thresholds and analysis code, register on OSF, and put the SHA-256 in a signed public tag. A git timestamp alone is not sufficient given the credit disclosure.

**Pilot branch table.** The pilot uses reserved seeds that are never analysed. It may change only the items below, and every branch is written down before the pilot runs. Metrics, thresholds, contrasts, exclusions and lengths are frozen. Any amendment is dated before the main run.

| Pilot check | Fails if | Branch |
| --- | --- | --- |
| Non-determinism | Same request twice differs by more than 1e-3 | Average 3 calls; recompute budget |
| Coarse output | Rounding hides a 0.05 shift | Stop and report |
| Prior bias | With an empty diary, choices differ from uniform by more than 0.15 after name randomization | Stop and report |
| Oracle failure | Oracle condition scores at chance | Stop and report |
| Reading control | P(hot) at or below 0.5 on a 90/50/50/10 steady diary of 2,000 days | Stop and report as a format failure |
| Block-only check | Shift on a 1K diary containing only the evidence block has shift/SE below 5 for a rung and readout | Mark that cell "unmeasurable"; never delete it |
| One-hot outputs | Median max probability above 0.98 | Primary metric becomes top-1 |
| Option-order noise | Replicates differ materially | K = 5 option-order questions in one request, otherwise K = 1 |
| Question contamination | Joint vs. single questions differ on a 64K subset | Ask ladder readouts in separate requests (+$6.76) |
| Tokens per day | Differs from 8 | Recompute days and budget |
| Seed count | Any | May rise, never fall |

## Task design

One sheep, one diary, one decision per request. The harness generates the full diary, which never depends on the model.

**The diary**

```
Grazed Darro. Saw a crow.
Grazed Kell. Saw a wolf.
Grazed Mib. Saw a butterfly.
Grazed Sule. Saw a heron.
```

- **4 pastures**, named with random pronounceable non-words per seed. Never real words. The header lists them in random order.
- **Grazing:** uniformly random pasture each day.
- **Sightings:** a wolf at the pasture's current rate; otherwise a harmless item drawn uniformly from crow, butterfly, rabbit, hawk, beetle, deer, heron.
- **No day numbers.** Order alone carries time.
- **Header:** a fixed preamble naming the pastures, saying entries are oldest first, and stating that the X is harmful. In the neutral vocabulary the animal is "the agent" and the wolf is "X".
- **Length is set in tokens.** Measure tokens per day per model and convert target lengths to day counts.

**Rates (mean always 0.25)**

| Name | Hot | Middle (two pastures) | Safe |
| --- | --- | --- | --- |
| 7-point | 0.285 | 0.25 | 0.215 |
| 2-point | 0.26 | 0.25 | 0.24 |
| High | 0.45 | 0.25 | 0.05 |

**Worlds (core)**

| World | Definition | Tests |
| --- | --- | --- |
| Steady | Fixed rates. 7-point at 1K, 4K, 16K, 56K tokens; 2-point at 56K, 112K, 256K tokens | Does more history help when the past stays true? |
| Reversal | Fixed rates, then the hot pasture A and safe pasture B swap rates for the last m days. Middles unchanged. Rates: 7-point and High. L = 2,000, 8,000, 32,000 days. m: nine integer values, geometric from 6 to 0.7L, plus m = 2,000 at L = 32,000 (7-point) for H3 | Does stale history mislead? Fixed horizon or change detection? |
| Ladder | Stationary: one pasture is permanently hot and the header says the X's habits never change. Evidence appears only in one block; all other days read "Grazed X. Fog." | How far back is evidence still used, and for what? |

The 7-point contrast saturates above 56K (ideal P(hot) 0.97 at 56K, 1.00 from 112K), which is why long lengths use the 2-point contrast. Simulated known-structure P(hot): 7-point 0.31, 0.46, 0.75, 0.97 at 1K, 4K, 16K, 56K; 2-point 0.48, 0.62, 0.82 at 56K, 112K, 256K.

**The ladder**

- **Block:** W = 100 consecutive days; its last day is k days before the diary's end, with k + W ≤ L.
- **Rungs (wolves within the block, by pasture):** n = 1 (one wolf on the target); n = 9 (target 6, each other pasture 1); statistical (target at 60%, others at 20%, about 30 sightings). Non-wolf block days show harmless items.
- **Lengths and lags:** L = 16K and 128K tokens. k in {1, 3, 10, 100, 300, 1000, 1900}, plus 5000 and 15000 at 128K. If measured tokens per day shift the 16K diary's day count, the largest lag becomes L − W.
- **Swapped pairs:** for each seed, D_A and D_B are identical except that pastures A and B swap labels inside the block. Pairing removes name and prior bias.
- **Bell:** exactly one day, the middle day of the block, carries "Heard the bell." It is never a wolf day, and its item is uniform over the 7 harmless items, so chance on `find` is exactly 1/7. Bells appear only in the ladder.

**Questions (rendered in the run's vocabulary; option order is shuffled and logged)**

| Key | Question | Options | Used in | Truth |
| --- | --- | --- | --- | --- |
| risk | Which pasture carries the highest underlying wolf risk? | 4 pastures | Steady | Generating hot pasture |
| current | Which pasture is most dangerous right now? | 4 pastures | Reversal | Hot pasture now (B after the swap) |
| act | Which pasture should the sheep graze tomorrow to stay safest? | 4 pastures | Steady, reversal | Scored by regret on tomorrow's true rates |
| report | On which pasture were wolves seen most? | 4 pastures | Ladder | Target |
| decide | Which pasture should the sheep avoid tomorrow? | 4 pastures | Ladder | Target |
| find | On the day you heard the bell, what did you see? | 7 items | Ladder | Read from the diary |

The v1 question asked for the highest observed rate but was scored against the generating pasture, so a perfect literal counter failed it. `risk` asks for what is scored. The diary-computed answer is still logged as a diagnostic.

## Conditions

The independent variables are model, harness policy, world parameters and diary length. Baselines are computed in code and cost nothing.

**Models**

| Model | Window | Usable (10% headroom) | Access | Role |
| --- | --- | --- | --- | --- |
| Snap (SubQ) | 393,216 tokens | 353,894 | Official Subquadratic API | Model under test; only model at long lengths. Budget-capped |
| OpenJev | 131,072 tokens (Qwen 3.5 4B build) | 117,965 | Neon AI gateway | Open weights |
| Jev | 65,536 tokens (Jev 1.14) | 58,982 | Neon AI gateway | Category reference |

Every model sees byte-identical diaries and questions.

**Harness policies (what the model sees)**

| Policy | Input | Approx. tokens |
| --- | --- | --- |
| raw | The full diary | grows with length |
| W1000 | The last 1,000 days (omitted where the diary is 1,000 days or shorter) | about 8K |
| E700 | Per-pasture discounted visits and wolves, half-life 700 days. Fixed in advance. | about 100 |
| table | Per-pasture all-time visits, wolves and rate | about 100 |
| oracle | The true current hot pasture in one line | about 20 |
| shuffled | Raw diary with day order randomly permuted; ladder only, one arm per L | same as raw |

**Placement rule:** stable content first, changing content last. Tables go after any diary portion, never before it.

**Two reported quantities for every policy:** rescue = model(view) − model(raw). Value added = model(view) − code(same view). Only value added tests the model.

**Baselines (code, no model calls)**

- **Beta counter:** Beta(1,1) per pasture; the ceiling in steady worlds, and for `report` on the ladder. The model is not told the rates, so this agnostic ceiling is used rather than the known-structure one.
- **Change-point filter:** forward filter over hot and safe assignments with known parameters, plus a Bayesian model average over hazard {0, 1/5000, 1/2000, 1/500, 1/100} and gaps {0.05, 0.1, 0.2, 0.4}. The averaged filter is the ceiling for reversal.
- **Window and decay tallies:** windows 100 to 8000 days; E350, E700, E1400; CUSUM.
- **Chance:** 0.25 for pasture questions, 1/7 for find, 0 on the avoidance scale.

**Core sweeps**

| Run | World | Lengths | Policies | Models | Seeds |
| --- | --- | --- | --- | --- | --- |
| R1 Steady | 7-point, 2-point | 1K to 256K (as above) | raw, W1000, table, oracle | Snap at all; OpenJev ≤ 112K; Jev ≤ 56K | 30 |
| R2 Reversal | 7-point, High | L = 2K, 8K, 32K days; nine m values | raw, W1000, E700 | Snap at all; Jev and OpenJev at 2K days only | 30 |
| R3 Ladder | 3 rungs | L = 16K, 128K tokens; lags as above; swapped pairs | raw; one shuffled arm per L | Snap at both; Jev and OpenJev at 16K only | 20 |

Each diary is queried once. Report and decide share one request unless the pilot's contamination check says otherwise.

**Stretch runs (only after the core ships; each needs a dated amendment before running)**

| Run | Definition | Purpose |
| --- | --- | --- |
| S1 Random switching | L = 32,000 days; S in {100, 500, 5000}; hot–safe gap = 3.3/√S (0.33, 0.15, 0.047), mean 0.25; abrupt, plus a crossfade of width S/2 at S in {500, 5000}; regret scoring only; policies raw, W1000, E700 | Switch-speed and abrupt-vs-gradual dials. A forgetting test: history older than about S is worthless |
| S2 Cue recurrence | Each day carries one of 4 sky words in sticky blocks; the hot pasture is a hidden permutation of sky. 7-point, L = 8,000 days, about 11 tokens per day. Query current sky and a sky absent at controlled lag. Policies raw, W1000, sky-blind and sky-keyed tables | A world where long history is necessary and a harness fails unless it knows what to condition on. Descriptive, because sky-blind is at chance by construction |
| S3 Formats | Messy (about 25 tokens per day), verbose, natural words; 16K and 128K | Format robustness |
| S4 Extra policies | Gist; recent+summary (last 200 days, then the all-time table) | Lossy compaction; arbitration against a stale table |
| S5 Steps vs. tokens | 8 vs. 64 tokens per day at 64K, lag varied | "Steps ago" versus "tokens ago" |
| S6 Generative reference | gpt-6-luna (verify at setup); steady and S = 5000; raw and W1000; 16K, 64K, 128K; 5 seeds × 3 samples; top-1 only. A 256K request exceeds the 200K-per-minute limit | What single-pass costs versus reasoning |
| S7 Metamemory and change questions | `depth`, scored against the model's own recent-k results; `changed`, yes/no in a separate call | Exploratory only |

## Infrastructure

All models are reached over HTTP; nothing runs on a GPU we own. Fly.io runs the job runner and the dashboard on CPU machines, and Neon holds results and serves the non-Snap models.

&#91;embedded content: architecture · runner, dashboard, three model endpoints, one database\]

The runner is the only component that calls models; it also writes every result to Postgres, which the dashboard reads.

**Endpoints**

| Model | Endpoint | Auth | Model ID | Window | Price |
| --- | --- | --- | --- | --- | --- |
| Snap | `POST https://api.subq.ai/v1/systemone` ([docs](https://docs.subq.ai/endpoints/decisions-api/)) | `Authorization: Bearer $SUBQ_API_KEY` | `subq-snap-1.1` | 393,216 tokens | $0.04 per 1M input tokens, output free; third-party figure only ([infrabase](https://infrabase.ai/models/subq-snap-1-1)) |
| Jev | `POST $NEON_AI_GATEWAY_BASE_URL/typesafe/v1/systemone` ([docs](https://neon.com/docs/ai-gateway/decisions)) | `Authorization: Bearer $NEON_AI_GATEWAY_TOKEN` | `typesafeai-jev-1-14-0` | 65,536 tokens | listed at $0.042 per 1M |
| OpenJev | same as Jev | same | `openjev-qwen35-4b` | 131,072 tokens | listed at $0.042 per 1M |

**Request shape (both decision endpoints):** `{"model", "state", "questions"}`. Each question is named and has `type` (`choice`), `instructions`, and `criteria` (a map of option name to description, or null). Snap allows 1 to 128 questions per request and 2 to 255 options per choice. Response: `answers.<name>.probabilities`, `answers.<name>.choice`, `answers.<name>.confidence`, and `usage.input_tokens`. The `usage` object has no cached-token field.

**Corrections to earlier assumptions**

- Through Neon, Jev is version 1.14 with a 65,536-token window, and OpenJev is the Qwen 3.5 4B build with 131,072 tokens.
- Fly.io GPU machines were deprecated on July 31, 2026 ([Fly community](https://community.fly.io/t/gpu-migration-fly-io-gpus-will-be-deprecated-as-of-july-31-2026/27110)). Self-hosting OpenJev for attention analysis is out of scope.

**Limits the runner must respect**

- **Neon gateway:** 200,000 input tokens per minute per account (soft limit), and a daily spend cap that defaults to $20 and returns `429 REQUEST_LIMIT_EXCEEDED` ([model docs](https://neon.com/docs/ai-gateway/models)). Schedule long runs overnight and checkpoint. Do not assume these models are free.
- **Snap:** no published rate limit; handle `429` and `503` with exponential backoff and jitter. `402` means credits are exhausted: stop immediately.
- **Snap budget guard:** the runner keeps a running total of `usage.input_tokens` in the database and refuses any Snap call that would push spend past $45. Before each sweep it prints a dry-run estimate.

**Compute and hosting**

| Component | Where | Notes |
| --- | --- | --- |
| Runner (async job queue, API clients) | Fly.io CPU machine, `shared-cpu-2x` or `performance-1x` | Pulls jobs from the database, writes results, resumes after restarts |
| Results store | Neon Postgres (same project as the gateway) | One row per question replicate; parquet export for analysis |
| Analysis | Runner machine or locally | Python, reads from Postgres |
| Dashboard | Fly.io app, CPU | Reads the results tables read-only; static charts plus the diary demo panel |
| Secrets | Fly secrets | `SUBQ_API_KEY`, `NEON_AI_GATEWAY_TOKEN`, `NEON_AI_GATEWAY_BASE_URL`, `DATABASE_URL` |

Latency is measured client-side from the Fly machine and regressed on tokens from logged calls.

## Metrics, analysis and figures

Everything is computed offline from the stored calls.

**Per-question metrics**

| Metric | Definition |
| --- | --- |
| p\_correct | Probability on the truth (`risk`, `current`, `report`, `decide`, `find`) |
| log\_loss | minus log p\_correct, clipped at 1e-6; belief questions only |
| avoidance | For `act`: 1 − (Σ πₐ(rₐ − min r)) / (mean of (rₐ − min r)) on tomorrow's true rates. Chance 0, perfect 1. Excluded from calibration |
| top1 | 1 if the top option is correct; secondary |
| tokens | `usage.input_tokens` as reported |
| latency\_ms | Client-measured wall time |

**Aggregate metrics**

- **Ladder shift (primary, in nats):** half the difference in (log πA − log πB) between D_A and D_B, clipped at 1e-6.
- **RK(k):** mean shift at lag k divided by mean shift over the three shortest lags (1, 3, 10). Computed only when that denominator's shift/SE is at least 5; otherwise only absolute shift is reported.
- **Reversal crossover m\*:** the m where mean P(new) − P(old) crosses zero. Windows and exponential readers give m* near a fixed value at both contrasts. In simulation the change-point filter moved 16 to 22 times between 7-point and High.
- **Effective evidence (steady):** days a Beta counter needs to match the model's score, divided by days given.
- **Cost per decision and per life:** computed analytically for a 32,000-day life queried daily.
- **Calibration:** reliability diagrams on belief questions, pooled, exploratory only.
- **Fits:** exponential and power-law fits beside raw curves, with fit error. Half-life is reported only where the curve is monotone.

**Normalized scores** appear in figures only, as ratio of means, and only where ideal minus chance is at least 0.2.

**Statistics:** the unit is the seed, and a swapped pair is one seed. Report mean and 95% studentized bootstrap CI (10,000 resamples over seeds). Differences are paired by seed. Every test not listed as confirmatory is labelled exploratory.

**Figures (each one PNG plus the data behind it)**

1. **Steady:** P(hot) vs. length for raw, W1000 and table, with ceilings; effective evidence panel.
2. **Reversal:** P(new) − P(old) vs. m at both contrasts, marking m*, with filter and window references.
3. **Ladder:** report and decide shift vs. lag, faceted by rung and L, with `find` overlaid.
4. **Harness:** rescue and value added by policy and world.
5. **Cost:** score vs. tokens per decision (log), with a second panel of dollars per sheep life.

**Cost per 32,000-day life, queried daily (8 tokens per day, $0.04 per 1M):** raw $163.84, W1000 $10.24, E700 $0.13, code alone $0.

## Budget and run plan

The core plan costs about $15.80 on Snap, about a third of the $45 hard stop. All estimates assume 8 tokens per day and a third-party price, and must be recomputed after the pilot.

| Run | Snap calls | Snap tokens | Snap cost | Neon calls | Neon tokens | Neon hours at full rate |
| --- | --- | --- | --- | --- | --- | --- |
| Pilot and format checks, including 36 latency-probe calls (2 diaries × 64K, 256K × cold, repeat, append × 3) and one ladder token-rate pair | 172 | 8.0M | $0.32 | 164 | 4.1M | 0.34 |
| R1 Steady | 780 | 16.3M | $0.65 | 1,200 | 13.0M | 1.08 |
| R2 Reversal | 4,920 | 202.5M | $8.10 | 3,240 | 26.0M | 2.17 |
| R3 Ladder | 2,160 | 169.0M | $6.76 | 1,920 | 30.8M | 2.57 |
| **Total** | **8,032** | **395.7M** | **$15.83** | **6,524** | **73.9M** | **6.16** |

Neon input at the listed price is about $3.10 in total. Separate ladder readout requests, if the pilot requires them, add $6.76. Stretch runs S1 to S3 are roughly $2.50 more on Snap; this is an estimate and was not part of the red-team check. Any money left stays reserved for reruns.

**Run order**

1. Generator, baselines, policies and analysis code, validated with no model calls.
2. Mock readers of known horizon through the full pipeline (gates below).
3. Freeze and register on OSF with a signed public tag.
4. Pilot on reserved seeds. Apply the branch table. Recompute the budget.
5. R1 on Jev and OpenJev first (cheap debugging), then Snap.
6. R2, then R3.
7. Analysis, figures, dashboard, write-up.
8. Stretch runs, each with a dated amendment.

## Build spec for the coding agent

Build in the milestone order below and do not call any paid model before milestone 2's gates pass. Everything that crosses a boundary is a pydantic model; every random choice comes from a seeded generator.

**Stack:** Python 3.12 with uv; httpx (async), pydantic v2, numpy, polars, psycopg 3, matplotlib, typer, pytest and hypothesis. Dashboard: FastAPI serving precomputed JSON plus one static page using Vega-Lite. Deploy runner and dashboard to Fly.io from one repo with two process groups.

**Repo layout**

```
sheep-wolf-bench/
  pyproject.toml  README.md  fly.toml  Dockerfile  Makefile
  docs/  PREREGISTRATION.md  SPEC.md  RESULTS.md
  configs/  pilot.yaml  r1_steady.yaml  r2_reversal.yaml  r3_ladder.yaml
  src/swb/
    diary/      worlds.py  render.py  names.py
    harness/    policies.py  tally.py
    questions/  build.py  truth.py
    baselines/  counter.py  filter.py  windows.py  mock_readers.py
    clients/    base.py  subq.py  neon_decision.py
    runner/     jobs.py  queue.py  budget.py  backoff.py
    store/      db.py  schema.sql  export.py
    analysis/   metrics.py  ladder.py  reversal.py  stats.py  figures.py
    dashboard/  app.py  static/
    cli.py
  tests/
```

**Determinism:** one root seed per run config. Derive named streams with `numpy.random.SeedSequence`: `world`, `grazing`, `sightings`, `names`, `block`, `bell`, `options`. A diary is fully defined by (config, seed); store its SHA-256 and regenerate on demand. Pilot seeds come from a reserved range.

**Client interface**

```python
class DecisionClient(Protocol):
    name: str
    model_id: str
    window: int
    async def decide(self, state: str, questions: dict[str, Question]) -> DecisionResult: ...
```

`DecisionResult` holds per-question probabilities, the reported `input_tokens`, latency in ms, HTTP status and raw JSON.

**Results table (Postgres, one row per question replicate)**

| Column | Type | Notes |
| --- | --- | --- |
| call\_id, row\_id | uuid | call groups a request; row is the primary key |
| run\_id, condition\_id | text | config name and the condition key |
| model, model\_version | text | from the response's `model` field |
| world, contrast, format, policy, vocab | text |  |
| length\_tokens\_target, input\_tokens | int | target vs. reported |
| n\_days, seed | int |  |
| reversal\_m, lag\_days, rung, pair\_side | int, int, text, text | null where not applicable; pair\_side is A or B |
| diary\_sha256 | text |  |
| question\_key, replicate, option\_order | text, int, jsonb |  |
| probabilities | jsonb | option name to probability |
| truth, truth\_empirical | text | generating truth and the diary-computed diagnostic |
| true\_rates | jsonb | tomorrow's rates, for regret |
| baseline\_scores | jsonb | counter, filter and window scores on the same diary and question |
| latency\_ms, http\_status | int |  |
| cost\_usd | numeric | Snap only, from input\_tokens |
| created\_at | timestamptz |  |

A `budget` table keeps cumulative Snap tokens and dollars; the runner checks it inside the same transaction that reserves a job.

**Validation gates (must pass before any paid call)**

- **Truth checks:** `truth` matches the generator's parameters; `truth_empirical` matches a recount by an independent parser.
- **Ceiling check:** known-structure P(hot) matches the steady table above within simulation error. Beta counter P(hot) is about 0.69 (7-point, 16K), 0.92 (7-point, 56K), 0.50, 0.61 and 0.75 (2-point at 56K, 112K, 256K).
- **Reversal check:** window and exponential readers give m* that does not change with contrast; the known-parameter filter's m* moves at least 10 times; a full-memory reader crosses below 0.7L.
- **Ladder check:** the Beta counter's report shift is flat across lags, and swapped pairs differ only inside the block.
- **Shuffle check:** shuffling preserves counts exactly and changes order.
- **Leak scan:** no rendered diary contains day numbers, or the words "hot" or "favorite". "Most dangerous" appears only in question text. No diary states which pasture is hot, except the oracle line.
- **Name check:** across 1,000 seeds, each name slot is the hot pasture about 25% of the time.
- **Token check:** rendered length is within 5% of the target, using reported `input_tokens` in the pilot. `swb calibrate` measures tokens per day per model and world from the pilot; `swb run` refuses a main config until its per-world day counts match. Every later call is rejected if it reports more tokens than the window or more than 5% away from the measured length.
- **Replay:** regenerating a diary from (config, seed) gives the same SHA-256.
- **Mock recovery:** readers with known horizon pass through the frozen pipeline and their horizon is recovered.
- **H2 null check:** a mock with one shared memory trace and saturating report and decide gains must not pass H2.

**Milestones**

1. **M0 Scaffold:** repo, config loading, database schema, CI running tests. Gate: `make test` passes.
2. **M1 Diary and baselines:** worlds, rendering, questions and truth, counters, filter, policies, mock readers. Gate: all validation gates above pass with no network calls.
3. **M2 Clients and runner:** clients, job queue, backoff, budget guard with a dry-run estimate. Gate: a mock server injecting 429, 503 and malformed responses completes a run, and the budget guard blocks a call that would exceed the cap.
4. **M3 Registration and pilot:** registration first, then about 60 calls per model plus the format checks. Gate: every branch-table check written to `docs/RESULTS.md`; budget recomputed.
5. **M4 Main runs:** R1 to R3. Gate: no unexplained gaps; every condition has all seeds.
6. **M5 Analysis:** metrics, CIs, hypothesis table, the five figures. Gate: `swb analyze` regenerates every number from the database.
7. **M6 Dashboard on Fly.io:** a benchmark page (headline chart, tabs for steady, reversal, ladder, harness, cost) and a demo panel (scroll a real diary, see what each policy hands the model, the model's probabilities, the baselines' answers). Gate: it deploys and loads under 2 seconds with precomputed JSON.

**Do not:** cache Snap responses across different requests, skip calls for conditions that "look obvious", tune prompts after seeing Snap results, change anything the branch table does not allow, or describe any result from a mock client as a finding.

## Open questions

Resolve these before M3; the coding agent should stop and ask rather than guess.

- [ ] Confirm Snap's $0.04 price with Subquadratic. Only a third-party source gives it, and the budget guard depends on it.
- [ ] Snap rate limits for this account (none published).
- [ ] Is Snap deterministic, and at what precision are probabilities returned? Answered by the pilot.
- [ ] Does Snap do prefix caching? Docs are silent, and `usage` has no cached-token field.
- [ ] Is Snap billed per request or per question? Docs are silent; K = 5 replicates assume one request is one bill.
- [ ] Neon pricing: the overview says free during private preview, while the models page requires prepaid credits. Confirm this account's status and daily cap.
- [ ] Does the Neon gateway accept the same question limits as Snap? Needed for K = 5 replicates.
- [ ] Exact tokens per diary day per tokenizer. Measured in the pilot.

## Sources

- [SubQ Decisions API docs](https://docs.subq.ai/endpoints/decisions-api/)
- [SubQ Snap 1.1 pricing (infrabase)](https://infrabase.ai/models/subq-snap-1-1)
- [Neon AI Gateway overview](https://neon.com/docs/ai-gateway/overview)
- [Neon AI Gateway decision models](https://neon.com/docs/ai-gateway/decisions)
- [Neon AI Gateway models and rate limits](https://neon.com/docs/ai-gateway/models)
- [Fly.io GPU deprecation thread](https://community.fly.io/t/gpu-migration-fly-io-gpus-will-be-deprecated-as-of-july-31-2026/27110)
- [Enough Coin Flips Can Make LLMs Act Bayesian](https://arxiv.org/html/2503.04722v2)
- [LLMs as Discounted Bayesian Filters](https://arxiv.org/html/2512.18489)
- [Can large language models explore in-context?](https://arxiv.org/abs/2403.15371v3)
- [RULER](https://arxiv.org/pdf/2404.06654.pdf)
- [Context Rot](https://www.trychroma.com/research/context-rot)
- [Lost in the Middle](https://ar5iv.labs.arxiv.org/html/2307.03172)
- [Lost in the Haystack](https://arxiv.org/html/2505.18148v1)
- [MemoryAgentBench](https://arxiv.org/html/2507.05257v2)
- [Forgetting as a Feature](https://arxiv.org/html/2601.09726v1)
- [POPGym](https://arxiv.org/pdf/2303.01859)
