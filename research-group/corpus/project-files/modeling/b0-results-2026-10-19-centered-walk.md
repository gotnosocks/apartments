# Centered walk results (2026-10-19)

**Run:** `centered-walk-b0-latest-6846d213-dense-w1500`. Fit-only, with the same data and settings as B0.3. The only change is the trend walk: it is now centered, with Student-t shocks.

- Commit: 6846d213, from [PR #1154](https://github.com/gotnosocks/apartments/pull/1154), tag archive/pr-1154.
- Hardware: A100-80GB.
- Wall time: 22.8 min, of which the fit took 22.4 min.
- Cost: about $0.90 (estimate).
- Divergences: 0 while sampling, 291 during warmup (B0.3 had 618 in warmup).

**Verdict:** The run did not converge. Most R-hats improved a lot, but the intercept got worse. The cause is in the model's structure, not the sampler (see below).

## R-hat compared with B0.3

| Term | B0.3 | Centered |
|---|---|---|
| tau | 2.23 | 1.30 |
| g (drift) | 4.82 | 1.08 |
| intercept | 2.21 | **4.01** |
| weekly levels (median / worst) | 2.20 / 3.53 | 1.31 / 1.73 |
| season (4 terms) | 3.3–4.6 | 2.8–4.6 |
| bath pools (+1 / +2 / +3 / −1) | 6.21 / 5.92 / 4.54 / 2.82 | 2.12 / 1.47 / 1.46 / 1.28 |
| bath steps, worst | 3.29 | 1.04 |
| s_bath | 1.93 | 1.20 |
| bed steps, flags, sigma, nu | < 1.02 | 1.08–1.16 (worse) |

## tau

- tau's median is 0.0092, with a 90% interval of 0.0079–0.0106. B0.3 gave 0.0335.
- The chain medians run 0.0086–0.0102, so tau is no longer stuck at its starting value.
- The realized shock spread is 0.012 a week, against 0.007 in B0.3. Part of the extra wiggle is yearly cycle that the walk takes over from the season terms.

## Scorecard against the written predictions

| Prediction | Result |
|---|---|
| tau between 0.006 and 0.008 | **Miss:** 0.0092 |
| R-hat < 1.01 on tau, levels, intercept and g | **Miss on all four:** 1.30, up to 1.73, 4.01 and 1.08 |
| +1 bath pool still fails | Hit: 2.12 |
| Season possibly still > 1.1 | Hit: 2.8–4.6 |
| Wall time ≤ 27 min | Hit: 22.8 |
| No sampling divergences | Hit: 0 |

## Cause

1. **The intercept and the level curve trade one for one.** Across chains, the correlation between each chain's mean intercept and its mean trend level is −1.00. Their sum varies about 80 times less than either term does alone.
   - Only week 0's level is fixed, at zero. Shifting every later week up and the intercept down by the same amount changes the fit very little.
   - The only thing resisting that shift is the walk's first step, and that resistance is weak when tau is about 0.01.
   - Each chain settles at a different point along that line. The bed steps are tied to the intercept, so they drift with it too.
2. **The season and the walk trade off.** The walk can draw the yearly cycle on its own. Season amplitude runs 0.035–0.046 across chains, against 0.023–0.032 in B0.3.
   - Each chain's trend curve differs from the 16-chain average by 0.0036. Adding each chain's intercept brings that to 0.0028, and adding its season brings it to 0.0007.
   - So the chains agree on the total; they just split it differently between trend, intercept and season.

Visual explainer: https://claude.ai/artifact/1AKeB5KvrUXFs6QbRmsE1h

## Candidate next changes (one per fit)

- Anchor the level curve where the data pin it down. Either:
  - make the weekly levels sum to zero and keep the intercept, or
  - drop the intercept and let the levels carry it.
- Stop the walk from absorbing the yearly cycle. This needs a separate change.
