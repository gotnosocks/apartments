# Building zones with year built, alteration and retail, 2026-10-21

The gym fit (`building-zones-gym-2026-10-21.md`) left open whether the through truck route's
-4.2% premium in the unit run was real. In the unit run the building effects of truck route
buildings rose to cancel it. Ben asked whether truck route buildings might be newer and nicer
in ways the model did not measure, so that a real discount and a real premium cancel, and he
asked for a fit to test this. The model `building-zones-age` (#1194) takes the gym model,
puts `bld:truck_through` back and adds year built in five bands against 1900 to 1939, a
year-unknown flag, alteration from 2000 up to the ad's year, and MapPLUTO retail with an
unknown flag. The PR has the data coverage tables and the predictions.

## The run

```sh
ops/modal-fit --dataset /data1/apartments/frontier/datasets/b0-edc83b49f9bacd8c-alldata-v36-dense-nyc \
  --split latest f023987f dense-w1000 building-zones-age b0 4 300 1000 5 \
  --seed 20261021 --no-loo --no-heldout
```

`building-zones-age-b0-latest-f023987f-dense-w1000` ran on a Modal A100 from 14:57 to 15:11 ET
on 2026-10-21, with 300 warmup and 1,000 sampling sweeps per chain against 150 and 650 for the
gym run. The fit stage took 799 s (warmup 99 s, sampling 588 s) and the container 820 s, at
$0.54 by `ops/modal-fit`'s estimate.

It passes the convergence gate. Max R-hat is 1.0044 on `beta[flag:income_restricted]` and min
bulk ESS is 604 on `amp[outer]`, the quantity that failed the gym run (R-hat 1.0149, ESS 415).
The new coefficients agree across chains to within 0.1 point: chain medians for truck route
are -3.91%, -3.92%, -3.83% and -3.92%, and for gym 6.85%, 6.81%, 6.85% and 6.85%.

## Results

Premiums, posterior median with 90% interval:

| column | age run | gym run | unit run |
|---|---|---|---|
| truck route | -3.90% (-4.59 to -3.26) | | -4.24% |
| gym | +6.84% (6.27 to 7.40) | +7.64% | |
| built before 1900 | +4.11% (3.83 to 4.36) | | |
| built 1940 to 1979 | -0.81% (-1.43 to -0.23) | | |
| built 1980 to 1999 | -1.69% (-2.27 to -1.07) | | |
| built 2000 to 2009 | -1.73% (-2.12 to -1.33) | | |
| built 2010 on | +4.04% (3.55 to 4.52) | | |
| year unknown | +1.19% (-0.36 to +2.61) | | |
| altered since 2000 | +3.84% (3.67 to 4.01) | | |
| retail | -1.87% (-2.11 to -1.62) | | |
| retail unknown | -0.60% (-1.72 to +0.53) | | |
| doorman, full-time | +15.56% (14.77 to 16.38) | +14.05% | +17.17% |
| doorman, part-time | +8.76% (7.99 to 9.50) | +8.43% | +11.08% |
| doorman, virtual | +2.83% (2.57 to 3.12) | +3.34% | +3.86% |
| elevator | +6.76% (6.39 to 7.12) | +6.69% | +7.98% |
| elevator unknown | +1.84% (1.35 to 2.37) | +1.66% | +1.55% |
| condo | +10.38% (9.92 to 10.83) | +10.47% | +10.86% |
| roof height, per e-fold | -0.72% (-1.06 to -0.42) | -0.75% | -0.37% |
| height unknown | -0.64% (-1.38 to +0.08) | +0.31% | +0.55% |
| size, per unit of log(size / bedroom median) | +28.64% (28.50 to 28.79) | +28.63% | +28.60% |
| laundry in unit | +6.42% (6.35 to 6.49) | +6.48% | +6.48% |
| laundry in building | +1.63% (1.56 to 1.69) | +1.64% | +1.65% |
| dishwasher | +2.03% (1.99 to 2.07) | +2.04% | +2.05% |

The size flags, the bed and bath steps, the error sigmas (0.084, 0.083, 0.089, 0.102) and nu
(4.11) match the gym run. The zone gap is +31.3% (30.9 to 31.8), against +30.2%.

Against buildings from 1900 to 1939, the oldest and the newest buildings both rent about 4%
higher, and the ones in between rent 1% to 2% lower. These premiums come on top of the
doorman, elevator and gym columns, which already carry most of what newer buildings offer.
The alteration term overlaps the 2010 band: MapPLUTO gives 45% of the ads in buildings from
2010 on an alteration year from 2000 on, against 12% to 23% in the other bands.

| zone | building spread | building share | map amplitude |
|---|---|---|---|
| Manhattan, gym run | 0.1873 | 0.439 | 0.954 |
| Manhattan, age run | 0.1840 | 0.452 | 0.897 |
| Brooklyn + Queens, gym run | 0.1167 | 0.310 | 0.377 |
| Brooklyn + Queens, age run | 0.1141 | 0.306 | 0.361 |

`T` (error + building effect + map value, demeaned by zone) has variance 0.0509 (0.0528 in
Manhattan, 0.0482 in Brooklyn + Queens), against 0.0511 for the gym run and 0.0530 for the
unit run.

I added each column group's contribution x·gamma back into `T` and took the rise in its
variance, alone and averaged over all 40,320 orderings of the eight groups:

| group | variance of contribution | rise alone | Shapley rise | Manhattan | Brooklyn + Queens |
|---|---|---|---|---|---|
| size | 0.00229 | 0.00731 | 0.00790 | 0.01033 | 0.00447 |
| laundry | 0.00064 | 0.00298 | 0.00366 | 0.00382 | 0.00344 |
| gym | 0.00094 | 0.00307 | 0.00365 | 0.00425 | 0.00281 |
| dishwasher | 0.00010 | 0.00074 | 0.00102 | 0.00105 | 0.00097 |
| year built | 0.00036 | 0.00080 | 0.00089 | 0.00067 | 0.00120 |
| altered since 2000 | 0.00025 | 0.00031 | 0.00052 | 0.00065 | 0.00033 |
| truck route | 0.00006 | -0.00026 | -0.00032 | -0.00029 | -0.00036 |
| retail | 0.00008 | -0.00051 | -0.00065 | -0.00059 | -0.00072 |

With all eight added back, `T` has variance 0.0675. Truck route and retail have negative
rises, meaning that adding their contribution back lowers the variance of `T`. The building
effects of these buildings sit above the neighbors' and cancel the negative coefficients.

### Truck route buildings

On the 71,632 training ads in truck route buildings, the predicted log rent changed by -0.04
points on average against the gym run, which had no truck column, and by 0.000 points against
the unit run. Against the unit run, the building effects of these buildings fell by 1.2 points
and the map value by 0.3 points, as year built, alteration, retail and gym took a share.

Ad-weighted mean building effect of truck route buildings, against buildings without a truck
route in the same 500 m cells (log points times 100):

| era | buildings | ads | age run | neighbors | unit run | neighbors |
|---|---|---|---|---|---|---|
| before 1900 | 257 | 2,593 | -3.7 | -6.6 | -1.8 | -4.5 |
| 1900 to 1939 | 687 | 23,215 | -4.0 | -4.8 | -4.3 | -5.5 |
| 1940 to 1979 | 60 | 5,514 | +4.3 | -2.3 | +4.8 | -3.4 |
| 1980 to 1999 | 43 | 5,267 | +5.0 | -0.7 | +4.9 | -2.8 |
| 2000 to 2009 | 109 | 15,927 | +7.8 | +2.0 | +6.4 | +1.0 |
| 2010 on | 127 | 18,763 | +0.9 | -0.4 | +6.7 | +4.8 |
| all | 1,292 | 71,632 | +1.3 | -3.3 | +2.5 | -2.8 |

| size | buildings | ads | age run | neighbors | unit run | neighbors |
|---|---|---|---|---|---|---|
| 1 to 5 units | 667 | 7,504 | +6.1 | +2.5 | +5.5 | +2.9 |
| 6 to 19 | 315 | 9,337 | -2.0 | -4.1 | -2.2 | -4.3 |
| 20 to 99 | 191 | 13,757 | -2.5 | -7.2 | -0.9 | -7.0 |
| 100 or more | 117 | 41,031 | +2.5 | -1.6 | +4.2 | -0.1 |

| training ads | buildings | ads | age run | neighbors |
|---|---|---|---|---|
| 1 to 4 | 439 | 937 | +1.8 | +1.8 |
| 5 to 19 | 406 | 4,019 | -0.5 | +0.9 |
| 20 to 99 | 302 | 13,505 | -1.7 | -5.8 |
| 100 or more | 145 | 53,171 | +2.2 | -3.1 |

Year built did not close the gap. Across all truck route buildings it went from 5.3 points in
the unit run to 4.6, and within the 2000 to 2009 band it widened from 5.4 to 5.8. Only for
buildings from 2010 on, which the new term rates +4%, did it close: from 1.9 points to 1.3.
Buildings with 20 or more training ads still sit 4 to 5 points above their neighbors, enough
to cancel the -3.9% coefficient. In buildings with few ads, whose effects shrink toward the
map, the coefficient applies in full. The -3.9% therefore still reads as a discount on small,
thinly listed truck route buildings. Large truck route buildings carry building effects that
year built, alteration, retail, gym, doorman and elevator do not explain.

### Held-out ads

Held-out ads of the latest split (189,649 ads, 68 draws per run, Student-t log density; elpd
is the age run minus the named run):

| rows | ads | elpd vs gym | elpd vs unit | RMSE age / gym / unit | mean bias age / gym |
|---|---|---|---|---|---|
| all | 189,649 | +31.7 (SE 18.4) | +20.4 (SE 18.5) | 0.11728 / 0.11732 / 0.11731 | -0.51% / -0.51% |
| Manhattan | 117,638 | -9.6 (SE 12.1) | -9.4 (SE 12.0) | 0.11826 / 0.11825 / 0.11826 | -0.55% / -0.55% |
| Brooklyn + Queens | 72,011 | +41.4 (SE 13.9) | +29.7 (SE 14.0) | 0.11567 / 0.11577 / 0.11575 | -0.45% / -0.44% |
| gym buildings | 66,343 | +6.9 (SE 6.5) | +4.1 (SE 6.5) | 0.11385 / 0.11386 / 0.11387 | -0.91% / -0.92% |
| truck route buildings | 8,854 | +4.0 (SE 2.8) | +0.8 (SE 2.6) | 0.10962 / 0.10966 / 0.10967 | -1.06% / -1.12% |
| retail buildings | 93,336 | -0.7 (SE 10.6) | -1.5 (SE 10.6) | 0.11582 / 0.11581 / 0.11581 | -0.68% / -0.70% |
| built 2000 on | 42,374 | +15.1 (SE 6.0) | +10.8 (SE 6.0) | 0.11435 / 0.11442 / 0.11441 | -1.39% / -1.40% |

By the building's training ads, elpd against the gym run:

| ads | 1 to 4 training ads | 5 to 19 | 20 or more |
|---|---|---|---|
| truck route | +1.2 (SE 1.4), 106 ads | -1.3 (SE 1.8), 468 | +4.1 (SE 1.7), 8,280 |
| gym | +2.1 (SE 2.0), 95 | +1.1 (SE 1.5), 582 | +3.6 (SE 6.0), 65,666 |
| retail | +4.4 (SE 4.4), 1,149 | -0.4 (SE 5.6), 6,868 | -4.7 (SE 7.9), 85,319 |
| built 2000 on | +7.1 (SE 2.9), 542 | +0.6 (SE 3.5), 2,453 | +7.3 (SE 3.8), 39,379 |
| all | +28.2 (SE 9.8), 5,943 | -11.5 (SE 10.4), 23,210 | +15.0 (SE 11.6), 160,496 |

No held-out ad is in a building with no training ads. The overall gain of +32 is under 2 SE.
The clearest gains are in Brooklyn + Queens (+41, about 3 SE), in buildings from 2000 on
(+15, 2.5 SE) and in buildings with 1 to 4 training ads (+28, 2.9 SE), where the measured
columns matter most. Coverage of the 90% predictive interval is 0.883 (gym 0.882), and of the
50% interval 0.481 (0.482). Median absolute error is 0.0669, against 0.0670.

My first pass at these scores used 100 draws for the age run and 68 for the others, and gave
+43 elpd and 0.890 coverage. More draws widen the sampled intervals and raise the log score
estimate, so I reran every run at 68 draws. The table shows that rerun.

Examples, at posterior medians with 90% predictive intervals:

| ad | held out | ask | predicted | 90% interval | gym run |
|---|---|---|---|---|---|
| 796 Avenue of the Americas, 2 bed, 2026-10-16 | no | $9,314 | $9,712 | $8,123 to $11,620 | $9,717 |
| 23 Eagle Street, Brooklyn, 1 bed, 2026-10-16 | yes | $6,059 | $4,908 | $4,202 to $5,841 | $4,908 |
| 85 East End Avenue, 1 bed, 2026-10-16 | yes | $6,183 | $5,512 | $4,640 to $6,543 | $5,514 |

## Predictions, scored

| # | Prediction | Result | Score |
|---|---|---|---|
| A1 | truck stays negative, between -3.5% and -1% | -3.90% (-4.59 to -3.26) | miss: barely shrank |
| A2 | gym falls by 1 to 3 points | +6.84%, a fall of 0.8 | miss: fell less |
| A3 | before 1900 -2 to +2; 1940-79 -5 to -1; 1980-99 -3 to +2; 2000-09 +1 to +6; 2010 on +4 to +12 | +4.11, -0.81, -1.69, -1.73, +4.04 | hit on 1980-99 and 2010 on, miss on the other three |
| A4 | altered between 0% and +4% | +3.84% | hit |
| A5 | retail between -3% and +0.5% | -1.87% | hit |
| A6 | full-time doorman and elevator fall 0.5 to 3 points; unit columns move under 0.5 | doorman +1.5, elevator +0.1; unit columns under 0.1 | miss on doorman and elevator, hit on unit columns |
| A7 | `T` variance falls by 0.001 to 0.004 | 0.0511 to 0.0509 | miss |
| A8 | the 2000-09 truck building gap halves or more | 5.4 to 5.8 points | miss |
| A9 | passes the gate in about 14 min at about $0.55 | R-hat 1.004, 13.3 min, $0.54 | hit |

I expected the new terms to work like a premium for recent construction and to take credit
from the doormen, the elevator and the gym. Instead the fit priced the oldest buildings as high
as the newest, and the full-time doorman premium rose. The test of Ben's alternative came out
against it. Truck route buildings are newer than their neighbors, but their age does not
explain why the large ones rent above their neighbors.

The scripts are in `building-zones-age-2026-10-21/` (`agecov.py` computed the PR's coverage
tables), and the draws-derived data (map grid, buildings, coefficients with chain medians and
traces, examples, `T` variance, contributions, held-out scores, the building tables and the
scored predictions) is at https://claude.ai/artifact/CaAoDoDPMjYrHqr6qUjosj.
