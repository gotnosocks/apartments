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
