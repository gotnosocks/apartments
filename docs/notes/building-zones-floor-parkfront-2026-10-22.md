# Floor model with park frontage: results, 2026-10-22

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


## Fit 2: the whole-building split

Run: `building-zones-floor-parkfront-b0-buildings-a5b3c5d3-dense-w1000`, fit-only on Modal (A100), 22.4 minutes, $0.89. Comparison: `building-zones-floor-b0-buildings-35131df8-dense-w1000`. I scored both runs with `docs/notes/building-zones-parkfront-2026-10-22/heldout/heldout_split.py`, each with its own commit's source, and compared them with `compare_buildings.py` and `flagged.py` from the same folder. The outputs are in `/data1/apartments/tmp/conference-followups/fit2/`.

The fit passes the gate: max R-hat 1.0058 (`beta[bed=0:full>=2]`), min bulk ESS 642 (`amp[outer]`). The comparison run misses it on one quantity, R-hat 1.0105 on `amp[outer]`.

- `bld:park_front`: +3.83 points, 90% interval +2.98 to +4.70, P(>0) = 1.00.
- The other coefficients move by at most 0.148 points (`alpha`), and the floor terms by at most 0.004 (`unit:lower`).
- `amp`, `bld_sd`, `sigma` and `nu` agree with the comparison run to the third decimal.

On the 184,437 held-out ads in 6,798 held-out buildings:

| held-out ads | ads | buildings | elpd difference | SE by building | per ad |
|---|---|---|---|---|---|
| all | 184,437 | 6,798 | +268.4 | 104.2 | 0.0015 |
| park-facing | 5,204 | 122 | +71.7 | 83.5 | 0.0138 |
| the rest | 179,233 | 6,676 | +196.7 | 62.5 | 0.0011 |

RMSE falls from 0.18169 to 0.18145, and 90% coverage goes from 0.9273 to 0.9272. The mean residual of the park-facing held-out ads falls from +4.71 points to +1.64.

The park frontage fit scores 2.6 SE better overall, but three quarters of that gain is on ads the flag doesn't touch. Their predictions differ only through the small shifts in shared terms, such as `alpha` at -0.148, and through the comparison run's unconverged `amp[outer]`. On the park-facing ads the gain is about 12 times larger per ad, at 0.9 SE, and the flag closes two thirds of their mean residual. So these 122 held-out buildings agree with the flag in direction and size, though they are too few for the gain to clear 2 SE.

The explained share of the held-out buildings' residuals is 0.00367, below the permutation null's 95th percentile of 0.00477. As with the location fit, the flag explains too little of the building-to-building spread to beat a random relabeling of buildings within zones.

## Predictions for the buildings split, scored

| prediction | result |
|---|---|
| passes the gate, 18 to 25 minutes, $0.75 to $1.10 | hit (22.4 min, $0.89) |
| median +2.5 to +5, interval excludes 0, at or above +3.46 | hit (+3.83) |
| other coefficients and floor curves move under 0.2 | hit (0.148 and 0.004) |
| elpd gain positive, larger per ad on park-facing ads | hit (+268.4; 0.0138 against 0.0011 per ad), though the park-facing gain alone is 0.9 SE |
| explained share fails the null's 95th percentile | hit (0.00367 against 0.00477) |
| RMSE and 90% coverage move under 0.0005 and 0.1 pp | hit (-0.00024, -0.01 pp) |
