# Floor priors and support stability

The selected model has **349 observations with known advertised floor labels out
of 52,863**. Only **two of the 172 current listings** have such labels. Its 18
observed levels create 17 floor increments; ten adjacent observed-level pairs
have no building represented at both endpoints. These counts use the selected,
reviewed source and the model's canonical floor normalization.

The current representation assigns an independent Normal prior with log SD 0.15
to every jump between observed labels. That is a prior on successive *observed
levels*, rather than on every integer label step. Missing support therefore changes
the prior: the earlier removal of floor 9 replaced the sum of two independent
increments for 8→10, SD 0.2121, with one increment, SD 0.15. This is a 29.3%
reduction in SD caused by support membership, separate from the corrected data.

## Alternative prior calculations

The new audit evaluates two integer-step alternatives. If each integer-label
increment has independent Normal SD `s`, summing a gap of `d` steps gives SD
`s * sqrt(d)`. Summing those increments into one coefficient per observed gap
preserves the exact multivariate prior on observed endpoint contrasts. It need
not add unidentifiable coefficients or sample every unobserved integer step.

One alternative keeps `s = 0.15`. The other chooses `s = 0.097788` once, from the
selected source, to match the current 1→41 prior SD of 0.6185. That second choice
matches only the overall range, not every local prior. Its scale stays fixed in
the support-removal checks; recalibrating it after each exclusion would reintroduce
support dependence.

| Listed-label contrast | Current observed-step prior SD | Integer-step SD 0.15 | Integer-step, matched range |
| --- | ---: | ---: | ---: |
| 1→2 | 0.1500 | 0.1500 | 0.0978 |
| 8→10 | 0.1500 | 0.2121 | 0.1383 |
| 11→14 | 0.1500 | 0.2598 | 0.1694 |
| 28→41 | 0.1500 | 0.5408 | 0.3526 |
| 1→41 | 0.6185 | 0.9487 | 0.6185 |

All values are prior log-price standard deviations, not estimated premiums.
Every possible single interior-level removal is checked. Integer-step priors
preserve the retained endpoint covariance, while observed-step priors change it.
A separate dense expansion of all 40 integer thresholds verifies the aggregation
algebra. Fourteen tests cover that equivalence, removal stability, range matching,
negative/ground labels, translation invariance and invalid inputs.

## What this means for the model

Neither integer-step alternative has been fitted or selected. Label distance is
not physical height: skipped floor numbering remains a separate measurement
problem. A wider prior over a large numerical gap is an assumption to test, not
evidence of a larger physical premium. Contrast-prior invariance also does not
make the full joint prior invariant when cohort centering, missingness, intercept
or building/unit populations change.

The archived selected posterior still associates 11→14 with −12.68%
[−22.44%, −1.36%] and 14→15 with +16.12% [+2.07%, +31.73%]. Both comparisons
lack shared endpoint buildings, and floor 14 has only two units in two buildings.
The 28→41 comparison has one unit at each endpoint and no shared building; its
posterior is +0.64% [−16.45%, +21.61%]. These are conditional associations under
the existing model. The prior audit checks the archived summaries' hashes; it
does not reread their posterior draws or repeat convergence diagnostics.

The 210-exclusion price-basis source refit should retain the existing floor
prior so its comparison isolates the source change. Subsequent floor research
should compare a floor-reporting-only model with the observed-step model and
these explicit prior alternatives, using common observations and joint floor
contrasts. Improvements in training residuals alone do not justify the 17
increments. Broader reviewed floor measurement is particularly valuable given
the two known current floor labels; an inferred unit-label candidate must remain
distinguishable from a direct source statement.

Artifact: `data/model/chelsea-floor-prior-stability-20260919`. It binds the
selected source, fit/protocol manifests and the exact audited design/contrast
files. The selected model, its source and the running sampler are unchanged.

```sh
UV_CACHE_DIR=/tmp/apartments-uv-cache OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  uv run --frozen --no-sync python -m models.floor_prior_stability \
  --output data/model/chelsea-floor-prior-stability-20260919
```
