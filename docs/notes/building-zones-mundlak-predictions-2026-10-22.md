# Building means (Mundlak) in the floor model: predictions, 2026-10-22

Ben opened the Modal budget for the night (2026-10-22 05:01Z, until 09:00 ET). The first item
on the queue is the bias the simulated recovery found
(`simulated-recovery-results-2026-10-22.md`): the unit coefficients come back high in every
run, because each building's true level correlates with its mean of the unit columns. I wrote
these predictions before launching either fit.

## The change

`rentfrontier.building_zones_mundlak` adds nine `bld:` columns to the floor model. Each holds a
building's mean, over all its rows, of a column that changes between ads in the building:

- `unit:log_size_rel`, `unit:size_unknown`, `unit:size_imputed`;
- `unit:laundry_in_unit`, `unit:laundry_in_building`, `unit:dishwasher`;
- `unit:garden`, the two floor-unknown flags together;
- log floor over the rows with a known floor, with buildings without any getting the mean over
  every known floor.

With the means in the design, the unit coefficients rest on differences within buildings. The
means take up the part of the building level that goes with them. Everything else in the model
is unchanged.

## Fit A: the realistic simulation again

I'll fit the new model on `sim-floor-realistic-20261022`, the same simulated rents and truth as
run 1, with the floor fit's settings (4 chains, 300 warmup, 1,000 sweeps, every 5th kept, seed
20261021, fit-only). The truth has no building-mean term, so the means' true coefficients are
0. But the truth's residual levels correlate with the means, so I expect the means to come back
away from 0 and the unit columns to lose their bias.

- It passes the gate (R-hat <= 1.01, ESS > 400).
- The six unit columns' bias (median less truth) falls below 0.1 points in size for each. In
  run 1 it was +0.64 (`log_size_rel`), +0.39 (in-unit laundry), +0.21 (in-building laundry),
  +0.13 (dishwasher), -0.17 (`size_unknown`) and -0.05 (`size_imputed`).
- At least 5 of those 6 columns cover their truth. In run 1 none did.
- Coverage over all scalar terms the truth has rises from 80.7% to between 84% and 95%.
- `bld:mean_log_size_rel` and `bld:mean_laundry_in_unit` come back positive, with 90% intervals
  above 0. The truth's building levels rise with both means.
- `bld:condo` moves closer to its truth of 9.99, within 0.3 points (run 1: 9.57).
- The elevator curve keeps its coverage of about 90% at floors 2 to 30.

## Fit B: real data

I'll fit the new model on the real dataset and split of the floor fit, with the same settings.
I compare it with `building-zones-floor-b0-latest-6b5a5b4a-dense-w1000`.

- It passes the gate.
- The unit premiums fall by about the bias the simulation found. In points of log rent x100:
  - `unit:log_size_rel` from 25.2 to between 23.5 and 25.0;
  - `unit:laundry_in_unit` from 6.1 to between 5.3 and 6.0;
  - `unit:laundry_in_building` from 1.7 to between 1.2 and 1.7;
  - `unit:dishwasher` from 2.0 to between 1.6 and 2.0;
  - `unit:size_unknown` from -4.1 to between -4.1 and -3.6.

  The real bias can be larger than the simulated one, since the simulation drew its truth from
  the floor fit's own estimates, after the shrinkage had already taken part of it.
- The elevator curve falls by 0 to 0.5 points at most floors, and floor 10 stays within 1 point
  of the floor fit's.
- `bld:mean_log_size_rel` and `bld:mean_laundry_in_unit` come back positive.
- The building spread `bld_sd` falls by 2% to 10% in each zone, since the means explain part of
  the levels.
- Held-out log score on the latest split's rows, scored on thelio from the saved draws, is
  within 2 SE of the floor fit's or better. I expect a small gain, under 0.002 nats a row.
