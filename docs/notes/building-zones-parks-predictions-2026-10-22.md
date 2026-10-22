# Parks and the waterfront in the building-means model: predictions, 2026-10-22

This is the second explanatory location feature on the night's queue. I wrote these
predictions before launching the fit. Like transit, it goes on top of the building-means
(Mundlak) model if Fit B makes that model the base, and on top of the floor model otherwise.
It does not include the transit columns, so each feature gets its own comparison against the
same base.

## The data

The parks snapshot from before covered only the Chelsea and West Village box. I refetched NYC
Parks properties over the extended registry's area (`external/parks/20261022-ec93668`, 1,041
properties). `rentfrontier.building_parks` also fetches the borough boundaries clipped to the
shoreline (gthc-hcne). It drops each borough's boundary points within 60 m of another
borough's, leaving shoreline. It writes `external/building-parks/20261022-ec936683` with
70,175 NYC buildings, and for each one it keeps:

- `park_km`, the distance to the nearest edge of a park of 1 acre or more (median 0.24 km);
- `big_park_km`, the same for parks of 30 acres or more, 19 of them in the area (median 1.05 km);
- `water_km`, the distance to the shoreline (median 1.15 km).

Spot checks: a building on Central Park West is 0.04 km from a park and 0.07 km from a big one.
Brooklyn Heights is 0.29 km from the water, and Ridgewood, next to the Brooklyn and Queens line,
is 1.8 km from it. No dataset rows are in NJ.

## The change

`rentfrontier.building_zones_parks` adds `bld:log_park_km`, `bld:log_big_park_km` and
`bld:log_water_km` to the base, each the log of the distance floored at 0.05 km. A building
missing from the snapshot gets the medians.

## A free check before the fit

I regressed the realistic simulation's true site levels on the columns plus the zone, weighted
by rows, on thelio:

| target | log park | log big park | log water | variance beyond zone explained |
|---|---|---|---|---|
| map F | +0.022 | +0.006 | -0.037 | 3.6% |
| building residual | +0.000 | -0.007 | -0.010 | 0.5% |
| F + residual | +0.023 | -0.001 | -0.047 | 3.5% |

With transit's services count added, the four columns together explain 26.8% of the map's
variance beyond the zone, against 16.9% for transit alone. The waterfront carries most of what
the parks columns add. Distance to a small park comes out with the wrong sign for an amenity:
the buildings next to small parks are more often in outer neighborhoods with more playgrounds.

## Predictions for the real-data fit

- It passes the gate (R-hat <= 1.01, ESS > 400).
- `bld:log_water_km` comes back negative, between -0.06 and -0.01, with its 90% interval
  below 0.
- `bld:log_big_park_km` lands between -0.03 and +0.01, with its interval covering 0.
- `bld:log_park_km` lands between -0.01 and +0.03. A positive value would be the neighborhood
  pattern above, not a price for being far from a park.
- Each zone's map amplitude falls by 0% to 4%. `bld_sd` moves by under 2%.
- The unit premiums move by under 0.2 points each.
- Held-out log score on the latest split comes within 2 SE of the base's, with no clear gain.
