# Monthly pricing, staleness and empirical prediction bands

`models/rolling_rent_validation.py` evaluates apartment-search update policies
with expanding monthly training sets. The declared Chelsea experiment uses every
month from January 2019 through December 2024, with the v4 historical dataset and
the existing fixed regularization settings. No hyperparameters are selected using
these outcomes. All encoders, imputations, categories and building/unit effects
are learned on rows strictly before each prediction month.

This is retrospective source-event-date research. Advertisements, attribute
interpretations and identity corrections were often collected much later than
their price dates. Strict temporal splitting does not turn them into information
available to a historical renter. These development years have already informed
other analyses; they are not untouched final tests.

## Three declared policies

- **Annual frozen:** fit before January, then retain the same coefficients and
  encoding for all twelve months. Apply the fitted seasonal pattern while holding
  the last estimated trend level constant. The horizon runs from one to twelve
  months, making the cost of stale parameters visible.
- **Monthly:** refit the complete centered amenity model before each month and
  predict that next month. Training expands; the regularization settings stay fixed.
- **Monthly with recent adjustment:** add a market offset to the monthly model's
  log predictions. Compute each of the preceding three calendar months' median
  log(actual/monthly prediction) residuals, then average those three medians.
  Require all three months and at least 100 observations; otherwise use zero and
  explicitly report insufficient support. This offset can lag a market reversal.

The January annual and monthly fits are the same artifact. Subsequent annual
forecasts cannot incorporate that year's new units, buildings, rents or categories.
Familiarity strata use the current monthly training identities for every policy,
so comparisons use the same rows. This means a unit labeled familiar for comparison
may still be unknown to the frozen annual model.

## Sequential empirical intervals

For each policy, collect its own earlier out-of-time prediction residuals from the
preceding twelve calendar months. Use the empirical 10th/90th and 2.5th/97.5th
percentiles of log(actual/predicted rent) for nominal 80% and 95% bands. Apply the
residual bounds multiplicatively to the current prediction. Quantiles use NumPy's
linear interpolation; these are empirical quantile bands, not conformal intervals
or guaranteed coverage statements.

Estimate residual quantiles separately for seen units, new units in seen buildings,
and unseen buildings. Each group needs at least 100 observations spanning three
months. Otherwise fall back to pooled earlier residuals under the same thresholds;
if those are also insufficient, publish no band. Each prediction records whether
its band uses the stratum, the pooled fallback, or is unavailable. Initial months
are retained for point metrics and counted as unavailable for interval metrics.

No current-month outcome enters its offset or band. Prior errors for the adjusted
policy reflect the adjustment that was actually available at each prior origin,
not an adjustment recomputed with today's knowledge. Repeated units, correlated
buildings, selection and market shocks can all make nominal coverage inaccurate.
Measure coverage rather than infer it from the interval label.

## Report and integrity checks

Report every month, calendar year, familiarity stratum and annual-model horizon,
alongside pooled and equal-month log-RMSE summaries. Point metrics include dollar
and percentage error, bias and proportions within 10%/20%. Interval metrics retain
available/unavailable counts, pooled fallback counts, coverage, misses below/above,
widths and interval score (width plus tail-miss penalties). Wide intervals should
not be called good solely because they cover more rents.

The protocol snapshots source manifests, membership hashes, source code, package
versions, settings and policy definitions before fitting. Each immutable monthly
fit binds to its own training/test membership. Each forecast also binds to the
annual fit and the complete chain of earlier forecast manifests. Valid checkpoints
copied into another month are rejected. Equal-input reruns verify and reuse saved
fits and forecasts. A partial run has no completed summary.

```sh
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 \
  uv run --locked --extra model python -m models.rolling_rent_validation \
  --dataset data/exports/chelsea-historical-20260918-v4 \
  --output data/model/chelsea-monthly-validation-20260918
```

Use `--prepare-only` to publish the protocol without fitting, or
`--max-new-months 2` for a bounded preflight or continuation under the same protocol.
Only a verified `summary/complete.json` proves all 72 months completed.
This experiment informs a future pricing service; it does not establish current
availability or a production-calibrated uncertainty estimate.

## Standalone results report

After completion, render the verified summary and monthly forecast chain:

```sh
uv run --locked --extra model python -m models.rolling_rent_report \
  --experiment data/model/chelsea-monthly-validation-20260918 \
  --output data/model/chelsea-monthly-validation-report-20260918
```

The resulting `report.html` contains its own Plotly JavaScript and works offline.
It plots monthly prediction errors, measured 95% coverage and interval widths,
with a table of yearly and familiarity-group results. The companion JSON retains
80% bands, tail misses, interval scores, support counts and every calibration rule.
The renderer verifies each monthly forecast bundle and its summary dependency
chain before publication. Rendering and identical replay passed on a synthetic
fixture. Browser-based visual inspection was unavailable in this environment.

The [completed Chelsea results](../analysis/chelsea-monthly-validation-2026-09-18.md)
record all 72 fits, an unchanged no-refit replay, actual-report replay and structural
checks. Pooled fallback intervals fail for unfamiliar buildings despite much
better aggregate coverage; that subgroup is not ready for calibrated serving.

The first real January 2019 fit reproduced all 300 predictions from the earlier
verified annual amenity model exactly. The repository regression suite passed
with 517 tests and two skips after adding the sequential runner.
