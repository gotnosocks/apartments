# L2's held-out scores from a short stretch of a chain

Ben asked on Nov 16 for ways to estimate the model at much lower expense. This note sizes
the cheapest of them with draws already on disk, at no cost.

## Cost of a fit now

L2's latest-split pool ran 3 H100 containers of 2 chains each and settled at $11.06. By the
record of container `l2kn-a`, its 2,813 s of fit split into 146 s preparing the design, 14 s
of setup, 109 s compiling, 445 s for 500 warmup sweeps and 2,099 s for 2,880 sampling
sweeps, the point where the time budget stopped the chains. So nine tenths of a container
goes to sweeps, and the pool makes 17,280 sampling sweeps over its 6 chains.

The gate sets that number. It asks for a bulk ESS above 400 on every scalar, and the scale
`drift_sd` reached 426 in container a. The scalars mix slowly because each is one number
informed by every unit or building. The predictions average over draws of a row's location
and spread, and those move little once the scalars sit in their posterior's range.

## The check

Each container keeps every 40th sweep's `pred_loc` and `pred_unit_sd` for the 189,647
held-out ads. `short-chains-2026-11-16/check.py` scores the ads with
`drift_score.score_rows` from subsets of the kept draws and compares each subset with the
whole pool of 432:

- the first 1, 2, 4 and 8 kept draws of chain 0 of container a (40 to 320 sweeps after
  warmup);
- the first 4 kept draws of both chains of container a;
- the same subsets from container b's chain 0, to show how much the answer depends on the
  chain.

For each it reports the held-out elpd, the 80% coverage, the mean absolute difference of the
median from the pool's, the Spearman correlation of the cdf at the ask with the pool's, and
the share of the pool's lowest 1% and lowest 10% of ads by cdf found in the subset's.

A fit of 500 warmup and 320 sampling sweeps in one container would take about 950 s where
a container now takes 2,813 s, so about $1.25 against the pool's $11.06.

The carried split holds out ads of units with earlier ads, so every held-out ad's building
has training rows. On the market, an ad in a building with no training row takes its
building's level as one draw from the prior per sweep. A few draws describe that level's
distribution poorly, so this check says nothing about such ads.

## Predictions (written before the check)

1. With 8 kept draws of one chain, the elpd is below the pool's by under 150 (65%), the
   80% coverage is within 0.3 points of the pool's (80%), the cdf's Spearman correlation is
   above 0.995 (80%), and at least 90% of the pool's lowest 1% are in the subset's (70%).
2. With 1 kept draw, the elpd is below the pool's by 300 to 1,500 (60%), and at least 80%
   of the pool's lowest 1% are in the subset's (60%).
3. Container b's chain gives figures within a third of container a's distance from the
   pool on elpd at 8 draws (55%).

## Results

The reference is the pool's stored scores (`pred_scores.npz`), since scoring 432 draws in
the check's blocks ran past the 4 GB cap.

| Kept draws | elpd against the pool's 237,430.7 | 80% coverage | Mean abs. median shift | Spearman of cdf | Pool's lowest 1% found | Lowest 10% found |
|---|---|---|---|---|---|---|
| a, chain 0: 1 | -58,400 | 62.4% | 0.039 | 0.840 | 46.5% | 62.8% |
| a, chain 0: 2 | -29,292 | 70.9% | 0.029 | 0.907 | 61.1% | 72.5% |
| a, chain 0: 4 | -14,539 | 75.6% | 0.021 | 0.950 | 71.9% | 80.1% |
| a, chain 0: 8 | -7,187 | 78.0% | 0.015 | 0.974 | 79.7% | 85.8% |
| a, both chains: 4 each | -7,153 | 78.0% | 0.015 | 0.974 | 80.0% | 85.8% |
| a, both chains: 72 each | -315 | 80.0% | 0.003 | 0.999 | 95.3% | 97.3% |
| b, chain 0: 8 | -7,050 | 78.0% | 0.015 | 0.974 | 79.0% | 85.6% |
| b, both chains: 72 each | -282 | 80.0% | 0.003 | 0.999 | 96.0% | 97.1% |

The pool's 80% coverage is 80.07%. Container b's other rows are within 230 elpd of
container a's.

Prediction scores:

1. Wrong on every part. With 8 draws the elpd is 7,187 below the pool's, the coverage is 2.1
   points lower, the correlation is 0.974 and 79.7% of the lowest 1% are found.
2. Wrong on both parts: 58,400 below, and 46.5% found.
3. Right: container b's distance at 8 draws is 7,050 against a's 7,187.

## Reading

The loss halves each time the draws double, and 8 draws from one chain score the same as 4
from each of two. So the loss follows the count of kept draws and has little to do with
the chain or with the scalars' position. A row's `pred_loc` carries a fresh draw of its
building's path and of the coefficients in each kept sweep, and one such draw moves the
median by 0.039 in log rent, about the size of the model's median absolute error
of 0.04. The predictive
distribution needs on the order of 150 such draws before the list of the lowest 1% settles
to within 5%.

At the same rate the pool of 432 draws itself stands about 135 to 160 elpd short of an
endless pool, and two pools of the same model would differ in about 3% of their lowest 1%.

So the number of sweeps is not what the predictions need. They need kept draws, and the
fits keep 1 sweep in 40. If a row's location loses its memory within a few sweeps, a fit of
500 warmup sweeps and 320 sampling sweeps keeping each one would predict about as well as
container a's 144 draws, at about $1.25. Keeping more draws would also sharpen the present
pools at no added sweeps.

## Second check: every sweep kept, on the k50 subsample

I run L2 on the k50 subsample on thelio's GPU with every sweep kept
(`REHEARSAL_KEEP=1`, 500 warmup, 1,200 draws, 2 chains), then measure

- the autocorrelation of `pred_loc` over sweeps, by lag, as the median over the 4,649
  held-out ads;
- the scores from chain 0's first 320 sweeps thinned by 1, 2, 4, 8 and 40, against the
  scores from all 2,400 kept draws;
- the sampling time a sweep, against 0.358 s with 1 sweep in 40 kept.

Predictions, written before the run:

1. The median lag-1 autocorrelation of `pred_loc` is below 0.5 (60%), and at lag 8 it is
   below 0.1 (75%).
2. Chain 0's first 320 sweeps, all kept, lose under 0.004 elpd an ad against the reference
   (60%) and find at least 90% of the reference's lowest 10% (65%).
3. Thinning those 320 sweeps by 40 (8 draws) loses 0.03 to 0.05 an ad (70%), the full
   data's 0.038.
4. Keeping every sweep raises the sampling time a sweep by under 25% (60%).

### Results of the second check

The run `frontier-l2-k50-keep1` sampled 1,200 sweeps of 2 chains in 433 s. I analyzed it
with `short-chains-2026-11-16/keep1.py`. As in every rehearsal on this subsample the run
misses the gate on Manhattan's building spread (R-hat 1.0689, bulk ESS 20), so the
reference below is the run's own 2,400 kept draws, with held-out elpd 5,839.9 and 80%
coverage 81.29%.

Autocorrelation of `pred_loc` over sweeps, across the 4,649 held-out ads:

| Lag | Median | 90th percentile |
|---|---|---|
| 1 | 0.177 | 0.411 |
| 2 | 0.071 | 0.234 |
| 4 | 0.023 | 0.095 |
| 8 | 0.005 | 0.050 |
| 16 | 0.000 | 0.039 |
| 40 | -0.002 | 0.038 |

Scores from the start of chain 0, against the reference:

| Sweeps | Kept | Draws | elpd lost | elpd lost an ad | 80% coverage | Lowest 1% found | Lowest 10% found |
|---|---|---|---|---|---|---|---|
| 320 | 1 in 1 | 320 | 6.9 | 0.0015 | 80.88% | 93.5% | 97.8% |
| 320 | 1 in 2 | 160 | 14.0 | 0.0030 | 80.92% | 93.5% | 97.0% |
| 320 | 1 in 4 | 80 | 25.5 | 0.0055 | 80.75% | 95.7% | 97.0% |
| 320 | 1 in 8 | 40 | 41.4 | 0.0089 | 80.40% | 93.5% | 94.8% |
| 320 | 1 in 40 | 8 | 148.4 | 0.0319 | 78.53% | 80.4% | 86.9% |
| 160 | 1 in 1 | 160 | 14.1 | 0.0030 | 80.81% | 91.3% | 95.9% |
| 160 | 1 in 2 | 80 | 21.0 | 0.0045 | 80.40% | 93.5% | 96.1% |
| 160 | 1 in 4 | 40 | 42.9 | 0.0092 | 80.28% | 91.3% | 93.8% |
| 160 | 1 in 8 | 20 | 89.4 | 0.0192 | 79.97% | 91.3% | 91.6% |
| 160 | 1 in 40 | 4 | 313.1 | 0.0674 | 75.99% | 73.9% | 79.5% |

The lowest 1% is 46 ads here, so its column moves in steps of 2.2 points.

The run's log reports 0.368 s a sweep, against 0.358 s with 1 sweep in 40 kept. The 433 s
over 1,200 sweeps come to 0.361 s, so the rise is between 1% and 3%.

Prediction scores:

1. Right on both parts: 0.177 at lag 1 and 0.005 at lag 8.
2. Right on both parts: 0.0015 an ad lost, and 97.8% of the lowest 10% found.
3. Right: 0.0319 an ad.
4. Right: the sweep time rose by 1% to 3%.

### Reading of the second check

A row's location forgets its previous sweep almost entirely: 160 consecutive sweeps score
the same as 160 draws spread over 320 sweeps (14.1 against 14.0 lost). So a kept sweep
costs at most 3% of a sweep's time and counts as about two thirds of an independent draw
(320 consecutive sweeps lose 6.9, about twice the loss expected of 320 independent draws). Two uses follow.

- Present pools can keep more draws. A pool of 3 containers runs about 17,000 sampling
  sweeps and keeps 432. Keeping 1 sweep in 4 would store ten times the draws for the same
  sweeps and close most of the 135 to 160 elpd between the pool and an endless one. The
  cost is storage: draws by rows by 4 bytes for each of the two stored arrays, which is
  about 6.5 GB for 4,320 draws of 189,647 held-out ads, so `drift_score` would need to read
  the draws in blocks.
- A fit used only for its predictions can be short. A single container with 500 warmup
  sweeps and 320 sampling sweeps, each kept, would cost about $1.25 against $11.06 for the
  pool, and on this subsample it ranks the ads as the long run does. Such a fit fails the
  convergence gate on the scalars by construction, so it cannot stand in for the fit that
  tests a model. It could serve the market and backtest fits of a model whose latest-split
  pool has passed the gate, which is a change to the Deals rule and is Ben's to decide.

Limits of this check:

- It ran on 1 building in 50. On the full data the scalars' position after 500 warmup
  sweeps may be further from the pool's than it was here, and the first check measured
  only kept draws of a long chain.
- Ads in a building with no training row take a draw of the building level from its prior
  each sweep. This split's held-out ads all have an earlier ad of the same unit, so that
  case is untested.
- Other routes to a cheaper fit were considered and set aside for now. Fixing the scales at
  plug-in values would need changes through most of `drift.py`'s sweep, and an earlier
  plug-in rebuild covered 0.805 against the fit's 0.808
  (`outlier-sprint-2026-11-11.md`). Variational inference is a poor match for a
  conditionally Gaussian model with over a million latent values, where each Gibbs sweep
  already draws the Gaussian block exactly.

A direct test on the full data is a single container on the latest split with
`--keep-every 1` and 320 sampling sweeps, scored against L2's pool, at about $1.25.

## Third check: a short fit on the full data

Ben approved this test on Nov 16. A single H100 container fits L2 on the latest split from
this section's merge commit, with 2 chains, 500 warmup sweeps and 320 sampling sweeps, each
kept, which stores 640 draws:

```sh
D=/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise
IN=/data1/apartments/pipeline/datasets/rows-b3ddebf19af1dc1e.parquet
ops/modal-fit --outside-budget --gpu H100 --dataset "$D" --input "$IN" --split latest \
  --baseline drift-building-phase-unitkn-level-b0-latest-b27d1dd8-l2kn COMMIT l2short \
  drift-building-phase-unitkn-level b0 2 500 320 1 --seed 1 --level-dof 4 \
  --no-loo --no-heldout
```

I score it with `drift_score` on the 189,647 held-out ads and compare it with L2's pool
(held-out elpd 237,430.7 from 432 draws) using `bed-text-2026-11-16/cmp.py`. I also score
each chain's 320 draws alone. The elpd difference between the two chains measures the noise
a comparison of two short fits would carry, which decides whether a short fit can also
compare two models.

Predictions, written before the launch:

1. The run misses the scalar gate (95%), as a chain of 320 sweeps must.
2. Its held-out elpd is within 150 of the pool's (65%). By the k50 check, 640 consecutive
   sweeps count as about 430 independent draws, near the pool's 432.
3. The 80% coverage is within 0.3 points of the pool's (70%).
4. The Spearman correlation of the two cdfs at the ask is above 0.995 (70%). At least 90%
   of the pool's lowest 1% are in the short fit's lowest 1% (65%), and at least 95% of its
   lowest 10% (70%).
5. The two chains' elpd, each from 320 draws, differ by under 60 (60%).
6. The container settles between $0.80 and $1.80 (70%).

I read the test as passed for predictions when the elpd lost against the pool is under
0.002 an ad (380 in all) and at least 95% of the pool's lowest 10% are found. A short fit
can stand in for a pool in a comparison of two models only when the chains' difference in
prediction 5 is small against the lead being tested.
