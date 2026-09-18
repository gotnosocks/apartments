# Distinguishing amenity values from reporting patterns

`models/amenity_ablation.py` compares the same robust log-rent model on exactly
the same advertisements, with three nested information sets:

- `baseline`: layout, area, market time, building and optional unit effects.
- `missingness`: baseline plus indicators that each amenity is unknown.
- `full`: missingness plus the reported amenity values.

Optional `laundry`, `doorman`, `hvac`, `pets`, `vertical` and `exposures` variants
add one family of values to the same full set of missingness indicators. These
are additions to missingness, not leave-one-out comparisons against the full model.

Numeric values are centered and scaled using known training observations; unknown
values have zero magnitude contrast. Known category indicators are centered on
their frequencies among **known training observations**. Unknown and unseen
category values have zero known-category contrasts. The explicit unknown indicator
is unchanged in every amenity variant. This prevents a full set of uncentered
category indicators from representing the same known/unknown mean difference
again with a weaker effective ridge penalty. A field with a single known category
contains no subtype contrast and cannot improve the full model over missingness.

The initial interrupted `chelsea-missingness-development-20260918` run used
uncentered category indicators. It is retained with a `SUPERSEDED.md` marker and
must not be interpreted as evidence for amenity values. Version 2 fixes this
design flaw. Earlier ordinary amenity model artifacts retain their original
encoding when replayed; saved metadata selects the appropriate behavior.

Building folds use the predeclared SHA256 modulo-five assignment. Each held-out
building and all its units are excluded from training. Annual splits use only
earlier price periods for training. Crossed splits enforce both restrictions.
All development data precedes 2025; this does not make the reused earlier years
untouched tests. Historical reconstruction retains its later collection and
interpretation clocks and is not a real-time forecasting backtest.

The protocol records row-membership hashes, group overlaps, source manifest,
implementation hashes, package versions, fixed penalties, and model variants
before fitting. Each completed variant is published with its encoder, coefficients,
predictions, convergence diagnostics and checksums. An unchanged run verifies and
resumes checkpoints. Paired uncertainty resamples entire test buildings and
describes prediction-error differences, not coefficient uncertainty.

```sh
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 uv run --locked --extra model python -m models.amenity_ablation \
  --dataset data/exports/chelsea-historical-20260918-v4 \
  --output data/model/chelsea-recovered-amenity-validation-20260918 \
  --years 2019 2021 2023 2024 --cross-years 2024
```

Default building folds cover all five partitions. Use a fresh output directory
after implementation or protocol changes. A predictive benefit from reported
amenities is still a conditional association and can include reporting-selection
effects; this comparison does not identify causal renovation returns or personal
willingness to pay.
