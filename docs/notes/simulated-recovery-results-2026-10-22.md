# Simulated recovery of the floor model: results, 2026-10-22

I fitted `building-zones-floor` three times on rents I simulated from known effects. The
datasets, truths and predictions are in `simulated-recovery-predictions-2026-10-22.md`
(PR #1198). Each fit used the floor fit's command at 6b5a5b4a with fit-only settings. I scored
each fit's saved draws against its truth with `python -m rentfrontier.simulate score`.
`/data1/apartments/tmp/sim-recovery/summary.json` holds every term, every floor, the map and
building coverage by density, and the four chains' medians. Each run's full scores are in
`/data1/apartments/tmp/sim-recovery/<scenario>/score.json`.

## The fits

| set | run | wall | sampling | cost | max R-hat | min ESS |
|---|---|---|---|---|---|---|
| realistic | `building-zones-floor-b0-latest-6b5a5b4a-sim-realistic-w1000` | 1,263 s | 895 s | $0.84 | 1.0078 | 654 |
| null | `building-zones-floor-b0-latest-6b5a5b4a-sim-null-w1000` | 1,155 s | 810 s | $0.77 | 1.0064 | 774 |
| height | `building-zones-floor-b0-latest-6b5a5b4a-sim-height-w1000` | 1,261 s | 918 s | $0.84 | 1.0050 | 644 |

All three pass the gate, and the worst R-hat and least ESS are on `amp[outer]` each time, as in
the floor fit on real data. The four chains agree closely. On every unit coefficient and every
floor of both curves, the spread of the chain medians stays under 0.09 points.

## Coverage

Coverage of 90% intervals over the 114 coefficients, nu and the four sigmas:

| group | terms | realistic | null | height |
|---|---|---|---|---|
| all scalar terms | 119 | 80.7% | 75.6% | 73.9% |
| floor curves | 51 | 90.2% | 72.5% | 78.4% |
| floor flags | 7 | 42.9% | 42.9% | 57.1% |
| building features | 22 | 72.7% | 77.3% | 63.6% |
| other terms | 34 | 79.4% | 82.4% | 73.5% |
| nu and sigmas | 5 | 80% | 100% | 100% |

I predicted 80 to 97% for every run. The realistic run lands inside that range, and the null and
height runs fall below it, so those two are misses. Run to run, the errors mostly don't come from
noise. The same coefficients miss in all three runs, by the same amount and in the same
direction.

| term | truth (realistic) | realistic | null (truth 0) | height |
|---|---|---|---|---|
| `unit:log_size_rel` | 25.20 | 25.84 | 25.87 (truth 25.20) | 25.79 |
| `unit:laundry_in_unit` | 6.13 | 6.52 | 0.41 | 6.56 |
| `unit:laundry_in_building` | 1.70 | 1.91 | 0.26 | 1.91 |
| `unit:dishwasher` | 1.98 | 2.11 | 0.13 | 2.15 |
| `unit:size_unknown` | -4.14 | -4.31 | -4.30 (truth -4.14) | -4.31 |
| `unit:garden` | 2.83 | 3.29 | 0.62 | 0.60 |
| `bld:condo` | 9.99 | 9.57 | -0.59 | 9.53 |

All figures are in points of log rent ×100. Each of these misses its own interval, and each moves
the same way in every run. The intervals of the common unit columns are 0.1 to 0.2 points wide,
and the bias is 0.13 to 0.68 points.

I checked the likely cause on the realistic truth. For each building with training rows I took
its true residual level and its mean of each unit column, then the row-weighted correlation:

| unit column | correlation with the building's true level | bias in the fit |
|---|---|---|
| `log_size_rel` | +0.24 | +0.59 to +0.68 |
| `laundry_in_unit` | +0.22 | +0.39 to +0.43 |
| `dishwasher` | +0.21 | +0.13 to +0.17 |
| `size_unknown` | -0.12 | -0.16 to -0.17 |
| `size_imputed` | +0.01 | -0.03 to -0.07 |
| `laundry_in_building` | -0.01 | +0.22 to +0.26 |

Buildings with bigger units, in-unit laundry and dishwashers have higher residual levels in the
fit's own estimates, and the simulated truth inherits that. The model gives each building a
partially pooled level, so it reads part of the between-building difference as a unit effect.
Each coefficient moves in the direction of its correlation. In-building laundry moves without a
correlation of its own, and I read it as taking part of in-unit laundry's shift, since both are
measured against unstated laundry. That's the classic bias of random effects correlated with
the regressors. The real fit has the same structure and should carry about the same bias, which
I haven't measured on real data. A fixed-effects comparison, or each building's mean of the unit
columns as a `bld:` term (Mundlak), would test it. Both are model changes and wait for Ben.

## Run 1, realistic

| prediction | result | |
|---|---|---|
| elevator curve inside the 90% band at every floor 2 to 30 | 26 of 29 floors; at 17, 21 and 28 the median is 0.22 to 0.27 points high and the band misses the truth by 0.01 to 0.02 | miss |
| elevator error under 0.5 points at every floor up to 40 | largest 0.58 at floor 40, 0.45 at 35 | miss |
| walk-up median positive at 3 to 6, rising 2 to 5 | 0.39, 0.78, 1.23, 1.57, 1.90 at floors 2 to 6 | hit |
| walk-up band covers the truth at 4 or more of 5 floors | all 5 | hit |
| `unit:lower` covers 0 with an interval of at least 1.5 points | -0.54 [-1.30, +0.31], 1.6 points wide | hit |
| `unit:elev_top` covers 3.92%, median 3.6 to 4.2% | 3.90 [3.82, 3.97] | hit |
| coverage 80 to 97% | 80.7% | hit |
| elevator coverage at 30 and up within 20 points of coverage below 30 | 88.9% against 89.3% | hit |
| nu and sigmas covered | nu 4.110 [4.089, 4.134] against 4.134 | miss by a hair |

## Run 2, null

| prediction | result | |
|---|---|---|
| curve intervals cover 0 at 90% or more of floors | elevator 66% (19 of 29 floors from 2 to 30), walk-up 100% | miss |
| no elevator median above 0.5 points up to floor 40 | largest 0.40 at floor 40 | hit |
| at most one floor flag misses 0 | four: garden +0.62, walk-up unknown +0.22, `elev_top` -0.10, `walkup_top` +0.10 | miss |
| at most three feature terms miss 0 | five: in-unit laundry +0.41, condo -0.59, elevator unknown +0.45, in-building laundry +0.26, dishwasher +0.13 | miss |
| no feature median above 0.7 points | largest 0.59 | hit |
| building-level slope within 0.05 of run 1 | 0.90 and 0.77 against 0.89 and 0.78 | hit |

The elevator curve, whose truth is 0 at every floor, comes back between +0.1 and +0.4 points
at almost every floor, and +0.69 at floor 41. The bias is small and positive throughout, which
fits the same mechanism: floor 1 units in elevator buildings sit in buildings with lower
levels than the units above them.

## Run 3, height

| prediction | result | |
|---|---|---|
| elevator median under 0.5 points in size at 10, 20, 30, 40 | 0.15, 0.08, -0.05, 0.06 | hit |
| intervals at 10 and 20 cover 0 | 20 covers; 10 is [0.002, 0.29] | miss at 10, by a hair |
| level keeps 85 to 115% of the planted term | 96% | hit |
| `bld:log_height` turns positive | -0.92 to +0.33 [0.03, 0.65] | hit |
| most of it goes to `bld:log_height` | 47% to the `bld:` columns, 46% to the residual levels, 3% to the map | half right |
| walk-up curve covers 0 at every floor | floor 5 misses, +0.16 [0.00, 0.31] | miss |

The planted term doesn't leak into the floor curve. The curve has the same offset of +0.1 to
+0.2 points at low floors as in the null run, where nothing was planted. The building level as a
whole absorbs the term. `bld:log_height` takes about half, and the residual levels take the rest.
The residual levels then cover worse in the tallest buildings: coverage among buildings with 100+
rows falls from 96% (Manhattan) and 95% (outer) in run 1 to 73% and 71%. Those buildings have the
most rows, the tightest intervals and the largest planted values.

## The map and the building levels

| | Manhattan | outer |
|---|---|---|
| F coverage, buildings with rows (realistic / null / height) | 98.7 / 99.1 / 97.3% | 98.3 / 93.8 / 97.7% |
| F slope of median on truth | 0.99 | 0.99 |
| building level coverage (realistic) | 90.4% | 90.4% |
| building level slope (realistic) | 0.89 | 0.78 |
| slope, 1 to 4 rows / 5 to 19 / 20 to 99 / 100+ | 0.79 / 0.94 / 0.97 / 0.98 | 0.63 / 0.87 / 0.96 / 0.99 |
| coverage, 1 to 4 rows / 100+ | 88.0 / 96.2% | 90.8 / 94.9% |

The map covers its truth at 94 to 99% in every density bin, more than 90%, because the truth is
a posterior median and smoother than the prior expects. The building levels cover at about 90%,
shrinking toward 0 as expected for buildings with few rows. Every building in the design has at
least one training row, so the empty-building bin has no sites. bld_sd comes back at 0.169 and
0.103 against realized truth SDs of 0.176 and 0.101.

## The misses

- The elevator curve's misses don't cluster at floors 30 and up. Coverage at 30 and up against
  below 30 is 89% and 89% in the realistic run, and 72% and 68% in the null run. In the height
  run it's 100% against 64%, a gap of 36 points, so my prediction of a gap under 20 misses there.
  The low floors miss in that run, not the high ones: the +0.1 to +0.2 offset at low floors
  falls outside the narrower intervals there.
- They don't cluster in sparse places either: building-level coverage is lowest among buildings
  with 1 to 4 rows (88% Manhattan), but only by a few points.
- They also don't cluster on rare flags. `unit:lower` (564 rows) and `bld:built_unknown` (7,368)
  cover in every run.
- They do cluster on common terms with narrow intervals, whose truth correlates with the building
  level. That's a bias of a fraction of a point, and the intervals don't account for it.
