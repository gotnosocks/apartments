# Building zones with the unit's floor, 2026-10-21

Ben asked for a test fit of something likely to explain variance among units, buildings or
neighborhoods, and the floor was the pick. The model `building-zones-floor` (#1196) takes the
age model (#1194, `building-zones-age-2026-10-21.md`) and adds a curve over floors for
elevator buildings and another for walk-ups, each with a Gaussian process prior on log floor,
plus flags for the top floor, penthouse, garden and lower-level labels and an unknown-floor
flag per group. The PR has the snapshot's coverage tables, the design and the predictions.

The data page with every table and curve is at
https://claude.ai/artifact/FxkYoSW942AWctAVGrf1iF, and the step-through explainer of the fit
is at EXPLAINER_URL.

## The run

```sh
ops/modal-fit --dataset /data1/apartments/frontier/datasets/b0-edc83b49f9bacd8c-alldata-v36-dense-nyc \
  --split latest 6b5a5b4a dense-w1000 building-zones-floor b0 4 300 1000 5 \
  --seed 20261021 --no-loo --no-heldout
```

`building-zones-floor-b0-latest-6b5a5b4a-dense-w1000` ran on a Modal A100 from 18:40 to 18:59
ET on 2026-10-21, with 300 warmup and 1,000 sampling sweeps per chain and 200 draws kept per
chain. The fit stage took 1,078 s by `ops/modal-fit`'s timer and the container 1,105 s, at
$0.73 by its estimate. The sampler logged 56 s preparing the data, 30 s compiling, 119 s of
warmup and 804 s of sampling. The design has 108 coefficients against the age model's 55, and
sampling took 37% longer than the age run's 588 s.

It passes the convergence gate. Max R-hat is 1.0097 and min bulk ESS 590, both on
`amp[outer]`, the same quantity that sat lowest in the age run (604). The four process
hyperparameters have R-hat at most 1.0013 and ESS from 3,685 to 4,010. Every curve value has
R-hat at most 1.004 and ESS of at least 1,690, and the four chains' medians agree to within
0.08 points at every floor.

## The floor curves

Premium over floor 1 in the same building group, posterior median with 90% interval, and the
spread of the four chains' medians. Share is the fraction of training ads at that floor.

| elevator floor | premium | chain medians | share |
|---|---|---|---|
| 2 | +1.2% (1.1 to 1.3) | 1.22 to 1.24 | 4.41% |
| 3 | +1.3% (1.2 to 1.4) | 1.32 to 1.33 | 4.79% |
| 4 | +1.5% (1.4 to 1.6) | 1.51 to 1.53 | 4.46% |
| 5 | +2.1% (2.0 to 2.2) | 2.08 to 2.08 | 3.86% |
| 6 | +2.5% (2.4 to 2.6) | 2.50 to 2.53 | 3.06% |
| 8 | +3.1% (2.9 to 3.2) | 3.08 to 3.10 | 1.70% |
| 10 | +3.8% (3.6 to 3.9) | 3.77 to 3.78 | 1.31% |
| 15 | +5.1% (4.9 to 5.3) | 5.07 to 5.09 | 0.82% |
| 20 | +6.7% (6.4 to 6.9) | 6.67 to 6.69 | 0.50% |
| 25 | +8.1% (7.8 to 8.4) | 8.07 to 8.11 | 0.34% |
| 30 | +10.0% (9.7 to 10.3) | 9.96 to 10.00 | 0.25% |
| 35 | +11.1% (10.8 to 11.5) | 11.13 to 11.16 | 0.15% |
| 40 | +13.8% (13.4 to 14.3) | 13.80 to 13.82 | 0.09% |
| 46 | +15.5% (15.0 to 16.1) | 15.52 to 15.57 | 0.05% |
| 47 and up | +19.5% (19.2 to 19.9) | 19.51 to 19.53 | 0.46% |

| walk-up floor | premium | chain medians | share |
|---|---|---|---|
| 2 | -0.3% (-0.4 to -0.2) | -0.32 to -0.31 | 6.51% |
| 3 | -0.4% (-0.5 to -0.3) | -0.42 to -0.41 | 5.99% |
| 4 | -0.6% (-0.7 to -0.5) | -0.61 to -0.60 | 3.88% |
| 5 | -0.9% (-1.0 to -0.7) | -0.90 to -0.86 | 1.67% |
| 6 and up | -0.7% (-1.0 to -0.4) | -0.74 to -0.71 | 0.28% |

In elevator buildings floor 2 rents 1.2 points above floor 1. Above that, each doubling of
the floor adds more than the one before: 0.3 points from floor 2 to 4, 1.6 from 4 to 8, 2.6
from 8 to 16 and 4.8 from 16 to 32. Nine
pairs of neighboring floors dip, by at most 0.6 points, which the per-floor nugget allows. The
capped column for floor 47 and up jumps 4 points over floor 46, since it pools every unit from
floor 47 to the 90s.

In walk-ups the curve is small and falls with each flight, by about 0.2 points a floor up to
floor 5. With the building effect already in place, a walk-up unit higher up rents for a
little less than one on the ground floor, which may be a discount for the stairs.

| process | amplitude | lengthscale on log floor |
|---|---|---|
| prior | 0.15 (0.09 to 0.34) | 0.70 (0.31 to 1.59) |
| elevator | 0.074 (0.063 to 0.090) | 0.98 (0.68 to 1.36) |
| walk-up | 0.100 (0.068 to 0.158) | 1.40 (0.71 to 2.78) |

The elevator lengthscale of about 1 means the curve's slope changes over roughly an e-fold of
floors. The walk-up lengthscale sits at twice its prior median, and its interval is wide,
since five floors give the process little to fit.

## The flags and other columns

Premiums, posterior median with 90% interval, the age run's median, the share of training ads
with the column set, and the column's contribution, the variance of x·beta over training ads:

| column | floor run | age run | share | contribution |
|---|---|---|---|---|
| unit:elev_top | +1.75% (1.67 to 1.83) | | 5.2% | 1.50e-05 |
| unit:walkup_top | -0.31% (-0.39 to -0.22) | | 5.5% | 4.98e-07 |
| unit:penthouse | +8.31% (8.13 to 8.49) | | 1.2% | 7.61e-05 |
| unit:garden | +2.88% (2.63 to 3.12) | | 0.5% | 4.35e-06 |
| unit:lower | -3.70% (-4.55 to -2.81) | | 0.03% | 4.71e-07 |
| unit:elev_floor_unknown | +3.97% (3.86 to 4.08) | | 10.3% | 1.40e-04 |
| unit:walkup_floor_unknown | -0.55% (-0.63 to -0.47) | | 23.3% | 5.36e-06 |
| elevator curve | | | 40.1% | 6.95e-04 |
| walk-up curve | | | 18.3% | 3.80e-06 |
| bld:elevator | +3.59% (3.23 to 3.94) | +6.76% | 52.9% | 3.11e-04 |
| bld:elevator_unknown | +1.91% (1.39 to 2.44) | +1.84% | 0.7% | 2.60e-06 |
| bld:doorman_full | +14.96% (14.18 to 15.81) | +15.56% | 18.2% | 2.89e-03 |
| bld:doorman_part | +8.42% (7.63 to 9.15) | +8.76% | 13.0% | 7.41e-04 |
| bld:doorman_virtual | +2.95% (2.68 to 3.21) | +2.83% | 20.8% | 1.39e-04 |
| bld:condo | +10.51% (10.02 to 10.94) | +10.38% | 15.3% | 1.30e-03 |
| bld:gym | +6.68% (6.09 to 7.22) | +6.84% | 31.7% | 9.05e-04 |
| bld:log_height | -0.92% (-1.25 to -0.59) | -0.72% | 96.8% | 5.15e-05 |
| bld:truck_through | -3.93% (-4.62 to -3.27) | -3.90% | 4.2% | 6.46e-05 |
| bld:built_pre1900 | +4.00% (3.74 to 4.25) | +4.11% | 10.4% | 1.44e-04 |
| bld:built_2010_on | +4.09% (3.62 to 4.58) | +4.04% | 12.3% | 1.73e-04 |
| bld:altered_2000_on | +3.89% (3.71 to 4.05) | +3.84% | 23.4% | 2.60e-04 |
| unit:log_size_rel | +28.65% (28.51 to 28.80) | +28.64% | 43.1% | 2.05e-03 |
| unit:laundry_in_unit | +6.32% (6.26 to 6.39) | +6.42% | 29.0% | 7.75e-04 |

The data page lists every column. `bld:elevator` lost 3.2 points to the elevator curve. Most
bath steps for units with two or more full baths fell, by 0.5 to 1.9 points, since those large
units sit on higher floors on average. The step for studios with four full baths, set on 14
training ads, rose 2.6 points. Every other column stayed within 0.6 points of the age run.

The penthouse flag adds 8.3% on top of the curve at the unit's floor and the top-floor flag,
so a penthouse on the 30th and top floor of an elevator building comes to about +21% over
floor 1. The elevator top-floor flag adds 1.75%, a premium for the view or the roof above the
floor's own height. A walk-up's top floor rents 0.3% below the curve at its floor.

An elevator ad with no floor rents 4.0% above floor 1, about the curve's value at floor 10.
A walk-up ad with no floor rents 0.55% below floor 1, close to the curve at floors 3 to 4.

## Held-out ads

Held-out ads of the latest split (189,649 ads, 100 draws per chain and 400 per run, Student-t
log density; elpd is the floor run minus the age run). RMSE, coverage of the 90% predictive
interval and median error (ask minus predicted median, in log points) are given as age run /
floor run.

| rows | ads | elpd (SE) | RMSE | 90% coverage | median error |
|---|---|---|---|---|---|
| all | 189,649 | +2,945 (83) | 0.1172 / 0.1154 | 90.4% / 90.4% | -0.8% / -0.8% |
| floor known | 134,331 | +3,107 (80) | 0.1134 / 0.1105 | 90.7% / 91.0% | -0.9% / -0.9% |
| elevator, floor 1 | 4,593 | +198 (16) | 0.1348 / 0.1308 | 85.7% / 86.6% | -3.4% / -1.3% |
| elevator, floor 2 | 8,688 | +199 (14) | 0.1119 / 0.1098 | 90.5% / 90.8% | -1.9% / -0.7% |
| elevator, floors 3 to 5 | 27,033 | +726 (29) | 0.1108 / 0.1082 | 90.9% / 91.2% | -1.7% / -0.8% |
| elevator, floors 6 to 9 | 18,478 | +603 (31) | 0.1137 / 0.1099 | 90.1% / 90.7% | -1.2% / -1.0% |
| elevator, floors 10 to 19 | 18,502 | +643 (36) | 0.1147 / 0.1097 | 90.4% / 90.9% | -0.7% / -1.0% |
| elevator, floors 20 to 39 | 12,431 | +439 (38) | 0.1115 / 0.1057 | 91.4% / 91.9% | +0.3% / -1.6% |
| elevator, floor 40 and up | 2,359 | +136 (34) | 0.1405 / 0.1278 | 85.6% / 88.2% | +2.6% / -3.3% |
| elevator, floor unknown | 15,272 | -202 (17) | 0.1338 / 0.1353 | 87.5% / 87.0% | -0.3% / -0.6% |
| elevator, top floor | 10,849 | +911 (56) | 0.1429 / 0.1293 | 85.6% / 87.6% | +1.8% / -1.2% |
| elevator, penthouse | 1,962 | +706 (46) | 0.2175 / 0.1751 | 68.8% / 78.8% | +10.5% / -0.3% |
| walk-up, floor 1 | 9,324 | +13 (8) | 0.1249 / 0.1246 | 88.5% / 88.1% | -0.5% / -1.1% |
| walk-up, floor 2 | 11,281 | +37 (4) | 0.1060 / 0.1057 | 92.9% / 92.8% | -0.4% / -0.6% |
| walk-up, floors 3 to 5 | 21,151 | +111 (13) | 0.1069 / 0.1063 | 92.6% / 92.2% | -0.6% / -0.5% |
| walk-up, floor unknown | 40,046 | +39 (8) | 0.1229 / 0.1229 | 90.1% / 89.9% | -0.4% / -0.3% |
| walk-up, top floor | 9,739 | +64 (13) | 0.1099 / 0.1090 | 92.4% / 92.3% | -0.7% / -0.5% |
| walk-up, penthouse | 430 | +5 (12) | 0.1362 / 0.1303 | 87.2% / 88.6% | +2.0% / -3.7% |
| walk-up, garden | 852 | +11 (7) | 0.1388 / 0.1371 | 87.1% / 87.1% | +1.4% / -0.8% |

The overall gain of +2,945 is 36 SE, against +32 (1.7 SE) for the age run over the gym run,
and it clears the 2 SE bar by a wide margin. Nearly all of it comes from elevator buildings
with a known floor. Penthouses gain the most per ad: their RMSE falls by a fifth and their
coverage rises 10 points. The age run underpredicted penthouses by a median 10.5% and now
misses by 0.3%.

Elevator ads with no floor lose 202 (12 SE). Their median error moved from -0.3% to -0.6% and
their coverage fell half a point, so the single +4.0% flag fits them a little worse than the
age run's building and elevator terms did. On floors 40 and up the floor run overshoots: the
age run predicted these ads 2.6% low, the floor run 3.3% high. The scores by band are
exploratory, since I chose the bands after the fit.

## Variance

`T` is the error plus building effect plus map value, demeaned by zone. Within-building
variance is the variance of the residual around each building's mean residual.

| ads | count | `T` variance | residual variance | within-building variance |
|---|---|---|---|---|
| all | 1,706,837 | 0.05087 to 0.04964 (-2.4%) | 0.01501 to 0.01461 (-2.7%) | 0.01427 to 0.01388 (-2.8%) |
| floor known | 1,133,317 | 0.04770 to 0.04583 (-3.9%) | 0.01395 to 0.01327 (-4.9%) | 0.01309 to 0.01244 (-5.0%) |
| elevator, floor known | 727,533 | 0.04908 to 0.04671 (-4.8%) | 0.01464 to 0.01365 (-6.8%) | 0.01407 to 0.01311 (-6.8%) |
| walk-up, floor known | 405,784 | 0.04053 to 0.04015 (-0.9%) | 0.01271 to 0.01259 (-1.0%) | 0.01133 to 0.01124 (-0.8%) |

## Building effects and the map

For the 44,368 buildings with training ads of known floor, the building effect d correlates
0.998 with the age run's, with a change of SD 0.86 points (median absolute change 0.23
points). For the 23,609 buildings without, the correlation is 0.9996 and the change SD 0.35
points. The building spread fell from 0.1300 to 0.1290 among buildings with floor data.

The map value correlates 0.99998 with the age run's, with a change of SD 0.15 points against
a spread of 22.4 points. The Manhattan map amplitude went from 0.897 to 0.916 and the outer
zone's from 0.361 to 0.360.

## Predictions, scored

| # | Prediction | Result | Score |
|---|---|---|---|
| F1 | elevator curve rises steadily with log floor, no dip | rises from +1.2% at floor 2 to +15.5% at floor 46, with nine dips of at most 0.6 points | miss |
| F2 | elevator floor 2: +1% to +4% | +1.2% (1.1 to 1.3) | hit |
| F3 | elevator floor 10: +4% to +12%, about +7% | +3.8% (3.6 to 3.9) | miss |
| F4 | elevator floor 30: +8% to +20% | +10.0% (9.7 to 10.3) | hit |
| F5 | intervals above floor 30 at least twice as wide as floor 10's | 0.3 points at floor 10, 0.9 at floor 40 | hit |
| F6 | walk-up curve small, peaks at floor 2 or 3 | small, but every floor is below floor 1 | miss |
| F7 | walk-up floor 2: -2% to +3% | -0.3% | hit |
| F8 | walk-up floor 5: -6% to +1%, below floor 2 | -0.9% | hit |
| F9 | elevator lengthscale 0.7 to 2.5 | 0.98 | hit |
| F10 | elevator amplitude 0.05 to 0.25 | 0.074 | hit |
| F11 | walk-up lengthscale stays close to its prior median of 0.7 | 1.40 | miss |
| F12 | elev_top +1% to +5% | +1.75% | hit |
| F13 | walkup_top -3% to +2% | -0.31% | hit |
| F14 | penthouse +5% to +15% | +8.3% | hit |
| F15 | garden +2% to +8% | +2.9% | hit |
| F16 | lower -15% to -4% | -3.7% (-4.6 to -2.8) | miss |
| F17 | elev_floor_unknown -1% to +4% | +3.97% | hit |
| F18 | walkup_floor_unknown -2% to +2% | -0.55% | hit |
| F19 | bld:elevator falls 2 to 5 points | +6.8% to +3.6%, down 3.2 | hit |
| F20 | building spread and surfaces barely move | correlations 0.998 and 0.99998 | hit |
| F21 | residual variance among known-floor ads falls 1% to 4% | falls 4.9% | miss |
| F22 | most of that fall is in elevator buildings | 6.8% in elevator buildings, 1.0% in walk-ups | hit |
| F23 | every quantity passes the convergence gate | max R-hat 1.010, min ESS 590 | hit |

17 hits and 6 misses. The curve rises overall but dips between some neighboring floors. I expected a steeper elevator curve at floor 10 and a small walk-up
premium for the first floors up, and both came in lower. The floor also explains more of the
residual than I expected.

## Scripts

The scripts in `building-zones-floor-2026-10-21/` ran on thelio from
`/data1/apartments/tmp/bzfl`, in this order:

1. `resid.py` writes each run's per-ad residuals, building effects and map values on the
   training rows.
2. `heldout.py` scores the held-out ads of both runs with 400 draws each, in chunks of 20,000
   rows.
3. `analyze.py` collects the curves, process hyperparameters, columns, variance and building
   changes into `analysis.json`.
4. `export.py` writes `floor-data.json` for the data page, and `page.py` writes the page.

`common.py` holds the run names and paths.
