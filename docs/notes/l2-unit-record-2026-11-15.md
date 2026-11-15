# L2 with a slowly reverting unit level (2026-11-15)

This note designs fit 3 of the causal sprint (`docs/notes/causal-sprint-2026-11-14.md`) and
records its predictions before any run. The base is L2 on the unitkn base
(`docs/notes/l2-unitkn-level-2026-11-14.md`, pool
`drift-building-phase-unitkn-level-b0-latest-b27d1dd8-l2kn`). The new model is
`drift-building-phase-unitkn-level-slow`.

## The evidence

The gap screen (`docs/notes/l2-gap-screen-2026-11-14.md`, candidate (c)) regressed each
held-out ad's gap, its log ask less L2's predictive median, on the unit's mean training
deviation `m`. The slope is -0.066 ± 0.003 overall. By the months since the unit's previous
ad it is -0.037 at 0 to 2 months and steepens from about -0.05 to -0.10 from 10 months on.
Before 2021 it is near 0. L2 carries a unit's premium into a new ad in full at any distance
in time, and the held-out asks recover less of it, more so as the record ages.

I ran two more checks on L2's outputs and the training rows
(`docs/notes/l2-unit-record-2026-11-15/screen.py`, output in
`/data1/apartments/tmp/sprint-20261114/unit-record/screen.json`). Nothing was fitted.

**Part A** moves the location of each held-out ad by a correction in `m` and the years `L`
since the unit's previous training ad, fits the slope on one half of the buildings, applies
it to the other half and rescores L2's exact predictive:

| correction | elpd gain over L2 | SE | slope |
|---|---|---|---|
| static, b m | 640.9 | 51.2 | -0.064, -0.068 |
| linear, b m L | 528.9 | 42.2 | -0.0187 a year |
| both, (b0 + b1 L) m | 671.2 | 51.4 | -0.042 - 0.0086 L, -0.052 - 0.0059 L |
| decay, b m (1 - exp(-L / 5)) | 585.4 | 45.7 | -0.152 |
| decay, T = 10 | 563.8 | 44.4 | -0.245 |
| decay, T = 20 | 548.4 | 43.4 | -0.431 |
| decay, T = 40 | 539.2 | 42.9 | -0.803 |
| decay, T = 80 | 534.2 | 42.6 | -1.548 |

The two slopes in each row are those fitted on the two halves. Both forms together beat the
static form by 30.3 ± 9.0 and the linear form by 142.3 ± 20.4. Most of the gain is a shrinkage
of the record that is already present at short lags, and a smaller part grows with the lag.

**Part B** reads the training rows alone. I took each training ad's residual against a
monthly index and its building, bedroom count and year, and averaged the product of two
residuals over every pair of training ads of a unit, by the lag between them:

| lag, years | 0-0.25 | 0.25-1 | 1-2 | 2-3 | 3-4 | 4-5 | 5-6 | 6-7 | 7-8 | 8-9 | 9-10 | 10-13 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| covariance, 1e-3 | 6.78 | 4.69 | 4.84 | 4.70 | 4.48 | 4.38 | 4.32 | 4.06 | 3.90 | 3.96 | 3.87 | 3.90 |

The SEs run from 0.20 to 0.35 thousandths. Under L2's kernel the covariance should settle at
a floor of ss^2 once the drift's 2.6-year time constant has passed, by about 8 years. The
pairs keep falling from 2 to 8 years, by about 0.9 thousandths. A least-squares fit of a
second, slow OU term over the bins from 1 year on gives a profile chi-square of 29.5 at a
time constant of 10 years, 5.4 at 20, 2.4 at 30 and at 60, 3.3 at 100 and 5.3 at 1,000
(infinity is L2). This favors a time constant of 30 to 60 years by about 1.7 sigma, if the
bins were independent, which they are not quite. The excess in the first bin, under 3 months,
most likely comes from an ad relisted within weeks, and this change leaves it alone.

## The change

In L2 a unit's level at an ad is u_k(t) = s_k + d_k(t). The lasting level s_k ~ Normal(0,
ss^2 / kap_k) is constant, and the drift d_k is an OU process with sd 0.031 and a time
constant of 2.6 years. In the new model s_k is an OU process too, with its own time constant
unit_tau, so the covariance of u_k between ads at t_a and t_b is

    (ss^2 / kap_k) exp(-|t_a - t_b| / unit_tau) + sd^2 exp(-|t_a - t_b| / tau).

At unit_tau = infinity the model is L2. The prior on log unit_tau is Normal(log 40, 1), so
its central 95% runs from 5.6 to 285 years.

I chose this form over the others the sprint plan listed for these reasons:

1. A static factor on the record, the largest single gain in Part A, cannot enter L2's graph
   as a separate parameter. A factor f on s_k at prediction alone is not a model of the
   training ads. A factor applied at every ad is absorbed into ss. A factor between the
   record and the new ad of the same unit at the same time forms a ridge with the row noise.
   The static part of Part A's gain is out of reach of a single change to the graph, and the
   predictions below leave it out.
2. A factor exp(-lag / tau) on the unit's deviation, read literally, is a covariance only if
   it acts on a stationary process. The OU on s_k is the stationary process with that decay,
   and it keeps the Kalman filter, the Matheron draw of u and the collapsed kap step exact.
3. The two time constants act on different lags, 2.6 years and decades, and Part B shows the
   training pairs alone separate them. kap stays on the slow part only, as it stayed on s_k.
   The OU drift keeps its own sd and its own time constant.

The time since earlier ads enters only through the training dates of the unit's ads, inside
the kernel. A held-out ad's rent reaches the fit only as its target, and its date is that of
the ad, as in L2.

## The sampler

The sweep is L2's with `drift.make_sampler`'s new `unit_slow` option, off by default, so every
earlier model draws what it drew before (the pin tests of unitkn, unitk, unitkn-level and
unitt pass unchanged):

1. The scale step samples log unit_tau along with ss, sd and tau by the slice steps, with u
   and the buildings' levels integrated out. The Kalman filter on each unit's state (s, d)
   takes the slow level's OU step between ads.
2. The collapsed kap step needs each unit's density as a function of its kap. With a slow
   level the lasting part is v_k R, with R the OU correlation at unit_tau, in place of v_k
   times a matrix of ones. Once a sweep I factor M = sd^2 OU(tau) + C^-1 for each bucket of
   units, take the eigenvalues g of L^-1 R L^-T, and read the density at any kap from
   -(1/2) sum[log(1 + v g) + z^2 / (1 + v g)]. Units with a single ad keep the closed form.
3. u is drawn by Matheron's rule as in L2, with the lasting level's prior draw an OU path
   over the unit's ads in place of a constant.

Tests in `frontier/tests/test_drift_building_phase_unitkn_level_slow.py` check the Kalman
density against the dense Gaussian density of the kernel, the kap step's density against
differences of that density at kap moved by factors of 0.05 to 20, and that a unit_tau of a
million years gives L2's density and predictions. A short run is pinned by its draws.

## Predictions

The rehearsal below runs on 1 building in 10 and scores no held-out ad. The first four rows
are predictions for a full fit of the model on the latest split, scored against L2 with
`python -m rentfrontier.drift_score`. The last three apply to the rehearsal.

| quantity | L2 | prediction for the slow level |
|---|---|---|
| elpd gain over L2, held-out ads | 237,431 | +300, SE 45 (80% range +100 to +550) |
| MAE of the median, log rent | 0.04005 | 0.0400 |
| 50% coverage | 51.96% | 51.9% |
| 80% coverage | 80.07% | 80.0% |
| unit_tau, posterior median | infinity | 35 years (80% interval 20 to 70) |
| ss | 0.0466 | 0.050 |
| gate on the 1-in-10 rehearsal | | passes with chance 0.6 |
| gate on a 3-container Modal pool | | passes with chance 0.65 |
| sweep on the 1-in-10 rehearsal, RTX 2060 | | 2.5 s (range 2.0 to 3.5) |

The reasoning for the gain: the decay forms of Part A at T of 20 to 80 years score 534 to
548, and at T = 40 the fitted slope of -0.80 is close to the -1 the slow OU implies at
unit_tau = 40. Two things pull the model's gain below that. The model learns the decay from
the training pairs, without the held-out ads' gaps, and Part A fitted its slope on held-out
ads of the other half. A refit also moves ss, sd and the noise scales, which spends part of
the gain on the training ads' fit. I expect about 55% of the decay forms' gain. The model
lowers the weight of old records, which mostly moves the median, so the coverage should change
little.

For the gate, unit_tau is weakly identified at the long end: Part B's profile is flat from 30
to 60 years, and the slice step on log unit_tau may mix slowly against ss, which trades with
it at lags under the record's span. I expect ss and unit_tau to be the parameters that miss,
if any do.

The model gives up nothing on the pre-2021 ads, where the screen found no slope, beyond the
small shrinkage a 35-year time constant puts on a 5-year-old record.
