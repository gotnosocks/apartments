# Chelsea recovered descriptions and amenity validation

The [subsequent stability analysis](chelsea-amenity-stability-2026-09-18.md) shows
substantial dependence of point contrasts on model assumptions, including a
doorman contrast that changes sign. Read those qualifications alongside the
point estimates below.

Recovering 27,240 archived descriptions and correcting extraction errors produced
a stronger Chelsea comparison: median error on unseen buildings is **14.04%**
with amenity values, versus **15.25%** with reporting patterns alone and **18.26%**
for the baseline. This extends the [initial amenity pilot](chelsea-amenities-2026-09-18.md).
The pilot remains retrospective research on advertised rents. It does not establish
signed lease prices, current availability, or causal amenity premiums.

## Verified archive recovery

All **27,240** unresolved description captures were recovered from their original
archived bodies, covering **19,440 advertisements**. Every body hash and source
listing identity passed verification, and full reparsing changed only
`/description`. No fresh scraping was needed. There were zero quarantines.

The immutable bundle is `data/exports/chelsea-description-recovery-20260918`.
Its 426 content-hashed checkpoints preserve interpretation timestamps. A subsequent
resume-reader fix handles literal Unicode line separators in valid JSON strings;
it leaves this completed, verified bundle unchanged. See the
[recovery contract](../data/description-recovery.md).

Historical transformation now verifies source shard counts, canonical membership
digests, and every recovery's original payload/body/reference identity before
using the text. Reinterpretation precedes correction overlays. Original values,
interpreted attributes, exact extraction evidence, and corrections remain in the
audit. Knowledge time includes the interpretation timestamp; historical price
dates do not pretend the evidence was available then.

## Evidence precision

The [first source-text audit](../data/attribute-precision-audit-2026-09-18.md)
reviewed 90 assertions and exposed common-terrace scope, ambiguous HVAC and pet
approval errors. These were corrected with source-grounded regression cases.
A [second review](../data/recovered-attribute-precision-audit-2026-09-18.md) examined
60 recovered-description assertions and found three unsupported inferences plus
two ambiguous roof-deck view claims. Those five now remain unknown: pedestrian
directions do not establish a walk-up building, permitted air conditioners are
not installed equipment, and views offered by some residences do not identify
this unit. These are agent judgments on convenience samples,
not human labels or estimates of population precision or recall.

The verified **historical v4** bundle accepts **54,105 advertisements** from
**22,253 units** and **1,140 buildings**. Use
`data/exports/chelsea-historical-20260918-v4`; its observations SHA256 is
`e03d83dc4a55d6e80228f56184aad192af5c2da2b8b55fa33fc444a5511c5420`.
Recovered prose helped identify furnished advertisements that the model should
exclude. A furnished/unfurnished substring error was also fixed. Relative to v2,
737 advertisements are newly excluded and 42 newly accepted. The final scope
fixes change 556 view records and 55 elevator records relative to intermediate
v3 without changing its accepted cohort. Both interrupted earlier comparisons
are marked superseded; their partial results are not reported as validation.

| Explicit evidence among accepted advertisements | Earlier v2 | Final v4 |
| --- | ---: | ---: |
| Pet policy | 5,484 | 11,537 |
| Directional window exposure | 4,896 | 8,220 |
| View exposure | 12,382 | 13,429 |
| Advertised floor | 314 | 379 |

These are nonmissing record counts, not accuracy estimates or independently
verified physical features. The standalone verified impact bundle is
`data/exports/chelsea-recovery-impact-20260918`, including source manifests,
cohort/attribute transitions, clock checks and reproducible comparison code.

## Matched model comparison

The [ablation protocol](../model/amenity-ablation.md) compares a layout/time/building
baseline, that baseline plus amenity-missingness indicators, and the full model
with actual reported values. All three use identical training and test rows.
Known category contrasts are centered on training observations so they cannot
duplicate a reporting signal with a weaker effective penalty. A reproduced
single-category counterexample exposed the initial encoding flaw; the corrected
encoding gives identical predictions when only missingness varies.

All **42 fits completed**: three variants on five building folds, four earlier-year
holdouts, and five crossed building/future-year tests. The frozen experiment is
`data/model/chelsea-recovered-amenity-validation-20260918`; its verified analysis
is `analysis/report.json`. All solver and objective-convergence gates passed.
The analytical selection retains 53,218 unit-months; the pre-2025 development
cohort contains 46,688 unit-months across 1,126 buildings.

| Held-out data | Rows | Baseline median absolute % error | Missingness only | Full amenities |
| --- | ---: | ---: | ---: | ---: |
| 2019, trained through 2018 | 4,200 | 7.63% | 7.62% | 7.22% |
| 2021, trained through 2020 | 3,394 | 19.19% | 19.27% | 18.84% |
| 2023, trained through 2022 | 3,706 | 8.01% | 7.78% | 7.36% |
| 2024, trained through 2023 | 3,591 | 8.07% | 7.83% | 7.59% |
| Unseen buildings, all five folds pooled | 46,688 | 18.26% | 15.25% | 14.04% |
| Unseen buildings in 2024, trained through 2023 | 3,591 | 18.61% | 15.55% | 13.78% |

The pooled rows each receive exactly one held-out prediction; metrics are computed
from those predictions, not averaged fold medians. Full amenities beat missingness
on median error in every individual building and crossed fold. Reporting patterns
explain a substantial part of the improvement, but actual known-value information
adds further predictive benefit. The four temporal comparisons also favor full
amenities over missingness on mean absolute log error, with their building-resampled
95% intervals below zero. Pandemic-period error remains large.

Across all building folds, the full-minus-missingness difference in mean absolute
log error is **−0.0151**, with a 95% building-bootstrap interval
**[−0.0198, −0.0102]**. On the crossed 2024 holdout it is **−0.0217**,
interval **[−0.0275, −0.0156]**. The pooled intervals use 2,000 resamples of test
buildings and condition on the already fitted models. They measure uncertainty
in prediction-error differences, not coefficient uncertainty or individual rent
intervals. Earlier-year periods are reused development data, and all evidence
remains retrospective; this is not untouched prospective validation.

The crossed full model still underpredicts by a median 5.95%, and only 68.0% of
its asking-rent predictions fall within 20%. Its better average error does not
establish reliable precision for every apartment or a calibrated user-facing model.

An unchanged experiment rerun verified and reused every completed checkpoint.
Reproduce with the command in the [ablation protocol](../model/amenity-ablation.md),
then run:

```sh
uv run --locked --extra model python -m models.amenity_ablation_analysis \
  --experiment data/model/chelsea-recovered-amenity-validation-20260918 \
  --output data/model/chelsea-recovered-amenity-validation-20260918/analysis
```

## Supported point contrasts and replay

The through-2023 full model exactly reproduces all **3,591** persisted 2024 test
predictions, with maximum absolute dollar difference zero. The reporter verifies
source, protocol, implementation, package versions and train/test membership hashes.
It also checks categorical coefficient differences against predictions from the
saved centered encoder. Report and full support counts are in the experiment's
`contrasts/report.json`.

| Conditional contrast | Fitted difference | At a $4,000 reference rent | Buildings with both categories |
| --- | ---: | ---: | ---: |
| Building laundry → in-unit laundry | +4.93% | +$197/month | 258 |
| Part-time → full-time doorman | +2.07% | +$83/month | 6 |
| Pets prohibited → allowed, restrictions unknown | +1.48% | +$59/month | 128 |
| Pets prohibited → approval required | +2.48% | +$99/month | 71 |
| Room AC → central AC | −0.77% | −$31/month | 18 |

These are regularized conditional point associations with no coefficient confidence
intervals. They are not causal premiums, renovation returns or individual willingness
to pay. The room-AC comparison has only 139 training unit-months from 80 units in
49 buildings; the negative contrast does not establish that central AC lowers rent.
Doorman type has little within-building comparative support. Reported changes within
a building can reflect service changes, source reporting changes or errors.

```sh
uv run --locked --extra model python -m models.amenity_ablation_contrasts \
  --dataset data/exports/chelsea-historical-20260918-v4 \
  --experiment data/model/chelsea-recovered-amenity-validation-20260918 \
  --output data/model/chelsea-recovered-amenity-validation-20260918/contrasts
```

Final repository regression validation: **489 passed, 2 skipped** in 22.83 seconds;
`git diff --check` passed. All 42 fits and the unchanged checkpoint replay completed.

For the through-2023 training partition, all observed directional/view indicators
have only a positive known value; the remaining records are unknown. They therefore
contribute reporting indicators, not independently identified present-versus-absent
exposure contrasts. More recovered positive claims do not solve that distinction.
Elevator has both known values; advertised floor has 319 known rows across 18 labels,
but none independently establishes physical height.

Physical floor remains unsupported. Coefficient uncertainty, shrinkage sensitivity,
prospective validation and freshness-aware apartment selection still require work.
