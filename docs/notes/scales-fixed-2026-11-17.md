# Holding the base model's scales in a fit of a variant (2026-11-17)

Ben asked on Nov 17 for the full fit of the base model with the bedroom-text flag
(`drift-building-bedtext`) to borrow its scales from the base model's fit. This note covers
the option that does it and a free check of it on thelio's GPU. The Modal fits get their own
predictions here before they are launched.

## The option

A full fit of the base model spends most of its sweeps on a handful of scales. In the market
pool `n9` the rows' noise scales `sigma` reached an ESS of 432 to 445 over 17,360 draws and
`drift_tau` 488, while the coefficients, the levels and the floor curves were past the gate
many times over. Those slow scales are also the ones the data fixes most tightly: each had a
posterior sd under 6% of its mean.

`--scales-fixed NAME` has `rentfrontier.drift`'s sweep hold a stored set of scales
(`rentfrontier.drift_scales`) and draw everything else given them. I stored the means of
these scales from the base model's two pools, `base-n9` from the market fit and `base-j9`
from the backtest:

- the rows' noise: `nu` and the four `sigma`
- the units: `unit_sd`, `drift_sd`, `drift_tau`
- the buildings: both zones' `bld_sd`, `building_ar_sd`, `building_ar_rho`
- the market's weekly step `tau`

The sweep still draws the wave amplitudes and the floor curves' amplitudes and lengthscales,
whose posterior sds were 11% to 44% of their means, along with the coefficients, the
market's level, the buildings' levels and paths, the units' levels and the rows' mixing
weights.

A fit run this way treats the held scales as known, so its intervals leave out their
uncertainty. With sds under 6% I expect that to narrow the predictive intervals by well
under a point of coverage. The gate applies to every quantity the sweep draws. The held
scales passed it in the pool they come from.

A backtest takes `base-j9`, whose pool was fitted on the backtest's training rows, so that
no rent after the scoring day reaches the fit through a scale.

## A free check on the k50 subsample

Before spending on Modal I check that a fit with held scales reproduces an ordinary fit of
the same model. Both runs use the plain base model on the k50 building subsample of the
Nov 14 rehearsals (41,576 training rows, 4,649 held-out ads), on thelio's GPU:

```sh
R=/data1/apartments/tmp/rehearsals-2026-11-14
systemd-run --user --unit=frontier-base-k50 -p MemoryMax=10G \
  ops/job gpu docs/notes/rehearsals-2026-11-14/rehearse.sh \
  drift-building k50-r8/base base-k50 500 2400 base-k50
python docs/notes/scales-fixed-2026-11-17/means.py $R/base-k50/runs/base-k50 $R/base-k50/scales.json
systemd-run --user --unit=frontier-held-k50 -p MemoryMax=10G \
  -E REHEARSAL_ENTRY=$PWD/docs/notes/scales-fixed-2026-11-17/held.py -E REHEARSAL_KEEP=20 \
  ops/job gpu docs/notes/rehearsals-2026-11-14/rehearse.sh \
  drift-building k50-r8/base held-k50 200 1200 held-k50 $R/base-k50/scales.json
```

The ordinary run goes first, with the rehearsals' settings of 500 warmup sweeps and 2,400
draws a chain. `means.py` averages its tight scales, and the held run takes those means
with 200 warmup sweeps and 1,200 draws a chain, half the ordinary run's sweeps. Both keep
60 draws a chain for scoring. I score each with `rentfrontier.drift_score` and compare them
with `scales-fixed-2026-11-17/cmp.py`.

The ordinary run is short for k50. Earlier k50 rehearsals of related models left `bld_sd`
and `unit_sd` far from the gate at these settings, so its scale means carry some chain
error, and its scores do too. I read the check as a comparison of the held run with the
best free reference available.

### Predictions (written before the runs)

1. The held run's held-out elpd is within 10 of the ordinary run's (75%).
2. The two runs' 80% coverages differ by under a point (80%). The held run's 80% interval is
   the narrower of the two on average (65%), by under 3% (75%).
3. The Spearman correlation of the two runs' cdf at the ask is above 0.995 (75%), and at
   least 95% of the ads in the ordinary run's lowest tenth are in the held run's (75%).
4. In the held run every quantity the sweep draws has R-hat at most 1.01 and bulk ESS above
   400 after 1,200 draws a chain (55%). The ordinary run misses the gate (90%).
5. The held run's sweep takes 70% to 100% of the ordinary run's time (70%). Most of a
   sweep's time goes to the Gaussian draws, which both runs make.

If predictions 1 to 3 hold, I write the Modal fits' settings and predictions below and
launch them. If the held run's scores sit clearly away from the ordinary run's, I look for
the cause in the held values and the sweep before any spend.

### Results

Both runs finished on thelio's GPU on Nov 17. The ordinary run's scale means went to the
held run through `means.py`, and `cmp.py` compared the two on the 4,649 held-out ads.

| Score | Held scales | Ordinary |
|---|---|---|
| sweeps a chain (warmup + draws) | 200 + 1,200 | 500 + 2,400 |
| time a sweep | 0.200 s | 0.316 s |
| warmup and sampling time | 280 s | 916 s |
| held-out elpd | 5,723.6 | 5,729.3 |
| median absolute error | 0.0403 | 0.0401 |
| coverage of the 50% / 80% / 95% interval | 53.6 / 81.8 / 95.3% | 53.9 / 81.8 / 95.2% |
| mean width of the 80% interval | 0.1797 | 0.1802 |
| worst R-hat | 1.015 (`beta[unit:size_unknown]`) | 1.070 (`unit_sd`) |
| lowest bulk ESS | 355 (`beta[ad:months_free]`) | 18 (`drift_sd`) |

The paired elpd difference is -5.7 for the held run with an SE of 5.2 clustered by
building. The Spearman correlation of the two cdfs at the ask is 0.9978, and 447 of the 464
ads in the ordinary run's lowest tenth are in the held run's (96.3%).

Scoring the predictions:

1. Elpd within 10: held (-5.7).
2. Coverage within a point: held (81.82% against 81.78%). The held run's 80% interval is
   narrower by 0.27%: held on both counts.
3. Spearman above 0.995 and at least 95% of the lowest tenth shared: held (0.9978, 96.3%).
4. The held run passing the gate at 1,200 draws: missed. Its worst quantities are
   coefficients at an ESS of 355 to 400 and an R-hat of 1.015. The ordinary run missed the
   gate by a wide margin, as predicted.
5. Sweep time of 70% to 100%: missed on the favourable side, at 63%.

The held run reproduces the ordinary run's scores, intervals and deal order in under a
third of its time. Part of the 5.7 elpd is the ordinary run's own chain error, since its
scales had an ESS as low as 18 and the held values are their means.

The check also corrects my expectation of the saving. With the scales held, the slowest
quantities are coefficients, at about 0.15 effective draws a sweep of two chains. That is
close to their rate in the full pool: in the market container `n9a` the slowest coefficient
(`beta[bed=0:full>=2]`) reached an ESS of 592 in 5,840 draws, against 432 for the slowest
`sigma`. Holding the scales removes the `sigma` bottleneck and shortens the sweep. I expect
one held container to reach the ESS two to three ordinary containers reach, and no more
than that.

## Modal fits

Each fit is one H100 container of 2 chains with 200 warmup sweeps, 3,600 draws a chain,
every 20th draw kept (360 in all, against the 434 a three-container pool keeps), and seed
1. At `n9a`'s rate of 592 effective draws in 5,840 for its slowest coefficient, 7,200 draws
give an ESS near 730. At 63% of `n9a`'s 0.745 s a sweep the sampling takes about 1,700 s.
If a sweep is no faster than `n9a`'s, the container's 2,520 s budget ends the run at about
3,200 draws a chain. I launch them from
`/data1/apartments/serve/master` at the merge commit of this section, each after the last
one's log reaches "synced":

```sh
IN=/data1/apartments/pipeline/datasets/rows-ddd2fe8f5da041b8.parquet
J=/data1/apartments/frontier/datasets/b0-ddd2fe8f5da041b8-alldata-dense-nyc-asof-20251110
M=/data1/apartments/frontier/datasets/b0-ddd2fe8f5da041b8-alldata-dense-nyc-market
ops/modal-fit --outside-budget --gpu H100 --dataset "$J" --input "$IN" --split market \
  --baseline drift-building-b0-market-67d14e17-j9 COMMIT heldbase-j \
  drift-building b0 2 200 3600 20 --seed 1 --level-dof 4 --scales-fixed base-j9 --no-loo --no-heldout
ops/modal-fit --outside-budget --gpu H100 --dataset "$J-bedtext" --input "$IN" --split market \
  --baseline drift-building-b0-market-67d14e17-j9 COMMIT heldbed-j \
  drift-building-bedtext b0 2 200 3600 20 --seed 1 --level-dof 4 --scales-fixed base-j9 --no-loo --no-heldout
ops/modal-fit --outside-budget --gpu H100 --dataset "$M-bedtext" --input "$IN" --split market \
  --baseline drift-building-b0-market-67d14e17-n9 COMMIT heldbed-m \
  drift-building-bedtext b0 2 200 3600 20 --seed 1 --level-dof 4 --scales-fixed base-n9 --no-loo --no-heldout
```

- `heldbase-j` is the plain base model on the backtest with the backtest pool's scales. It
  tests on the full data that a held fit reproduces j9, and it is the paired reference for
  the flag: the k50 difference of 0.0012 elpd an ad would be about 11 on the backtest's
  9,346 open ads, as large as the flag's gain in the short fits (+13.2).
- `heldbed-j` adds the flag on the same rows with the same scales.
- `heldbed-m` is the flagged model on every ad to date, with the market pool's scales. I
  built its dataset with `python -m rentfrontier.b0bedtext $M $M-bedtext`.

`ops/modal/cap.py` prices each launch before it starts and reserves that amount. A full
container that ran to its budget settled at $3.59 to $3.78 (`n9a`, `j9a`). These stop
earlier, and I expect each to settle near $2.70, about $8 for the three, from the $37.76
left.

I score each backtest run with `rentfrontier.drift_score` on the 9,346 open ads and compare
pairs with `docs/notes/bed-text-2026-11-16/cmp.py` and
`docs/notes/bedtext-base-2026-11-17/place.py`, as for the short fits.

### Predictions (written before the fits)

1. `heldbase-j` reproduces j9: its final-ask elpd is within 20 of j9's 9,978.6 (70%), its
   80% coverage within a point of 79.2% (85%), and at least 97% of j9's lowest tenth is in
   its lowest tenth (75%).
2. Every quantity the sweep draws passes the gate in a single container: in `heldbase-j`
   (75%), in `heldbed-j` (75%), in `heldbed-m` (75%), in all of them (60%). The slowest
   quantity is a coefficient in each (80%), with an ESS of 500 to 1,100 (60%).
3. A sweep takes 0.42 to 0.56 s (70%).
4. `heldbed-j` beats `heldbase-j` on final-ask elpd (80%), by 5 to 25 (60%).
5. The flagged ads in the lowest tenth fall from 21 to 25 under `heldbase-j` to 11 to 17
   under `heldbed-j` (65%).
6. In `heldbed-m` the coefficient of `ad:bed_text_smaller` is negative with a 95% interval
   clear of zero (90%).

### Publishing

If `heldbed-m` and `heldbed-j` pass the gate on every sampled quantity and prediction 1
holds on all three counts, I publish Deals from `heldbed-m` with `heldbed-j` as its
backtest, after `drift_deals validate`. If a fit misses the gate, I look at its slowest
quantity before adding a container. If `heldbase-j` sits away from j9, nothing is published
and the cause comes first.

### Results

The three fits ran on Nov 17 from 11:16 PM ET at commit `f288a423`, each to its full 3,600
draws a chain. I scored the two backtest runs with `rentfrontier.drift_score` and rescored
j9 the same way for the comparison of deal order.

| Fit | Worst R-hat | Lowest bulk ESS | Time a sweep | Sampling | Settled |
|---|---|---|---|---|---|
| `heldbase-j` | 1.0043 (`beta[ad:features_unstated]`) | 686 (`beta[bed=0:full>=2]`) | 0.319 s | 1,151 s | $1.96 |
| `heldbed-j` | 1.0042 (`beta[ad:features_unstated]`) | 671 (`beta[bed=0:full>=2]`) | 0.322 s | 1,159 s | $1.95 |
| `heldbed-m` | 1.0052 (`beta[ad:months_free]`) | 782 (`beta[ad:months_free]`) | 0.348 s | 1,253 s | $2.06 |

All three pass the gate on every quantity the sweep draws (258, 260 and 261 quantities).
The three cost $5.97, and the sprint has spent $68.21 of $100.

Scores on the backtest's 9,346 open ads, by final ask:

| Score | j9 (ordinary pool) | `heldbase-j` | `heldbed-j` |
|---|---|---|---|
| elpd | 9,978.6 | 9,972.7 | 9,993.8 |
| median absolute error | 0.0474 | 0.0475 | 0.0471 |
| coverage of the 50% / 80% / 90% / 95% interval | 51.4 / 79.2 / 89.1 / 94.5% | 51.3 / 79.1 / 89.0 / 94.5% | 51.3 / 79.4 / 89.1 / 94.6% |

Of the 934 ads in j9's lowest tenth by cdf at the ask, 914 are in `heldbase-j`'s (97.9%),
and the Spearman correlation of the two cdfs is 0.9995.

`cmp.py` pairs `heldbed-j` with `heldbase-j`. The flag leads by 21.0 elpd with an SE of 8.1
clustered by building. The 196 flagged ads contribute 5.6 (SE 6.8) and the 9,106 ads with
no bedroom-text flag of either kind 15.5 (SE 4.4). I attribute that to the unit-mean
column, which lowers the price of an unflagged ad in a unit whose earlier ads were flagged. The flagged ads' mean
prediction falls by 0.031 in log rent. Of the 930 ads in the base fit's lowest tenth, 913
stay, and 12 of the 17 leaving are flagged.

`place.py` places each ad's first ask. The flagged ads in the lowest tenth fall from 23
under `heldbase-j` to 13 under `heldbed-j`, and all 13 are among the 23. Across all ads the
lowest tenth holds 604 and 598 ads, with the same median of 26 days on the market and
shares raised and cut within a point of each other.

In `heldbed-m` the coefficient of `ad:bed_text_smaller` is -0.0036 (95% interval -0.0051 to
-0.0021), and the unit-mean column's is -0.0593 (-0.0614 to -0.0573).

Scoring the predictions:

1. `heldbase-j` reproduces j9: held on all three counts (elpd 5.9 lower, 80% coverage 79.1%
   against 79.2%, 97.9% of the lowest tenth shared).
2. The gate in a single container: held for all three. The slowest quantity is a
   coefficient in each, with an ESS of 671 to 782: held.
3. A sweep of 0.42 to 0.56 s: missed on the fast side, at 0.32 to 0.35 s. The H100 gains
   more from the shorter sweep than thelio's GPU did on k50.
4. `heldbed-j` ahead of `heldbase-j` by 5 to 25: held (+21.0, SE 8.1).
5. Flagged ads in the lowest tenth from 21 to 25 down to 11 to 17: held (23 to 13).
6. A negative coefficient with a 95% interval clear of zero: held.

### Published

The publishing rule is met. I ran `drift_deals publish` for `heldbed-m` with `heldbed-j` as
its backtest into a staging directory and compared it with the live table from n9. Both
list the same 6,774 ads, the Spearman correlation of `below_share` is 0.996, and 96 of the
live table's first 100 ads are in the staging table's first 100. The 4 leaving moved to
ranks 102 to 162. The backtest table by first-ask place is close to j9's: the lowest tenth
has a median of 26 days on the market, 17.2% cut and 37.1% raised, against 26 days, 17.6%
and 37.1%.

I copied the staging files to `/data1/apartments/site/deals` at 11:50 PM ET on Nov 17. The
Deals page now reads `drift-building-bedtext-b0-market-f288a423-heldbed-m`. The earlier
files from n9 are in `/data1/apartments/tmp/po-deals-live-n9-backup`. The flagged model has
no fit on the latest split, so the page's sentence on held-out ads is absent until one is
run.

```sh
python -m rentfrontier.drift_deals publish drift-building-bedtext-b0-market-f288a423-heldbed-m \
  --out /data1/apartments/tmp/po-deals-heldbed \
  --registry /data1/apartments/external/registry/20261110-f1fc080-extend/registry.parquet \
  --backtest drift-building-bedtext-b0-market-f288a423-heldbed-j \
  --texts /data1/apartments/tmp/overhaul/texts-m6.parquet
```
