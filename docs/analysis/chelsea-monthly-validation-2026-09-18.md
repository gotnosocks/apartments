# Chelsea monthly pricing validation

Monthly refitting improves asking-rent predictions in every evaluated year from
2019 through 2024. Across 23,487 held-out unit-months, median absolute percentage
error falls from **9.82% with a frozen annual model to 7.97% with monthly refits**.
The recent-error adjustment yields 7.89%; its incremental benefit is much smaller
and is not consistent across all years. These results favor keeping the market
model fresh rather than explaining the large 2021 errors through amenity changes.

The completed experiment has 72 converged monthly fits and 1,003 buildings in its
test rows. All three policies predict the same rows. The annual model reuses the
January fit for its entire year; monthly models train only on earlier source
price months. The adjustment uses only the preceding three months' out-of-time
errors. The [protocol](../model/rolling-rent-validation.md) defines exact sampling,
support thresholds, interval rules and the retrospective interpretation.

## Point predictions

| Test year | Unit-months | Annual frozen median error | Monthly median error | Monthly + adjustment median error |
| --- | ---: | ---: | ---: | ---: |
| 2019 | 4,200 | 7.22% | 7.00% | 7.07% |
| 2020 | 5,111 | 14.83% | 9.33% | 9.08% |
| 2021 | 3,394 | 18.84% | 10.44% | 10.13% |
| 2022 | 3,485 | 8.62% | 7.66% | 7.59% |
| 2023 | 3,706 | 7.36% | 7.05% | 6.99% |
| 2024 | 3,591 | 7.59% | 6.83% | 6.78% |

Equal-month mean log RMSE is 0.17599 for annual frozen, 0.14392 for monthly,
and 0.14365 for monthly plus adjustment. Pooled log RMSE is respectively
0.18509, 0.14572 and 0.14499. This keeps the primary equal-origin comparison
separate from a pooled score dominated by busy listing months.

In 2021, annual predictions have median signed error −17.66%. Monthly refitting
reduces that to −3.73%, and the adjustment to −0.35%. In 2020, the corresponding
biases are +12.70%, +3.07% and +0.77%. The adjustment responds to earlier errors;
it cannot anticipate a reversal and slightly worsens 2019 median error.

## Interval coverage exposes a building-transfer failure

The nominal bands are sequential empirical residual quantiles, not assumed
confidence levels. The first three months lack sufficient earlier errors, leaving
926 of the 23,487 predictions without intervals. Coverage denominators exclude
those rows explicitly; point metrics retain them.

| Policy | Measured 80% coverage | Measured 95% coverage | Median full 95% width / predicted rent |
| --- | ---: | ---: | ---: |
| Annual frozen | 73.10% | 91.83% | 61.22% |
| Monthly | 78.93% | 94.30% | 53.03% |
| Monthly + adjustment | 79.14% | 94.35% | 52.51% |

The following breakdown uses the adjusted policy. Familiarity is defined against
the current monthly training identities for every policy.

| Familiarity | Prediction rows | Median error | Rows with bands | Measured 95% coverage | Pooled-fallback band rows |
| --- | ---: | ---: | ---: | ---: | ---: |
| Seen unit | 16,200 | 7.19% | 15,649 | 94.52% | 0 |
| New unit, seen building | 7,077 | 9.55% | 6,719 | 94.69% | 0 |
| New building | 210 | 16.91% | 193 | **68.39%** | 193 |

The newly seen buildings comprise 149 distinct buildings, with too little prior
new-building data in any twelve-month calibration window to meet the declared
100-row threshold. Every available new-building interval therefore uses pooled
errors. This fallback fails badly: even nominal 80% bands cover only 47.15% of
those rows. Most 95% misses are above the upper bound (22.80% of rows), consistent
with a median signed point error of −8.43% in new buildings.

**These pooled fallback bands must not be promoted as calibrated new-building
uncertainty.** The unadjusted monthly policy also fails there (69.43% coverage for
nominal 95%), so dropping the recent adjustment does not solve the problem.
Future service output needs an explicit unsupported-uncertainty state for this
group until a separate building-transfer calibration policy is validated.

Even for familiar properties, the bands are broad: the adjusted model's median
95% width is about $2,408 across all eligible rows. Near-nominal aggregate coverage
does not establish sharp or reliable individual-apartment intervals. The complete
report includes tail misses, interval scores, widths and month-by-month coverage.

## Artifacts and checks

- Experiment: `data/model/chelsea-monthly-validation-20260918`.
- Protocol SHA-256: `4000d9cc4f8073e4a99d0eb28c2639e27c95ec6c5b8f4fcc3849c65f91269118`.
- [Standalone interactive report](../../data/model/chelsea-monthly-validation-report-20260918/report.html), with bundled JavaScript for offline use.
- Companion report JSON, Plotly figure JSON and rendering source are in the same
  checksummed report bundle. The renderer verified all 72 monthly forecast bundles
  and their dependency chain against the completed summary.
- An unchanged experiment replay completed successfully, verifying and reusing
  all 72 fits and forecasts without refitting. The actual report also reproduced
  identically; structural checks confirmed nine 72-month traces, 30 comparison
  rows and bundled JavaScript without external script loads.
- January 2019 predictions match the earlier annual amenity fit exactly for all
  300 rows. Tests cover no current/future outcome leakage into adjustments or
  bands, calendar windows, interval denominators, resumability and swapped-checkpoint
  rejection. The repository suite passed with **517 tests and two skips**.

The report renderer also passed an identical-replay smoke check on synthetic data.
No browser was available for visual inspection; the actual report was generated
and its structured contents verified.

All years are reused development data. Attributes and corrected identities were
often collected after their source price dates. These are retrospective asking-rent
comparisons, not historically executable forecasts, signed lease prices, current
availability, or a prospective final test. The model/settings sensitivity and
amenity identification limits established in the earlier reports still apply.

Next steps are to validate uncertainty for unfamiliar buildings and connect the
saved robust model to freshness-aware candidate scoring and renter preferences.
The broader NYC collection and dated public-record joins remain outside this
Chelsea pilot result.
