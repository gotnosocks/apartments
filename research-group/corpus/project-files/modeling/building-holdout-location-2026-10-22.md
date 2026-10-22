# Location terms on held-out buildings: results, 2026-10-22

This tests whether the six transit, parks and noise columns predict rent at buildings the model
has never seen. The latest split couldn't test it, since every building it holds out has
training ads. The `buildings` split from #1212 holds out 6,798 of the 67,977 buildings whole,
184,437 ads in all. I fit both models on the rest at the code of #1212 (35131df8), with the
night's settings: 4 chains, 300 warmup, 1,000 sweeps with every 5th kept, seed 20261021,
fit-only.

| fit | run | fit stages | Modal cost estimate |
|---|---|---|---|
| floor | `building-zones-floor-b0-buildings-35131df8-dense-w1000` | 18 min | $0.78 |
| location | `building-zones-location-b0-buildings-35131df8-dense-w1000` | 19 min | $0.83 |

The cost estimates come from the `ops/modal-fit` log line of each run. The predictions are in
docs/notes/building-holdout-location-predictions-2026-10-22.md.

In the folder `building-holdout-location-2026-10-22`:

- `summary.json` compares the location fit with the floor fit on posterior medians.
  `build_summary.py` writes it.
- `heldout/heldout_split.py` scores each run's held-out ads with 400 draws and the Student-t
  likelihood. A held-out building's level comes from its zone's prior, drawn with the fit.
- `heldout/compare_buildings.py` pairs the two runs ad by ad, splits the result by fifths of
  each column and runs the explained-share test. Its output is
  `heldout/compare-buildings.json`.

All numbers are in points of log rent x100.

## Against the predictions

| prediction | result | hit |
|---|---|---|
| both fits pass the gate | location: max R-hat 1.008, min ESS 565, both on `amp[outer]`. Floor: max R-hat 1.0105 on `amp[outer]`, min ESS 668 | no, the floor fit misses by 0.0005 |
| each location coefficient lands inside the latest-split combined fit's 90% interval | all six do (table below) | yes |
| the location fit beats the floor fit by more than 2 SE, by +300 to +2,000 | +26 (SE 116, by building) | no |
| RMSE falls by 0.1 to 0.6 points | 18.169 to 18.166, a fall of 0.003 | no |
| 90% coverage moves by under 1 point | 0.9273 to 0.9272 | yes |
| the gain is larger near Central Park, Prospect Park and the water | nearest fifth by big-park distance -9 (SE 57), by water -131 (SE 62) | no |
| the location contribution's explained share of the floor fit's building residuals beats the 95th percentile of a within-zone permutation null | -0.021 against a null 95th percentile of -0.011 | no |

The floor fit's four chains agree on `amp[outer]`: their medians run from 0.329 to 0.342, and
each chain's 90% band is about 0.14 wide. In the location fit, `amp[outer]` also has the lowest
ESS (565). I haven't rerun it on another seed, and I score it anyway. The comparison below rests
on predictions, which a slow amplitude moves little.

## The coefficients

| term | building split (90%) | latest split (90%) |
|---|---|---|
| `bld:log_station_km` | -0.40 (-0.63 to -0.16) | -0.42 (-0.64 to -0.20) |
| `bld:log1p_routes` | +1.08 (+0.62 to +1.53) | +0.97 (+0.53 to +1.40) |
| `bld:log_park_km` | +0.22 (+0.05 to +0.41) | +0.21 (+0.05 to +0.40) |
| `bld:log_big_park_km` | -2.13 (-2.66 to -1.63) | -2.08 (-2.59 to -1.63) |
| `bld:log_water_km` | -1.92 (-3.24 to -0.60) | -1.65 (-2.93 to -0.40) |
| `bld:log1p_noise` | -0.56 (-0.74 to -0.36) | -0.60 (-0.77 to -0.41) |

Holding out a tenth of the buildings leaves the coefficients where they were. Every other term
moves by under 0.1 against the floor fit on the same split, except the intercept (+0.16). The
Manhattan map amplitude falls from 0.891 to 0.839 and the outside one from 0.335 to 0.325, as on
the latest split. The building spread stays at 0.184 and 0.115.

## Held-out buildings

On the 184,437 held-out ads, the location fit's log score beats the floor fit's by 26, with an
SE of 116 from per-building sums. RMSE is 18.17 in both, against 11.5 on the latest split, since
a new building's level comes from the prior. 90% coverage is 0.927 in both.

By fifths of each column (elpd difference, SE):

| column | nearest or lowest fifth | middle | farthest or highest fifth |
|---|---|---|---|
| `bld:log_station_km` | +47 (65) | +43 (79) | -64 (55) |
| `bld:log1p_routes` | +49 (52) | -153 (75) | +130 (72) |
| `bld:log_park_km` | -72 (67) | +162 (87) | -63 (40) |
| `bld:log_big_park_km` | -9 (57) | +26 (96) | +10 (33) |
| `bld:log_water_km` | -131 (62) | +144 (87) | +13 (46) |
| `bld:log1p_noise` | +37 (57) | +23 (92) | -34 (42) |

Two cells reach 2 SE, both against the location fit: the middle fifths of routes and the
nearest fifth by water. Among 18 cells that is about what chance gives, and each row splits the
same held-out ads three ways, so none of these is a finding on its own.

## The map gives it back

I averaged each fit's predictions over every held-out building's ads and compared them:

- The location columns' contribution has an SD of 2.2 points across the held-out buildings.
- The location fit's map, at the same buildings, moves against that contribution: the two
  correlate at -0.97.
- The location fit's prediction minus the floor fit's has an SD of 0.64 points, against a
  floor-fit residual SD of 13.9.

The six columns change the map much more than the prediction. My reading of the -0.97
correlation is that the floor fit's map already carries the rent level near big parks and the
water at the map's scale, and the location fit's map lowers it there to make room for the
columns. The floor fit's residual does
go the way the change points: its slope on the prediction change is 0.65, weighted by ads. But
the change is too small to show against a residual this size, and its explained share (0.0006)
falls inside the null (95th percentile 0.004).

## Reading it

This is the outside check the location columns needed, and they fail it as predictors. The
coefficients hold up on a tenth fewer buildings, and each stays within 0.1 of its single fit
when the other columns are in (docs/notes/building-zones-location-2026-10-22.md), but they don't
predict a new building's rent detectably better than the map does. They split the map into parts
with names. The big-park and water terms say how much of the map's level along Central Park,
Prospect Park and the shore those distances account for, at about 4.7 and 3.5 points across the
middle 80% of buildings. If the map already holds the level of those places at a 1 km scale, as
the correlation suggests, the names add little to a forecast.

My prediction of +300 to +2,000 assumed the columns would add to the map at new buildings. They
mostly replace it. My guess is that a column would need to vary within the map's scale to
help a forecast, as a street's noise or a building's view of the park might, and that these
distances mostly vary more slowly. I haven't tested that.

Neither fit is served, and the site doesn't change.

The explainer page for these fits is https://claude.ai/artifact/WPb5gigeP4qpMQSmqLiDVj.
