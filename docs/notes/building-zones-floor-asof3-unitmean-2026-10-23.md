# As-of floor model with unit effects and unit means: results, 2026-10-23

This note reports follow-up fit 4, planned in `building-zones-floor-asof3-unit-predictions-2026-10-23.md` and changed before launch to `building-zones-floor-asof3-unitmean`, which adds the unit means of the columns that can change between a unit's ads. The fit ran with the joint amplitude step of #1267, so it also tests `amp-joint-predictions-2026-10-23.md`. I scored its held-out ads with `docs/notes/conference-followups-2026-10-22/score.py` (400 draws), which since #1273 draws each ad's unit effect from its chain's running mean and variance, and compared them with fit 8 (`building-zones-floor-asof3-cap64`, the same build and held-out ads) using `compare.py`. Fit 4 keeps the asof3 floor curve with floors 47 and up in one node, while fit 8 runs the curve to 64, so the comparison also carries fit 8's change at the top floors (+52 elpd in `building-zones-floor-asof3-cap64-2026-10-23.md`, small next to the gaps below). Points are points of log rent x100.

| run | wall | sampling | cost | max R-hat | min ESS |
|---|---|---|---|---|---|
| `building-zones-floor-asof3-unitmean-b0-latest-96a9156e-unitmean-jointamp-w1000` | 25 min | 983 s | about $1.01 | 1.0334 (`bed=0:full>=3`) | 178 (`unit:elev_f17`) |

The fit misses the gate. The sweep took 0.86 s, against fit 8's 0.78 s.

## The gate miss

68 of the 121 coefficients miss, with R-hat over 1.01 or ESS under 400. Every other quantity passes, including `unit_sd` (1.0025, 716), the zone amplitudes, the noise scales and all eight unit-mean coefficients (R-hat at most 1.0091, ESS at least 405). The misses are the 47 elevator floor steps, the 7 walk-up floor steps, 9 bath steps, 3 bedroom steps, `elev_top` and `penthouse`. Those columns stay fixed between a unit's ads and vary between units of a building. The building columns (doorman, condo, gym, age, height) and the unit columns that change between ads pass. Over the bedroom, bath and elevator floor coefficients the median ESS falls from 2,090 in fit 8 to 308.

The four chains still agree closely on most of the failing terms: their medians spread by 0.2 points or less, except the thin studio and one-bedroom bath steps (`bed=0:full>=3` 1.38, `bed=1:full>=3` 0.64). The kept draws of `bed>=1`, every 5th sweep, have a lag-1 autocorrelation of 0.44 to 0.59 in each chain.

I traced this to the model structure, through the order of the Gibbs blocks, and not to the data. The miss covers bedroom steps with hundreds of thousands of rows as well as the thin bath steps, so thin data can't explain it. The sweep draws the coefficients with the building levels integrated out and the unit effects held at their last draw (step 1 in the `building_zones_floor_asof2_unit` docstring). For a column that stays fixed inside a unit, shifting its coefficient and the effects of every unit with that value in opposite directions leaves the likelihood almost unchanged. Only the effects' prior, with `su` near 0.08 against a noise scale near 0.05, holds them apart, so each alternation moves the pair a short way. Building columns don't suffer, since step 1 already integrates out the building levels. The fix I'd make is to integrate the unit effects out of the coefficient draw in the same way. With the weights g_k = 1 / (1 + su^2 C_k) from step 2, that comes down to a correction to the coefficients' precision from each unit's sums of c x. I'd write it as a new module with its own tests and predictions, and I won't refit on a new seed.

## Within and between units

Binary columns are percent premiums, 100 (exp(b) - 1), and `unit:log_size_rel` is an elasticity. The within coefficient is the column's own. The between coefficient is the column's plus its unit mean's. Intervals are 90% posterior intervals from the saved draws, with no cluster adjustment. These columns all pass the gate.

| column | rows off unit mean | within (90%) | between (90%) |
|---|---:|---|---|
| unit:laundry_in_unit | 216,321 | +2.11 (2.04 to 2.19) | +8.83 (8.74 to 8.93) |
| unit:laundry_in_building | 238,105 | +0.75 (0.68 to 0.81) | +2.59 (2.51 to 2.68) |
| unit:dishwasher | 470,762 | +0.59 (0.54 to 0.63) | +2.94 (2.88 to 3.00) |
| unit:log_size_rel | 365,101 | 0.043 (0.040 to 0.045) | 0.316 (0.315 to 0.318) |
| unit:size_imputed | 357,274 | -0.12 (-0.17 to -0.07) | -0.78 (-0.87 to -0.69) |
| unit:size_unknown | 239,739 | -0.33 (-0.40 to -0.27) | -3.85 (-3.91 to -3.78) |
| flag:rent_stabilized | 40,695 | -1.32 (-1.45 to -1.19) | -3.48 (-3.67 to -3.29) |
| unit:garden | 3 | +9 (-54 to +136) | +2.44 (2.17 to 2.72) |

Within units, every premium is a fraction of the between-unit one: about a quarter for the laundry and stabilized terms, a fifth for the dishwasher, and an eighth for the size elasticity. The garden label differs from its unit's mean on 3 rows, so its within coefficient rests on almost nothing.

### Against the unit fixed-effects OLS of #1263

`endpoint-unit-fe-2026-10-23.md` fitted unit and month fixed effects by OLS on Sol's 61,914 repeat-ad pairs, with 95% intervals clustered by unit and week. Fit 4 uses every training ad of each unit, a time model, priors and partial pooling, so a gap between the two mixes sample, estimator and prior.

| column | OLS within (95%) | fit 4 within (90%) | fit 4 term |
|---|---|---|---|
| unit:laundry_in_unit | +0.78 (0.49 to 1.08) | +2.11 (2.04 to 2.19) | within |
| unit:laundry_in_building | +0.43 (0.19 to 0.67) | +0.75 (0.68 to 0.81) | within |
| unit:dishwasher | +0.53 (0.38 to 0.68) | +0.59 (0.54 to 0.63) | within |
| unit:log_size_rel | 0.002 (-0.007 to 0.011) | 0.043 (0.040 to 0.045) | within |
| unit:size_imputed | +0.20 (0.01 to 0.40) | -0.12 (-0.17 to -0.07) | within |
| unit:size_unknown | +0.13 (-0.14 to 0.39) | -0.33 (-0.40 to -0.27) | within |
| flag:rent_stabilized | -0.72 (-1.44 to -0.003) | -1.32 (-1.45 to -1.19) | within |
| flag:shared_space | -0.23 (-0.72 to 0.27) | -1.14 (-1.25 to -1.04) | one coefficient |
| bld:altered_2000_on | +1.19 (0.35 to 2.04) | +3.22 (3.05 to 3.38) | one coefficient |
| unit:walkup_floor_unknown | -0.10 (-3.19 to 3.10) | -0.61 (-0.71 to -0.51) | one coefficient, misses the gate |

The two estimators agree on the dishwasher and come close on laundry in the building. Fit 4's in-unit laundry premium is almost three times the OLS one, with intervals that don't overlap. Its size elasticity is small but clear of zero, where the OLS one is zero. The OLS sample keeps pairs at least 270 days apart, and fit 4 also learns from ads close together in time, so the two weigh different kinds of change in a label. The last three rows have no unit mean in fit 4, so their coefficients mix within and between units and don't measure the same quantity as the OLS ones.

## Scales

| quantity | fit 8 | fit 4 | change |
|---|---|---|---|
| `sigma`, groups 0 to 3 | 0.083, 0.082, 0.088, 0.101 | 0.050, 0.049, 0.054, 0.062 | -38% to -41% |
| `bld_sd`, Manhattan and outer | 0.185, 0.114 | 0.176, 0.107 | -5%, -7% |
| `nu` | 4.10 | 2.70 | -34% |
| `unit_sd` | | 0.0794 (0.0792 to 0.0796) | |

Half of the noise goes into the unit effects, and the Student-t tails get heavier. The building levels keep almost all their spread.

## Held-out ads

Every held-out ad on this split is the latest ad of a unit with training rows, so every one gets its unit's effect. That makes the split close to the most favorable one for unit effects. A unit-disjoint split (objection 17) would test them on new units.

| run | elpd | RMSE | coverage 50/80/90/95 | median 90% width |
|---|---|---|---|---|
| fit 8 | 148,234 | 0.1158 | 0.493, 0.798, 0.903, 0.954 | 0.364 |
| fit 4 | 177,137 | 0.1018 | 0.496, 0.789, 0.893, 0.949 | 0.301 |

The elpd change is +28,903, with SEs of 297 by row, 483 by building and 688 two-way by building and week. `unit_heldout.py` gives the RMSE, coverage and width. Fit 4's coefficients haven't converged, but their chains agree to within 0.2 points on all but two thin bath steps, so the held-out gain doesn't depend on which chain one reads.

## Against the predictions

From `building-zones-floor-asof3-unit-predictions-2026-10-23.md`:

- Passes the gate and takes 25 to 50 minutes at $1.00 to $2.20: 25 minutes and $1.01, but it misses the gate. Miss.
- `unit_sd` has a median of 0.05 to 0.10 with a 90% interval narrower than 0.005: 0.0794, width 0.0004. Hit.
- `sigma` falls by 15% to 40% in every group: 38% to 41%, with two groups past 40%. Miss, narrowly.
- `bld_sd` falls by under 20%: 5% and 7%. Hit.
- Held-out RMSE falls to between 0.085 and 0.105: 0.1018. Hit.
- Held-out elpd rises by 10,000 to 50,000, far beyond 2 SE: +28,903 at 60 SE by building. Hit.
- 90% coverage stays between 0.88 and 0.92: 0.893. Hit.
- The median 90% width shrinks by 10% to 35%: 17%. Hit.
- Floor, bedroom and elevator floor coefficients move by under 1 point: the bedroom steps move by 0.7 at most and the elevator floors below 47 by 1.12 at most (floor 28), with floor 47 left out since fit 8 changed it. The bath steps move by up to 6.1 (`bed=0:full>=3`). Miss, on terms that miss the gate.
- In-unit laundry and dishwasher fall by 0.5 to 3 points: on the within coefficients, laundry falls by 4.1 and the dishwasher by 1.4. One hit and one miss, counted as a miss.
- Building amenity coefficients move by under 1 point: 0.91 at most (`bld:condo`). Hit.
- Each unit-mean coefficient reaches the gate: R-hat at most 1.0091 and ESS at least 405. Hit.
- In-unit laundry within 0 to 3 points: +2.11. Hit. Between 4 to 8: +8.83. Miss.
- Dishwasher within 0 to 1.5: +0.59. Hit. Between 1 to 3: +2.94. Hit.
- The size elasticity within is 30% to 80% of between: 14%. Miss.
- Rent stabilized within -4% to 0%: -1.32%. Hit. Between below within: -3.48%. Hit.
- Garden within interval includes 0: -54 to +136. Hit.
- `unit_sd` changes by under 10% against the unit effect alone: no unit-only run exists, so I can't score it.

That gives 14 hits and 6 misses, with one not scored.

From `amp-joint-predictions-2026-10-23.md`, with IATs from `amp_diag.py`:

1. `amp[outer]` IAT of 3.5 sweeps or less: 1.7. Hit.
2. `amp[outer]` ESS of at least 1,100 and R-hat of 1.005 or less: 2,306 and 1.0004. Hit.
3. `amp[outer]` no longer has the worst R-hat or least ESS. Hit.
4. `amp[manhattan]` IAT of 3.0 or less: 1.2. Hit.
5. The run passes the gate: it misses on the coefficients. Miss, for a reason outside the step.
6. Medians between 0.32 and 0.42 (outer) and 0.80 and 1.00 (Manhattan): 0.370 and 0.867. Hit.
7. Seconds per sweep rise by under 10% against fit 8: 0.857 against 0.775, up 10.6%. Miss, narrowly, and fit 4 also adds the unit effects to every sweep, so the rise overstates the step's own cost.

That gives 5 hits and 2 misses. The joint step fixes `amp[outer]`.

## Reading

On this split, giving each unit its own level cuts held-out RMSE from 0.116 to 0.102 and narrows the intervals by 17% at the same coverage. The gain comes from the unit's own earlier ads, so it says how much of a unit's rent its past ads carry. It doesn't measure how well the model prices a new unit.

The unit means separate two quantities the base model blends. Between units, in-unit laundry goes with rents 8.8% higher and a dishwasher with 2.9%. When the label changes between ads of the same unit, the rent moves by 2.1% and 0.6%. Some of a between-unit premium can come from other features of units that have the amenity, and some of a within-unit change can come from how ads report it, so neither number is the amenity's worth by itself. The OLS on repeat pairs gives within-unit premiums of the same size for the dishwasher and smaller ones for laundry.

The floor, bedroom and bath coefficients need the collapsed coefficient draw before anyone reads them from a unit-effect fit. The joint amplitude step needs nothing more.
