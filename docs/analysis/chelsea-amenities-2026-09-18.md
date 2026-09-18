# Chelsea historical amenities pilot — September 18, 2026

This records the initial v2 experiment. The
[recovery and validation follow-up](chelsea-recovery-ablation-2026-09-18.md)
contains the newer v4 dataset, full description recovery, missingness controls,
all five building folds, and crossed building/time results.

Adding source-backed amenities improves the matched robust model in the first
development comparisons, especially on unseen buildings. This is evidence to
continue the approach, not grounds to promote the model as validated or causal.
Pandemic-period errors remain large and physical-floor effects remain unsupported.

## Source correction and analytical cohort

The first project reset inspected an older directory ending in `-canonical-units`.
The newer `/data1/apartments/archive/datasets/chelsea-granular-20260917-canonical-url-v1`
is complete and includes canonical membership tables. No archive rebuild was
needed to obtain those identities.

The new historical adapter produced **54,800 accepted advertisements**, linked
to **22,424 source-declared units** in **1,141 buildings**, from 65,350 rental
advertisements. It uses the initial ACTIVE event of each advertisement and only
attributes captured from that advertisement's own page. Conflicts and exclusions
retain their source values, correction records, and evidence in a separate audit.

The frozen, verified dataset is
`data/exports/chelsea-historical-20260918-v2`. Its observations SHA256 is
`f64ad677928a6c6ca3c85513db650f1829388c1a7c9a9f0c7d4aab5d711ecb11`.
Use v2: source and implementation hashes were verified before and after building,
and knowledge time includes the canonical identity transformation's completion.
The earlier v1 was superseded because its implementation hash was recorded only
after computation, leaving a concurrent-edit ambiguity.

Model preparation retains 53,899 unit-months, selecting the latest initial
advertisement in each month as a whole row. This matches the older cohort's size
but does **not** assert identical training values: the older model aggregated
monthly prices using their median. The new rule keeps a price and its associated
amenities together. All models compared below use exactly the same rows.

This is retrospective reconstruction: price dates span 2010–August 2026, but the
source pages were collected later. A historical page may itself display updated
building amenities. Own-advertisement provenance reduces cross-listing mistakes;
it does not independently establish historical amenity validity. The evaluation
is not a historically executable forecasting backtest.

## Matched experiment

`models/amenity_rent_model.py` extends the existing sparse robust model, retaining
incremental bedroom effects, bathrooms, training-only relative area, missing-area
indicator, smooth monthly trend, seasonality, building effects and optional unit
effects. Added features cover laundry, doorman, HVAC, pet rules, views/exposures,
elevator, and separately represented advertised/physical floors and interactions.
Unknowns remain separate; training-only vocabulary and scaling are saved.

The protocol was recorded before running the comparison. Fixed penalties are
building 10, unit 8, trend 1,000 and amenities 10; no settings were tuned using
these results. These are development settings informed by the existing research,
not a claim of previously untouched tests. All 2025+ outcomes are excluded from
this experiment. The robust solver's numerical and objective-convergence gates
passed for all twenty fits.

The following table compares the models **with unit effects**. Models without
unit effects were also fitted on identical folds and retained in the artifacts.

| Evaluation | Test rows | Baseline median absolute percentage error | With amenities | Baseline log RMSE | With amenities |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2019, trained through 2018 | 4,244 | 7.56% | 7.13% | 0.1431 | 0.1378 |
| 2021, trained through 2020 | 3,426 | 19.21% | 18.65% | 0.2720 | 0.2662 |
| 2023, trained through 2022 | 3,745 | 7.99% | 7.33% | 0.1506 | 0.1409 |
| 2024, trained through 2023 | 3,632 | 8.00% | 7.38% | 0.1675 | 0.1413 |
| Entire unseen buildings, pre-2025 periods | 8,638 | 17.58% | 14.01% | 0.2806 | 0.2260 |

The building holdout contains 217 buildings, selected by a fixed SHA256 modulo-five
rule. All their units and dates remain outside training. Other buildings inform
the same market periods: this is a cross-building transfer test, not a future
market test. It is one of the five possible folds; all-fold and crossed
building/time validation remain to be done.

Paired resampling of whole buildings gives an amenity-minus-baseline difference
in **mean absolute log error** of -0.0476 on unseen buildings, with a 95%
bootstrap interval of [-0.0801, -0.0165] over 400 resamples. Negative favors the
amenity model. That interval concerns prediction-error differences, not the
uncertainty of an amenity coefficient. Improvements are supported by this
resampling for 2019, 2023 and 2024; the 2021 interval includes zero. Selection of
further models based on these results makes these development folds reused.

## Interpretable contrasts and evidence support

For the model trained through 2023, category contrasts hold all other inputs
fixed. Dollar equivalents below use a reference apartment predicted at $4,000
per month. They are regularized conditional associations without coefficient
confidence intervals; they are not estimates of an individual's willingness to
pay or causal returns to renovation.

| Contrast | With unit effects | Dollar equivalent | Without unit effects | Buildings with both reported categories |
| --- | ---: | ---: | ---: | ---: |
| Building laundry → in-unit laundry | +4.89% | +$196/month | +4.81% | 259 |
| Part-time → full-time doorman | +2.92% | +$117/month | +2.97% | 6 |
| Pets not allowed → allowed, restrictions unknown | +0.50% | +$20/month | +0.44% | 72 |
| Room AC → central AC | -0.47% | -$19/month | -0.50% | 12 |

Laundry has substantially better comparative support: 18,419 building-laundry
unit-months across 418 buildings and 11,924 in-unit-laundry unit-months across
690 buildings. The HVAC comparison has only 89 room-AC rows across 32 buildings;
its small negative sign is not an established market preference. Doorman service
largely varies between buildings, so its separation from building effects remains
dependent on regularization even though the two specifications agree here.
Building counts with both categories can reflect changes in source reporting or
service as well as genuine variation; they are not matched causal pairs.

The [contrast artifact](../../data/model/chelsea-amenity-development-20260918/contrasts/contrasts.json)
includes counts for both categories, distinct units/buildings, and both fitted
contrasts. No physical floors were recovered. The model cannot estimate physical
height premiums or the requested floor/elevator interaction from this dataset.

## Description recovery

Across 88,689 rental captures, 27,240 descriptions were unresolved Flight
references. The attribute audit found only 492 explicit advertised floors and
zero physical floors; directional exposure coverage was sparse. Empty feature
arrays were not interpreted as explicit negative evidence.

A deterministic convenience sample of ten unresolved descriptions, from ten
buildings, was recovered from the **same archived bodies**, with body hashes
verified. Full reparsing changed only `/description`; property details and price
history were unchanged. Six of those ten descriptions added usable attribute
evidence, but this sample is not a population-level precision or coverage estimate.

The parser now understands Flight's UTF-8 byte-counted text records, including
adjacent records, split Unicode, and embedded text that resembles record headers.
Truncated, oversized, conflicting, or cyclic input is handled explicitly. The
decoder is included in granular-transform implementation hashing. Existing source
datasets remain unchanged. Recovery evidence is in
`data/exports/flight-description-audit-20260918/reparse-evidence.jsonl`.

## Reproduction and next work

```sh
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 uv run --locked --extra model python -m models.amenity_rent_model \
  --dataset data/exports/chelsea-historical-20260918-v2 \
  --output data/model/chelsea-amenity-development-20260918 \
  --years 2019 2021 2023 2024

uv run --locked --extra model python -m models.amenity_model_analysis \
  --dataset data/exports/chelsea-historical-20260918-v2 \
  --experiment data/model/chelsea-amenity-development-20260918 \
  --output data/model/chelsea-amenity-development-20260918/contrasts
```

Completed fold bundles include saved encoders/coefficients, held-out predictions,
convergence diagnostics, support counts, and hashes. An exclusive experiment lock
prevents duplicate writers; unchanged runs verify and resume completed folds.
The full unchanged experiment rerun verified and reused all completed folds.
Final repository validation: **443 tests passed, 2 skipped**, in 20.87 seconds;
`git diff --check` passed. All twenty experimental fits and the ten-page offline
reparse were terminal and successful at the end of this work interval.

Next: scale description recovery without mutating raw inputs, audit extraction
precision, and rebuild a new analytical version. Compare meaningful amenity values
against missingness-only effects, then expand building/time folds and shrinkage
sensitivity. Improve pandemic/recovery time dynamics separately. Calibrated
prediction and contrast uncertainty, prospective collection, floor evidence, and
freshness-aware search still remain before promoting a high-quality user-facing
model. The long-term project goal remains active.
