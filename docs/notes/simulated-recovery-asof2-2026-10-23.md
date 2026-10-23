# Simulated recovery on the as-of floor model: results, 2026-10-23

This note reports follow-up fits 6 and 7, planned in `simulated-recovery-asof2-predictions-2026-10-23.md` (#1244). Each fits `building-zones-floor-asof2` to rents I simulated from that model's own medians. I scored each fit's saved draws against its truth with `python -m rentfrontier.simulate score`, and the full scores are in `simulated-recovery-asof2-2026-10-23/`. Points below are points of log rent x100.

## Fit 6, realistic truth

| run | wall | sampling | cost | max R-hat | min ESS |
|---|---|---|---|---|---|
| `building-zones-floor-asof2-b0-latest-0e260c3a-sim-realistic-w1000` | 1,199 s | 773 s | $0.79 | 1.0089 (`amp[outer]`) | 609 (`amp[outer]`) |

The four chains agree. On every unit coefficient and every floor of both curves, their medians spread by under 0.13 points, apart from three studio and one-bedroom bath steps with few rows (`bed=0:full>=4` 0.90, `bed=1:full>=4` 0.60, `bed=0:full>=3` 0.41).

Coverage of 90% intervals, against the first recovery's realistic run (`simulated-recovery-results-2026-10-22.md`):

| group | terms | fit 6 | first recovery |
|---|---|---|---|
| all scalar terms | 119 | 86.6% | 80.7% |
| floor curves | 51 | 96.1% | 90.2% |
| floor flags | 7 | 71.4% | 42.9% |
| building features | 22 | 81.8% | 72.7% |
| other terms | 34 | 82.4% | 79.4% |
| nu and sigmas | 5 | 60% | 80% |

The unit columns repeat the first recovery's pattern, with biases within 0.12 points of the first recovery's:

| term | truth | fit 6 median (90%) | bias | first recovery bias |
|---|---|---|---|---|
| `unit:log_size_rel` | 26.04 | 26.71 (26.60 to 26.82) | +0.67 | +0.64 |
| `unit:laundry_in_unit` | 6.16 | 6.61 (6.55 to 6.67) | +0.45 | +0.39 |
| `unit:laundry_in_building` | 1.71 | 1.95 (1.89 to 2.01) | +0.25 | +0.21 |
| `unit:dishwasher` | 1.94 | 2.07 (2.03 to 2.11) | +0.13 | +0.13 |
| `unit:size_unknown` | -3.53 | -3.68 (-3.73 to -3.63) | -0.16 | -0.17 |
| `unit:garden` | 2.79 | 3.37 (3.13 to 3.57) | +0.58 | +0.46 |
| `bld:condo` | 10.01 | 9.55 (9.15 to 9.91) | -0.46 | -0.42 |

Each of these misses its interval. The first recovery traced them to building levels correlated with the unit columns: buildings with bigger units and in-unit laundry carry higher true levels, and the partially pooled level leaves part of that difference to the unit coefficients. The building levels come back shrunk here too, with a slope of recovered on true level of 0.90 in Manhattan and 0.77 in the outer zone. The as-of features and the corrected build leave this bias where it was.

The other misses are small: `bed=4:full>=3` +0.35, `half>=1` +0.15, `flag:rent_stabilized` -0.19, `unit:size_imputed` -0.05, `unit:walkup_floor_unknown` +0.20, `unit:elev_f38` -0.44 and `unit:elev_f46` +0.56 (floors with under 2,000 rows), and two of the five noise terms, `sigma[0]` +0.03 and `sigma[2]` -0.02. The planted changes come back: `unit:elev_top` 3.96 against 3.92, and `unit:lower` 0.27 (-0.52 to 1.11) against 0.

### Against the predictions

- Passes the gate, with the worst R-hat and least ESS on `amp[outer]`. Hit.
- 90% coverage between 75% and 90%: 86.6%. Hit.
- `unit:log_size_rel` 0.4 to 0.9 points above its truth: +0.67. Hit. `unit:laundry_in_unit` 0.2 to 0.6 above: +0.45. Hit.
- Floor flags cover 3 or fewer of 7: they cover 5. Miss. Only `unit:garden` and `unit:walkup_floor_unknown` miss.

That gives 3 hits and 1 miss.

### Reading

The as-of floor model recovers its own truth about as well as the floor model did, and it keeps the same upward bias on the common amenity columns: about +0.45 points on in-unit laundry and +0.67 on size. Fit 4 (unit means) and fit 7 (a planted contextual effect) test that bias from two sides. Fit 7 asks whether a between-building effect of the size the Mundlak fit found reproduces the real-data gap between the floor and Mundlak models.

## Fit 7, contextual truth

| run | wall | sampling | cost | max R-hat | min ESS |
|---|---|---|---|---|---|
| `building-zones-floor-asof2-b0-latest-0e260c3a-sim-mundlak-w1000` | 1,161 s | 812 s | $0.77 | 1.0115 (`amp[outer]`) | 591 (`amp[outer]`) |

Fit 7 misses the gate on `amp[outer]`, the outer zone's map amplitude, by 0.0015 in R-hat. Every other quantity has R-hat under 1.005 and ESS above 1,300. On the unit columns the four chains' medians spread by 0.01 points or less, and on `bld:condo`, the widest, by 0.07. The same amplitude carried the worst R-hat and least ESS in fit 6 (1.0089, 609) and in the earlier floor fits recorded in `building-holdout-location-2026-10-22.md` and #1245, so this is the model's weakest-mixing quantity rather than something the planted term caused. I score the run as a recovery check, since none of the terms below depends on that amplitude's last digit, and I don't rerun it.

Coverage of 90% intervals, against fit 6:

| group | terms | fit 7 | fit 6 |
|---|---|---|---|
| all scalar terms | 119 | 71.4% | 86.6% |
| floor curves | 51 | 92.2% | 96.1% |
| floor flags | 7 | 71.4% | 71.4% |
| building features | 22 | 27.3% | 81.8% |
| other terms | 34 | 67.6% | 82.4% |
| nu and sigmas | 5 | 80% | 60% |

The unit columns, with each one's bias in fit 6 for the part a fit shows with no contextual term in its truth:

| term | truth | fit 7 median (90%) | bias | fit 6 bias | real-data gap, floor minus Mundlak |
|---|---|---|---|---|---|
| `unit:log_size_rel` | 24.25 | 25.46 (25.34 to 25.57) | +1.21 | +0.67 | +1.79 |
| `unit:laundry_in_unit` | 5.55 | 6.24 (6.18 to 6.30) | +0.69 | +0.45 | +0.61 |
| `unit:laundry_in_building` | 1.39 | 1.81 (1.75 to 1.87) | +0.42 | +0.25 | |
| `unit:dishwasher` | 1.83 | 1.99 (1.95 to 2.03) | +0.16 | +0.13 | +0.11 |
| `unit:size_unknown` | -3.91 | -4.15 (-4.20 to -4.10) | -0.24 | -0.16 | |
| `unit:garden` | 2.23 | 2.79 (2.57 to 3.00) | +0.56 | +0.58 | |
| `unit:size_imputed` | -0.47 | -0.49 (-0.54 to -0.44) | -0.02 | -0.05 | |

The building columns take up most of the planted term. Sixteen of the 22 terms in that group miss their intervals, among them `bld:condo` +3.87, `bld:doorman_full` +3.70, `bld:doorman_part` +2.37, `bld:built_2010_on` +2.12, `bld:built_pre1900` +1.65 and `bld:elevator` +1.52. `alpha` comes back 2.80 points low. Building levels cover their truth on 63% of Manhattan buildings and 79% of outer ones, against 91% and 90% in fit 6, with slopes of recovered on true level of 0.87 and 0.78.

### Against the predictions

- Passes the gate: max R-hat 1.0115 on `amp[outer]`. Miss.
- `unit:log_size_rel` 1.0 to 2.5 points above its truth and outside its 90% interval: +1.21, outside. Hit.
- `unit:laundry_in_unit` 0.3 to 1.0 above its truth: +0.69. Hit.
- `unit:dishwasher` within 0.4 of its truth: +0.16. Hit.
- The three biases share the real-data gap's sign, and the size bias lands within 1 point of 1.79: all three positive, and 1.21 is 0.58 from 1.79. Hit.
- Building feature coverage below run 1's 73%: 27.3%. Hit.
- Overall coverage below fit 6's: 71.4% against 86.6%. Hit.

That gives 6 hits and 1 miss.

### Reading

A contextual effect of the size the Mundlak fit found, planted in the truth and left out of the model, pushes the as-of floor model's size elasticity 1.21 points above its truth and in-unit laundry 0.69 above. On real data the floor model sits 1.79 and 0.61 points above the Mundlak fit. So the planted effect reproduces the laundry gap and about two thirds of the size gap. About half of the size bias, 0.67 points, shows up in fit 6 too, with no contextual term in the truth, so the partial pooling of building levels accounts for that part and the contextual term for the rest. The run supports the Mundlak reading of the real-data gap: the floor model's unit coefficients carry some between-building difference. It also leaves about 0.6 points of the size gap to something this simulation leaves out.

The building columns pay for the omission. Condo, doorman and age terms move by 1.5 to 3.9 points to absorb building means the model has no column for, and building-level coverage falls by about a quarter in Manhattan.
