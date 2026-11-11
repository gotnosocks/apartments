# Asks from before the off-market day (2026-11-11)

During the outlier sprint (`docs/notes/outlier-sprint-2026-11-11.md`) I read the 300 ads
furthest from the served model, `drift-building-b0-latest-67d14e17-b9`. Of the 22 asks the
readers flagged, 8 came from a price change dated on the day the ad closed: an ad runs for
weeks at $2,999, goes into contract at $2,999, and shows $4,000 on the day it leaves the
market. The pipeline keeps a change on the off-market day when it stays within a factor of
2 of the ask before it (`ads.kept_changes`, as `latest-ask-v9` does). Ben's definition of the
closing price is the last ask before the listing goes off the market.

## Free checks on the served fit

I compared, for every listing in the pipeline database, the last change kept now with the
last change dated before the off-market day (`PIPELINE_STALE_DAYS=-1`, which gives
`latest-ask-v10`), and joined both to the served fit's diagnostics
(`/data1/apartments/site/diagnostics/ads.parquet`, 195,423 ads).

1. 9,748 of the diagnostics ads (5.0%) take a change dated on or after their off-market day.
   76% of those changes are raises, and the median is +4.9%.
2. Those ads carry 7.0% of the squared gaps. Their mean gap is +0.020, against -0.004 overall.
3. The gap rises with the closing change: a slope of 0.37 on the log of the change. Ads whose
   closing change raised the price 15% to 40% sit 8.7% over the model on average (1,155 ads),
   and those raised over 40% sit 15% over it (65 ads).

So the model reads part of a closing raise as the apartment's level and the rest as noise.

## The change

`rentfrontier.b0closing` writes a copy of the served dataset in which a row priced at its
listing's last kept change takes the last change dated before the off-market day instead. It
reads the records file of the dataset's own pipeline build, so no other ad, field or row
changes. The copy is `/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closing`.

The build read all 1,896,471 listings from the records file in 4 minutes at a 2.1 GB peak. It
changed 104,330 rows. In 72% of them the closing change was a raise, and the median change
dropped from the target is +4.6%. On the latest split, 10,943 of the 189,647 held-out ads
(5.8%) change, with a median of +3.6%. Both datasets hold out the same ads, since the split
reads only the unit, the date and the audit id.

The fit is otherwise b9: the latest split of `drift-building` at the served commit's model,
fit-only, as two H100 containers of 2 chains, `2 500 9000 40 --seed S --no-loo --no-heldout`
with seeds 1 and 2. It changes the target of the changed rows, so I compare it with b9's
first four chains (`...-67d14e17-b9ab`, as the doorman fit was compared) on the held-out
ads whose target both datasets share, and report the changed held-out ads separately.

## Predictions (written before launch)

1. The pool passes the gate (70%).
2. The noise's degrees of freedom `nu` rise from 1.69 to between 1.72 and 1.95, since fewer
   ads sit far from their unit (55%).
3. Each bedroom group's `sigma` moves by under 5% (65%).
4. On the shared held-out ads, elpd gains over b9ab (60%), by more than 2 combined SE (30%).
5. On the shared held-out ads, the median absolute error of the predictive median and the 80%
   coverage each move by under 0.001 and 0.003 (70%).
6. On the changed held-out ads, the predictive median sits closer to the new target than b9's
   sits to the old one (65%).
7. $7 to $8 for the two containers.

If the pool passes and wins on the shared rows, the next step is a pipeline change: set
`PIPELINE_STALE_DAYS=-1` for production builds and refit the market and backtest datasets
so Deals can switch.
