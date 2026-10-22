# Transit, parks and noise together in the floor model: predictions, 2026-10-22

The three location fits of 2026-10-22 each put one feature set on the floor model
(`building-zones-floor-b0-latest-6b5a5b4a-dense-w1000`). This fit puts all six columns on it
together, so I can check whether the three sets overlap and use the result as a location base
for the next features. I wrote these predictions before launching the fit.

## The change

`rentfrontier.building_zones_location` appends the transit, parks and noise columns to the
floor model's design, in that order, using the same snapshots and the same `columns` functions
as the single-feature models:

- `external/building-transit/20261022-a4d8ac25`: `bld:log_station_km`, `bld:log1p_routes`;
- `external/building-parks/20261022-ec936683`: `bld:log_park_km`, `bld:log_big_park_km`,
  `bld:log_water_km`;
- `external/building-noise/20261022-208c44b3`: `bld:log1p_noise`.

The data, settings, seed and split match the three single fits.

## What the single fits found

In points of log rent x100, medians with 90% intervals:

| term | single fit |
|---|---|
| `bld:log_station_km` | -0.32 (-0.55 to -0.12) |
| `bld:log1p_routes` | +0.99 (+0.57 to +1.40) |
| `bld:log_park_km` | +0.14 (-0.05 to +0.32) |
| `bld:log_big_park_km` | -2.13 (-2.62 to -1.63) |
| `bld:log_water_km` | -1.61 (-2.99 to -0.25) |
| `bld:log1p_noise` | -0.58 (-0.75 to -0.39) |

## Predictions

- It passes the gate (R-hat <= 1.01, ESS > 400).
- `bld:log_big_park_km` stays between -2.6 and -1.6, with its interval below 0. Its spread
  across buildings did not overlap transit's, and big parks sit away from the densest transit.
- `bld:log_water_km` stays negative, between -2.5 and -0.5, though its interval may reach 0
  now that the other columns take part of the shoreline pattern.
- `bld:log1p_routes` shrinks toward 0, landing between +0.3 and +1.0. Services and noise both
  run high in the dense parts of each zone, so part of each one's term goes to the other.
- `bld:log1p_noise` lands between -0.7 and -0.2, the same sign with less magnitude.
- `bld:log_station_km` and `bld:log_park_km` stay within 0.3 points of their single fits.
- No term changes sign with an interval that excludes 0.
- The Manhattan map amplitude falls by 3% to 12% from the floor fit's 0.916, and the outside
  amplitude ends between 0.32 and 0.40. Both are inside each fit's own uncertainty, so neither
  counts for much.
- `bld_sd` moves by under 2% in each zone.
- The unit premiums move by under 0.1 points each.
