# Chelsea: which amenity families improve predictions?

Elevator and floor information supplies most of the extra prediction benefit from
known amenity values. Laundry has a stable positive fitted contrast in the full
model, but adding laundry values alone does not clearly improve prediction for
previously unseen buildings. Predictive usefulness and contrast stability answer
different questions.

The [matched experiment](../model/amenity-feature-blocks.md) completed 36 fits:
six feature families on five building holdouts and the 2024 annual holdout. Each
family is added separately to layout, area, time, building/unit effects and all
amenity missingness indicators. The three reference models reuse verified saved
predictions. These are additive comparisons, not leave-one-out importance scores;
correlated families' gains cannot be summed or assigned causal shares.

## Held-out prediction errors

Pooled building results contain exactly one held-out prediction for each of 46,688
development unit-months across 1,126 buildings. The annual test contains 3,591
2024 unit-months from 629 buildings, with training ending before 2024. It can
include buildings and units seen in training. Both are reused development cohorts.

| Model | Unseen-building median absolute percentage error | 2024 median absolute percentage error |
| --- | ---: | ---: |
| Baseline | 18.262% | 8.072% |
| All missingness indicators | 15.253% | 7.829% |
| Missingness + laundry values | 15.206% | 7.723% |
| Missingness + doorman values | 15.195% | 7.826% |
| Missingness + HVAC values | 15.245% | 7.817% |
| Missingness + pet rules | 15.216% | 7.784% |
| Missingness + elevator/floor values | 14.188% | 7.547% |
| Missingness + exposure values | 15.253% | 7.829% |
| All known values + missingness | 14.035% | 7.589% |

The vertical family contains elevator, listed floor, physical floor, its elevator
interaction, and the floor-label gap. Physical floors are unobserved in this
dataset and listed floors are sparse: this experiment does not independently
identify all those effects or prove a physical-floor premium.

For pooled unseen buildings, the elevator/floor model reduces mean absolute log
error by 0.013777 relative to missingness controls. Its 2,000 held-out-building
resample range is [−0.018885, −0.008389]. Laundry's difference is +0.000408
[−0.001271, +0.002112]; doorman's is −0.000778 [−0.001731, +0.000137].
HVAC and pet-rule improvements are much smaller (−0.000050 and −0.000283).
These ranges condition on already-fitted models and describe paired error
comparisons, not parameter uncertainty or causal effects.

On the annual holdout, laundry improves mean absolute log error by 0.001710
with a resample range of [−0.003267, −0.000387]. The vertical model has slightly
better median percentage error than the full model but worse mean absolute log
error by 0.002678 [0.000809, 0.004796]. A single metric should not silently
determine the preferred model.

## Exposure identification limit

All six splits verified that the twelve centered exposure-value columns are
exactly zero and exposure-block predictions equal missingness-only predictions
exactly. The source has positive assertions and unknowns, with no verified
negative exposure values. The model can learn reporting patterns, but it cannot
estimate a present-versus-absent exposure contrast. This is a limitation of the
evidence, not evidence that renters assign exposures zero value.

## Reproduction

The completed checksummed artifact is
`data/model/chelsea-feature-blocks-20260918`; the protocol SHA-256 is
`8540345a52a4408d1b886723b47b8a23819008070cc7c857770dfbba1d65a1d2`.
Its `summary/report.json` contains every split, metric and paired comparison;
per-fit bundles retain fitted coefficients, encoders and predictions. Source
snapshots, split membership and reference hashes bind the experiment to the v4
historical analytical dataset. An unchanged replay completed successfully, reusing
all 36 verified fits without fitting again. The project regression suite passed with 513 tests
and two skips before this results documentation was added.

These results concern retrospectively reconstructed advertised asking rents.
They do not establish lease prices, current availability, future calibration,
or historically executable predictions. Short-horizon temporal validation,
prediction uncertainty and freshness-aware search remain outstanding.
