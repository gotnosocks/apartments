# Mid-block avenue frontage on held-out buildings: predictions, 2026-10-22

This fit tests Ben's prior that a building standing mid-block on an avenue rents 2.5% to 6% below
its side-street neighbors. The location columns failed the whole-building holdout
(docs/notes/building-holdout-location-2026-10-22.md), and my reading there was that a column
needs to vary within the map's 1 km scale to help a new building's forecast. Avenue frontage
changes from one building to the next, so it is a direct test of that reading. I wrote these
predictions before launching the fit.

## The column

`rentfrontier.building_zones_avenue` adds one building column to `building-zones-location`:
`bld:avenue_midblock` is 1 when the widest street the building faces is over 60 ft curb to
curb and its lot isn't a corner lot. Both come from the frontage snapshot
(`frontage/20261020-fbf9a82`), which the frontage fit (#1186, #1187) built from LION and the
building footprints. That fit coded the width in bands with corner as its own column, and Ben
judged the bands not convincingly additive. This column asks a narrower question: a corner on an
avenue also faces a side street, and a mid-block building faces only the avenue.

On the latest split's 1,706,837 training ads, 96,016 (5.6%) are in the 2,424 mid-block avenue
buildings, and 13% of those ads are in buildings already flagged as fronting a through truck
route (`bld:truck_through`).

## The free check

Before writing this, I compared the building effects of the latest-split location fit
(`building-zones-location-b0-latest-732b36ec-dense-w1000`) across groups, weighted by training
ads. The script and its output are in `/data1/apartments/tmp/avenue/` (`check.py`,
`check.json`). In log points x100:

- mid-block on a street over 60 ft: -2.5;
- on a street of 40 ft or less: -2.3;
- a corner on a street over 60 ft: +4.5.

Within 300 m cells holding both kinds of building, mid-block avenue buildings sit 0.6 points
below their side-street neighbors on average (SE 0.7, median -2.0, 313 cells). The gap in 150 m
cells is -0.9 (SE 0.6). So the model's building effects show little room for a mid-block
avenue term, and most of the street premium sits in wide-street corners.

## The fit

I'll run `building-zones-avenue` on the whole-building split from #1212 (6,798 buildings held
out whole), on dataset `b0-edc83b49f9bacd8c-alldata-v36-dense-nyc`, at the commit that adds the
module, with the night's settings: 4 chains, 300 warmup, 1,000 sweeps with every 5th kept, seed
20261021, fit-only. I'll score it against the location fit on the same split,
`building-zones-location-b0-buildings-35131df8-dense-w1000`, with the held-out scoring from
docs/notes/building-holdout-location-2026-10-22/heldout/.

## Predictions

- It passes the gate (R-hat <= 1.01, ESS > 400). The fit stages take 17 to 22 minutes, at a
  Modal cost estimate of $0.75 to $0.95.
- `bld:avenue_midblock` has a median between -2.5 and +0.5 points, and its 90% interval reaches
  0. If the median is below -2.5, Ben's prior holds and the free check missed it.
- `bld:truck_through` moves by under 0.5 points, and every other term by under 0.1.
- On the 184,437 held-out ads, the avenue fit's elpd differs from the location fit's by less
  than 2 SE (by building).
- On the held-out ads in mid-block avenue buildings, the elpd difference is under 50 in size.
- RMSE and 90% coverage on held-out ads move by under 0.01 points and 0.1 percentage points.
