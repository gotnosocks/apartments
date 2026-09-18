# Chelsea amenity estimate stability

The doorman point estimate is **not stable to building shrinkage**: the fitted
full-time-versus-part-time contrast changes from −1.72% to +6.93% across the
predeclared settings. Laundry remains positive but ranges from +2.80% to +6.80%.
Better held-out prediction has not established a single reliable marginal premium
for either feature. These results qualify the earlier
[recovery and prediction comparison](chelsea-recovery-ablation-2026-09-18.md).

## Matched model sensitivity

Twenty fits compare ten specifications on two unchanged v4 train/test partitions:
the 2024 annual holdout and one crossed 2024/unseen-building holdout. Building
penalties are 1, 10 and 100, with and without unit effects; additional specifications
vary unit and amenity penalties around the existing defaults. The
[method](../model/amenity-uncertainty.md) explains why building/unit controls and
their effective shrinkage cannot be separated by this comparison.

The following ranges use the same **43,097 pre-2024 training unit-months** for all
ten specifications. They are ranges across model settings, not confidence intervals.
Dollar ranges apply the fitted percentages to a $4,000 reference rent while holding
other encoded inputs fixed.

| Known-category comparison | Earlier default point estimate | Range across settings | Dollar range at $4,000 |
| --- | ---: | ---: | ---: |
| Building → in-unit laundry | +4.93% | +2.80% to +6.80% | +$112 to +$272 |
| Part-time → full-time doorman | +2.07% | −1.72% to +6.93% | −$69 to +$277 |
| Pets prohibited → allowed, restrictions unknown | +1.48% | +1.04% to +4.17% | +$42 to +$167 |
| Pets prohibited → approval required | +2.48% | +1.11% to +5.31% | +$44 to +$212 |
| Room → central AC | −0.77% | −1.01% to −0.63% | −$40 to −$25 |

The sparse room-AC sample and retrospective source classifications still preclude
interpreting its negative association as a causal discount. Directional robustness
across these settings alone is insufficient evidence of a real market preference.
The doorman contrast is particularly weakly identified: only six buildings and
two units report both categories in this training cohort.

Prediction tradeoffs also depend on the target. With unit effects, weakening
building shrinkage from 10 to 1 improves the 2024 annual median error from 7.59%
to 7.03%, but worsens the crossed unseen-building error from 14.84% to 17.38%.
Strengthening it to 100 produces 8.45% annual error and 13.50% crossed error.
The crossed test here contains 548 rows from 112 buildings in one predeclared
fold. These reused development results do not justify selecting a new global
winner or promising its performance on unseen future data.

The immutable experiment is `data/model/chelsea-amenity-sensitivity-20260918`.
Its `summary/report.json` contains every setting, support count and metric.
`grid-verification/verification.json` independently checks all twenty results
against their intended split/settings/row counts and completion hashes.

Review found a checkpoint-identity gap in the first runner: a valid same-protocol
checkpoint copied into another setting directory could substitute the wrong fit.
No such substitution occurred in this experiment; every grid cell was independently
verified. Runner v2 binds checkpoints to split, complete specification and membership
hashes, rejects swapped valid checkpoints, and snapshots its implementation in a
checksummed bundle. The original v1 implementation is preserved under the existing
experiment's `implementation/` directory. Changed runner versions require a fresh
output directory; completed scientific artifacts remain immutable.

## Numerical error versus model assumptions

Twelve tighter fixed-objective refinements of the original model and the weak/strong
building specifications change all fifteen checked category contrasts by at most
**0.000292 percentage points**. That is far too small to explain the ranges above.
Mean held-out prediction changes are at most $0.107 across the three checks.
The [numerical diagnostic](../model/amenity-solver-diagnostic.md) retains exact
stationarity, objective and prediction comparisons without replacing any model.

## Building-resampling experiment

A separate fixed-seed 200-draw cluster bootstrap completed in
`data/model/chelsea-amenity-building-bootstrap-20260918`. All 200 fits converged,
and all five contrasts were estimable in every draw. The completed summary and an
unchanged replay were verified. It resamples whole training buildings, clones
repeated building/unit identities independently, and refits the complete fixed
estimator, including its encoder.

| Known-category comparison | 2.5th percentile | Median | 97.5th percentile | Positive draws |
| --- | ---: | ---: | ---: | ---: |
| Building → in-unit laundry | +3.17% | +4.85% | +7.19% | 200/200 |
| Part-time → full-time doorman | −1.59% | +2.00% | +5.57% | 168/200 |
| Pets prohibited → allowed, restrictions unknown | −0.32% | +1.46% | +3.22% | 188/200 |
| Pets prohibited → approval required | +0.53% | +2.65% | +5.54% | 199/200 |
| Room → central AC | −3.79% | −0.76% | +2.26% | 61/200 |

Laundry's positive direction survives both checks. Doorman crosses zero under
both model-setting changes and building resampling. The negative room-to-central
AC point estimate is not directionally stable under building resampling, despite
its stable sign across the ten settings. A tighter numerical check of bootstrap
replicate zero changes its five contrasts by at most 0.000358 percentage points.

These percentiles describe sampling stability conditional
on the selected regularized algorithm and captured-building sample. They do not
cover the model-setting variation above, regularization bias, source errors,
selection of advertised properties, or shared market shocks. They are neither
causal estimates nor calibrated population confidence intervals.

The separate [feature-family comparison](chelsea-feature-blocks-2026-09-18.md)
finds that elevator/floor information supplies most of the known-value prediction
gain. A stable laundry contrast does not imply a large incremental prediction gain
for previously unseen buildings.
