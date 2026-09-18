# Historical robust analysis workflow

This document preserves earlier experiments. The main model is now the PyMC
Bayesian posterior; see [current analysis](current-analysis.md). References below
to the main model describe the historical workflow at the time of those experiments.

# Refit current evidence, then analyze contributions and residuals

The main workflow is scrape → transform → fit → analyze. Forecasting and
unseen-building transfer are secondary diagnostics. The examples below support
iterative research rather than prescribing a fixed set of renter-facing features.

The [interactive review page](analysis-review-page.md) reads the latest reviewed
model, its exact dataset and residuals. It brings source descriptions, grouped
contributions, apartment history and supported joint feature comparisons into
one read-only view. Unsupported or reporting-only changes remain explicit.

## Fit the latest supplied observations

```sh
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 \
  .venv/bin/python -m models.fit_robust_analysis \
  --historical-dataset data/exports/chelsea-serving-history-20260918-asof1600 \
  --current-snapshot data/probes/chelsea-candidate-refresh-20260918/snapshot \
  --output data/model/chelsea-current-analysis-20260918 \
  --as-of 2026-09-18T17:37:26Z --max-age-days 1
```

This versioned analysis fit uses historical own-advertisement initial asks for
months before the analysis month, and the latest eligible ACTIVE captures for the
current month. Current rows are selected without budget or preference filters.
They must satisfy the existing rent/layout support and freshness checks. A unit
contributes at most one observation per month. Inactive captures do not become
new current-month market asks, and current attributes are not copied backward
onto historical rows.

The two price sampling rules are explicit in every row and the dataset manifest:
historical initial asks versus current capture-time asks. The latter may reflect
price reductions or listing survival. That distinction should be examined in
modeling iterations; combining the rows does not erase it.

The command publishes a verified analytical dataset and refits the existing
robust log-rent specification, including current buildings and units. It preserves
the fitted encoding, coefficients, source membership, current capture IDs,
layout support and convergence checks. Portable fitted values must agree with
the scientific encoder for every training row at that row's own month. Exact
replay reuses the completed fit. New evidence or policies need a new output path.

This analysis model permits the current month in fitting. It is separate from
the earlier next-month serving fit and does not inherit that model's forecast
age restriction or claim a new holdout score. The supplied fresh snapshot may
still cover only a small part of Chelsea; refitting cannot repair missing
collection coverage.

## Generate a source-linked residual queue

```sh
.venv/bin/python -m models.residual_review \
  --model data/model/chelsea-current-analysis-20260918/model \
  --dataset data/model/chelsea-current-analysis-20260918/dataset \
  --output data/model/chelsea-residual-review-20260918 --top-units 20
```

The dataset must match the model's exact verified training manifest. Residuals
are **in-sample fitted diagnostics**, intentionally including the apartment's own
price evidence. Positive `asking_minus_fitted` means the ask exceeds the fitted
value. `asking_vs_fitted_percent` divides that difference by fitted rent;
`log_residual` is `log(ask/fitted)`.

The queue contains the 20 largest positive and 20 largest negative log residuals,
with distinct units within each tail, plus every current capture. This prevents
repeated advertisements for one apartment from consuming the whole review queue.
Each entry retains the original model input, source advertisement, canonical unit,
capture references, fitted value, grouped and detailed log contributions, and
review status. Full-cohort residuals and factor-support metadata are also saved.

Contributions sum to **log fitted rent**. Building/unit offsets, date effects,
layout, size, amenity terms and missingness are shown separately. Those terms
describe the fitted parameterization; centering and shrinkage mean a term's
standalone dollar interpretation is not unique. For a marginal contrast, re-encode
both the reference and changed apartment with `RobustPricingModel.marginal_contributions`.
That recomputes interactions and bedroom-dependent size normalization. Keep the
reference apartment/date, unknown-value warnings and held-fixed assumptions
visible. Existing contrast sensitivity and building-resampling studies remain
useful evidence about feature interpretation.

## Use residuals to improve the model

Inspect immutable source evidence before deciding what a large residual means.
Useful distinctions include source price-entry changes, extraction mistakes,
wrong apartment identity, nonresidential use, unusual lease/price terms, missing
features and unexplained market variation. Large fitted building/unit offsets
can also absorb omitted features, so a small residual does not prove complete
feature coverage.

Record findings separately from the automatic queue. Apply supported data edits
through versioned overlays, or test a conservative extraction/cohort change when
the mechanism recurs. Preserve raw prices, old interpretations and unresolved
cases. Refit and inspect changes in both residual structure and feature contrasts,
including cases beyond those that motivated the change. Never infer a replacement
price merely because it would reduce model error.

The [first residual-driven source audit](../analysis/chelsea-residual-review-2026-09-18.md)
found rapid source price corrections, explicitly commercial listings, a location/
net-effective conflict, and plausible omitted apartment features. It illustrates
why residual review should guide the next modeling iteration.

The subsequent [cohort revision and matched refit](../analysis/chelsea-reviewed-cohort-2026-09-18.md)
quarantines source-evidenced scope/price-basis issues through a separate decision
bundle. `models.refit_analysis_revision` requires decisions bound to the exact
parent dataset, retains quarantined rows and reasons, and compares both models
on the same retained observations. This separates membership changes from fitted
value and feature-contrast sensitivity.

The [interior-evidence iteration](../analysis/chelsea-interior-evidence-2026-09-18.md)
screens ceiling measurements, multi-level layouts, floor-through wording and
skylights across the cohort. Reviewing residual matches uncovered four more
scope/lease-term problems. The latest analysis fit is
`data/model/chelsea-reviewed-analysis-20260918-v3`; its residual queue is
`data/model/chelsea-interior-reviewed-residuals-20260918`. Interior matches remain
review evidence pending feature-scope and missingness-controlled comparisons.

The subsequent [interior model experiment](../analysis/chelsea-interior-model-2026-09-18.md)
completed those comparisons under three group penalties. Known ceiling/level
values add little beyond reporting; the level contrast has sparse within-building
support and overlaps with private outdoor/luxury features. The nine fits and
changed-residual review remain separate research artifacts. The main reviewed
analysis model remains `chelsea-reviewed-analysis-20260918-v3`.

The [outdoor contribution experiment](../analysis/chelsea-outdoor-model-2026-09-18.md)
adds source-linked private/shared type evidence and compares two acceptance
policies across 18 matched fits. Private-space contrasts depend materially on
source policy. Review of the largest fitted changes finds ambiguous structured
labels and genuine access wording missed by strict text rules. Both experiments
remain separate from the main reviewed model; outdoor area is not yet modeled.

The [outdoor scope follow-up](../analysis/chelsea-outdoor-scope-2026-09-18.md)
measures private wording, apartment access, shared facilities and views as separate
source occurrences. A fresh 25-unit evaluation finds missed access claims and
ambiguous building-garden entries classified as private. These measurements are
held for review; they do not become model inputs. Temporary closures and area
exclusions also need separate interpretation before the next contribution fit.

The next [Bayesian research round](bayesian-feature-research.md) estimates joint
coefficient and group uncertainty on the current cohort, with separate full/half
bathroom increments and bedroom-relative bathroom shortfall. The [bathroom audit](../analysis/chelsea-bathroom-evidence-2026-09-18.md)
recovers explicit counts and reviews en-suite wording; the [group-effect audit](../analysis/chelsea-group-effects-2026-09-18.md)
finds shared facilities, basement position, flexible/railroad bedrooms and bundled
luxury features behind several extreme offsets. These are separate research
artifacts. Sampling diagnostics and source-policy sensitivity must be assessed
before promoting uncertainty estimates to the analysis page.
The [first converged fit](../analysis/chelsea-bayesian-bathrooms-2026-09-18.md)
now passes parameter and derived diagnostics. Its research report remains separate:
the [stronger-feature-prior comparison](../analysis/chelsea-bayesian-prior-sensitivity-2026-09-18.md)
is complete, while source sensitivity, group-prior sensitivity and larger-apartment
residual dispersion still need work.
The separate [Bayesian research page](bayesian-research-page.md) displays the
accepted intervals, direct prior comparisons and all 13 current residuals. The
[bedroom-scale experiment](../analysis/chelsea-bayesian-residual-scale-2026-09-18.md)
failed its parameter convergence gate; its uncertainty estimates remain withheld.
