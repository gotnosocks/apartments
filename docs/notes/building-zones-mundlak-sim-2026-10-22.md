# Building means on the realistic simulation (Fit A): results, 2026-10-22

I fit `building-zones-mundlak` on `sim-floor-realistic-20261022`, the rents run 1 of the
simulated recovery used (docs/notes/simulated-recovery-results-2026-10-22.md). The settings
match run 1: 4 chains, 300 warmup, 1,000 sweeps with every 5th kept, seed 20261021, fit-only.
The run is `building-zones-mundlak-b0-latest-a6d25054-sim-realistic-w1000`. It took 20 minutes
on a Modal A100 for an estimated $0.78. I scored its draws against the truth with
`python -m rentfrontier.simulate score`. The predictions are in
docs/notes/building-zones-mundlak-predictions-2026-10-22.md, and the numbers below come from
`building-zones-mundlak-sim-2026-10-22/summary.json`.

## Against the predictions

| prediction | result | hit |
|---|---|---|
| passes the gate | max R-hat 1.005, min ESS 796 | yes |
| the six unit columns' bias under 0.1 points each | largest 0.02 points | yes |
| at least 5 of the 6 cover their truth | 6 of 6 | yes |
| coverage over all scalar terms rises to 84% to 95% | 80.7%, unchanged | no |
| the size and in-unit laundry means come back positive | +20.0 and +6.0 points | yes |
| `bld:condo` within 0.3 points of its truth of 9.99 | 6.62 | no |
| the elevator curve keeps about 90% coverage at floors 2 to 30 | 100% | yes |

The unit columns, in points of log rent x100:

| term | truth | run 1 | Fit A |
|---|---|---|---|
| `unit:log_size_rel` | 25.20 | 25.84 | 25.20 |
| `unit:laundry_in_unit` | 6.13 | 6.52 | 6.10 |
| `unit:laundry_in_building` | 1.70 | 1.91 | 1.68 |
| `unit:dishwasher` | 1.98 | 2.11 | 1.99 |
| `unit:size_unknown` | -4.14 | -4.31 | -4.15 |
| `unit:size_imputed` | -0.51 | -0.56 | -0.53 |

The floor flags improve too: `unit:garden`, `unit:elev_floor_unknown` and
`unit:walkup_floor_unknown` all cover now, and the floor-flag coverage goes from 43% to 71%.

## What got worse

The building attributes shrink toward 0. Coverage of the 22 building features falls from 73%
to 41%, and their RMS error goes from 0.24 to 1.16 points:

| term | truth | run 1 | Fit A |
|---|---|---|---|
| `bld:condo` | 9.99 | 9.57 | 6.62 |
| `bld:doorman_full` | 13.94 | 13.76 | 11.24 |
| `bld:elevator` | 3.53 | 3.59 | 2.55 |
| `bld:built_2010_on` | 4.01 | 4.09 | 2.50 |
| `bld:built_pre1900` | 3.92 | 3.94 | 2.80 |
| `bld:retail` | -1.90 | -1.65 | -0.87 |

The means do not come back near 0: `bld:mean_log_size_rel` is +20.0 points,
`bld:mean_laundry_in_unit` +6.0, `bld:mean_dishwasher` +4.4 and `bld:mean_garden` +3.8. The
Manhattan building spread falls from 0.169 to 0.145 (realized truth 0.176). Each map's slope on
its truth falls from 0.99 to 0.90 in Manhattan and 0.93 outside it. The scorer's map and level
comparisons leave out the part of each building's level the means carry, so those coverages
(47% and 52% in Manhattan) understate Fit A, and I don't read them as misses of the map.

## Reading it

The means fix the bias I set out to fix: with them in, the unit columns rest on differences
within a building and land on their truth. The cost falls on everything measured between
buildings. The simulated truth makes that cost larger than it may be on real data. The truth's
building residuals come out of the floor fit, which estimated them alongside the building
attributes, so they are uncorrelated with the attributes but correlated with each building's
unit mix. Given the means, the fit lets them carry that unit-mix correlation, and since the mix
also goes with condo, doorman and new construction, the means take part of those terms' share
as well. A truth drawn from a different fit would split the building level differently, and
this simulation can't say which split real buildings follow.

For the location features this matters directly. Transit, parks and noise are building-level
columns, like condo. On the building-means base they would share their variance with the
means, and in this simulation building-level terms on that base lost 10% to 50% of their size.
On the floor base the same terms came back within about 0.4 points.

Fit B, the same model on real data, is running now. I'll decide the base for the location fits
from both results.
