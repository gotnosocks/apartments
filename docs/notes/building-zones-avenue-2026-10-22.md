# Mid-block avenue frontage on held-out buildings: results, 2026-10-22

This fit adds `bld:avenue_midblock` to the location model: 1 when the widest street a building
faces is over 60 ft curb to curb and its lot isn't a corner (#1217). I fit it on the
whole-building split from #1212, which holds out 6,798 buildings and their 184,437 ads, at
c33ce2bd with the night's settings: 4 chains, 300 warmup, 1,000 sweeps with every 5th kept, seed
20261021, fit-only. I compare it with the location fit on the same split.

| fit | run | fit stages | Modal cost estimate |
|---|---|---|---|
| location | `building-zones-location-b0-buildings-35131df8-dense-w1000` | 19 min | $0.83 |
| avenue | `building-zones-avenue-b0-buildings-c33ce2bd-dense-w1000` | 18 min | $0.74 |

The predictions are in docs/notes/building-zones-avenue-predictions-2026-10-22.md, and the
explainer is https://claude.ai/artifact/GZuHVXLLdTyCvVHmXBF63V.

In the folder `building-zones-avenue-2026-10-22`:

- `summary.json` compares the two fits on posterior medians, and `build_summary.py` writes it.
- `heldout/heldout_split.py` scores each run's held-out ads with 400 draws, and
  `heldout/compare_buildings.py` pairs the runs ad by ad and runs the explained-share test
  (`heldout/compare-buildings.json`). Its fifths split doesn't suit a 0/1 column, so
  `heldout/flagged.py` pairs the flagged and unflagged ads separately (`heldout/flagged.json`).
- `free-check/` holds the check I ran before the fit.

All numbers are in points of log rent x100.

## Against the predictions

| prediction | result | |
|---|---|---|
| passes the gate | max R-hat 1.006, min ESS 682 (`amp[outer]`) | held |
| 17 to 22 minutes, $0.75 to $0.95 | 18 min, $0.74 | time held, cost missed by a cent |
| median of `bld:avenue_midblock` in -2.5 to +0.5, 90% interval reaching 0 | -1.83, interval -2.48 to -1.27 | median held, interval missed |
| `bld:truck_through` moves under 0.5 | +0.56 | missed |
| other terms move under 0.1 | `bld:log_big_park_km` -0.18, the rest under 0.1 | missed |
| held-out elpd within 2 SE | +85.8, SE 89.4 | held |
| on flagged held-out ads, elpd difference under 50 in size | +62.7, SE 59.4 | missed |
| RMSE moves under 0.01, coverage under 0.1 pp | 18.166 to 18.152 (-0.014), 92.72% to 92.69% | RMSE missed, coverage held |

The chains agree on the new term: their medians are -1.85, -1.85, -1.85 and -1.76.

## On held-out buildings

The held-out sample includes 8,678 ads in 236 mid-block avenue buildings. The location model
priced them 2.73 points too high on average (mean residual -2.73), and the avenue fit cuts that
to -1.18. On those ads elpd rises by 62.7 (SE 59.4 by building) and RMSE falls from 17.67 to
17.51. On the other 175,759 ads elpd rises by 23.1 (SE 66.8). Over all held-out ads the gain is
+85.8 with SE 89.4, under 1 SE.

The explained-share test against a within-zone shuffle doesn't beat its null: the column's
contribution explains 0.13% of the held-out building residuals, against a null 95th percentile
of 0.29%.

## Reading it

The fit puts mid-block avenue buildings 1.8 points below other buildings with the same measured
traits, and the held-out buildings agree on the sign and on roughly the size. The comparison
group is every other building, though, and that group includes wide-street corners. My free check
had them 4.5 points above the average building effect, while side-street buildings sat at -2.3
and mid-block avenue ones at -2.5. Within 300 m cells, mid-block avenue buildings sat only 0.6
points (SE 0.7) below their side-street neighbors. So I read most of the -1.8 as the gap between
a mid-block avenue building and an avenue corner, not between an avenue and a side street. This
fit doesn't separate the two. A fit with a wide-corner column beside this one would.

`bld:truck_through` moved up by 0.56, toward zero. Many truck routes run along avenues, so the
two columns share some of the same contrast.

## Selection

This fit ran fit-only on the whole-building split, so the served model stays as it is. Under the
evaluation rules the held-out gain is under 2 SE and the explained share doesn't beat its null,
so on this evidence the column doesn't go into the served model.
