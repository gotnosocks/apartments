# Park frontage on held-out buildings: predictions, 2026-10-22

This fit tests whether a building facing a large park rents above its neighbors one row back.
The location model already carries `bld:log_park_km` and `bld:log_big_park_km`, but both
measure from the building's point and change slowly across a few blocks, so a building on Central
Park West and one 60 m back on 72nd Street read almost the same. The flag here changes between
those two buildings. I wrote these predictions before launching the fit.

## The column

`rentfrontier.building_park_front` measures, for each registry building, the distance from its
footprint outline to the edge of the nearest NYC Parks property of 5 acres or more. I leave out
malls, parkways, traffic triangles and plazas, managed sites and institutional grounds, since the
Broadway and Eastern Parkway medians, Grand Army Plaza's circle and the lawns around the Natural
History Museum aren't parks to look onto. I keep the High Line and the Battery Park City
esplanade, which are open green space a window can look onto. The flag doesn't change over time, so an
ad from before the High Line's sections opened (2009 to 2014) still gets it. The snapshot is
`building-park-front/20261022-5ddc0e5d`: 70,175 buildings, 68,650 of them with an outline.

`rentfrontier.building_zones_parkfront` adds one building column to `building-zones-location`:
`bld:park_front` is 1 when that distance is under 40 m, which takes in a building across a
street or an avenue from the park. A building with no outline gets 0.

On the latest split's 1,706,837 training ads, 52,661 (3.1%) are in the 1,124 buildings under
40 m.

## The free check

I compared the building effects of the latest-split location fit
(`building-zones-location-b0-latest-732b36ec-dense-w1000`) for buildings facing a park against
buildings in the same small cell that don't. The script and its output are in
`/data1/apartments/tmp/parkfront/` (`check.py`, `check.json`). In log points x100, weighted by
training ads:

| threshold | buildings | gap in 300 m cells | gap in 150 m cells |
|---|---|---|---|
| under 30 m | 838 | +3.3 (SE 1.2, 134 cells) | +1.8 (SE 1.1, 174 cells) |
| under 40 m | 1,124 | +4.8 (SE 1.2, 157 cells) | +3.9 (SE 1.1, 219 cells) |
| under 60 m | 1,708 | +4.2 (SE 1.1, 170 cells) | +4.0 (SE 0.9, 238 cells) |

The medians run lower, 1.6 to 3.0, so a few cells with large gaps lift the means. Buildings
within 200 m of a park that don't face it average -2.8, against +1.6 for those facing it. I
chose 40 m before fitting, as the threshold closest to a street's width plus sidewalks.

## The fit

I'll run `building-zones-parkfront` on the whole-building split from #1212 (6,798 buildings
held out whole), on dataset `b0-edc83b49f9bacd8c-alldata-v36-dense-nyc`, at the commit that
adds the module, with the night's settings: 4 chains, 300 warmup, 1,000 sweeps with every 5th
kept, seed 20261021, fit-only. I'll score it against the location fit on the same split,
`building-zones-location-b0-buildings-35131df8-dense-w1000`, with the held-out scoring from
docs/notes/building-holdout-location-2026-10-22/heldout/.

## Predictions

- It passes the gate (R-hat <= 1.01, ESS > 400). The fit stages take 17 to 22 minutes, at a
  Modal cost estimate of $0.75 to $0.95.
- `bld:park_front` has a median between +2 and +5 points, and its 90% interval excludes 0.
- `bld:log_park_km` and `bld:log_big_park_km` move by under 1 point each, and the other terms
  by under 0.1.
- On the 184,437 held-out ads, the park fit's elpd beats the location fit's, but by less than
  2 SE (by building), since only about 3% of ads are in park-facing buildings.
- On the held-out ads in park-facing buildings, the park fit's elpd is higher.
- RMSE and 90% coverage on all held-out ads move by under 0.02 points and 0.1 percentage points.
