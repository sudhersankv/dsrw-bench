# Results

The main runs finished on 2026-11-09. Pilot seeds are reserved and were never analysed. The hypotheses and code were frozen locally at a git tag, not publicly registered on OSF.

| Field | Value |
| --- | --- |
| Preregistration | Frozen locally at tag `freeze-2026-11-09`; not yet publicly registered. See `docs/PREREGISTRATION.md` |
| Code commit | `0148a9a` for the pilot; main runs from `ed72076` onward, with runner fixes that did not touch the diaries or scoring |
| Result dataset | Neon Postgres `results` table; parquet export via `swb export` |
| Dates run | 2026-11-09 |
| Calls | Snap 10,020 main, Jev 4,020 main, 14,040 in all |
| Snap spend | $22.88 including the pilot |

## Pilot branch table (M3 gate), Snap

| Pilot check | Measured | Failed? | Branch taken |
| --- | --- | --- | --- |
| Non-determinism | Largest difference between identical requests: 0.0 (40 probabilities) | No | One call per request |
| Coarse output | Full float precision | No | None |
| Prior bias | Largest deviation from uniform by option position: 0.036 (limit 0.15) | No | None |
| Oracle failure | P(truth) on `risk` with the answer stated: 0.864 | No | None |
| Reading control | P(hot) 0.857 on High contrast, 2,000 days (limit 0.5). Weaker than the registered 90/50/50/10 | No | None |
| Block-only check | Shift/SE from 9.0 to 51.3 across all rungs and readouts, 20 seeds (limit 5). The original 2-seed cell was too small to judge, so 18 reserved seeds were added | No | None |
| One-hot outputs | Median max probability 0.48 (limit 0.98) | No | None |
| Option-order noise | Same diary, shuffled options: P(truth) range up to 0.24 within one seed. Replicates add 1.3% tokens | Yes | Proposed: K = 5 |
| Question contamination | Joint vs. single at 64K: mean absolute difference about 0.07, largest 0.285, 6 pairs per readout. Confounded with option-order noise | Inconclusive | Proposed: separate ladder requests, +$6.76, because H2 compares these two readouts directly |
| Tokens per day | Steady and reversal 11.60; ladder 9.83; overhead about 410 to 435 tokens (assumed 8) | Yes | Recompute day counts from token targets |
| Seed count | No change | No | None |
| Token check (rendered length within 5% of target) | 16K target reported about 24,200 tokens at the 8-per-day assumption | Yes | Fixed by recomputing day counts; `swb run` refuses paid runs until calibrated |

**Latency probe (exploratory).** Median latency at 256K tokens: cold 1,238 ms, repeat 1,239 ms, append 1,298 ms. At 64K: 858, 862 and 840 ms. This client-side probe shows no sign of prefix caching.

## Pilot results for Jev and OpenJev

| Check | Jev | OpenJev |
| --- | --- | --- |
| Non-determinism (identical calls) | Up to 0.12: failed; K = 5 replicates stand in for averaging | Up to 0.05: failed |
| One-hot outputs | Median max 0.99: failed; scored top-1 only | Median max 0.705: passed |
| Prior bias | 0.033: passed | 0.173: **failed, stop and report** |
| Reading control | P(hot) 0.792: passed | P(hot) 0.395: **failed, stop and report** |
| Real limits | Rejected above about 33,000 tokens, despite 65,536 listed | Reported usage appears to count the diary once per question (about 12 tokens per day per question) |

OpenJev is excluded from the main runs by the pre-set rule. A burst of requests caused gateway limit errors on OpenJev, which the runner first misread as a spending cap.

## Recomputed budget

Lengths are set in tokens, so the main-run token targets and costs stay close to plan while day counts fall. The 32,000-day reversal diary would need about 371,600 tokens, over Snap's 353,894 usable window, so it becomes about 22,000 days (256K tokens).

| Run | Cost |
| --- | --- |
| Snap, main runs (actual) | $22.42 |
| Snap, including pilot (actual) | $22.88 |
| Jev, main runs at list price | about $1.93 |

## Run completeness (M4 gate)

| Run | Model | Conditions expected | Conditions complete | Seeds per condition | Gaps explained |
| --- | --- | --- | --- | --- | --- |
| R1 | Snap, Jev | all | all | 30 | none |
| R2 | Snap, Jev | all | all | 30 | 59 Snap calls failed and were retried successfully |
| R3 | Snap, Jev | all | all | 20 | 3 Snap calls failed once and were retried successfully |

Jev ran whole diaries only up to about 16K tokens, because of its real limit.

## Confirmatory hypotheses (Snap, Holm over three)

| ID | Verdict | Effect | 95% CI | Holm p |
| --- | --- | --- | --- | --- |
| H1 | Not supported | +0.018 raw minus last 1,000 days, P(hot) | -0.002 to 0.040 | 0.080 |
| H2 | Untestable | Report answer saturated: stronger evidence moved it 0.46x as far as weaker evidence | | |
| H3 | Not supported | +0.024 last 1,000 days minus raw, P(new), below the 0.05 threshold | 0.004 to 0.049 | 0.028 |

## Descriptive results

### Steady: growth curves and effective evidence

Snap's P(hot) stayed flat from 0.33 at 1K to 0.30 at 56K (7-point), and was 0.27 at 256K (2-point, chance 0.25). A Beta counter reached 0.79 and 0.67. Given a four-row all-time table, Snap reached 0.71 and 0.55. Jev stayed at about 0.37 to 0.39 at up to 16K, top-1 only.

### Reversal: crossover m* by contrast

On the 256K diaries, Snap's new-minus-old margin ranged from -0.04 to +0.04 (7-point), and from -0.21 to +0.16 (High). Crossover was about 3,200 days (7-point) and about 5,900 days (High). With the margin this close to zero the 7-point crossover is noisy, and it did not shrink with the larger contrast as change detection would predict. The last 1,000 days reached +0.06 and +0.23. A change-point filter reached +0.82 and +0.99.

### Ladder: report and decide by rung and lag, and `find`

At 128K tokens, `find` was 0.91 to 0.99 at every lag up to 12,921 days. Report shift for a single clue was about 4 nats and did not fade with distance. Decide shift for a single clue was 3.7 to 5.3 nats. With nine sightings, report shift was five to seven times decide shift at every lag. The oldest clues had the strongest effect. The old-clue sub-scores are capped at 100 for this reason, and they mean no fading rather than a strong effect.

### Harness: rescue, value added and cost

Snap's rescue from the all-time table was +0.20 on average, with value added -0.04. From the last 1,000 days, rescue was +0.03. The table cost about 650 tokens per decision. Cost figures per sheep life assume 8 tokens per diary day; the measured rate was 11.6.

### Cross-model comparison at 16K

Descriptive only. Snap's shared-length Flock score is 45. Jev has none, because it is top-1 only and two sub-scores cannot be computed.

### Calibration on belief questions (exploratory)

Not produced for this run.

## Deviations and amendments

The runner was patched during the main runs for database speed, gateway-limit retries and the token check. None of these changed diaries, questions or scoring. See the Amendments table in `docs/PREREGISTRATION.md`. The block-only check was extended from 2 to 20 reserved seeds after the first pilot run, at a cost of under $0.01.
