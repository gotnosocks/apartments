# Building means on real data (Fit B): results, 2026-10-22

I fit `building-zones-mundlak` on the floor fit's dataset and split
(`b0-edc83b49f9bacd8c-alldata-v36-dense-nyc`, latest split), with the same settings: 4 chains,
300 warmup, 1,000 sweeps with every 5th kept, seed 20261021, fit-only. The run is
`building-zones-mundlak-b0-latest-a6d25054-dense-w1000`. It took 20 minutes on a Modal A100
for an estimated $0.80. I compare it with `building-zones-floor-b0-latest-6b5a5b4a-dense-w1000`
on the posterior medians. The predictions are in
docs/notes/building-zones-mundlak-predictions-2026-10-22.md, and the numbers below come from
`building-zones-mundlak-real-2026-10-22/summary.json`.

## Against the predictions

All in points of log rent x100.

| prediction | result | hit |
|---|---|---|
| passes the gate | max R-hat 1.006 (`bld_sd[outer]`), min ESS 767 (`amp[outer]`) | yes |
| `unit:log_size_rel` from 25.2 to 23.5 to 25.0 | 24.25 | yes |
| `unit:laundry_in_unit` from 6.1 to 5.3 to 6.0 | 5.55 | yes |
| `unit:laundry_in_building` from 1.7 to 1.2 to 1.7 | 1.39 | yes |
| `unit:dishwasher` from 2.0 to 1.6 to 2.0 | 1.83 | yes |
| `unit:size_unknown` from -4.1 to -4.1 to -3.6 | -3.91 | yes |
| the elevator curve falls 0 to 0.5 points, floor 10 within 1 point | elevator floors move -0.08 to +0.02; floor 10 3.70 to 3.65 | yes |
| the size and in-unit laundry means come back positive | +26.5 and +8.1 | yes |

The unit columns fall by more than the simulation's bias: size by 0.95 points against a
simulated bias of 0.64, and in-unit laundry by 0.58 against 0.39. As the predictions note
expected, the real bias can be larger, since the simulation drew its truth after the floor
fit's shrinkage had already taken part of it.

## The building terms

The building attributes shrink on real data much as they did in the simulation:

| term | floor | means | simulation, means fit (truth) |
|---|---|---|---|
| `bld:condo` | 9.99 | 6.01 | 6.62 (9.99) |
| `bld:doorman_full` | 13.94 | 10.47 | 11.24 (13.94) |
| `bld:elevator` | 3.53 | 2.20 | 2.55 (3.53) |
| `bld:built_2010_on` | 4.01 | 1.97 | 2.50 (4.01) |
| `bld:built_pre1900` | 3.92 | 2.44 | 2.80 (3.92) |
| `bld:retail` | -1.90 | -0.84 | -0.87 (-1.90) |
| `bld:log_height` | -0.92 | -0.17 | -0.14 (-0.92) |

The means are larger than in the simulation: `bld:mean_log_size_rel` +26.5 (simulation +20.0),
`bld:mean_laundry_in_unit` +8.1 (+6.0), `bld:mean_dishwasher` +5.4 (+4.4), `bld:mean_garden`
+4.7 (+3.8). The building spread falls from 0.183 to 0.147 in Manhattan and from 0.114 to
0.107 outside it. The map amplitude falls from 0.92 to 0.72 in Manhattan and from 0.36 to
0.33 outside it. The bedroom, bath, season and flag terms move by under 0.6 points, except `bed=0:full>=4`
(+1.5, on an interval 20 points wide). The intercept falls by 4.3 points, since the means are not
centered.

## Reading it

The real fit follows the simulation term by term. On the realistic simulation the floor model
got the building terms right and the unit terms wrong, and the means model did the reverse.
Real data gives the same two pictures, so the simulation is a good guide to which numbers
each model gets right, as long as real buildings split their levels roughly the way the floor
fit did.

The two models answer different questions about a building quality. On the floor model,
`bld:condo` is the rent difference between a condo and a rental building that differ in
nothing else the model measures. On the means model it is the difference between two such
buildings with the same unit mix. Condos have bigger units with more in-unit laundry, so part
of what a condo is worth goes to the means. The goal asks for the first, so I'm keeping the
building and location terms on the floor model and taking the unit premiums from the means
model: size 24.3, in-unit laundry 5.6, in-building laundry 1.4, dishwasher 1.8.

The three location fits (transit, parks, noise) therefore go on the floor model.

I haven't scored either fit's held-out rows. The night ran fit-only, and neither model is the
served one, so this result doesn't change the site.
