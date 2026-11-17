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
