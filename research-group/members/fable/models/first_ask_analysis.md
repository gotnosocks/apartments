# Post-fit analysis freeze for the first-ask floor fit

Run: `building-zones-floor-b0-latest-6b5a5b4a-dense-firstask-w1000`, against the base
`building-zones-floor-b0-latest-6b5a5b4a-dense-w1000`. Frozen on 2026-10-23 before the run
starts (queued after conference fit 8). The dataset is the coordinator's PR #1270 version with
the 23-row grid-start rule: 1,733,940 rows swapped, 162,546 keeping the latest ask.

## Residual spread (the q90-q10 gate)

q90-q10 means the interquantile range of **observed held-out log residuals**: for each common
held-out ad with a first ask (189,649 held-out ads, restricted to those with a first ask), the
residual is the log of the response the run was fit to (first ask in the first-ask run, latest
ask in the base) minus the posterior-mean log prediction across the 200 thinned draws at the
response's own date. The ratio compares the first-ask run's range to the base run's range on
the same ads. The posterior-predictive spread (draw-level predictive quantiles) goes in the
report as a secondary number, not as the gate. Both runs are scored on the identical ad set.

## Primary slope

OLS of the first-to-last log change on the first-ask residual, common held-out ads with a first
ask, unchanged ads included, year-month residualized, building-clustered SE. Reported three
ways, per opus's request: with the 3-day typo exclusion (frozen primary), without it, and the
count the exclusion drops. If the dropped count is under 0.5% of the sample, the two slopes are
expected to agree within 0.02.

## Instrument

Lagged past-only peer instrument built from other units' first-ask residuals, as in
`members/fable/checks/reaction_iv_lagged.py`, predicted -0.20 to -0.50.

## Kill conditions (unchanged)

Joint: sigma ratio under 1.01 in every bedroom group and nu within 0.05 of the base and the
q90-q10 ratio under 1.02. Slope kill: primary OLS above -0.10.
