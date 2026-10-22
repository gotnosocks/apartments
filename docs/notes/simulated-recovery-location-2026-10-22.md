# Simulated recovery of the location terms: results, 2026-10-22

I fit `building-zones-location` on rents I drew from the combined location fit's own medians
(`sim-location-fitted-20261022`), at the code of #1212 (35131df8), with the night's settings: 4
chains, 300 warmup, 1,000 sweeps with every 5th kept, seed 20261021, fit-only. The run is
`building-zones-location-b0-latest-35131df8-dense-w1000`. Its fit stages took 20 minutes, at a
Modal cost estimate of $0.88 from the `ops/modal-fit` log. The predictions are in
docs/notes/simulated-recovery-location-predictions-2026-10-22.md.

In the folder `simulated-recovery-location-2026-10-22`:

- `score.json` is the output of `python -m rentfrontier.simulate score`. This PR also fixes the
  scorer, which failed on a fit with no columns beyond the truth's.
- `leak.py` compares the fitted map with the true map at every building with training rows,
  by fifths of each location column. Its output is `leak.json`.

All numbers are in points of log rent x100.

## Against the predictions

| prediction | result | hit |
|---|---|---|
| passes the gate | max R-hat 1.003 (`unit:elev_f16`), min ESS 688 (`amp[outer]`) | yes |
| each location coefficient's 90% interval covers its planted value | all six do (table below) | yes |
| water's median within 0.8 of -1.65 | -1.16, off by 0.49 | yes |
| the other five within 0.3 of the truth | off by 0.00 to 0.18 | yes |
| 90% coverage of all coefficients, nu and the sigmas between 80% and 97% | 82.4% over 125 terms | yes |
| map error under 0.5 in size in the nearest and farthest fifths by big-park distance | -0.35 and +0.22 | yes |
| the same by water distance | +0.45 and -0.24 | yes |
| the source fit's amplitudes inside the new fit's 90% intervals | Manhattan 0.868 in 0.728 to 1.027, outside 0.345 in 0.281 to 0.423 | yes |

## The location terms

| term | planted | recovered (90%) |
|---|---|---|
| `bld:log_station_km` | -0.42 | -0.41 (-0.62 to -0.22) |
| `bld:log1p_routes` | +0.97 | +0.79 (+0.38 to +1.19) |
| `bld:log_park_km` | +0.21 | +0.18 (+0.02 to +0.34) |
| `bld:log_big_park_km` | -2.08 | -2.22 (-2.71 to -1.80) |
| `bld:log_water_km` | -1.65 | -1.16 (-2.28 to +0.01) |
| `bld:log1p_noise` | -0.60 | -0.56 (-0.72 to -0.38) |

The water term comes back 0.49 smaller in size, and its interval reaches 0. In the nearest
fifth by water distance the map runs 0.45 above the truth, which accounts for that gap: the map
took a little of the water's level. The big-park term goes the other way, 0.15 larger in size
than planted, and the map in the nearest fifth by big-park distance runs 0.35 below the truth.
Both moves are smaller than each term's posterior SD.

Across all buildings with training rows, the slope of the map's error on the planted location
contribution is -0.02 in Manhattan and -0.03 outside it. The planted contribution has an SD of
1.9 and 2.3 points across those buildings, and the map's error an SD of 0.5 and 0.4.

## The other terms

Coverage is 82.4% over 125 scalar terms, with 22 misses. As in the floor model's recovery, the
misses are mostly terms with many rows and narrow intervals: size, in-unit laundry, dishwasher
and the bed steps, each off by under 1.1 points. `bld:condo` comes back at 9.37 against 10.01,
and `bld:built_1980_1999` at -1.13 against -1.82. The map's 90% bands cover the true map at
every building with rows in both zones, with slopes of 0.99 and 1.00. The building spread
comes back at 0.170 and 0.102 against realized spreads of 0.176 and 0.101.

## Reading it

When the six location terms are true, the model returns them, and the map doesn't absorb them.
The leakage between the map and the water term runs under half a point, and the big-park term
around Central and Prospect Park comes back whole.

This helps read the building holdout. There the location fit's map moved against the columns
at held-out buildings, so its forecasts barely changed. Here, with the columns true by
construction, the model keeps them apart from the map, so the holdout result doesn't come from
the model failing to tell the two apart. It fits a simpler reading: the floor fit's map already
holds the level near big parks and the water, both fits describe the same level, and the
columns name part of it without adding information a new building's forecast can use. The
simulation can't say whether the columns cause that level, only that the model would find them
if they did.
