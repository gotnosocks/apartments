# Simulated recovery on the as-of floor model: predictions, 2026-10-23

These are follow-up fits 6 and 7. Each one fits `building-zones-floor-asof2` to rents I drew myself, so I can check the fitted terms against the truth. I wrote these predictions before launching either fit. The results go in a separate note, and I'll record each miss there as a miss.

## The data

I built both datasets with `python -m rentfrontier.simulate make` (#1240) from the as-of fit on the corrected build, `building-zones-floor-asof2-b0-latest-d5de95e7-dense-w1000`. The truth for every term is that fit's posterior median over its kept draws. The truths are in `/data1/apartments/tmp/sim-recovery-asof2/<scenario>/truth.npz`.

| fit | dataset | seed | what changes from the fit's medians |
|---|---|---|---|
| 6 | `sim-asof2-realistic-20261023` | 20261023 | walk-up curve +0.4 points a flight, `unit:elev_top` log 1.04, `unit:lower` 0, as in run 1 of the first recovery (`simulated-recovery-predictions-2026-10-22.md`) |
| 7 | `sim-asof2-mundlak-20261023` | 20261024 | every column the Mundlak fit `building-zones-mundlak-b0-latest-a6d25054-dense-w1000` shares with this model takes that fit's median, and each building's level gains the Mundlak fit's contextual terms: its 9 `bld:mean_*` coefficients times the building's mean of the matching unit column over training rows |

The contextual coefficients planted in fit 7, in points of log rent x100: `mean_log_size_rel` 26.5, `mean_laundry_in_unit` 8.1, `mean_dishwasher` 5.4, `mean_garden` 4.7, `mean_laundry_in_building` 3.1, `mean_floor_unknown` 1.7, `mean_log_floor` 1.1, `mean_size_imputed` -1.2 and `mean_size_unknown` -2.9. The planted building term has SD 7.6 points across sites. It isn't centred, so the simulated log rent has mean 8.059 against 8.140 in the real data. The intercept and the weekly walk absorb that offset, so I'll leave both out of the scoring.

The data change since the first recovery runs: the as-of features, the corrected build, and a truth taken from the as-of fit.

## The fits

Both fits run as the as-of fit ran: model `building-zones-floor-asof2` at master, ads from `rows-b495f6dd53222649.parquet`, 4 chains, 300 warmup and 1,000 sweeps with every 5th kept, seed 20261021, fit-only. I'll launch them one at a time as `ops/modal/cap.py` allows. I expect each to take about 21 minutes and cost about $0.90, as the as-of fit did.

## Predictions for fit 6

The truth here matches the model, so this run checks the earlier recovery on the new features and a new seed.

- It passes the gate (R-hat <= 1.01, ESS > 400). The worst R-hat and least ESS fall on `amp[outer]`.
- 90% coverage over the coefficients, nu and the four sigmas is between 75% and 90%. Run 1 had 80.7%.
- The same unit columns miss in the same direction as in run 1. `unit:log_size_rel` comes back 0.4 to 0.9 points above its truth of 26.04, and `unit:laundry_in_unit` 0.2 to 0.6 points above its truth of 6.16.
- The floor flags cover 3 or fewer of their 7 truths, as in run 1.

## Predictions for fit 7

This run puts a contextual effect in the truth and leaves it out of the model. If the real-data gap between the floor model and the Mundlak model comes from such an effect, this run should reproduce the gap. On real data, the as-of floor fit puts `unit:log_size_rel` at 26.04 and the Mundlak fit at 24.25, a gap of 1.79 points. The in-unit laundry gap is 0.61 points and the dishwasher gap 0.11.

- It passes the gate.
- `unit:log_size_rel` comes back 1.0 to 2.5 points above its truth of 24.25, and outside its 90% interval.
- `unit:laundry_in_unit` comes back 0.3 to 1.0 points above its truth of 5.55.
- `unit:dishwasher` comes back within 0.4 points of its truth of 1.83.
- Each of the three biases has the same sign as the real-data gap, and the size bias lands within 1 point of 1.79.
- The building features take up part of the planted term, so their coverage falls below run 1's 73%.
- Overall 90% coverage across the scalar terms falls below fit 6's.

If the size bias comes back under 0.5 points, a contextual effect of the size the Mundlak fit found can't explain the real-data gap, and I'll say so.
