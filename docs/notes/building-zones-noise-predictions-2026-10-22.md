# Outdoor noise in the floor model: predictions, 2026-10-22

This is the third explanatory location feature on the night's queue. I wrote these predictions
before launching the fit. Like transit and parks, it goes on top of the floor model. It
leaves out the transit and parks columns, so it gets its own comparison against the same base.

## The data

The noise snapshot from before covered only the Chelsea and West Village box, and it held every
complaint, which would run to millions of rows citywide. `rentfrontier.building_noise` asks
NYC 311 (erm2-nwe9) for each month's outdoor noise complaints from 2020 to 2025, counted by
the point each was geocoded to. The outdoor types are street and sidewalk, commercial, vehicle
and DEP's general noise type (construction, alarms, air conditioners). I left out residential
noise, helicopters, parks and houses of worship. The six years hold 2.05 million complaints.

For every NYC building it keeps `noise_per_year`, the complaints a year within 150 m, and
writes `external/building-noise/20261022-208c44b3` with 70,175 buildings (median 87.5, 90th
percentile 242).

A count of complaints also measures how willing neighbors are to call 311, and that rises with
rents. So the coefficient will mix the cost of noise with the kind of neighborhood that calls.

## The change

`rentfrontier.building_zones_noise` adds `bld:log1p_noise`, log(1 + `noise_per_year`), to the
base. A building missing from the snapshot gets the median.

## A free check before the fit

I regressed the realistic simulation's true site levels on the column plus the zone, weighted by
rows, on thelio. The column's spread across sites is 0.80.

| target | coef | variance beyond zone explained |
|---|---|---|
| map F | -0.002 | 0.0% |
| building residual | -0.009 | 0.3% |
| F + residual | -0.011 | 0.2% |

The complaint rate explains almost none of the levels. The two effects in the note above may
cancel, or noise may vary on a finer scale than 150 m around each building.

## Predictions for the real-data fit

- It passes the gate (R-hat <= 1.01, ESS > 400).
- `bld:log1p_noise` lands between -0.02 and +0.005, with its 90% interval reaching 0 or lying
  just below it.
- Map amplitudes and `bld_sd` move by under 1%. Unit premiums move by under 0.1 points.
- Held-out log score comes within 1 SE of the base's.

If this holds, I'll record outdoor 311 noise at 150 m as not explaining building levels, and
look next at traffic volume on the building's own street, which a complaint count only partly
reflects.
