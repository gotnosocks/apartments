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
