# Results

The Snap pilot has run. Jev and OpenJev have not, because the Neon gateway refused the token. No main run has started. Pilot seeds are reserved and never analysed, so nothing below is a finding about any model.

| Field | Value |
| --- | --- |
| Preregistration | Frozen locally at tag `freeze-2026-11-09`; not yet publicly registered. See `docs/PREREGISTRATION.md` |
| Code commit | `0148a9a` for the pilot |
| Result dataset | Neon Postgres `results` table, `run_id = pilot` |
| Dates run | Pilot: 2026-11-09 |

## Pilot branch table (M3 gate), Snap only

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

## Recomputed budget

Spent so far: 11.57M Snap tokens, $0.46.

Lengths are set in tokens, so the main-run token targets and costs stay close to plan while day counts fall. The 32,000-day reversal diary would need about 371,600 tokens, over Snap's 353,894 usable window, so it becomes about 22,000 days (256K tokens).

| Run | Snap cost, approximate |
| --- | --- |
| R1 to R3, as planned | $15.50 |
| Separate ladder requests | +$6.76 |
| K = 5 replicates (+1.3% tokens) | +$0.30 |
| **Total for main runs** | **about $22.60** |

## Run completeness (M4 gate)

| Run | Model | Conditions expected | Conditions complete | Seeds per condition | Gaps explained |
| --- | --- | --- | --- | --- | --- |
| | | | | | |

## Confirmatory hypotheses (Snap, Holm over three)

| ID | Verdict | Effect | 95% CI | Holm p |
| --- | --- | --- | --- | --- |
| H1 | | | | |
| H2 | | | | |
| H3 | | | | |

## Descriptive results

### Steady: growth curves and effective evidence

### Reversal: crossover m* by contrast

### Ladder: report and decide by rung and lag, and `find`

### Harness: rescue, value added and cost

### Cross-model comparison at 16K

### Calibration on belief questions (exploratory)

## Deviations and amendments

See the Amendments table in `docs/PREREGISTRATION.md`. The block-only check was extended from 2 to 20 reserved seeds after the first pilot run, at a cost of under $0.01.
