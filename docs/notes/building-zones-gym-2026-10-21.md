# Building zones with a building gym, without truck routes, 2026-10-21

The unit features fit (`building-zones-unit-2026-10-21.md`) gave the through truck route a
premium of -4.2%, but the building effects of truck route buildings rose to cancel it, so the
column left predictions where they were. Ben asked to drop it and test whether the building
has a gym. The model `building-zones-gym` (#1192) is the unit features design with
`bld:truck_through` removed and `bld:gym` added. Everything else is unchanged.

## Data

`rentfrontier.building_gym` reads each listing's latest raw StreetEasy record and takes its
amenity list. A building gets a gym when at least half of its listings stating any amenities
list the GYM code. Snapshot `building-gym/20261021-752c7d3d` holds 73,457 buildings: 4,571 with
a gym and 2,640 with no listing stating amenities.

On the latest split's 1,706,837 training ads, 31.7% are in gym buildings, 67.8% in buildings
without one and 0.5% (8,240 ads) in buildings with no amenities stated. I counted that last
group as no gym, with no flag of its own. Listings of the same building disagree about the gym
for 22.7% of ads, but only 1.5% of ads are in buildings with a gym share between 0.3 and 0.7.

Share of each group's ads with the other building column set:

| column | gym | no gym | unknown |
|---|---|---|---|
| doorman full-time | 42.2% | 7.1% | 0.1% |
| doorman part-time | 33.2% | 3.7% | 0.2% |
| doorman virtual | 18.5% | 22.1% | 0.1% |
| elevator | 98.2% | 32.1% | 3.3% |
| condo | 34.3% | 6.6% | 1.6% |

## The run

```sh
ops/modal-fit --dataset /data1/apartments/frontier/datasets/b0-edc83b49f9bacd8c-alldata-v36-dense-nyc \
  --split latest COMMIT dense-w650 building-zones-gym b0 4 150 650 5 \
  --seed 20261021 --no-loo --no-heldout
```

`building-zones-gym-b0-latest-f2d01c92-dense-w650` ran on a Modal A100 from 12:14 to 12:24 ET
on 2026-10-21. The fit stage took 557 s and the container 577 s, at $0.38 by `ops/modal-fit`'s estimate.

It fails the convergence gate. Max R-hat is 1.0149 on `amp[outer]`, the Brooklyn + Queens map
amplitude, against the 1.01 bar, and min bulk ESS is 415 on the same quantity. The four
chains' medians for it are 0.371, 0.375, 0.379 and 0.381. Every other quantity passes. The unit
run passed with R-hat 1.0078, but its `amp[outer]` already had the lowest ESS, 456. Under the
repo's rules the run cannot be served, and I did not rerun it on another seed. The gym
coefficient itself mixes well: chain medians 7.63%, 7.67%, 7.68% and 7.60%.

## Predictions, written before the fit (#1192)

Against the unit run `building-zones-unit-b0-latest-a3aec3ff-dense-w650`:

| # | Prediction |
|---|---|
| G1 | The gym premium comes out between +1% and +5%, median near +3%. |
| G2 | Full-time doorman falls from 17.2% by 2 to 4 points, part-time doorman and elevator by 1 to 3 points, condo by under 2. |
| G3 | Size, laundry and dishwasher premiums each move by under 1 point. |
| G4 | On truck route ads, the predicted log rent (map + building + columns) changes by under 0.5 points on average. |
| G5 | The variance of T, demeaned within zone, falls from 0.0530 by under 0.001. |
| G6 | In the building-level screen, gym explains 5% to 15% of the unit run's building effects, above its permutation null. |
| G7 | On held-out ads of the latest split, elpd rises by 0 to 1,500 against the unit run, and RMSE moves by under 0.001. |
| G8 | The fit converges on the unit run's settings within the 1 hour cap, at about $0.45. |

## Results

Premiums, posterior median with 90% interval:

| column | gym run | unit run | attrs base |
|---|---|---|---|
| gym | +7.64% (7.12 to 8.16) | | |
| doorman, full-time | +14.05% (13.26 to 14.93) | +17.17% | +19.57% |
| doorman, part-time | +8.43% (7.71 to 9.23) | +11.08% | +11.96% |
| doorman, virtual | +3.34% (3.07 to 3.60) | +3.86% | +4.39% |
| elevator | +6.69% (6.34 to 7.07) | +7.98% | +9.05% |
| elevator unknown | +1.66% (1.14 to 2.22) | +1.55% | +1.73% |
| condo | +10.47% (10.00 to 10.93) | +10.86% | +14.76% |
| roof height, per e-fold | -0.75% (-1.08 to -0.43) | -0.37% | -0.73% |
| height unknown | +0.31% (-0.37 to +0.97) | +0.55% | +0.23% |
| size, per unit of log(size / bedroom median) | +28.63% (28.49 to 28.78) | +28.60% | |
| size imputed | -0.63% (-0.68 to -0.59) | -0.63% | |
| size unknown | -3.89% (-3.94 to -3.84) | -3.89% | |
| laundry in unit | +6.48% (6.40 to 6.55) | +6.48% | |
| laundry in building | +1.64% (1.57 to 1.70) | +1.65% | |
| dishwasher | +2.04% (2.00 to 2.09) | +2.05% | |

The bed and bath steps, the error sigmas (0.084, 0.083, 0.089, 0.103) and nu (4.11) match the
unit run. The zone gap is +30.2% (29.8 to 30.7), against +29.8%.

| zone | building spread | building share | map amplitude |
|---|---|---|---|
| Manhattan, unit run | 0.1889 | 0.463 | 0.898 |
| Manhattan, gym run | 0.1873 | 0.439 | 0.954 |
| Brooklyn + Queens, unit run | 0.1173 | 0.318 | 0.385 |
| Brooklyn + Queens, gym run | 0.1167 | 0.310 | 0.377 |

`T` (error + building effect + map value, demeaned by zone) has variance 0.0511 (0.0531 in
Manhattan, 0.0483 in Brooklyn + Queens), against 0.0530 for the unit run and 0.0622 for the
attrs base.

I added each new column group's contribution x·gamma back into `T` and took the rise in its
variance, alone and averaged over all 24 orderings of the four groups:

| group | variance of contribution | rise alone | Shapley rise |
|---|---|---|---|
| size | 0.00228 | 0.00735 | 0.00797 |
| laundry | 0.00065 | 0.00314 | 0.00377 |
| gym | 0.00116 | 0.00338 | 0.00407 (Manhattan 0.00463, Brooklyn + Queens 0.00327) |
| dishwasher | 0.00010 | 0.00078 | 0.00105 |

With all four added back, `T` has variance 0.0680. Measured by Shapley rise, gym comes second
after size.

The ad-weighted mean building effect of gym buildings went from +6.5% in the attrs base and
+6.1% in the unit run to +3.3% here, and that of buildings without a gym went from -3.0% and
-2.8% to -1.5%. The gym term takes about 4 points of the gap between the two groups out of the
building effects and into a measured amenity.

In the building-level screen (grouped 5-fold CV, building means weighted by inverse posterior
variance, 50 permutations), the gym flag explains 1.15% of the unit run's building effects and
0.90% of the attrs base's. Both beat the null, whose 95th percentile is below zero.

On the 71,632 training ads in truck route buildings, the predicted log rent rose by 0.04 points
on average (0.003 points for other ads). In the unit run their building effects had risen to
cancel the -4.2% term. With the term gone, they fell by 5.1 points and the map value fell by
0.7 points, and the gym term and the shifted building columns made up the rest. On held-out truck route ads the change is
also 0.04 points.

Held-out ads of the latest split (189,649 ads, 68 draws per run, Student-t log density; elpd is
the gym run minus the named run):

| rows | ads | elpd vs unit | elpd vs attrs | RMSE gym / unit / attrs | mean bias gym / unit / attrs |
|---|---|---|---|---|---|
| all | 189,649 | -11.4 (SE 2.9) | +9,807 (SE 162) | 0.11732 / 0.11731 / 0.12436 | -0.51% / -0.51% / -0.35% |
| Manhattan | 117,638 | +0.3 (SE 2.1) | +7,385 | 0.11825 / 0.11826 / 0.12635 | -0.55% / -0.55% / -0.38% |
| Brooklyn + Queens | 72,011 | -11.6 (SE 2.0) | +2,422 | 0.11577 / 0.11575 / 0.12103 | -0.44% / -0.44% / -0.29% |
| gym buildings | 66,343 | -2.8 (SE 1.5) | +4,576 | 0.11386 / 0.11387 / 0.12216 | -0.92% / -0.90% / -0.69% |
| no-gym buildings | 123,306 | -8.6 (SE 2.4) | | | -0.29% / -0.30% / -0.17% |
| truck route buildings | 8,854 | -3.2 (SE 1.2) | | | -1.12% / -1.08% / |

Coverage of the 90% predictive interval is 0.882 (unit 0.882, attrs 0.879), and of the 50%
interval 0.482 (0.482, 0.479). Median absolute error is 0.0670 for both the gym and unit runs.
The held-out predictions are nearly identical to the unit run's. My reading is that for
buildings with training ads, the unit run's building effects already carried most of the gym
difference, as the shift in mean building effects above suggests. I have not counted the
held-out ads in buildings with no training ads, where a measured gym would matter most.

Examples, at posterior medians with 90% predictive intervals. All three are gym buildings:

| ad | held out | ask | predicted | 90% interval |
|---|---|---|---|---|
| 796 Avenue of the Americas, 2 bed, 2026-10-16 | no | $9,314 | $9,717 | $8,214 to $11,650 |
| 23 Eagle Street, Brooklyn, 1 bed, 2026-10-16 | yes | $6,059 | $4,908 | $4,109 to $5,797 |
| 85 East End Avenue, 1 bed, 2026-10-16 | yes | $6,183 | $5,514 | $4,661 to $6,541 |

| # | Result | Score |
|---|---|---|
| G1 | +7.64% (7.12 to 8.16) | miss, high |
| G2 | full-time doorman -3.1 points, part-time -2.7, elevator -1.3, condo -0.4 | hit |
| G3 | largest move 0.03 points | hit |
| G4 | +0.04 points on training and held-out ads | hit |
| G5 | 0.0511, a fall of 0.0019 | miss: fell twice as far |
| G6 | 1.1% of the unit run's building effects, above the null | miss, far below the range |
| G7 | elpd -11 (SE 3), RMSE +0.00001 | miss on elpd, hit on RMSE |
| G8 | 9.6 min, $0.38, R-hat 1.015 on `amp[outer]` | miss: fails the gate |

I set the gym premium low because the doormen and elevator overlap it so much, but the fit
moved credit from them and from the building effects. Measured as a share of `T`, gym does
more than laundry. In the screen it explains little, since the screen asks the flag to
account for all of each building's effect, most of which varies among buildings with the same
gym value. The held-out scores do not move.

The scripts are in `building-zones-gym-2026-10-21/`, and the draws-derived data (map grid,
buildings, coefficients with chain medians and traces, examples, `T` variance, contributions,
screen, held-out scores and the scored predictions) is at
https://claude.ai/artifact/Mj7DNLFMQzus4fYcXehbqs.
