# Floor model with park frontage on the latest split: results, 2026-10-22

This is conference follow-up 1. I added `bld:park_front` to the floor model and fit it on the latest split. The predictions are in `building-zones-floor-parkfront-predictions-2026-10-22.md`, written before the launch.

Run: `building-zones-floor-parkfront-b0-latest-a5b3c5d3-dense-w1000`, fit-only on Modal (A100), 19 minutes, $0.76. Comparison: `building-zones-floor-b0-latest-6b5a5b4a-dense-w1000`.

## Convergence

The fit passes the gate. Max R-hat is 1.004 (`log_size_rel`), min bulk ESS 647 (`amp[outer]`).

## Coefficients

- `bld:park_front`: +4.23 points, 90% interval +3.42 to +5.04, P(>0) = 1.00. The location fit put it at +3.46 with the distance terms beside it.
- The other coefficients move by at most 0.156 points (`alpha`). The floor terms move by at most 0.004.
- `amp`, `bld_sd`, `sigma` and `nu` don't change at the reported precision.

## Held-out score

I scored both runs on the same 189,649 held-out ads with `docs/notes/conference-followups-2026-10-22/score.py` (400 draws), then ran `compare.py . parkfront:floor`.

| | elpd | RMSE | coverage 50 / 80 / 90 / 95 |
|---|---|---|---|
| park front | 149,300.3 | 0.11538 | 0.494 / 0.800 / 0.9045 / 0.955 |
| floor | 149,302.6 | 0.11538 | 0.494 / 0.799 / 0.9045 / 0.955 |

Park front minus floor is -2.2 elpd, with an SE of 1 by row, by building and two-way. The park frontage fit scores about 2 SE worse than the floor fit on these ads.

Split by building, using the 40 m threshold from the park frontage snapshot:

| held-out ads | ads | buildings | elpd difference | SE by building |
|---|---|---|---|---|
| park-facing | 6,599 | 643 | -0.9 | 1.2 |
| the rest | 183,050 | 35,599 | -1.3 | 0.6 |

On the latest split nearly every held-out ad sits in a building with training ads, so its building effect can already absorb whatever the park adds. I expect the flag to have moved that premium out of the park-facing buildings' intercepts into a named term, but I haven't checked the intercepts. The held-out predictions stay where they were, and the small loss fits a term that adds a parameter without adding information about known buildings. The buildings split (fit 2) is the test where the flag has to predict a building the fit has never seen.

## Predictions, scored

| prediction | result |
|---|---|
| passes the gate, 18 to 25 minutes, $0.75 to $1.10 | hit (19 min, $0.76) |
| median +2.5 to +5, interval excludes 0, at or above +3.46 | hit (+4.23) |
| other coefficients and floor curves move under 0.2 | hit (0.156 and 0.004) |
| latest-split elpd gain positive and under 2 SE | miss: -2.2, SE 1, about 2 SE worse |
| RMSE and 90% coverage move under 0.0005 and 0.1 pp | hit (RMSE +0.000003, 90% coverage 90.4508% against 90.4481%, +0.003 pp) |

The buildings-split predictions wait for fit 2.
