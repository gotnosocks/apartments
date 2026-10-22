# Park frontage on held-out buildings: results, 2026-10-22

This fit adds `bld:park_front` to the location model: 1 when the building's footprint outline
lies within 40 m of the edge of an NYC Parks property of 5 acres or more (#1218). I fit it on
the whole-building split from #1212, which holds out 6,798 buildings and their 184,437 ads, at
188d83cf with the night's settings: 4 chains, 300 warmup, 1,000 sweeps with every 5th kept, seed
20261021, fit-only. I compare it with the location fit on the same split.

| fit | run | fit stages | Modal cost estimate |
|---|---|---|---|
| location | `building-zones-location-b0-buildings-35131df8-dense-w1000` | 19 min | $0.83 |
| park | `building-zones-parkfront-b0-buildings-188d83cf-dense-w1000` | 17.7 min | $0.75 |

The predictions are in docs/notes/building-zones-parkfront-predictions-2026-10-22.md, and the
explainer is https://claude.ai/artifact/3quJMTsRerKcoze8bkNkNJ.

The folder `building-zones-parkfront-2026-10-22` holds the same files as the avenue fit's folder:

- `summary.json` compares the two fits on posterior medians, and `build_summary.py` writes it.
- `heldout/heldout_split.py` scores each run's held-out ads with 400 draws.
  `heldout/compare_buildings.py` pairs the runs ad by ad and runs the explained-share test, and
  `heldout/flagged.py` pairs the park-facing and other ads separately.
- `free-check/` holds the check I ran before the fit, re-run on the 5ddc0e5d snapshot.

All numbers are in points of log rent x100.

## Against the predictions

| prediction | result | |
|---|---|---|
| passes the gate | max R-hat 1.006, min ESS 688 (`amp[outer]`) | held |
| 17 to 22 minutes, $0.75 to $0.95 | 17.7 min, $0.75 | held |
| median of `bld:park_front` in +2 to +5, 90% interval excluding 0 | +3.46, interval +2.57 to +4.25 | held |
| `bld:log_park_km` and `bld:log_big_park_km` move under 1 | +0.15 and +0.26 | held |
| other terms move under 0.1 | `bld:log_water_km` +0.24, `bld:height_unknown` +0.12, the rest under 0.1 | missed |
| held-out elpd beats the location fit by less than 2 SE | +187.1, SE 80.1 (2.3 SE) | missed |
| on park-facing held-out ads, elpd higher | +51.6, SE 66.6 | held |
| RMSE moves under 0.02, coverage under 0.1 pp | 18.166 to 18.144 (-0.022), 92.72% to 92.71% | RMSE missed, coverage held |

The chains agree on the new term: their medians are 3.46, 3.45, 3.40 and 3.53.

## On held-out buildings

The held-out sample includes 5,204 ads in 122 park-facing buildings. The location model priced
them 4.27 points too low on average, and the park fit cuts that to 1.62. On those ads elpd rises
by 51.6 (SE 66.6 by building) and RMSE falls from 19.90 to 19.58.

On the other 179,233 ads elpd rises by 135.4 (SE 44.7), and RMSE falls from 18.113 to 18.101.
I read that gain as coming from the smooth terms: with the first row carried by the flag,
`bld:log_park_km`, `bld:log_big_park_km` and `bld:log_water_km` all moved, and those terms
reach every building. Over all held-out ads the gain is +187.1 with SE 80.1, 2.3 SE.

The explained-share test against a within-zone shuffle doesn't beat its null. The column's
contribution explains 0.30% of the held-out building residuals, against a null 95th percentile
of 0.46%. The change in the whole prediction explains 0.409%, against a null 95th percentile of
0.410%.

## Reading it

The fit puts a building facing a large park 3.5 points (90% interval 2.6 to 4.3) above other
buildings with the same measured traits, and the held-out park-facing buildings agree on the
sign and on most of the size. The free check before the fit gave a gap of 3.9 (SE 1.1) between
park-facing buildings and others in the same 150 m cell, close to the fitted value.

Of the block-scale columns fit on this split so far (avenue and park), it is the only one to beat the location fit on held-out buildings by
more than 2 SE. The explained-share test, though, misses its null by a hair on the prediction
change and clearly on the column's own contribution, so the evidence is short of the evaluation
rules' bar for a building-level feature.

## Selection

This fit ran fit-only on the whole-building split, so the served model stays as it is. A
latest-split fit with the column is the next step before it could be served.
