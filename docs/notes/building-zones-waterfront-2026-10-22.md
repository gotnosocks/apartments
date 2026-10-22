# Waterfront on held-out buildings: results, 2026-10-22

This fit adds `bld:waterfront` to the location model: 1 when the building's point lies within
150 m of the shoreline (#1219). I fit it on the whole-building split from #1212, which holds out
6,798 buildings and their 184,437 ads, at 201e8224 with the night's settings: 4 chains, 300
warmup, 1,000 sweeps with every 5th kept, seed 20261021, fit-only. I compare it with the
location fit on the same split.

| fit | run | fit stages | Modal cost estimate |
|---|---|---|---|
| location | `building-zones-location-b0-buildings-35131df8-dense-w1000` | 19 min | $0.83 |
| waterfront | `building-zones-waterfront-b0-buildings-201e8224-dense-w1000` | 22.0 min | $0.91 |

The fit-stage times and cost estimates come from the last line of each run's `ops/modal-fit` log.

The predictions are in docs/notes/building-zones-waterfront-predictions-2026-10-22.md, and the
explainer is https://claude.ai/artifact/9pcPNDye2ZwhV3kMuMCdP5.

The folder `building-zones-waterfront-2026-10-22` holds the same files as the park fit's folder:
`summary.json` and `build_summary.py`, the held-out scoring scripts and outputs in `heldout/`,
and the check I ran before the fit in `free-check/`.

All numbers are in points of log rent x100.

## Against the predictions

| prediction | result | |
|---|---|---|
| passes the gate | max R-hat 1.006, min ESS 716 (`amp[outer]`) | held |
| 17 to 22 minutes, $0.70 to $0.95 | 22.0 min, $0.91 | held |
| median of `bld:waterfront` in -1 to +3, 90% interval reaching 0 | +5.24, interval +3.40 to +7.15 | missed |
| `bld:log_water_km` moves under 0.5 | -1.92 to +0.19 | missed |
| other terms move under 0.2 | `alpha` +0.22, the rest under 0.1 | missed |
| held-out elpd within 2 SE | -229.0, SE 130.2 | held |
| on waterfront held-out ads, elpd difference within 2 SE of 0 | -174.7, SE 102.1 | held |
| RMSE moves under 0.02, coverage under 0.1 pp | 18.166 to 18.191 (+0.025), 92.72% to 92.70% | RMSE missed, coverage held |

The chains agree on the new term: their medians are 5.32, 5.15, 5.22 and 5.37.

## On the training buildings

The step took over the shoreline gradient. In the location fit `bld:log_water_km` sat at -1.92,
so rent rose toward the water across the whole city. With the step in the model, that term
falls to +0.19 (90% interval -1.32 to +1.71), and the first 150 m carries a premium of 5.2
points. The free check had pointed to about half of that: +3.0 (SE 1.5) against neighbors in
the same 300 m cell, and +1.6 (SE 1.4) in 150 m cells.

## On held-out buildings

The held-out sample includes 3,622 ads in 42 waterfront buildings. The location model already
priced them 4.13 points too high on average, and the waterfront fit raises that to 7.00. On those
ads elpd falls by 174.7 (SE 102.1 by building), RMSE rises from 17.75 to 18.65, and 90%
coverage falls from 92.8% to 91.5%. On the other 180,815 ads elpd falls by 54.3 (SE 77.8), from
the weaker smooth term. Over all held-out ads the change is -229.0 with SE 130.2, 1.8 SE worse.

The explained-share test against a within-zone shuffle comes out below zero. The column's
contribution explains -0.68% of the held-out building residuals, against a null 95th percentile
of 0.53%, and the prediction change explains -0.47%, against 0.38%.

## Reading it

The training buildings within 150 m of the water rent above what the smooth term and the other
traits predict, and the held-out ones rent below it. With 42 held-out buildings the gap between
the two could come partly from a few buildings on either side. The step also removes a smooth
gradient that was doing useful work on buildings farther back. So the location model's smooth
`bld:log_water_km` describes the held-out buildings better than a first-row step. A building's
point and a 150 m cut can't tell a view of the river from a highway between the building and the
water, so this result doesn't rule out a premium for an open view.

## Selection

This fit ran fit-only on the whole-building split, so the served model stays as it is. The
column makes held-out predictions worse, and its explained share is below zero. It doesn't go
into the served model.
