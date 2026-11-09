# How the scores are calculated

Scores on a model card describe one model. They are descriptive and support no hypothesis. The confirmatory tests are H1, H2 and H3 in `SPEC.md`, reported separately on the card.

Every score uses the `raw` policy (the model reads the whole diary) unless stated. The unit is the seed. Ratios are ratio of means across seeds. Confidence intervals are 95% studentized bootstrap over seeds, 10,000 resamples for final results (2,000 is acceptable in demo mode). A score is clipped to 0 to 100.

A cell counts only if the ceiling is at least 0.20 above chance (`ceiling − 0.25 ≥ 0.20`). A score with no usable cells is `null` and shows as "not testable", never as zero.

| Sub-score | Test | Calculation |
| --- | --- | --- |
| **Uses history** | Steady | 100 × mean(P_model(hot) − 0.25) / mean(P_beta(hot) − 0.25) on `risk`, pooled over usable cells the model fits. `P_beta` is the Beta counter's posterior |
| **Adapts** | Reversal | 100 × mean(P_model(new) − 0.25) / mean(P_filter(new) − 0.25) on `current`, pooled over the usable cells among the nine m values, both contrasts and the lengths the model fits. `P_filter` is the Bayesian-averaged change-point filter |
| **Recalls** | Ladder | 100 × mean of RK(report) over lags k ≥ 100, statistical rung, longest L the model fits |
| **Acts on old evidence** | Ladder | 100 × mean of RK(decide), same cells as Recalls |

**Flock score** = mean of Uses history, Adapts and Acts on old evidence. It is null unless all three exist. Recalls is shown beside it but excluded, because the gap between Recalls and Acts is the finding, not a virtue.

**What Adapts covers.** The usable-cell rule keeps only swaps the filter has already detected, so short swaps drop out where stale evidence matters most. On the R2 grid about 14 of 36 cells survive at L = 2,000 and 8,000 days and 9 of 18 at L = 32,000 days. No 7-point cell survives at L = 2,000 days (the only reversal length Jev and OpenJev fit), so their Adapts is high-contrast only. The card's `how` note states how many cells were dropped.

**Reference lines.** Uses history and Adapts are measured against code (a Beta counter and a change-point filter). Recalls and Acts are measured against the model's own response to a fresh clue, so a weak but flat model can score 100 on them. None of these references is a true ceiling.

**RK(k)** = mean ladder shift at lag k ÷ mean shift over the three shortest lags (1, 3, 10). The shift is half the difference in (log πA − log πB) between the swapped diaries, clipped at 1e-6. If the denominator's shift/SE is below 5, RK is unavailable and the cell is "unmeasurable".

**Comparing models.** Models with larger windows are tested on more lengths. The leaderboard therefore ranks models on the shared lengths only (`shared_length_tokens`). Each card scores every length that model fits and shows both numbers: all-lengths Flock and shared-length Flock.

**Verbalized models** (adapter `openai_chat`) give one answer instead of probabilities. Their probabilities are one-hot, so log-odds shifts are not meaningful: Recalls and Acts are `null`, and the card says "top-1 only".

**Demo data.** Any card built from mock readers has `is_demo = true` and carries a visible "DEMO DATA, NOT A MODEL RESULT" stamp on the site and in the downloaded image.
