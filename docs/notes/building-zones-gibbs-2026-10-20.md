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
