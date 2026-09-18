# Building-transfer prediction-band validation

**Deferred:** the protocol was prepared, but no real-data fits were launched.
The user's clarified priority is factor, residual and counterfactual analysis
after refitting current listings; unseen-building prediction is secondary.

`models.building_transfer_validation` evaluates empirical asking-rent bands for
buildings excluded from model fitting. It follows the monthly validation's failed
pooled fallback for unfamiliar buildings. These are development comparisons;
nominal 80% and 95% labels are not coverage guarantees.

## Fixed partitions and clocks

The existing five building folds are retained: the first eight hexadecimal
digits of SHA-256 of the canonical building ID, modulo five. For evaluation fold
`j`, calibration uses fold `(j + 1) % 5`; the remaining three folds fit the point
model. All units and dates of a building remain in its assigned role within that
experiment. No seed is selected based on results.

Each monthly fit uses only source price months strictly before its origin. The
robust centered-amenity specification and penalties are unchanged. The fit learns
its own imputation, feature scaling, category frequencies, building/unit effects
and time terms from training rows only. Both calibration and evaluation buildings
have zero fitted group effects because they are wholly withheld.

The declared evaluation is January 2019–December 2024, preceded by January–December
2018 warm-up. Each of five folds has 84 monthly fits, for **420 fits**. The current
month's point forecasts for calibration buildings are saved for future months;
they cannot calibrate the current evaluation predictions.

For each origin, interval calibration uses only the preceding twelve calendar
months of the reserved calibration fold's one-month-ahead `log(actual/prediction)`
errors. Support requires at least 100 rows, 30 distinct buildings and six distinct
months. Insufficient support yields unavailable bands, without pooled fallback.

## Two declared empirical rules

Both rules use signed log errors and equal-tail inverse empirical CDF quantiles
at 10%/90% and 2.5%/97.5%. The selected value is the first observed error whose
cumulative weight reaches the requested probability; no interpolation is used.
Endpoints are the point prediction multiplied by the exponentiated quantiles.

- **Row weighted:** each prior calibration unit-month has equal weight.
- **Building balanced:** each calibration building has equal total weight,
  divided evenly among its observed unit-months in the window.

The second rule targets a distribution that first samples a building uniformly,
then a row within that building. It may differ from the listing-volume-weighted
market. Neither rule establishes exchangeability under market shifts or
within-building dependence, and neither is presented as conformal calibration.
There is no tuning of interval levels, tail probabilities, windows or support
thresholds on the reported evaluation outcomes.

## Evaluation

Each evaluation row appears exactly once across the five outer folds. Report
point error, row-weighted coverage, equal-building average coverage, lower and
upper misses, interval widths, proper interval scores, and unavailable-band
counts. Preserve fold and calendar-year results alongside the pooled results.

Also evaluate the **natural new-building subset**: rows in a building's first
source price month in this archive. This uses archive history only to label an
evaluation stratum; it never affects predictions or calibration. It is not the
building's construction date or proof that it was new to the real rental market.
The small natural subset can expose differences between withheld mature buildings
and newly encountered buildings that aggregate five-fold metrics conceal.

The folds share data in different roles, so their errors and coverage estimates
are dependent. Per-row binomial standard errors would overstate independence.
No sampling-confidence claim is inferred from these descriptive percentages.

## Running and replay

```sh
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 \
  .venv/bin/python -m models.building_transfer_validation \
  --dataset data/exports/chelsea-serving-history-20260918-asof1600 \
  --output data/model/chelsea-building-transfer-20260918 --prepare-only
```

Remove `--prepare-only` to fit all folds. `--folds 0 2 4` and `--folds 1 3` can run
as separate workers against the same frozen protocol; locks prevent two workers
from running the same fold. Worker selection does not change the experiment's
five-fold membership. `--max-new-months` bounds new forecast checkpoints for a
preflight; a normal rerun resumes without refitting completed months.

The protocol stores source manifests, full fit/calibration/evaluation membership
hashes, settings, software versions and copied implementation files. Each saved
fit contains encoder state, coefficients, convergence diagnostics and both sets
of point predictions. Forecast checkpoints bind the fit and prior forecast chain.
Replay verifies point-row membership and recomputes the inexpensive interval
rules from the exact earlier calibration history. Changed rules or inputs require
a new output directory. Final publication requires all five fold summaries and
exactly-once coverage of the source evaluation cohort.

## Interpretation and promotion

The point model fits only three fifths of the buildings in each experiment. Even
good held-out coverage would not directly calibrate the full-data serving model.
Artificially withheld buildings and newly appearing buildings can also differ.
Any eventual serving policy needs a separately bound calibration artifact and
validation of its deployment population; this command does not promote bands.

Historical attributes and corrected identities were often collected after their
price events, and these years have already been used for development. Results
are retrospective asking-rent comparisons, not historically executable forecasts,
prospective final tests, lease-price intervals or causal amenity effects.
