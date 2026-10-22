# Waterfront frontage on held-out buildings: predictions, 2026-10-22

This fit tests whether the first row of buildings along the water rents above the buildings
behind it. The location model already carries `bld:log_water_km`, which changes smoothly with
distance and spreads any waterfront premium over the blocks behind the shore. The flag here
steps between the first row and the rest. I wrote these predictions before launching the fit.

## The column

`rentfrontier.building_zones_waterfront` adds one building column to `building-zones-location`:
`bld:waterfront` is 1 when the building's point lies within 150 m of the shoreline. It reads
`water_km` from the parks snapshot (`building-parks/20261022-ec936683`), the same table the
location model's `bld:log_water_km` comes from, so it needs no new data. The shoreline there is
the borough boundaries less their land borders, so it includes the Harlem River and Newtown
Creek. 150 m takes in a building with the FDR Drive, the West Side Highway or an esplanade between
it and the water, and a lot of 30 to 60 m depth.

On the latest split's 1,706,837 training ads, 51,663 (3.0%) are in the 429 buildings within
150 m.

## The free check

I compared the building effects of the latest-split location fit
(`building-zones-location-b0-latest-732b36ec-dense-w1000`) for buildings within each distance of
the shore against buildings in the same small cell that are farther away. The script and its
output are in `/data1/apartments/tmp/waterfront/` (`check.py`, `check.json`). In log points x100,
weighted by training ads:

| threshold | buildings | gap in 300 m cells | gap in 150 m cells |
|---|---|---|---|
| under 100 m | 168 | +1.7 (SE 2.2, 52 cells; median +0.7) | +1.2 (SE 3.1, 46 cells; median 0.0) |
| under 150 m | 429 | +3.0 (SE 1.5, 77 cells; median +3.8) | +1.6 (SE 1.4, 77 cells; median -0.3) |
| under 250 m | 1,738 | -0.1 (SE 1.1, 114 cells) | -0.4 (SE 1.1, 151 cells) |

So the location fit's building effects leave little room for a first-row premium. The signal at
150 m is about 2 SE in 300 m cells and about 1 SE in 150 m cells. Much of the shore in the
data has a highway along it, which may offset a view.

## The fit

I'll run `building-zones-waterfront` on the whole-building split from #1212 (6,798 buildings
held out whole), on dataset `b0-edc83b49f9bacd8c-alldata-v36-dense-nyc`, at the commit that
adds the module, with the night's settings: 4 chains, 300 warmup, 1,000 sweeps with every 5th
kept, seed 20261021, fit-only. I'll score it against the location fit on the same split,
`building-zones-location-b0-buildings-35131df8-dense-w1000`, with the held-out scoring from
docs/notes/building-zones-avenue-2026-10-22/heldout/.

## Predictions

- It passes the gate (R-hat <= 1.01, ESS > 400). The fit stages take 17 to 22 minutes, at a
  Modal cost estimate of $0.70 to $0.95.
- `bld:waterfront` has a median between -1 and +3 points, and its 90% interval reaches 0.
- `bld:log_water_km` moves by under 0.5 points, and the other terms by under 0.2.
- On the 184,437 held-out ads, the waterfront fit's elpd differs from the location fit's by
  less than 2 SE (by building).
- On the held-out ads in waterfront buildings, the elpd difference is within 2 SE of 0.
- RMSE and 90% coverage on all held-out ads move by under 0.02 points and 0.1 percentage points.
