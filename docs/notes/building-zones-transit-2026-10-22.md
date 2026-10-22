# Transit access in the floor model: results, 2026-10-22

I fit `building-zones-transit` on the floor fit's dataset and split
(`b0-edc83b49f9bacd8c-alldata-v36-dense-nyc`, latest split) with the floor fit's settings: 4
chains, 300 warmup, 1,000 sweeps with every 5th kept, seed 20261021, fit-only. The run is
`building-zones-transit-b0-latest-488a36f5-dense-w1000`. It took 17 minutes on a Modal A100 for
an estimated $0.66. I compare it with the base fit,
`building-zones-floor-b0-latest-6b5a5b4a-dense-w1000`, on posterior medians. The predictions
are in docs/notes/building-zones-transit-predictions-2026-10-22.md. The numbers below come from
`building-zones-transit-2026-10-22/summary.json`, which `build_summary.py` in the same folder
writes:

    python build_summary.py building-zones-transit-b0-latest-488a36f5-dense-w1000 summary.json

## Against the predictions

All coefficients in points of log rent x100.

| prediction | result | hit |
|---|---|---|
| passes the gate | max R-hat 1.008, min ESS 711 (both `amp[outer]`) | yes |
| `bld:log1p_routes` between +3 and +10, 90% interval above 0 | +0.99 (0.57 to 1.40) | no, a third of the low end |
| `bld:log_station_km` within 2 of 0, interval covering 0 or slightly below | -0.32 (-0.55 to -0.12) | partly: the point is close to 0, but the interval sits wholly below it |
| each zone's map amplitude falls 0% to 8% | Manhattan 0.916 to 0.887 (-3%), outside 0.360 to 0.332 (-8%) | yes |
| `bld_sd` moves by under 2% | 0.183 and 0.114, unchanged | yes |
| the unit premiums move by under 0.2 | all unit columns move by under 0.01 | yes |
| held-out log score within 2 SE of the base | not scored, the fit ran fit-only | not run |

The routes coefficient came out much smaller than the free check suggested. That check
regressed the simulated site levels, map value included, on the two columns and the zone alone.
A likely reason for the gap is that the fit's map, which bends to any smooth pattern, keeps most
of the share the check gave to the routes count. I haven't tested that directly.

## The size of it

Both terms point the expected way: more services nearby and a shorter walk to the nearest stop
go with higher rent. Over the fit's 67,977 buildings, the two terms together add 1.0 points at the 10th percentile,
1.8 at the median and 3.0 at the 90th. A building with 6
services within 0.8 km, the Manhattan median, gets about 0.8 points more from the routes term
than one with 2, the median outside Manhattan. A building 0.8 km from a stop gets about 0.45
points less than one 0.2 km away.

The intercept falls by 2.1 points, which takes back the new terms' average over the fit's rows.
That row average is 2.08 points, above the 1.9-point average over buildings, since the rows lean toward Manhattan. No other
term moves by more than 0.11 points.

## Reading it

Transit access, measured this way, comes out as a small premium on top of the map: about 2 points
between a building at the 10th percentile and one at the 90th. It takes 3% of the map's amplitude in Manhattan and 8%
outside it. By the rule I set before the fit, this counts as a measured premium and not as
absorbed by the map, since the amplitude fell by more than 2% and the routes interval sits above
0. The amplitude part of that rule is weak: each fit's 90% interval on the amplitude spans a
third or more of its median, so a 3% or 8% fall is well inside either fit's uncertainty. The
routes interval carries the conclusion. It is a small premium, and with no held-out score I
can't yet say whether it predicts better.

The map still carries most of the location signal. A straight-line distance and a count of
services within 0.8 km are coarse measures of access, so commute time to job centers is a
natural next transit feature to try.

Neither model is served, so the site doesn't change.

The explainer page for this fit is https://claude.ai/artifact/QNn6Fo5yNdJZSKUnWcSkng.
