# Building zones on a Gibbs sampler, 2026-10-20

Ben asked for the building-zones model on a Gibbs sampler and a fit-only Modal run of it. The
model is the one in #1173 and #1175, unchanged: three zones with NJ included, the 1 km
surfaces, the weekly normal walk and a level for every building around its zone's surface,
fitted to the bath-fixed v36 dense dataset `b0-edc83b49f9bacd8c-alldata-v36-dense`. Only the
sampler changes, and the model has no building attributes.

On all data, ChEES settled on 3 leapfrog steps, fitted to the 73k building levels, and the
amplitudes, waves and walk barely moved in 1,500 warmup draws (run
`building-zones-b0-latest-70e1b061-dense-w1500`, max R-hat 6.57). #1175 put a floor of 64
steps under it, but that fit never ran.

## The sampler

`rentfrontier.building_zones_gibbs` writes the Student-t as a scale mixture, each ad with its
own precision weight lam_i ~ Gamma(nu / 2, nu / 2). Given the weights, every location and
level term is Gaussian, and a sweep goes:

1. Draw the global block, 922 coefficients: the 31 fixed coefficients other than alpha, the
   walk's 674 levels, the drift g and the 216 wave coefficients. I integrate the building
   levels out first. Each level meets only its own rows and its prior, so each one adds a
   scalar to the precision, and eliminating it is a rank-one update. The sampler sums those
   updates over blocks of 4,096 buildings with rows, then factors the dense 922 x 922 Schur
   complement whole.
2. Draw each zone's building spread b_z, still with the levels integrated out. Given the
   global block, each building's marginal likelihood is closed-form.
3. Draw every building's level given the global block and b_z, each building on its own,
   centred on F(s).
4. Draw nu and the four sigmas with the weights integrated out, from the Student-t likelihood
   of the residuals, then draw the weights.
5. Draw tau given the walk, and each zone's amplitude given its waves.

Steps 1 to 3 draw the levels last, after the two steps that integrate them out, and step 4
does the same for the weights, so each partially collapsed step keeps the posterior. The walk
is parametrised by its levels M, with alpha = M_0 and L = M - M_0. The NumPyro model starts from
flat totals D = M + Bs beta_season, and the map from (beta, D) to (beta, M) has Jacobian 1.
The run writes the keys building zones' ChEES run writes, so its summary, diagnostics and
building quantiles read the run unchanged.

## Checks on thelio

- `test_global_system_matches_the_dense_schur_complement` builds the joint precision of the
  global block and the levels row by row on a toy design, takes its Schur complement densely,
  and matches the sampler's precision and linear term to 1e-7.
- `test_recovers_simulated_scales` redraws a toy design's rents from the model at known values
  and recovers nu, tau, sigma and the outer and NJ building spreads.
- `test_run` runs the model end to end through `rentfrontier.run` on a toy design and reads the
  run back with the summary.

On the 5% latest-split sample (88,631 rows, 27,719 buildings with rows) I ran four chains of
200 warmup and 1,000 draws on thelio's CPU, at 1.68 s a sweep of all four chains, and set the
result beside the single NUTS chain of 200 draws from #1173. The 90% intervals match to within
the NUTS chain's own noise:

| quantity | Gibbs 5 / 50 / 95% | ESS | NUTS 5 / 50 / 95% | ESS |
|---|---|---|---|---|
| amp, Manhattan | 0.677 / 0.801 / 0.956 | 1,090 | 0.674 / 0.794 / 0.965 | 150 |
| amp, outer | 0.303 / 0.371 / 0.454 | 597 | 0.301 / 0.362 / 0.438 | 82 |
| amp, NJ | 0.305 / 0.458 / 0.665 | 826 | 0.320 / 0.440 / 0.628 | 77 |
| bld_sd, Manhattan | 0.2162 / 0.2192 / 0.2223 | 1,717 | 0.2161 / 0.2189 / 0.2213 | 53 |
| bld_sd, outer | 0.1338 / 0.1359 / 0.1380 | 1,387 | 0.1337 / 0.1360 / 0.1379 | 31 |
| bld_sd, NJ | 0.1369 / 0.1437 / 0.1513 | 1,829 | 0.1389 / 0.1455 / 0.1529 | 19 |
| bld_share, Manhattan | 0.567 / 0.577 / 0.587 | 610 | 0.568 / 0.577 / 0.586 | 137 |
| bld_share, outer | 0.379 / 0.389 / 0.399 | 630 | 0.380 / 0.389 / 0.398 | 79 |
| bld_share, NJ | 0.579 / 0.622 / 0.670 | 652 | 0.576 / 0.620 / 0.663 | 87 |
| nu | 3.763 / 3.875 / 3.983 | 699 | 3.759 / 3.866 / 3.967 | 191 |
| tau | 0.0057 / 0.0063 / 0.0070 | 320 | 0.0057 / 0.0063 / 0.0070 | 38 |

The largest R-hat is 1.017, on tau, which also mixes slowest: 320 effective draws from 4,000,
or about one in 12.5 sweeps. Every chain reached the posterior within the first 40 warmup
sweeps.

## Time on all rows

The full latest-split training set has 1,772,176 rows and 73,433 buildings. On thelio's 8 GB
GPU a sweep took 0.63 s for one chain and 1.36 s for two, and four chains ran out of its
memory. My first attempt closed the sweep over the rows' arrays, and jit compiled them in as
constants: it passed 12 GB of host memory before the first sweep and was killed. The sweep
now takes them as an argument, and setup and compilation take 20 s.

On 5% of the rows tau, the slowest quantity, gave one effective draw per 12.5 sweeps of a
chain. I chose four chains of 150 warmup and 650 draws, keeping every fifth. At thelio's rate
that comes to 800 x 2.72 s, about 36 minutes for the fit stage, under the hour's cap, and
should give tau about 200 effective draws if all rows mix as the sample did. An A100 has far
more double-precision throughput than thelio's card, so the fit should run faster than that.
`ops/modal/cap.py` takes 1.4 s an iteration per pair of chains for this model until its first
Modal fit measures its own rate, and estimates the run at 3,280 s and $2.18.

```sh
ops/modal-fit --dataset /data1/apartments/frontier/datasets/b0-edc83b49f9bacd8c-alldata-v36-dense \
  --split latest COMMIT dense-w650 building-zones-gibbs b0 4 150 650 5 \
  --seed 20261020 --no-loo --no-heldout
```

## Predictions, written before the fit

The timing run above printed each chain's state after 11 sweeps from the start: nu 3.90 and
3.87, Manhattan's building spread 0.267 and 0.269, the outer zone's 0.151 and 0.150. Those
sweeps had not converged, but I saw them before writing these.

| # | Prediction |
|---|---|
| G1 | The fit converges: max R-hat under 1.05 and min bulk ESS over 100 on the traced scalars. |
| G2 | The fit stage takes under 40 minutes, the whole run under 55, and it costs under $2.20. |
| G3 | nu lands between 3.6 and 4.2. |
| G4 | The building spread lands between 0.23 and 0.30 in Manhattan, 0.13 and 0.18 in the outer zone and 0.12 and 0.20 in NJ, above the 5% fit's in Manhattan, since more ads per building leave less of a building's mean to noise. |
| G5 | The building share of location variance lands between 0.50 and 0.70 in Manhattan and between 0.33 and 0.55 in the outer zone. |
| G6 | tau lands between 0.005 and 0.008. |
| G7 | The amplitudes land between 0.5 and 1.2 in Manhattan, 0.25 and 0.6 in the outer zone and 0.25 and 1.0 in NJ. |

## Results

The fit `building-zones-gibbs-b0-latest-f1cd5984-dense-w650` ran on a Modal A100-40GB from
17:08 to 17:18 ET on 2026-10-20, fit-only, seed 20261020. The fit stage took 532 s and the
whole container 569 s, and the Modal ledger settled it at $0.38. The A100 swept all four
chains in 0.54 s, five times faster than the 2.72 s projected above from thelio's two-chain
rate, so cap.py's stated rate
overstated the cost about sixfold. The next launch takes this fit's own rate.

It misses the repo's convergence gate (split R-hat at or below 1.01, bulk ESS above 400) on
three of 50 quantities:

| quantity | R-hat | bulk ESS |
|---|---|---|
| beta[bed=2:full>=4] | 1.0177 | 402 |
| beta[bed=0:full>=3] | 1.0136 | 414 |
| amp[outer] | 1.0062 | 367 |

The two bath steps cover few ads, studios with three full baths and two-bedrooms with four,
and they mix slowest among the fixed coefficients. tau, the slowest quantity on 5% of the
rows, reached 743 effective draws here. Every other quantity passes, most with ESS over 1,000.

| # | Prediction | Posterior median (90% interval) | Result |
|---|---|---|---|
| G1 | max R-hat under 1.05, min ESS over 100 | max R-hat 1.018, min ESS 367 | hit, though the repo gate fails |
| G2 | fit stage under 40 min, run under 55, under $2.20 | 8.9 min, 9.5 min, $0.38 | hit |
| G3 | nu 3.6 to 4.2 | 3.85 (3.83 to 3.87) | hit |
| G4 | building spread 0.23 to 0.30 Manhattan, 0.13 to 0.18 outer, 0.12 to 0.20 NJ | 0.266, 0.150, 0.161 | hit |
| G5 | building share 0.50 to 0.70 Manhattan, 0.33 to 0.55 outer | 0.559, 0.402 (NJ 0.660) | hit |
| G6 | tau 0.005 to 0.008 | 0.0044 (0.0041 to 0.0046) | miss |
| G7 | amplitude 0.5 to 1.2 Manhattan, 0.25 to 0.6 outer, 0.25 to 1.0 NJ | 1.10, 0.476, 0.719 | hit |

The noise scales are 0.086, 0.085, 0.091 and 0.104. On all rows tau fell by a third from the
5% sample's 0.0063. My guess is that the sample's sparse weeks let noise into the walk, but
I have not checked that. The building spreads rose above the 5% fit's in every
zone, by 21% in Manhattan, and the Manhattan amplitude rose from 0.80 to 1.10.

I compared the zones by averaging each zone's map over its own ads. Manhattan comes out 37.3%
(36.8 to 37.9) above Brooklyn + Queens. The whitened-zones and two-zone 1 km fits put that gap
at 32.2% and 32.3%, so it rose about five points once each building had its own level. I have
not checked why. NJ comes out 5.1% (4.3 to 5.8) above Brooklyn + Queens. These intervals count
only the map's uncertainty, so they are narrow.

A tour of the fit drawn from its saved draws, with each chain shown, is at
https://claude.ai/artifact/KeHuAEF5jutBYu9cFGSLnc.

Under Ben's standing rule, a fit that fails to converge is not retried on another seed. The
slow bath steps and amp[outer] are the place to look: the bath steps through how their sparse
cells are coded, and amp[outer] through an interweaving step for the waves like b0's, which
the reviewer of #1180 suggested for slow scale parameters.
