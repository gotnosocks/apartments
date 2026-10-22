# Parks and the waterfront in the floor model: results, 2026-10-22

I fit `building-zones-parks` on the floor fit's dataset and split
(`b0-edc83b49f9bacd8c-alldata-v36-dense-nyc`, latest split) with the floor fit's settings: 4
chains, 300 warmup, 1,000 sweeps with every 5th kept, seed 20261021, fit-only. The run is
`building-zones-parks-b0-latest-930e2a14-dense-w1000`. It took 20 minutes on a Modal A100 for
an estimated $0.79. I compare it with the base fit,
`building-zones-floor-b0-latest-6b5a5b4a-dense-w1000`, on posterior medians. The predictions
are in docs/notes/building-zones-parks-predictions-2026-10-22.md. The numbers below come from
`building-zones-parks-2026-10-22/summary.json`, which `build_summary.py` in the same folder
writes:

    python build_summary.py building-zones-parks-b0-latest-930e2a14-dense-w1000 summary.json

This fit adds the three distance columns to the floor model alone, without transit, so each
location feature gets its own test against the same base.

## Against the predictions

All coefficients in points of log rent x100 per unit of log km.

| prediction | result | hit |
|---|---|---|
| passes the gate | max R-hat 1.004 (`unit:log_size_rel`), min ESS 626 (`amp[outer]`) | yes |
| `bld:log_water_km` between -6 and -1, interval below 0 | -1.61 (-2.99 to -0.25) | yes |
| `bld:log_big_park_km` between -3 and +1, interval covering 0 | -2.13 (-2.62 to -1.63) | partly: the point is in range, but the interval sits wholly below 0 |
| `bld:log_park_km` between -1 and +3 | +0.14 (-0.05 to +0.32) | yes |
| each zone's map amplitude falls 0% to 4% | Manhattan 0.916 to 0.892 (-3%), outside 0.360 to 0.351 (-3%) | yes |
| `bld_sd` moves by under 2% | 0.183 and 0.114, unchanged | yes |
| the unit premiums move by under 0.2 | all move by under 0.01 | yes |
| held-out log score within 2 SE of the base | not scored, the fit ran fit-only | not run |

The chains agree on all three coefficients: their medians differ by at most 0.14 points, on
`log_water_km`, whose 90% interval is 2.7 points wide.

## The size of it

Distances are over the fit's 67,977 buildings. The terms' spread between the 10th and 90th
percentile buildings:

| term | median distance | p10 to p90 of the term |
|---|---|---|
| big park, 30 acres or more | 1.05 km | -1.9 to +2.8, a spread of 4.8 points |
| shoreline | 1.15 km | -1.8 to +1.4, a spread of 3.2 points |
| park of 1 acre or more | 0.24 km | -0.4 to -0.1, a spread of 0.3 points |
| all three | | -2.9 to +2.7, a spread of 5.7 points |

A building 0.25 km from a big park rents for about 3.0 points more than one 1 km away
(2.13 x ln 4). A building 0.2 km from the water rents for about 3.7 points more than one 2 km
away (1.61 x ln 10). The intercept falls by 0.28 points, close to the terms' 0.24-point average
over the fit's rows. No other term moves by more than 0.06 points.

## Reading it

Being close to a big park is worth more than I expected, and its interval is well clear of 0.
The waterfront premium matches the prediction but its interval is wide, from 0.25 to 3 points
per log km. Small parks add nothing I can tell apart from 0, which fits the free check: the
buildings near small parks tend to be in outer neighborhoods.

Together the three terms spread about 5.7 points across the middle 80% of buildings, almost
three times the transit terms' 2 points. The map amplitude falls 3% in each zone. As with
transit, that fall is well inside each fit's uncertainty on the amplitude, so the coefficients'
intervals carry the result and the amplitude doesn't.

The big park term may partly stand for the neighborhoods around Central Park and Prospect
Park, which the map also describes. Checking that would take a natural experiment, such as a
new park opening or one getting much larger, with little else in the area changing.

Neither model is served, so the site doesn't change.
