# As-of floor model and the wider amplitude prior: results, 2026-10-23

Both fits here ran on the old build, dataset `b0-edc83b49f9bacd8c-alldata-v36-dense-nyc` with ads from `rows-edc83b49f9bacd8c.parquet`, before the studio 3+ bath corrections (#1235). The predictions are in `building-zones-floor-asof-predictions-2026-10-23.md` and `building-zones-floor-asof-amp1-predictions-2026-10-23.md`, written before each launch. The refit on the corrected build has its own predictions in `building-zones-floor-asof2-predictions-2026-10-23.md`.

I scored each run on the same 189,649 held-out ads with `docs/notes/conference-followups-2026-10-22/score.py` (400 draws), using each run's own commit's source, and compared them with `compare.py`. The outputs are `asof-latest.npz` and `amp1-latest.npz` in `/data1/apartments/tmp/conference-followups/`.

## The as-of base

Run: `building-zones-floor-asof-b0-latest-9070e131-dense-w1000`, fit-only on Modal, 23 minutes, $0.92. Comparison: `building-zones-floor-b0-latest-6b5a5b4a-dense-w1000`.

The fit misses the gate on one quantity, the studio coefficient for 3+ full baths `beta[bed=0:full>=3]`, with R-hat 1.0103 and bulk ESS 373. Every other quantity passes. I didn't refit on a new seed. I read the 70 training rows in that cell instead, and none of them was a studio with 3+ full baths:
- about 14 were commercial spaces;
- about 25 had the bedroom count missing or swapped;
- 7 came from 45 Wall St;
- the rest were whole houses, shared rooms or empty ads.

Under the as-of rebuild 13 of these rows lost the size they had imputed from later ads, which loosened the cell further. The Data improvements thread corrected these rows in the ledger (#1235).

| | elpd | RMSE | coverage 50 / 80 / 90 / 95 |
|---|---|---|---|
| as-of | 149,128 | 0.1154 | 0.495 / 0.800 / 0.905 / 0.955 |
| floor | 149,303 | 0.1154 | 0.494 / 0.799 / 0.904 / 0.955 |

As-of minus floor is -175 elpd, with an SE of 82 by row, 104 by building and 106 two-way, about 1.7 SE. The snapshot features gave each held-out ad the sizes and building flags of its own and later ads, and taking them away costs about 175 elpd over 189,649 ads.

Coefficients against the floor fit, in points:
- `log_size_rel` 25.20 to 26.07 (+0.87); `size_unknown` +0.60;
- `elevator` +0.03, `doorman_full` +0.16, `gym` -0.20;
- the floor curves move by at most 0.26 (`walkup_f5`);
- `bed=0:full>=3` 31.82 to 41.04 (+9.21) and `bed=0:full>=4` -12.59, both in the misfit cell.

`nu` goes from 4.134 to 4.103, `bld_sd` from 0.1832 and 0.1139 to 0.1845 and 0.1142, and `amp` from 0.916 and 0.360 to 0.905 and 0.370. `sigma` doesn't change at the reported precision.

| prediction | result |
|---|---|
| passes the gate, 18 to 30 minutes, $0.75 to $1.20 | miss on the gate (one quantity); time and cost hit |
| elpd falls by 100 to 2,000 and by more than 2 SE by building | partial: -175 is in range, at 1.7 SE |
| RMSE rises under 0.003, 90% coverage within 1 pp of 0.904 | hit |
| log size coefficients move under 0.03 | hit (0.0087 on the log scale) |
| elevator, doorman, gym move under 1 point | hit |
| floor curves move under 0.5 points below floor 47 | hit (0.26) |
| `bld_sd`, `sigma`, `nu` change under 2% | hit |

## Fit 3: HalfNormal(1.0) on the zone map amplitude

Run: `building-zones-floor-asof-amp1-b0-latest-2015f8ef-dense-w1000`, fit-only on Modal, 19 minutes, $0.79. Comparison: the as-of base above.

The fit misses the gate on the same quantity, R-hat 1.0102 and bulk ESS 373, for the reason above.

The Manhattan amplitude goes from 0.905 to 1.027 (+0.12), and the outer amplitude from 0.370 to 0.385 (+0.015). The largest coefficient move is 0.015 points (`bed=0:full>=4`), and `bld_sd`, `sigma` and `nu` don't change at the reported precision. The old prior held the Manhattan amplitude about 13% lower.

On held-out ads fit 3 matches the as-of base: elpd 149,128 in both, a difference under 1 with SE under 1, RMSE 0.1154, coverage 0.494 / 0.800 / 0.905 / 0.955. Against the floor fit it is -174, SE 104 by building.

| prediction | result |
|---|---|
| passes the gate, 18 to 30 minutes, $0.75 to $1.20 | miss on the gate (same quantity); time and cost hit |
| Manhattan amplitude rises by 0.02 to 0.15 | hit (+0.12) |
| outer amplitude moves under 0.03 | hit (+0.015) |
| elpd changes under 2 SE by building | hit (under 1) |
| RMSE and coverage move under 0.0005 and 0.1 pp | hit |
| coefficients and hyperparameters move under 0.1 points or 1% | hit |

The wider prior stays in the remaining follow-ups only where the amplitude matters to the question. The refit on the corrected build keeps HalfNormal(0.3), so its comparison with the as-of base isolates the data change.
