# Preregistration

Does the Sheep Remember the Wolf? Long context vs. harness memory in decision models.

Status: **frozen locally on 2026-11-09 (tag `freeze-2026-11-09`, hashes in `docs/FREEZE.txt`), not yet publicly registered.** This file is drawn from `docs/SPEC.md` (v2). The spec calls for public registration before any Snap call. The Snap pilot ran before it, as recorded under Amendments. Public registration must happen before the main runs.

| Field | Value |
| --- | --- |
| OSF registration link | |
| SHA-256 of this file and the analysis code | |
| Signed public tag | |
| Date frozen | |

**Disclosure:** Snap credits come from Subquadratic. Results are published whatever they show.

## Research questions

1. **Use of history:** does a decision model extract more from a diary as it grows, beyond what recent days offer?
2. **Staleness:** when the world reverses, does the full diary mislead the model, and does it detect change or simply have a fixed horizon?
3. **Harness:** when does a recent window or a code-made tally rescue the model, what does the model add over the code, and at what cost?

## Confirmatory hypotheses

Tested on Snap, with Holm correction over these three at family-wise alpha 0.05.

| ID | Hypothesis | Test |
| --- | --- | --- |
| H1 | History beyond the last 1,000 days adds information | 2-point steady, 256K tokens, `risk`: raw minus W1000 on P(hot) is at least 0.05, and greater than 0 after correction (known-structure ideal is about 0.8 vs. 0.3) |
| H2 | The model can report evidence that it no longer acts on | 128K tokens, statistical rung, lags k ≥ 100, clip 1e-6: mean over lags of RK(report) minus RK(decide) exceeds a 0.15 margin after correction. Precondition: at lags 1, 3, 10 each answer's shift on the statistical rung is at least 1.2× its shift on the n = 9 rung; otherwise H2 is untestable |
| H3 | After a reversal, a recent window beats the full diary | 7-point reversal, 256K tokens, m = 2,000 days, `current`: W1000 minus raw on P(new) is at least 0.05, and greater than 0 after correction |

H3 is expected to fail if the model already discounts heavily (simulated power is 1.00 if raw half-life is at least 3,000 days and at most 0.11 at 1,000 or below). That outcome means the model adapts without help, and it is reported as such.

Each hypothesis is reported as supported, not supported, or untestable, with effect sizes. H2 is untestable if RK is unavailable: RK is computed only when the shift/SE of its denominator is at least 5. Negative results are reported in full.

Any hypothesis is untestable unless every condition it uses has all its registered seeds (H1 30, H2 20, H3 30). A partial run never gets a verdict.

m = 2,000 is run as an extra R2 cell for H3 (`configs/r2_reversal.yaml`), because the geometric grid for L = 32,000 does not contain it. If that cell is missing, H3 is untestable.

## Descriptive results

Labelled as such, and supporting no hypothesis: growth curves and effective evidence, reversal crossover m* by contrast, the report × rung × lag surface, `find`, table reading, cross-model comparison at 16K, rescue and value added, and calibration on belief questions. The scores in `docs/SCORING.md` are also descriptive.

## Statistics

The unit is the seed (one sheep life), and a swapped pair is one seed. Report the mean and a 95% studentized bootstrap CI with 10,000 resamples over seeds. Differences are paired by seed. Every test not listed as confirmatory is labelled exploratory.

## Pilot branch table

The pilot uses reserved seeds that are never analysed. It may change only the items below. Metrics, thresholds, contrasts, exclusions and lengths are frozen. Any amendment is dated before the main run.

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

**Known deviation to resolve before freezing.** `configs/pilot.yaml` runs the reading control on the High contrast (45/25/25/5), because no 90/50/50/10 contrast exists in the code. Either add that contrast or amend the check here.

## Registration steps

1. Resolve the open questions in `docs/SPEC.md` and the two items flagged above.
2. Confirm `swb gates` passes and the mock pipeline has run.
3. Freeze the hypotheses, thresholds and analysis code.
4. Register on OSF and fill in the link above.
5. Put the SHA-256 in a signed public tag. A git timestamp alone is not sufficient given the credit disclosure.
6. Only then make the first Snap call, which is the pilot.

## Amendments

Each amendment is dated before the run it affects.

| Date | Change | Reason |
| --- | --- | --- |
| 2026-11-08 | H2 precondition added: each answer's response must still grow with evidence at short lags. | A shared memory trace with unequal saturating gains passed the 0.15 margin in simulation, which the spec's H2 null check forbids. Status: drafted before any model call, to be confirmed at freeze. |
| 2026-11-08 | Every hypothesis requires its full registered seed count. | A verdict from a partial run would not be the registered test. |
| 2026-11-08 | m = 2,000 added to R2 at L = 32,000 (7-point), raw and W1000. | H3 is registered at a swap age the geometric grid does not contain. Adds 60 Snap calls, about $0.31. |
| 2026-11-08 | Ladder tokens per day measured separately in the pilot and enforced per world. | Ladder days are mostly short "Fog." lines, so one rate overstated their real context size. |
| 2026-11-09 | Deviation: the Snap pilot ran after a local freeze but before OSF registration, on the project owner's instruction. | Pilot seeds are reserved and never analysed, and it may change only branch-table items. Main runs had not started. |
| 2026-11-09 | Deviation: the pilot's reading control used High (45/25/25/5) rather than 90/50/50/10. | The code has no 90/50/50/10 contrast. This makes the reading control a weaker check. |
| 2026-11-09 | Main runs proceed without OSF registration, on the project owner's instruction. | Results may be described as frozen locally, not as publicly preregistered. |
| 2026-11-09 | Branch applied: K = 5 option-order replicates per request. | Option order moved Snap's answer by up to 0.24. Replicates add 1.3% tokens. |
| 2026-11-09 | Branch applied: ladder report (with find) and decide go in separate requests. | The pilot could not rule out priming, and H2 compares these two readouts. |
| 2026-11-09 | Branch applied: day counts recomputed from Snap's measured rate (11.60 tokens per day, 9.83 on the ladder). All models read the same diaries. | The 8-per-day assumption was wrong. R2's longest diary is about 22,000 days (256K tokens), since 32,000 days exceeds Snap's usable window. |
| 2026-11-09 | Branch applied: OpenJev is excluded from the main runs. | It failed two stop-and-report checks: reading control P(hot) 0.395 (minimum 0.5) and prior bias 0.173 (limit 0.15). |
| 2026-11-09 | Token check, applied during the main run: a call may report up to 10% fewer tokens than expected, and more when it asks several questions. | Snap's ladder diaries at 128K varied with the random pasture names and reached 5.6% below the average, with no sign of truncation. Day counts are unchanged. |
| 2026-11-09 | Jev runs at about 33,000 tokens or less, and is reported top-1 only. | The gateway rejected longer requests despite the listed 65,536 window. Median max probability was 0.99, above the 0.98 one-hot limit. Identical calls differed by up to 0.12, so K = 5 replicates stand in for averaging three calls. |
