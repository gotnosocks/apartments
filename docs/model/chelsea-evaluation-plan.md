# Chelsea model evaluation plan

**Priority update, September 18:** this document records earlier prediction-focused
development plans. The user's clarified primary workflow is scrape → transform →
fit → analyze, with factor, residual and counterfactual analysis. Unseen-building
performance and forecast calibration below are secondary diagnostics, not product
promotion gates. See [project intent](../project-intent.md) for the current scope.

Audit date: 2026-09-18. Existing fit artifacts were read without modification.
This is an evaluation plan, not a report that the proposed folds have been run.

The robust incremental point model remains the strongest measured baseline for
2026 asking-rent point predictions. The accepted Bayesian model supplies useful
uncertainty and a stronger same-period unseen-unit result, but its 2026 forecast
is worse. The building-only Timeseers candidate is promising on the repeatedly
examined 2025 validation set. None of those comparisons makes 2026 pristine again.

## Existing evidence

All three families use the frozen 53,899-row canonical unit-month initial-ask
cohort: 22,424 units, 1,141 buildings, January 2010–August 2026. Its source is
`/data1/apartments/archive/datasets/chelsea-granular-20260917-canonical-url-v1`.
The older directory ending in `-canonical-units` is a different artifact and
must not be substituted. The modeling input SHA256 is
`53921470380bd8f716c024721bdca3fbd57c8b011ec3177da13de6c9eb0c760c`.

| Fit and evaluation | Rows | Median absolute percentage error | Log RMSE | Median signed percentage error | 80% predictive coverage |
| --- | ---: | ---: | ---: | ---: | ---: |
| Robust incremental; Jan–Aug 2026 | 2,801 | 7.102% | 0.13432 | -3.894% | Not supplied |
| Bayesian unit + drift; Jan–Aug 2026 | 2,801 | 9.410% | 0.15679 | -8.392% | 75.295% |
| Robust incremental; whole-unit holdout, all periods | 11,060 | 7.972% | 0.15401 | -0.019% | Not supplied |
| Bayesian unit + drift; same whole-unit holdout | 11,060 | 7.040% | 0.14012 | +0.305% | 82.568% |
| Accepted Timeseers building-only; 2025 validation | 3,785 | 6.986% | 0.13605 | -1.376% | 81.532% |

Sources: `results.json` in
`/data1/apartments/archive/fits/chelsea-minimal-canonical-20260917-incremental`,
`/data1/apartments/archive/fits/chelsea-bayesian-20260918-final/temporal-2026`,
`/data1/apartments/archive/fits/chelsea-bayesian-20260918-final/unit-holdout`, and
`/data1/apartments/archive/fits/chelsea-timeseers-20260918/validation-simple-long`.

The Bayesian 2026 fit passes its saved sampling checks: maximum R-hat 1.00922,
minimum bulk ESS 712, minimum tail ESS 1,238, zero divergences. Its poorer
forecast and undercoverage remain real despite convergence. Its full-data fit
has 53,899 training rows and zero evaluation rows; that fit is not additional
validation evidence. The Bayesian family was selected using 2025 mean log
predictive density. The saved selection record describes the whole-unit holdout
as exploratory because family selection had already seen some of those units.

The accepted Timeseers run has maximum R-hat 1.00801, minimum bulk ESS 583,
minimum tail ESS 965, and zero divergences. Its mean 2025 log predictive density
is 0.70463, compared with 0.68777 for the selected Bayesian unit + drift candidate
on the same 2025 rows. This is a validation advantage on a reused selection set,
not evidence that Timeseers beats the robust model on future data. The shorter
`validation-simple` run and interrupted/default/pilot runs are not the accepted
Timeseers result.

The robust 2026 test is 99.93% seen-building observations; its whole-unit holdout
is 99.59% seen-building observations. Neither establishes prediction quality for
unseen buildings. Those strata matter for generalizing elevator, doorman, laundry,
and HVAC associations beyond a building's memorized rent premium.

## What the historical cohort can establish

`models/minimal_rent_model.py::load_source` associates an initial ACTIVE price
history event with attributes captured from that advertisement's own page,
excludes inconsistent layouts, and aggregates repeated advertisements to one
unit-month. It does not join arbitrary latest-unit attributes to every old event.
Nevertheless, the historical pages were collected much later than many events.
These tests reconstruct source-reported episode history; they do not establish
what was actually known before a 2018 or 2024 forecast date. Identity resolution
and attribute corrections also require a recorded-time cutoff for a strict
knowledge-at-the-time claim.

Keep two explicit cohorts:

1. **Historical episode cohort:** the frozen initial-ask dataset for retrospective
   trend/seasonality, layout, repeat-unit, and forecast-policy comparisons. Record
   any attributes' unverified historical validity. Do not attach newly scraped
   building amenities to earlier episodes merely because unit IDs match.
2. **Contemporary evidence cohort:** asking rent and attributes supported by the
   same dated capture, plus explicit effective-date corrections. This supports
   current amenity modeling. Until repeated collection spans enough months, it
   cannot identify seasonality or a market trend on its own. Sparse historical
   correction assertions support only the fields and periods they explicitly name.

In the original v2 planning cohort, square footage is missing on 34,962 of 53,899
historical rows (64.9%). The [v4 follow-up](../analysis/chelsea-recovery-ablation-2026-09-18.md)
records the latest cohort and completed validation. Training-only
imputation plus a missing indicator is a sensitivity assumption; comparison with
a no-size model and an observed-size subset is necessary. A missing amenity code
is also unknown, not an observed absence.

## Earlier rolling-origin development evaluation

Freeze the cohort, eligibility policy, feature extraction version, and fold
manifest before comparing new candidates. Use expanding training windows with
annual December origins from **2016 through 2023**, predicting the next calendar
year, 2017–2024. This covers eight origins including the pandemic shock and
recovery without reusing 2025 or 2026 as the new development objective. The eight
test years contain respectively 4,498, 4,274, 4,244, 5,174, 3,426, 3,515, 3,745,
and 3,632 rows in the original v2 planning cohort. These are available row counts, not
completed validation results.

Report the first three months and all twelve months separately, using one frozen
fit per origin. Do not update the model using outcomes from within its test year.
Fit medians, category dictionaries, centering, hyperparameters, and group effects
using training rows only. When choosing penalties or priors, use earlier nested
origins inside that training window, or preregister fixed settings; tuning on the
eight outer folds and then describing those same scores as independent testing
would be misleading.

Compare a small, declared family set first:

- Robust incremental bedrooms + bathrooms + optional size + building/unit effects,
  holding the last estimated trend level and applying month-of-year seasonality.
- The accepted Bayesian Student-t unit + drift specification, unchanged.
- The accepted Timeseers building-only specification, unchanged, with final-slope
  extrapolation and no simulated future changepoints.
- One Timeseers unit-effect extension if it passes diagnostics; change this one
  modeling choice before expanding amenity terms.

Keep the constant-level robust baseline even if the newer spline/changepoint
model is more expressive. Forecast-horizon error, signed bias, and conditional
coverage will show whether extrapolating a slope helps consistently or merely
fits the most recent validation year. The quarterly-spline design is currently
constructed through the requested prediction horizon; record that horizon and
verify that extending it does not materially change already-issued short-horizon
predictions through a changed prior/basis.

Use equal-origin average log RMSE as the primary point-prediction selection score,
with all per-origin scores shown. Also report median/mean absolute percentage
error, dollar MAE, signed bias, and proportions within 10% and 20%. For Bayesian
fits include predictive log density, 80%/95% coverage and interval widths, per
origin and horizon. Report seen-unit, unseen-unit/seen-building, and unseen-building
strata separately. A pooled score dominated by high-volume years is insufficient.
Use paired building-cluster resampling for uncertainty in score differences,
preserving all a building's units and months together; show origin-level variation
rather than presenting correlated rows as independent replications.

## Unseen-building evaluation

Create deterministic, versioned five-fold assignments from canonical building IDs,
for example SHA256 of `chelsea-building-fold-v1|<building_id>` modulo five. All
units and all dates of each building stay on the same side of a split. Publish
counts by fold, year, bedroom count and known amenity category before fitting.
Do not retry seeds because one outcome looks favorable.

Two separate questions require separate tables:

- Same-period grouped building holdout measures cross-building transfer while
  other buildings in that period can inform market conditions. It is not a
  future-market forecast.
- Crossed building/time holdout trains on other buildings strictly before each
  origin, and evaluates withheld buildings in its next year. This is the relevant
  combined stress test for expansion into an unseen building in a later market.

Start with the cheap robust benchmark across all five building folds and the
2017–2024 origins. Screen expanded families on exactly the same fold IDs; expensive
posterior fits can follow for candidates with meaningful transfer improvements.
Within each outer building fold, choose any tuning settings using only the other
buildings and earlier periods. New-building Bayesian predictions must integrate
uncertainty for a new group instead of treating its missing fitted intercept as
known zero. Report the corresponding shrinkage assumption in point models.

## Interpretable amenity extension

Before adding regressors, publish coverage and support per field: known positive,
known negative, unknown, building count, unit count, dates, contradictions, and
within-building variation. Preserve partial exposure statements as tri-state maps
(e.g. `{"south": true}` says nothing about north). Separate advertised floor from
physical level; never infer the latter by subtracting one above a labeled 13th
floor without building-specific evidence.

Add documented categories for laundry, doorman, HVAC and pet rules, then floor,
elevator and their interaction, then views/exposures where support permits.
Predeclare reference categories and unknown handling. Compare an identical-row
base model with and without each feature block; otherwise changing coverage can
masquerade as predictive benefit. Also publish a coverage-expanded evaluation
when accepting partial features permits more units into the model.

Time-invariant building amenities are confounded with unrestricted building
intercepts. Within-building variation can identify some unit amenities; doorman
and elevator often require cross-building comparisons and explicit shrinkage or
structural assumptions. A hierarchical residual building effect permits a
conditional decomposition but does not make its amenity coefficient causal.
Report sensitivity to including/excluding unit effects, building shrinkage, and
building-average covariates. Use building holdouts and posterior/prior sensitivity
to distinguish a stable transferable association from an arbitrary allocation
between an amenity coefficient and its building intercept.

Report supported marginal predictions for concrete changes, with other inputs
fixed, uncertainty, and the count of comparable buildings/units. Floor premiums
must be conditional on elevator and physical level. Separate estimated market
price associations from a user's willingness to pay. The search frontier should
use the latter as supplied preferences, report unknown attributes explicitly, and
be checked for ranking stability across model/attribute uncertainty.

## Promotion and future evidence

Freeze the proposed family/feature choice after this development exercise, then
report 2025 and Jan–Aug 2026 once as **retrospective comparisons against known
benchmarks**. They are not newly untouched tests. Require interpretable coefficient
support, reproducible source/fold hashes, passing numerical diagnostics, and no
material degradation hidden by aggregate scores before replacing a baseline.
Prediction and uncertainty winners may remain different models.

A new prospective test requires future captures and asking-price observations
that were unavailable when the specification was frozen, with exact collection
and knowledge cutoffs saved. September 2026 cannot automatically be called pristine
because it has already been scraped and may have influenced design. Fix a future
collection window and freeze predictions before observing its outcomes. Continue
to call the target gross advertised asking rent, not a signed lease or realized
transaction rent.
