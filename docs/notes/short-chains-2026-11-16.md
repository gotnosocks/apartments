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
median by 0.039 in log rent, more than half the size of the model's median absolute error
of 0.04. The predictive
distribution needs on the order of 150 such draws before the list of the lowest 1% settles
to within 5%.

At the same rate the pool of 432 draws itself stands about 100 to 135 elpd short of an
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
