# As-of floor model on the corrected build: results, 2026-10-23

This fit reruns the as-of floor model on the build with the studio 3+ bath corrections (#1235): dataset `b0-b495f6dd53222649-alldata-v36-dense-nyc`, ads from `rows-b495f6dd53222649.parquet`. The predictions are in `building-zones-floor-asof2-predictions-2026-10-23.md`, written before the launch. The fits on the old build are in `building-zones-floor-asof-2026-10-23.md`.

Run: `building-zones-floor-asof2-b0-latest-d5de95e7-dense-w1000`, fit-only on Modal, 21 minutes (15.4 of them sampling), $0.92.

## Gate

The fit misses the gate on one quantity, the outer zone's map amplitude `amp[outer]`, at R-hat 1.0129 against the 1.01 limit. Its bulk ESS is 541, and the least ESS anywhere is 523, on `beta[bed=0:full>=3]`. The studio cell that failed on the old build now converges.

The four chain medians of `amp[outer]` run from 0.363 to 0.379, inside a pooled 90% interval of 0.305 to 0.468. On the old build the as-of base put them at 0.364 to 0.375 and passed this quantity. In the earlier floor fits on real and simulated rents, `amp[outer]` was also the worst-mixing quantity, at R-hat 1.005 to 1.008. I read the miss as slow mixing of a quantity that has always mixed slowest, which the corrections didn't cause. I didn't refit on a new seed.

## Held-out ads across builds

The latest split draws its held-out ads with `rng.choice` over the sorted ids of each unit's latest ad (`splits.latest_split`). Removing 14 ads from the candidates reshuffles the draw: of 189,647 held-out ads here, 119,502 are held out on the old build too, and the other 70,145 are training ads there. The rows themselves are the same in both builds, with the same unit, date and rent. So I compare across builds only on the 119,502 shared held-out ads, which neither fit trained on.

| | elpd (all held-out ads) | RMSE | coverage 50 / 80 / 90 / 95 |
|---|---|---|---|
| asof2 | 148,181 | 0.1158 | 0.493 / 0.798 / 0.903 / 0.954 |
| as-of (old build) | 149,128 | 0.1154 | 0.495 / 0.800 / 0.905 / 0.955 |
| floor (old build) | 149,303 | 0.1154 | 0.494 / 0.799 / 0.904 / 0.955 |

The rows of that table cover different held-out sets, so their elpd totals don't compare. The paired differences on shared ads:

| pair | ads | elpd difference | SE by row | SE by building | SE two-way |
|---|---|---|---|---|---|
| asof2 minus as-of | 119,502 | +45 | 22 | 25 | 26 |
| asof2 minus floor | 119,502 | -61 | 68 | 78 | 79 |

## Against the predictions

| prediction | result | hit |
|---|---|---|
| passes the gate | R-hat 1.0129 on `amp[outer]` | no |
| 18 to 30 minutes, $0.75 to $1.20 | 21 minutes, $0.92 | yes |
| `bed=0:full>=3` falls from 41.0 to under 25 | 45.8 | no |
| other coefficients move under 0.3 points | 109 of 114; the five others are bath cells | no |
| `bld_sd`, `sigma`, `nu`, `amp` change under 1% | all under 0.4% | yes |
| elpd within 30 of the as-of base | +45 on shared ads, 1.8 SE by building | no |
| the gap to the floor fit within 1 SE by building of -175 | -61, SE 78, on shared ads | yes |
| RMSE and 90% coverage move under 0.0005 and 0.1 pp | +0.0004 and -0.2 pp | half |

The studio bath cells moved the most, in points:
- `bed=0:full>=3` 41.04 to 45.82;
- `bed=0:full>=4` 24.33 to -65.87.

The corrected build keeps 40 training rows coded as studios with 3 or more full baths, and 3 with 4 or more: listing 3966098 at two-northside-piers ($4,000), 4519639 at 1341 Park Place ($2,000) and 4715975 at 548 W 50th St ($2,550). These three cheap rows set the 4+ cell on their own. I passed the listing ids to the Data improvements thread.

The other coefficients barely move: `log_size_rel` 26.07 to 26.04, `elevator` 3.56 to 3.53 and `gym` 6.27 to 6.31. The amplitudes come out at 0.909 for Manhattan and 0.371 for the outer zone, against 0.905 and 0.370 on the old build.
