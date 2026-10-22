# Elevated subway track on held-out buildings: results, 2026-10-22

This fit adds `bld:elevated` to the location model: 1 when the building's footprint outline lies
within 30 m of an elevated subway track (#1222). I fit it on the whole-building split from #1212,
which holds out 6,798 buildings and their 184,437 ads, at 4a327dbd with the night's settings: 4
chains, 300 warmup, 1,000 sweeps with every 5th kept, seed 20261021, fit-only. I compare it with
the location fit on the same split.

| fit | run | fit stages | Modal cost estimate |
|---|---|---|---|
| location | `building-zones-location-b0-buildings-35131df8-dense-w1000` | 19 min | $0.83 |
| elevated | `building-zones-elevated-b0-buildings-4a327dbd-dense-w1000` | 17.6 min | $0.73 |

The fit-stage times and cost estimates come from the last line of each run's `ops/modal-fit` log.

The predictions are in docs/notes/building-zones-elevated-predictions-2026-10-22.md, and the
explainer is https://claude.ai/artifact/5Q6MzGHVLeoPrdCgpRJwuD.

The folder `building-zones-elevated-2026-10-22` holds the same files as the waterfront fit's
folder: `summary.json` and `build_summary.py`, the held-out scoring scripts and outputs in
`heldout/`, and the check I ran before the fit in `free-check/` (`check_outline.py` measures from
the footprint outline as the column does, and `check.py` from the building's point).

All numbers are in points of log rent x100.

## Against the predictions

| prediction | result | |
|---|---|---|
| passes the gate | max R-hat 1.006, min ESS 699 (`amp[outer]`) | held |
| 16 to 22 minutes, $0.70 to $0.95 | 17.6 min, $0.73 | held |
| median of `bld:elevated` in -5 to -1, 90% interval excluding 0 | -2.46, interval -3.55 to -1.52 | held |
| `bld:log_station_km` and `bld:log1p_routes` move under 0.3 | -0.05 and -0.02 | held |
| other terms move under 0.2 | `alpha` -0.08, `bld:retail` +0.07, the rest under 0.05 | held |
| held-out elpd within 2 SE | -40.6, SE 51.3 | held |
| on elevated-track held-out ads, elpd within 2 SE of 0 | -6.6, SE 32.4 | held |
| on those ads, mean residual moves toward 0 | -0.62 to +1.48 | missed |
| RMSE moves under 0.01, coverage under 0.1 pp | 18.166 to 18.169 (+0.003), 92.72% to 92.76% | held |

The chains agree on the new term: their medians are -2.47, -2.42, -2.51 and -2.46.

## On the training buildings

The fit puts a building under 30 m from the track 2.5 points below other buildings with the same
measured traits. The free check before the fit gave -3.1 (SE 0.9) against neighbors in the same
150 m cell, and -1.6 (SE 1.1) in 300 m cells, so the fitted value lies between the two. Nothing
else in the model moved: the station and route terms, which reward being near the same lines,
changed by 0.05 or less.

## On held-out buildings

The held-out sample includes 1,005 ads in 46 elevated-track buildings. The location model priced
them 0.62 points too high on average, so it already had them about right. The elevated fit lowers
them by about 2.1 and leaves them 1.48 too low. On those ads elpd falls by 6.6 (SE 32.4 by building),
RMSE stays at 15.49, and 90% coverage goes from 91.6% to 92.0%. On the other 183,432 ads elpd
falls by 34.0 (SE 40.0). Over all held-out ads the change is -40.6 with SE 51.3.

The explained-share test against a within-zone shuffle doesn't beat its null. The column's
contribution explains -0.014% of the held-out building residuals, against a null 95th percentile
of 0.043%, and the prediction change explains -0.054%, against 0.27%.

## Reading it

Training buildings along the track rent below their neighbors, and the 46 held-out ones don't.
With only 46 held-out buildings, the held-out sample can't tell a 2.5-point discount from
none: the elpd SE on them is 32, and the whole effect on their ads is a few points. So the held-out buildings neither confirm nor rule out
the training estimate, and they lean toward a smaller one.

## Selection

This fit ran fit-only on the whole-building split, so the served model stays as it is. The
column doesn't improve held-out predictions or beat the explained-share null, so it doesn't go
into the served model.
