# Building zones with unit size, laundry, dishwasher and truck routes, 2026-10-21

The residual screen (`residual-screen-2026-10-21.md`) ranked stated size against the bedroom
median and in-unit laundry first among the fields the model leaves out. A dishwasher and a
through truck route followed, the truck route being the street measure with a within-block
sign. Ben gave the go for a model with all four and a fit-only Modal run of it. The base is
building zones with attributes at 1 km with the 2 bedroom bath ladder capped at three full
baths (#1185), with no frontage columns, since the frontage fit (#1187) did not show them
adding much.

## Data

`rentfrontier.unit_features` writes snapshot `unit-features/20261021-16cea7c` with one row per
pipeline listing and one per registry building. On the latest split's 1,706,837 training rows:

| column | how I code it | rows set |
|---|---|---|
| `unit:log_size_rel` | log of size over the bedroom median of stated sizes, clipped at plus or minus log 2.5, 0 when unknown | 44.9% have a size |
| `unit:size_imputed` | size from the unit's other listings (12.9% of rows) or the same line (5.9%) | 18.8% |
| `unit:size_unknown` | no size from any layer | 55.1% |
| `unit:laundry_in_unit` | the pipeline's `laundry_type` | 29.0% |
| `unit:laundry_in_building` | the same | 36.8% |
| `unit:dishwasher` | DISHWASHER in the latest raw record's features | 54.8% |
| `bld:truck_through` | the building faces an NYC DOT through truck route | 4.2% |

The size fill follows `size-coverage-2026-10-21.md`. Among rows with a size, `log_size_rel`
has median -0.03 and standard deviation 0.27, and 0.3% sit at the clip. Laundry takes unstated
as its reference, since StreetEasy has no code for a unit with no laundry.

The unit columns vary between ads of one building, so `rentfrontier.building_zones_unit` puts
them in the rows' fixed design beside the bed and bath steps. The truck route column is
constant within a building and joins the building columns. Every coefficient takes the
Normal(0, 0.5) prior in the global block.

## Checks on thelio

- `tests/test_unit_features.py` checks the label parse, the unit and line fills, the
  penthouse and top-floor exclusions, and the size range on a toy building.
- `test_columns_code_size_laundry_dishwasher_and_trucks` checks each column against toy
  tables and checks the attributes design underneath is unchanged, with no frontage column.
- `test_recovers_simulated_unit_coefficients` redraws a toy design with all 15 building and
  unit coefficients at known values and recovers each within its 99.8% interval.
- `test_run` runs the model end to end through `rentfrontier.run`.

## Before

From the 1 km attributes run `building-zones-attrs-b0-latest-9bd8c1a3-dense-w650`, which still
has the 2 bedroom 4 bath step:

- `T` = error + building effect + map value, demeaned by zone, has variance 0.0622 (0.0662 in
  Manhattan, 0.0566 in Brooklyn + Queens).
- Building spread 0.228 in Manhattan and 0.141 in Brooklyn + Queens. Map amplitudes 1.03 and
  0.38.
- Pairs of buildings 100 to 200 m apart in one neighborhood differ by rms 0.230 across a 41 to
  70 ft street and 0.202 with no street between them.

## The run

```sh
ops/modal-fit --dataset /data1/apartments/frontier/datasets/b0-edc83b49f9bacd8c-alldata-v36-dense-nyc \
  --split latest COMMIT dense-w650 building-zones-unit b0 4 150 650 5 \
  --seed 20261021 --no-loo --no-heldout
```

## Predictions, written before the fit

Premiums are percent changes in the asking rent. Within-building comparisons come from the
screen's joint fit within tax blocks, which these columns can only partly reproduce, since the
model's building effects take up the building-level part.

| # | Prediction |
|---|---|
| U1 | Max R-hat 1.004 to 1.015 and min bulk ESS 400 to 900, on a bath step. Every new coefficient has bulk ESS over 1,000. |
| U2 | The fit stage takes 8 to 12 minutes and the run costs $0.33 to $0.50. |
| U3 | `unit:log_size_rel` 0.35 to 0.60: a unit 10% larger than its bedroom median rents 3.4% to 5.9% more. |
| U4 | `unit:size_unknown` -2% to +1%, and `unit:size_imputed` -1.5% to +1.5%. |
| U5 | In-unit laundry +5% to +10% and in-building laundry 0% to +4%, both against unstated. |
| U6 | Dishwasher +1% to +4%. |
| U7 | Through truck route -4% to -0.5%. |
| U8 | Every attribute coefficient stays within 2 points of the 1 km run's. Doorman full-time and condo are the likeliest to fall, by up to 2 points, as laundry and size take part of their credit. |
| U9 | Building spread falls 0.010 to 0.030 in Manhattan (from 0.228) and 0.005 to 0.020 in Brooklyn + Queens (from 0.141). Map amplitudes fall by 0 to 0.05 in Manhattan and 0 to 0.03 in Brooklyn + Queens. |
| U10 | Each group's sigma falls 0.001 to 0.006, and nu stays within 0.1 of 3.83. |
| U11 | Variance of `T` (error + building + map) falls from 0.0622 to 0.050 to 0.057. |
| U12 | The pair gap across 41 to 70 ft streets falls from 0.230 to 0.215 to 0.228, and pairs with no street between them fall from 0.202 to 0.190 to 0.200. |

## Results

The fit `building-zones-unit-b0-latest-a3aec3ff-dense-w650` ran on a Modal A100 from 09:47 to
09:57 ET on 2026-10-21, fit-only, seed 20261021. The fit stage took 593 s and the whole
container 616 s, at an estimated $0.41.

It passes the repo's convergence gate. Max R-hat is 1.0078 on `bld_sd[manhattan]` and min bulk
ESS 456 on `amp[outer]`. The new coefficients have R-hat at or below 1.006 and bulk ESS between
1,061 and 2,272.

| column | premium, median (90% interval) | 1 km run |
|---|---|---|
| size, per unit of log(size / bedroom median) | +28.6% (28.5 to 28.8) | |
| size imputed from the unit or line | -0.63% (-0.67 to -0.58) | |
| size unknown | -3.89% (-3.94 to -3.84) | |
| laundry in unit, against unstated | +6.48% (6.41 to 6.55) | |
| laundry in building, against unstated | +1.65% (1.58 to 1.71) | |
| dishwasher | +2.05% (2.01 to 2.09) | |
| through truck route | -4.24% (-4.96 to -3.50) | |
| roof height, per e-fold | -0.37% (-0.70 to -0.05) | -0.73% |
| height unknown | +0.55% (-0.12 to +1.23) | +0.23% |
| elevator | +7.98% (7.66 to 8.35) | +9.05% |
| elevator unknown | +1.55% (1.02 to 2.10) | +1.73% |
| condo | +10.86% (10.39 to 11.31) | +14.76% |
| doorman, full-time | +17.17% (16.37 to 18.00) | +19.57% |
| doorman, part-time | +11.08% (10.35 to 11.89) | +11.96% |
| doorman, virtual | +3.86% (3.58 to 4.13) | +4.39% |
| half bath | +11.29% (11.21 to 11.39) | +14.32% |
| studio, 2 full baths | +30.72% (29.81 to 31.67) | +44.32% |
| 2 bed, 2 full baths | +19.97% (19.88 to 20.05) | +23.49% |
| 2 bed, 3 full baths | +26.09% (25.35 to 26.85) | +34.35% |
| 3 bed, 3 full baths | +27.39% (27.09 to 27.69) | +32.88% |

The size slope of 0.25 on the log scale means a unit 10% larger than its bedroom median asks
2.4% more. The common bath steps fell by 3 to 14 points, while the bedroom steps moved by at most 1.5.
The rare ones moved both ways: a 1 bed with 3 full baths rose 2.9 points, on 155 rows, and a
studio with 4 full baths rose 13 points, on 14 rows.
Until this fit the bath steps were carrying part of the size difference between units with the
same bedroom count. A 2 bed with 3 full baths is mostly a larger 2 bed.

The zone gap stayed at +29.8% (29.4 to 30.3), against +30.1%. The error sigmas by bedroom band
fell from 0.086, 0.086, 0.092 and 0.103 to 0.084, 0.083, 0.089 and 0.103, and nu rose from
3.83 to 4.11, so the error tails are a little lighter.

| zone | building spread | building share | map amplitude |
|---|---|---|---|
| Manhattan, before | 0.228 | 0.494 | 1.03 |
| Manhattan, after | 0.189 | 0.463 | 0.90 |
| Brooklyn + Queens, before | 0.141 | 0.363 | 0.38 |
| Brooklyn + Queens, after | 0.117 | 0.318 | 0.38 |

`T` (error + building effect + map value, demeaned by zone) has variance 0.0530, against
0.0622: 0.0551 in Manhattan (from 0.0662) and 0.0500 in Brooklyn + Queens (from 0.0566). Each
part fell: the error from 0.0165 to 0.0150, the building effects from 0.0252 to 0.0183 and
the map from 0.0310 to 0.0266.

The map moved by rms 0.019 over the training ads. The largest falls, averaged over the
neighborhood's ads, came in loft districts, where units run large for their bedroom count:

| neighborhood | ads | map before | map after | move |
|---|---|---|---|---|
| Tribeca | 15,634 | 0.447 | 0.363 | -0.084 |
| Soho | 11,594 | 0.441 | 0.378 | -0.062 |
| Flatiron | 13,323 | 0.329 | 0.281 | -0.047 |
| Hudson Square | 2,976 | 0.410 | 0.364 | -0.046 |
| NoMad | 10,766 | 0.190 | 0.153 | -0.037 |
| DUMBO | 5,777 | 0.353 | 0.318 | -0.036 |
| Chinatown | 5,001 | -0.137 | -0.112 | +0.025 |
| Two Bridges | 6,227 | -0.168 | -0.144 | +0.023 |
| Yorkville | 79,850 | -0.174 | -0.156 | +0.018 |

Part of what the map called a Tribeca premium was the size of Tribeca's apartments.

Pairs of buildings 100 to 200 m apart, with at least 5 training ads each, by the widest street
between them (the same 300,000 sampled pairs as in the frontage note):

| between them | neighborhood | pairs | rms before | rms after |
|---|---|---|---|---|
| no street | same | 11,420 | 0.202 | 0.168 |
| 40 ft or less | same | 136,104 | 0.212 | 0.176 |
| 40 ft or less | different | 8,585 | 0.227 | 0.186 |
| 41 to 70 ft | same | 45,452 | 0.230 | 0.191 |
| 41 to 70 ft | different | 11,489 | 0.262 | 0.217 |
| over 70 ft | same | 267 | 0.181 | 0.142 |

Every row fell by 15% to 22%. The step from no street to a 41 to 70 ft street went from 0.028 to
0.023, so the new columns account for a share of the difference between neighboring buildings
without explaining the extra gap across a mid-width street.

Examples, at posterior medians with 90% predictive intervals:

| ad | held out | ask | predicted | 90% interval |
|---|---|---|---|---|
| 796 Avenue of the Americas, 2 bed, 2026-10-16 | no | $9,314 | $9,716 | $8,214 to $11,650 |
| 23 Eagle Street, Brooklyn, 1 bed, 2026-10-16 | yes | $6,059 | $4,908 | $4,110 to $5,796 |
| 85 East End Avenue, 1 bed, 2026-10-16 | yes | $6,183 | $5,513 | $4,661 to $6,539 |

The Eagle Street ad has no size from any layer (its `unit:size_unknown` term is set) and falls
above its interval.

| # | Prediction | Result | Score |
|---|---|---|---|
| U1 | max R-hat 1.004 to 1.015, min ESS 400 to 900 on a bath step, new coefficients ESS over 1,000 | 1.0078; 456 on `amp[outer]`; 1,061 or more | partial: the slowest quantity was the outer amplitude |
| U2 | fit stage 8 to 12 min, $0.33 to $0.50 | 9.9 min, $0.41 | hit |
| U3 | size slope 0.35 to 0.60 | 0.252 | miss, low |
| U4 | size unknown -2% to +1%, size imputed within 1.5% | -3.9%, -0.6% | miss on unknown |
| U5 | in-unit laundry +5% to +10%, in-building 0% to +4% | +6.5%, +1.7% | hit |
| U6 | dishwasher +1% to +4% | +2.1% | hit |
| U7 | through truck route -4% to -0.5% | -4.2% (-5.0 to -3.5) | miss, just beyond |
| U8 | attributes within 2 points, doorman full-time and condo likeliest to fall | condo -3.9 points, doorman full-time -2.4, the other building columns within 1.1 | miss on the range, hit on which fell; the bath steps were not part of this prediction and fell further |
| U9 | spread falls 0.010 to 0.030 and 0.005 to 0.020; amplitudes fall 0 to 0.05 and 0 to 0.03 | falls of 0.040 and 0.023; amplitudes 1.03 to 0.90 and 0.379 to 0.385 | miss: both spreads and the Manhattan amplitude fell more, and the outer amplitude rose 0.006 |
| U10 | each sigma falls 0.001 to 0.006, nu within 0.1 of 3.83 | falls of 0.0009 to 0.0024, nu 4.11 | miss on nu and one sigma |
| U11 | `T` variance falls to 0.050 to 0.057 | 0.0530 | hit |
| U12 | pair gaps 0.215 to 0.228 and 0.190 to 0.200 | 0.191 and 0.168 | miss: both fell more |

I underestimated how much of the building and map spread was unit size. I set the size slope
from the bands of the residual screen's joint fit within tax blocks, but the fitted slope sits lower, likely because imputed
sizes add noise and because the bath steps were already holding part of it. The size unknown
flag at -3.9% matches the skew in `size-coverage-2026-10-21.md`, where ads with no size sit
below the rest within the same building.

The scripts are in `building-zones-unit-2026-10-21/`, and the draws-derived data (map
grid, buildings with their unit column means, coefficients with chain medians and traces, the
pair gap table, map moves, examples, `T` variance and the scored predictions) is at
https://claude.ai/artifact/PvBs8AxoZmFCJZd58ynrig.
