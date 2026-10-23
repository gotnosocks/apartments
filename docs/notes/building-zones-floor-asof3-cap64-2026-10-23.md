# As-of floor model with the elevator floor curve to 64: results, 2026-10-23

This note reports follow-up fit 8, planned in `building-zones-floor-asof3-cap64-predictions-2026-10-23.md`. The fit gives elevator floors 48 to 64 their own points on the floor curve, where the asof2 fit of #1241 pooled every floor from 47 up into one node. I scored its held-out ads with `docs/notes/conference-followups-2026-10-22/score.py` (400 draws) and compared them with the asof2 fit's using `compare.py`. Points are points of log rent x100.

| run | wall | sampling | cost | max R-hat | min ESS |
|---|---|---|---|---|---|
| `building-zones-floor-asof3-cap64-b0-latest-26504752-cap64-w1000` | 21 min | 881 s | about $0.83 | 1.0078 (`amp[outer]`) | 554 (`amp[outer]`) |

The sweep took 0.78 s. Every quantity other than `amp[outer]` has R-hat under 1.006 and ESS over 630, and the next worst is the thin studio bath step `bed=0:full>=3` (1.0053, 635). On the coefficients, the four chains' medians spread by 0.3 points or less, apart from three studio and one-bedroom bath steps with under 200 rows (`bed=0:full>=3` 0.80, `bed=1:full>=4` 0.40, `bed=1:full>=3` 0.30). The widest spread on the new floors is 0.27, at floor 59.

## The top of the elevator curve

| elevator floor | training rows | fit 8 median (90%) | asof2 median (90%) |
|---|---|---|---|
| 30 | 4,824 | 9.42 (9.13 to 9.70) | 9.38 (9.08 to 9.66) |
| 40 | 1,833 | 12.70 (12.27 to 13.14) | 12.74 (12.34 to 13.16) |
| 46 | 1,045 | 14.29 (13.72 to 14.84) | 14.28 (13.76 to 14.80) |
| 47 | 974 | 14.54 (14.03 to 15.08) | 17.57 (17.29 to 17.83), floors 47 and up |
| 50 | 743 | 16.17 (15.52 to 16.82) | |
| 55 | 291 | 19.47 (18.61 to 20.28) | |
| 60 | 379 | 23.04 (22.22 to 23.98) | |
| 64 and up | 976 | 25.71 (25.06 to 26.46) | |

Below 47 the curve stays where it was, within 0.06 points at every floor. Above 47 it climbs about 0.66 points a floor, twice its slope of about 0.30 a floor between 30 and 46. Floors 55 to 63 have 133 to 379 training rows each. The curve's lengthscale in log floor, `gp_ls[elev]`, falls from 0.98 (0.68 to 1.34) to 0.48 (0.38 to 0.62), which lets the curve bend upward over the top floors. Its amplitude `gp_amp[elev]` barely moves (0.074 to 0.072).

## Held-out ads

Both runs list the same 189,647 held-out ads. The new build sets two studios to one bath and drops one row, and the dropped row left the latest split's draw alone.

| ads | count | buildings | elpd change, fit 8 minus asof2 | SE by building |
|---|---|---|---|---|
| all | 189,647 | | +52 | 24 |
| floor unknown | 55,115 | 23,246 | -0.8 | 2.2 |
| floor under 30 | 128,135 | 21,755 | +8.1 | 6.7 |
| floors 30 to 46 | 5,336 | 354 | +1.1 | 6.6 |
| floor 47 | 105 | 45 | +16.9 | 4.1 |
| floors 48 and up | 956 | 71 | +27.3 | 23.8 |

I took each ad's floor from the unit floor snapshot `20261021-d84914c0` (`floor_bands.py`). Almost all of the gain comes from floors 47 and up: the 105 ads at 47 move by 4 SE, since the pooled node priced them as if they sat higher. Above 47 the gain is spread over 71 buildings, and its SE is as large as the gain. Coverage of 90% intervals on the ads at 48 and up goes from 86.4% to 86.7%, and their median residual from -3.6 to -4.5 points. Overall coverage stays at 49.3%, 79.8%, 90.3% and 95.4% for the 50%, 80%, 90% and 95% intervals.

## Against the predictions

- Passes the gate and takes 18 to 35 minutes at $0.75 to $1.40: passes, 21 minutes, about $0.83. Hit.
- The curve rises from 47 to 64 by between 1 and 6 points: it rises by 11.2. Miss.
- Its 90% band at 64 is under 4 points wide: 1.4. Hit.
- The curve below 47 moves by under 0.3 points at every floor: 0.06 at most. Hit.
- `gp_ls[elev]` changes by under 15%: it falls by 51%. Miss.
- Held-out elpd on elevator ads at floor 48 and up rises by 5 to 60: +27.3. Hit.
- On all shared held-out ads the change stays within 2 SE by building: +52 at 2.2 SE. Miss, narrowly.
- Other coefficients move by under 0.3 points: 0.24 at most (`bed=0:full>=3`). Hit.
- `bld_sd`, `sigma` and `nu` move by under 1%: 0.04% at most. Hit.
- From `amp-joint-predictions-2026-10-23.md`, without the joint step `amp[outer]` again has the worst R-hat or the least ESS, with an IAT of 5.5 to 8 sweeps: it has both, with an IAT of 7.3 from `amp_diag.py` (`amp[manhattan]` 3.8). Hit.

That gives 7 hits and 3 misses.

## Reading

I expected the top floors to add a few points over the pooled node. They add 11, and the curve has to shorten its lengthscale by half to fit them. Held-out ads above 47 back the change in direction, though not by much, since they come from only 71 buildings. Fits 6 and 7 showed that the partially pooled building levels leave part of each between-building difference to the unit columns. The top floors come mostly from a few very tall buildings, so some of the 11 points may belong to those buildings rather than to height within a building. A within-building check on the floors above 47 would separate the two; `floor_support.py` counts the contrasts it would need. The more negative median residual at floor 48 and up fits the same reading: the curve overprices the held-out ads there by about a point more than the pooled node did.

The run mixes `amp[outer]` as slowly as every centred run before it. That supports reading its gate misses in asof2 and fit 7 as a sampler problem, which the joint step in #1267 targets in fits 4 and 5.
