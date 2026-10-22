# Elevated subway track on held-out buildings: predictions, 2026-10-22

This fit tests whether a building on a street with an elevated subway line over it rents below
its neighbors one row back. The structure brings train noise every few minutes, shade over the
street and the sidewalk, and steel at the height of the second and third floors. The location
model carries `bld:log_station_km` and `bld:log1p_routes`, which reward being near the same
lines and change slowly over a neighborhood. The flag here changes between a building under the
tracks and the one around the corner. I wrote these predictions before launching the fit.

## The column

`rentfrontier.building_elevated` finds the elevated track in the MTA's subway GTFS feed: for each
shape, it keeps the stretch between consecutive stops whose station structure is Elevated or
Viaduct in the MTA station list. It then measures, for each registry building, the distance
from its footprint outline to the nearest point of that track. A stretch between an elevated
stop and an underground one is left out, so the track between the last elevated stop and the
portal reads as not elevated. On Broadway that covers the block east of Marcy Avenue, where the
structure runs on toward the Williamsburg Bridge. The GTFS shape also cuts the curve from
Broadway onto Myrtle Avenue about 50 m south of the street, so a few dozen buildings there read
too far. The snapshot is `building-elevated/20261022-c9be347c`: 70,175 buildings, 68,650 of
them with an outline.

`rentfrontier.building_zones_elevated` adds one building column to `building-zones-location`:
`bld:elevated` is 1 when that distance is under 30 m. Buildings facing the structure on
Broadway and Myrtle Avenue measure 9 to 13 m, so 30 m takes in the buildings on both sides of
the street and leaves out the ones on the side streets.

On the latest split's 1,706,837 training ads, 11,162 (0.7%) are in the 518 buildings under
30 m. Nearly all are in Brooklyn, along the J/M/Z on Broadway and the M on Myrtle Avenue: 6,139
in Bushwick, 2,523 in Stuyvesant Heights, 1,595 in Williamsburg and 837 in Ocean Hill. The
whole-building holdout includes only 46 of these buildings, with 1,005 ads.

## The free check

I compared the building effects of the latest-split location fit
(`building-zones-location-b0-latest-732b36ec-dense-w1000`) for buildings under each distance
against buildings in the same small cell that are farther away. The scripts and their output
are in `/data1/apartments/tmp/elevated/` (`check_outline.py`, `check-outline.json`; `check.py`
measures from the building's point instead). In log points x100, weighted by training ads:

| threshold | buildings | gap in 300 m cells | gap in 150 m cells |
|---|---|---|---|
| under 20 m | 419 | -0.8 (SE 1.0, 32 cells) | -2.5 (SE 0.9, 64 cells) |
| under 30 m | 518 | -1.6 (SE 1.1, 34 cells) | -3.1 (SE 0.9, 69 cells) |
| under 40 m | 684 | -1.4 (SE 1.0, 35 cells) | -2.4 (SE 0.8, 76 cells) |

I ran these three thresholds before choosing 30 m. All three point the same way and by about
the same amount, so the choice matters little. Buildings under 30 m average -4.1 against +0.4
for the others within 300 m.

## The fit

I'll run `building-zones-elevated` on the whole-building split from #1212 (6,798 buildings held
out whole), on dataset `b0-edc83b49f9bacd8c-alldata-v36-dense-nyc`, at the commit that adds the
module, with the night's settings: 4 chains, 300 warmup, 1,000 sweeps with every 5th kept, seed
20261021, fit-only. I'll score it against the location fit on the same split,
`building-zones-location-b0-buildings-35131df8-dense-w1000`, with the held-out scoring from
docs/notes/building-zones-parkfront-2026-10-22/heldout/.

## Predictions

- It passes the gate (R-hat <= 1.01, ESS > 400). The fit stages take 16 to 22 minutes, at a
  Modal cost estimate of $0.70 to $0.95.
- `bld:elevated` has a median between -5 and -1 points, and its 90% interval excludes 0.
- `bld:log_station_km` and `bld:log1p_routes` move by under 0.3 points, and the other terms by
  under 0.2.
- On the 184,437 held-out ads, the elevated fit's elpd differs from the location fit's by less
  than 2 SE (by building), since under 1% of ads are in these buildings.
- On the 1,005 held-out ads in elevated-track buildings, the elpd difference is within 2 SE of
  0, and their mean residual moves toward 0.
- RMSE and 90% coverage on all held-out ads move by under 0.01 points and 0.1 percentage points.
