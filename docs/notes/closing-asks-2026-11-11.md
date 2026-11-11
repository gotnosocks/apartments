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
dropped from the target is +4.6%. Each changed row takes the day of its new
change, or its own day for the 7,537 rows whose new change came before it, as `b0data` dates
a `latest` ask. On the latest split, 10,943 of the 189,647 held-out ads
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

## As launched

Two H100 containers from master `5f766394` on the closing dataset, seeds 1 and 2, launched
at 14:55 and 15:03 ET: `drift-building-b0-latest-5f766394-c1a` and `-c1b`.

## Results (scored 2026-11-11 16:05 ET)

The containers ran 51 and 50 minutes and cost $7.37 by the launcher's estimate. I pooled
them as `drift-building-b0-latest-5f766394-c1` (4 chains of 3,400 draws, 85 kept) and scored
it with `drift_score`. The pool misses the gate on split R-hat alone, on the three
hyperparameters of the unit walk (`drift.HYP`): `drift_tau` 1.0114, `unit_sd` 1.0111 and
`drift_sd` 1.0104, over the limit of 1.01. Every bulk ESS clears 400; the least is 740, on
`drift_tau`. Every coefficient and the other scalars pass.

So c1 cannot be served. Its scores still say whether the closing ask helps. I compared it
with b9's first four chains (b9ab), clustering the SE by building:

| held-out ads | n | | b9ab | c1 |
|---|---:|---|---:|---:|
| target unchanged | 178,704 | elpd | 219,006.5 | 219,596.0 |
| | | c1 minus b9ab | | +589.5, SE 107.7 |
| | | median abs error | 0.04044 | 0.04043 |
| | | coverage 50 / 80 / 90 / 95 | .528 / .810 / .903 / .953 | .527 / .810 / .903 / .952 |
| target changed | 10,943 | median abs error, each on its own target | 0.0449 | 0.0438 |
| | | coverage 50 / 80 / 90 / 95 | .474 / .756 / .863 / .928 | .486 / .772 / .879 / .937 |

On the changed ads b9ab's median sits 0.0538 from the new target. The elpd of the changed
ads is not comparable between the two, since their targets differ.

The scalars move little. `nu` rises from 1.692 to 1.720, the four `sigma` rise by 0.3% to
2.2%, `drift_tau` goes from 9.56 to 9.61.

The predictions, scored:

1. Gate passes: **miss** (R-hat 1.0104 to 1.0114 on the walk's three hyperparameters).
2. `nu` between 1.72 and 1.95: **hit**, at the bottom edge (1.720).
3. Each `sigma` moves by under 5%: **hit** (at most 2.2%).
4. elpd gains on the shared ads: **hit**. By more than 2 SE: **hit** (5.5 SE).
5. Error and 80% coverage move by under 0.001 and 0.003: **hit** (0.00001 and 0.0000).
6. On the changed ads the median sits closer to the new target than b9's does to the old:
   **hit** (0.0438 against 0.0449).
7. $7 to $8: **hit** ($7.37).

### The gate miss

The rule for a missed gate is to look at the data, then the model, then the sampler.

- Data: the change touches the targets of 5.5% of rows, and the three quantities are the
  walk's hyperparameters, not a row's. They move together, since the sampler draws them as a
  block. `drift_tau`'s posterior median moves by 0.5%, and its traces wander the way b9ab's
  do. In c1 the first chain's halves average 9.53 and 9.76. In b9ab the
  third chain's average 9.73 and 9.59.
- Model: `drift_tau` is the slowest quantity in every drift-building fit since b6. It is
  the least-ESS quantity in b9 (1,344 over 6 chains) and b9ab (834 over 4).
- Sampler: a 2-chain container's `drift_tau` R-hat has run from 1.000 to 1.017 (b9a 1.0049,
  b9b 1.0062, b9c 0.9999, b6c 1.0172, j6b 1.0141; here c1a 1.0171 and c1b 1.0026). The
  misses all come from c1a: on its own it has `unit_sd` at 1.0156 and `drift_sd` at 1.0140,
  while c1b has all three under 1.004. Four
  chains of this length sit close to the limit. b9 and the other served fits used 6 chains,
  and the doorman fit's 4 chains came from the night's budget.

I read this as the 4-chain design being too thin for the walk's hyperparameters. It is not a defect of the
closing data. Adding a third container to c1 would rerun a failed fit, so c1 stays failed.

## The slow walk hyperparameters, looked at again (2026-11-11 17:30 ET)

Ben asked for the gate miss to be looked into before any refit, so I read c1's and b9's
saved traces (3,400 draws per chain) on thelio.

- Data. The closing rewrite changes no row's unit and adds no step to a unit's path. Pairs
  of a unit's ads on the same day fall from 1,457 to 1,165, steps of more than a factor of 2
  go from 2,802 to 2,805, and the sd of a unit's step goes from 0.171 to 0.173.
- Model. `drift_tau`, `unit_sd` and `drift_sd` lie on a ridge: within every chain of c1
  and b9, `drift_tau` correlates at -0.97 with `unit_sd` and at +0.97 with `drift_sd`, and
  `unit_sd` with `drift_sd` at -0.98 to -0.99. The ridge is the split of a unit's variation
  between its lasting level and its walk, which the data pins only in sum. `drift_tau` also
  correlates at +0.3 with `nu` and +0.25 to +0.46 with the `sigma`s, and at 0.0 with every
  building and zone scale. The chains of c1 and b9 mix alike, with integrated
  autocorrelation times of 10 to 20 draws for all three quantities.
- Sampler. With that mixing a chain's mean of `drift_tau` has a Monte Carlo error of about
  0.04. c1's four chain means (9.64, 9.59, 9.72, 9.68) spread by 0.057 and b9ab's (9.60,
  9.63, 9.66, 9.63) by 0.025. Every pair of b9's containers gives R-hat under 1.006 on the
  three quantities (b9ab 1.0051, b9bc 1.0041, b9ac 1.0024), against c1's 1.0114.

c1's miss is consistent with the luck of four chains on a ridge they cross slowly. The
data show no sign of causing it, and the same design passed for b9 by a margin of about 0.005. A
reparameterization that samples the ridge's direction apart from its width (a unit's total
variance and the walk's share of it, with `drift_tau`) would cut the autocorrelation and
make a 4-chain fit's gate depend less on seeds. That is a change to the model, for a fit
of its own.

## The off-day changes, causally (2026-11-11 17:30 ET)

Ben asked why the price an ad takes on the day it leaves the market should be dropped. A
fit gain does not answer that, so I looked at the process behind the change, with free
reads only. 104,330 rows change. 72% of the changes are raises (median +4.6%), 95% of
listings have a single change on the off day, and that change is dated on the off day
itself in nearly every case. The ask before it is a median 7 days old. So nearly all of
these prices appear on an ad for less than a day, as it comes down.

The status events within 3 days of the off day:

| status | share | raises | median change |
|---|---:|---:|---:|
| rented | 52.8% | 79% | +6.3% |
| no longer available | 28.6% | 54% | +0.2% |
| delisted | 19.5% | 79% | +7.7% |

The raises follow the market, which points at lease terms rather than at typing. In
2020 and 2021, with concessions everywhere, 82% to 84% are raises with a median of +11%.
In 2014 to 2016 about half are. The off-day price is a multiple of $50 while the ask
before it is not in 23.6% of changes, and the reverse holds in 5.9%. That pattern fits a
lister replacing a computed net rent with the lease's round gross rent.

I tested that reading with exact arithmetic. If the ask before is a net effective rent of
a gross rent G with m months free on an L month lease, it equals G(L - m)/L. Searching L
from 12 to 24 and m up to L/3, 28.3% of raises match to within $1. Prices jittered at
random match 11.5% of the time, so about 17% of raises (11,600 rows) are net to gross
conversions beyond chance. The match rate runs 0.33 to 0.43 in 2014 to 2020 and falls to
0.19 in 2026, with concessions. The records hold almost nothing structured about this:
`rentedPrice` is set on 58 rows and `netEffectiveRent` on 8, and the record's price
equals the off-day price in 98.4% of rows. Concession wording ("net effective", "months
free", "gross") appears in 5% of the raises' ads.

When the unit is listed again, its next ad asks near the off-day price: regressing the
next ask on the two prices gives the off-day price a weight of 0.90 for raises, 1.08 for
raises with an arithmetic match and 0.42 for cuts. These weights are not adjusted for the
market's rise between ads, which favors the higher price of a raise, so I read them only
as showing that the off-day price is a real number for the unit and not noise.

A Sonnet reader judged 100 changes, drawn in six strata by direction, size and arithmetic
match, from the unit's history, the building's other units and the ad text. Weighted by
stratum size (90,843 rows), the readers' mechanisms:

| mechanism | share | raises | cuts | renter paid the off-day price |
|---|---:|---:|---:|---:|
| net to gross | 40.9% | 39.1% | 1.8% | 14.3% |
| signed rent | 30.4% | 18.7% | 11.7% | 25.7% |
| ordinary change on the off day | 16.0% | 5.8% | 10.2% | 7.3% |
| artifact | 2.7% | 2.6% | 0.1% | 0.7% |
| relisting price | 2.6% | 2.5% | 0.1% | 1.2% |
| typo | 0.1% | | 0.1% | 0.1% |
| unclear | 7.4% | 7.2% | 0.2% | |

Most of the calls are low or medium confidence. The readers called only 7 net to gross
cases high, and many rest on the ratio alone. The signed rents are mostly rented ads
that move by a negotiated amount on the rented day, like 4203881, listed at $6,850 and
rented the next day at $5,850 while the building's other 1BRs asked $6,070 to $7,600.

### Conclusion

The rewrite should stand, for every mechanism. The model's target is the ask, the last
price a renter could have answered before the ad came down. In about 71% of the changes
the off-day price is a lease term, either the gross rent behind a net ask or the rent
signed after negotiation, and no renter saw it as an ask. Another 16% are asks entered on
the day the ad came down, and 5% are artifacts, relisting prices and typos. Limiting the
rewrite to the exact net to gross matches would keep the signed rents, which are not
asks, and the arithmetic catches only 28% of raises anyway.

The signed rents are the only data the project holds on rents people actually pay, in
about 30% of these rows. I would keep the off-day price beside the closing ask in the
closing dataset, as data for a study of paid rents against asks, but not as the target.

## The 6-chain fit (c2), not launched

On 2026-11-11 Ben stopped c2 before its first container and ruled out Modal fits for the
rest of the outlier sprint. c2 and the predictions below wait for after the sprint
(`docs/TODO.md`).

c2 repeats the fit with b9's design: three containers of 2 chains, seeds 11, 12 and 13,
pooled as `drift-building-b0-latest-5f766394-c2`, and compared with all 6 of b9's chains.
The budget pays for a container about every 10 hours, so I launch them one at a time as the
balance covers each. The pool is fixed at three parts.

Predictions (written before launch):

1. The pool passes the gate (80%).
2. `nu` between 1.70 and 1.75 (75%).
3. On the 178,704 held-out ads with an unchanged target, elpd gains over b9 by more than 2
   SE (80%), and by between 400 and 800 (60%).
4. On those ads the median abs error and the 80% coverage move by under 0.0005 and 0.003
   (80%).
5. On the 10,943 changed ads, the 80% coverage lies between 0.76 and 0.79 (70%).
6. $11 to $12 for the three containers.
