# As-of floor model with amenity premiums by period: predictions, 2026-10-23

This is follow-up fit 5. It asks whether renters paid for in-unit laundry, a dishwasher, a garden and a doorman differently before the pandemic, during it and after it. `rentfrontier.building_zones_floor_asof3_periods` takes the asof3 design and splits each of those six columns into three, by the period of the ad's latest-ask day:

- `pre2020-03`, before 2020-03-01 (817,641 rows of the dataset);
- `2020-03to2021`, from 2020-03-01 through 2021-12-31 (388,988 rows);
- `2022on`, from 2022-01-01 on (689,842 rows).

The three columns for an amenity add up to the original column. Each keeps the original's Normal(0, 0.5) prior. Everything else matches the as-of floor model on the build after #1242. I wrote these predictions before the launch.

The time walk already carries the citywide swing in rents across 2020 and 2021. A split coefficient measures the amenity's premium within its period, against units of the same building zone, floor and size without it. Building composition also moved: ads from doorman buildings in Manhattan made up a larger share of the 2020 market. The building levels absorb a building's persistent level, so I read the split as a change in the premium and not in the mix, with that caveat.

## The fit

- Model `building-zones-floor-asof3-periods`, split latest, dataset `b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc`, input `rows-b3ddebf19af1dc1e.parquet`.
- 4 chains, 300 warmup, 1,000 sweeps with every 5th kept, seed 20261021, fit-only.
- I compare each amenity's three coefficients with each other, and with the single coefficient from fit 8 (cap64 on the same build) when it lands. Until then the reference values come from the asof2 fit (`building-zones-floor-asof2-b0-latest-d5de95e7-dense-w1000`), with 90% intervals:

| column | asof2 median | 90% interval |
|---|---|---|
| `unit:laundry_in_unit` | 0.0616 | 0.0610 to 0.0622 |
| `unit:dishwasher` | 0.0194 | 0.0190 to 0.0198 |
| `unit:garden` | 0.0279 | 0.0253 to 0.0302 |
| `bld:doorman_full` | 0.1403 | 0.1338 to 0.1474 |
| `bld:doorman_part` | 0.0811 | 0.0738 to 0.0881 |
| `bld:doorman_virtual` | 0.0286 | 0.0259 to 0.0313 |

## Predictions

- The fit passes the gate (R-hat at most 1.01, bulk ESS over 400) and takes 25 to 50 minutes on Modal. The twelve extra columns cost under 5% more time per sweep than asof3.
- In-unit laundry is worth 1 to 3 points more in `2020-03to2021` than in `pre2020-03`, since people spent more time at home. In `2022on` it sits between the two.
- The garden premium is 1 to 5 points higher in `2020-03to2021` than in `pre2020-03`. Its 90% intervals are wide enough that the difference may not clear them.
- The full doorman premium falls by 1 to 4 points in `2020-03to2021` against `pre2020-03`, as the discounts of 2020 fell hardest on the high-end Manhattan buildings, and comes back to within 1.5 points of `pre2020-03` in `2022on`.
- The dishwasher, part-time doorman and virtual doorman premiums change by under 1.5 points across periods.
- Every column outside the split moves by under 0.5 points against fit 8. `sigma` and `bld_sd` change by under 1%.
- Nearly all held-out ads on the latest split fall in `2022on`, so held-out RMSE and elpd change by less than 2 SE against fit 8.

If the fit misses the gate, I'll trace the failing quantity to the data or the model structure, and I won't rerun it on a new seed.
