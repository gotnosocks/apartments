# Transit, parks and noise together in the floor model: results, 2026-10-22

I fit `building-zones-location`, which adds all six location columns from the transit, parks and
noise fits to the floor model at once. It ran on the floor fit's dataset and split
(`b0-edc83b49f9bacd8c-alldata-v36-dense-nyc`, latest split) with the same settings: 4 chains,
300 warmup, 1,000 sweeps with every 5th kept, seed 20261021, fit-only. The run is
`building-zones-location-b0-latest-732b36ec-dense-w1000`. It took about 16 minutes on a Modal
A100 for an estimated $0.66. The predictions are in
docs/notes/building-zones-location-predictions-2026-10-22.md.

In the folder `building-zones-location-2026-10-22`:

- `summary.json` compares the run with the floor fit on posterior medians. `build_summary.py`
  writes it.
- `heldout/` holds the held-out scoring I ran afterwards on thelio, the scripts and their
  output:
  - `heldout.py` scores each run's latest-split held-out ads (400 draws, Student-t);
  - `compare.py` pairs each run with the floor run;
  - `byfeature.py` splits the combined run's gain by fifths of each column;
  - `variance.py` splits the fitted rent of the training ads into map, building, location and
    error variance.

All numbers are in points of log rent x100.

## Against the predictions

| prediction | result | hit |
|---|---|---|
| `bld:log_big_park_km` stays in -2.6 to -1.6, interval below 0 | -2.08 (-2.59 to -1.63) | yes |
| `bld:log_water_km` stays in -2.5 to -0.5 | -1.65 (-2.93 to -0.40) | yes |
| `bld:log1p_routes` lands in +0.3 to +1.0 | +0.97 (+0.53 to +1.40) | yes, but it barely shrank from the single fit's +0.99 |
| `bld:log1p_noise` lands in -0.7 to -0.2 | -0.60 (-0.77 to -0.41) | yes |
| station and park stay within 0.3 of their single fits | station -0.32 to -0.42, park +0.14 to +0.21 | yes |
| no term changes sign with an interval excluding 0 | none changes sign. `bld:log_park_km` was +0.14 (-0.05 to +0.32) and is now +0.21 (+0.05 to +0.40) | yes |
| Manhattan amplitude falls 3% to 12% from 0.916 | 0.868 (-5.3%) | yes |
| outside amplitude ends in 0.32 to 0.40 | 0.346 | yes |
| `bld_sd` moves under 2% | 0.183 and 0.114, unchanged | yes |
| unit premiums move under 0.1 | all under 0.01 | yes |

It passes the gate: max R-hat 1.005 (`nu`), min ESS 616 (`amp[outer]`). The four chains agree
on every location term to within 0.1 points except water, whose chain medians run from -1.59 to
-1.76.

The six columns barely overlap. Each coefficient lands within 0.1 points of its single fit.
I expected routes to shrink once parks and the water were in, since the waterfront and the
subway lines both run along Manhattan's avenues and through downtown Brooklyn. It stays at 0.97.

## Each feature

I measure the spread as the 10th to 90th percentile of a term's contribution over the training
ads. The share is the variance of a term's contribution as a fraction of the variance of log
rent across those ads (0.192). The held-out columns give the paired log score of the combined
fit minus the floor fit's on the latest split's held-out ads in the bottom and top fifth of the
column, with SE from per-building sums.

| term | coefficient (90%) | spread p10 to p90 | share of rent variance | held-out, bottom fifth | held-out, top fifth |
|---|---|---|---|---|---|
| `bld:log_station_km` | -0.42 (-0.64 to -0.20) | 0.7 | 0.004% | -0.3 (SE 0.5) | +0.5 (0.6) |
| `bld:log1p_routes` | +0.97 (+0.53 to +1.40) | 1.8 | 0.02% | -0.5 (0.9) | +0.5 (0.6) |
| `bld:log_park_km` | +0.21 (+0.05 to +0.40) | 0.4 | 0.001% | +2.1 (1.3) | -0.6 (0.5) |
| `bld:log_big_park_km` | -2.08 (-2.59 to -1.63) | 4.7 | 0.18% | +1.7 (1.3) | -0.1 (0.4) |
| `bld:log_water_km` | -1.65 (-2.93 to -0.40) | 3.5 | 0.09% | -0.4 (0.4) | +0.6 (1.3) |
| `bld:log1p_noise` | -0.60 (-0.77 to -0.41) | 1.2 | 0.01% | +0.1 (0.8) | -0.2 (0.5) |

Each fifth holds about 38,000 held-out ads (51,000 for the routes bottom fifth, where ties at 0
routes fall together). None of the held-out differences reaches 2 SE. RMSE changes by under 0.002
points in every fifth.

Big parks carry most of what the six columns explain: a building at the 10th percentile of
distance to a big park, mostly along Central and Prospect Park, rents 4.7 points above one at
the 90th, the rest alike. The water comes next at 3.5 points. Together the six terms explain
0.26% of the variance of log rent. That is small because the map already describes these
places. The test is how much of the map they take over.

## Map, building and error variance

Over the 1,706,837 training ads, with each fit's posterior medians:

| part | floor fit | combined fit | change |
|---|---|---|---|
| map | 0.0436 | 0.0403 | -7.6% |
| location terms | 0 | 0.0005 | |
| map plus location terms | 0.0436 | 0.0429 | -1.5% |
| building effects | 0.0159 | 0.0159 | -0.4% |
| error | 0.0146 | 0.0146 | 0.0% |

The six columns take over 7.6% of the map's variance. The location terms and the map that
remains correlate positively, so the two together keep 98.5% of the old map's variance. The
building effects and the error don't move. The columns explain a part of where rents are high,
and the rest of the map still holds the larger part.

Of the map that remains, routes correlates most with it (0.55), then the water (0.36). Those
correlations say the map still holds rent that lines up with transit and the waterfront beyond
what the linear terms take.

## Held-out log score on the latest split

On the 189,649 held-out ads of the latest split, paired with the floor fit:

| fit | elpd difference | SE (buildings) |
|---|---|---|
| transit | +0.2 | 0.7 |
| parks | +2.9 | 1.6 |
| noise | -0.3 | 0.8 |
| combined | +1.9 | 1.7 |

RMSE is 11.537 against 11.538, and 90% coverage 0.9046 against 0.9045. No fit clears 2 SE. On
the latest split every held-out building also has training ads, so the building effect already
holds most of what a location column could add, and the split can't show much. Breaking the
held-out ads down by their building's training ads gives the same answer: buildings with 1 or 2
training ads differ by -0.4 (SE 0.8), and buildings with 3 to 5 by +1.4 (SE 0.7). The
whole-building split from #1212 holds out buildings with no training ads at all, which tests
the columns where they matter. Those two fits run next.

## Reading it

Distance to a big park and to the water are the two location facts in this model with a clear
price. A Central Park or Prospect Park edge is worth about 4.7 points over a building 90th
percentile far from one, and the waterfront about 3.5. Transit routes add about 1.8 points
across the middle 80%, nearest-station distance 0.7 and outdoor noise 1.2. These numbers move by
under 0.1 between the single fits and the combined one, so each holds up whether or not the
others are in.

The model isn't served. The latest split can't tell the combined fit from the floor fit, so the
selection rules don't pass, and the site doesn't change.
