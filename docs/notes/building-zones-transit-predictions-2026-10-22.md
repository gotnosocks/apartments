# Transit access in the building-means model: predictions, 2026-10-22

This is the first explanatory location feature on the night's queue. I wrote these predictions
before launching the fit. I'll fit it on top of the building-means (Mundlak) model if Fit B
makes that model the base, and on top of the floor model otherwise. The comparisons below are
against whichever base the fit uses.

## The data

`rentfrontier.building_transit` measures each building's straight-line distance to every
subway stop (the MTA's 496 stations with their daytime routes) and every PATH stop (13), and
writes `external/building-transit/20261022-a4d8ac25`. It covers 76,204 NYC and NJ buildings.
For each one it keeps:

- `station_km`, the distance to the nearest stop (median 0.33 km);
- `routes_800m`, the distinct daytime services at stops within 0.8 km, with PATH counted as one
  (median 3).

## The change

`rentfrontier.building_zones_transit` adds two `bld:` columns to the base:

- `bld:log_station_km`, log of `station_km` floored at 0.05 km;
- `bld:log1p_routes`, log(1 + `routes_800m`).

A building missing from the snapshot gets the snapshot's medians. Everything else is unchanged.

## A free check before the fit

I regressed the realistic simulation's true site levels (the floor fit's own map value F and
building residual, weighted by rows) on the two columns plus the zone, on thelio:

| target | log km coef | log(1+routes) coef | variance beyond zone explained |
|---|---|---|---|
| map F | -0.002 | +0.103 | 16.9% |
| building residual | -0.004 | -0.025 | 1.4% |
| F + residual | -0.006 | +0.078 | 7.6% |

The services count carries almost all of it. Distance to the nearest stop adds little once the
count is in. Median `routes_800m` is 6 in Manhattan and 2 outside it.

## Predictions for the real-data fit

- It passes the gate (R-hat <= 1.01, ESS > 400).
- `bld:log1p_routes` comes back positive, between +0.03 and +0.10, with its 90% interval above
  0. The map soaks up most of the same pattern already, so the coefficient comes in below the
  check's +0.10.
- `bld:log_station_km` lands within 0.02 of 0, with its 90% interval covering 0 or slightly
  below it.
- Each zone's map amplitude falls by 0% to 8%. The building spread `bld_sd` moves by under 2%.
- The unit premiums move by under 0.2 points each.
- Held-out log score on the latest split, scored on thelio from the saved draws, comes within 2
  SE of the base's. I expect no clear gain: the map can already represent a smooth pattern
  tied to stations, so the feature mostly renames variance the map already explains.

If the amplitude falls by less than 2% and the routes coefficient covers 0, I'll record transit
access as already absorbed by the map at this resolution, and not as a measured premium.
