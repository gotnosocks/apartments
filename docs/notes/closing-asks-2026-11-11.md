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
data show no sign of causing it, and the same design passed for b9 by a margin of about 0.005. I
proposed here a reparameterization that samples the ridge's direction apart from its width
(a unit's total variance and the walk's share of it, with `drift_tau`). The second look
below withdraws it: the scale step already slices along the ridge.

## The gate miss, second look (2026-11-11 19:00 ET)

Ben asked for the miss to be checked against the data and the sampler a second time, with
the question of which units decide where a chain lies on the ridge. Work files are under
`/data1/apartments/tmp/outlier-sprint/s2/B1`, `B2` and `B3`; each has a `results.md` or
an `.out` log with the tables behind the numbers here.

**The ridge.** In the logs of the three scales, the first principal axis is (-0.199,
+0.323, +0.925) for `unit_sd`, `drift_sd` and `drift_tau`, and it carries 99.2% of their
variance. The sd along it is 0.0622 in c1 and 0.0637 in b9, and the two fits' axes lie
0.21 degrees apart. Its ends are `drift_tau` of 8.8 and 10.6 years. Along it
`unit_sd² + drift_sd²` varies by 0.27% and `drift_sd²/drift_tau` by 2.0%: the data fix a
unit's total variance and the walk's rate of change per year, and they say little about
how long the walk takes to forget, since the longest unit history is 12.9 years.

**Data: which units decide the ridge position.** I rebuilt each unit's likelihood at the
two ends of the ridge from the saved posterior means (`B1/a3.py`), for the 321,060 units
with two or more training ads, and took the difference a unit makes to its building's
likelihood.

- The 100 units with the largest differences hold 0.55% of the absolute total and 4.3% of
  the squared total. Data simulated from a Gaussian model on the same rows give 0.6% and
  4.2%, so the real ads are no more concentrated than error-free ads would be.
- Units with a likely record error (a step over a factor of 2, bedroom counts differing
  between ads, or asks alternating between two levels) are 3.5% of these units. They hold
  4.3% of the absolute total and 5.7% of the squared total with `sigma` held, and 6.6% and
  10.1% when `sigma` moves along the ridge with the scales. The 1,947 units with a step
  over a factor of 2 hold about 1%.
- The Student-t weights are the reason. At a step over a factor of 2, the ad with the
  smaller weight has a median weight of 0.039, and with Gaussian noise the error units
  would hold 77% of the squared total.
- Deleting both ads of every factor-2 step (3,957 ads) changes the difference between the
  ends by -0.9 with `sigma` held, and deleting as many ads at random changes it by -4.3.
- Held-out ads show no preference for either end. Regressing each held-out ad's log
  density on the draw's ridge coordinate over c1's 340 kept draws, the ends differ by
  -42 elpd with a standard error of 68.
- The units with an ad changed by the closing rewrite are 13.5% of these units and hold
  17% to 18% of the absolute total, in line with their having more ads. The
  reconstruction on b9's ads gives the same concentration.

This reconstruction has limits, and the statements above rest on magnitudes alone. Its
signed sums fail two checks: summed over all units the ends differ by +1,263 where the
posterior implies about 0, and it predicts the closing rewrite to move the ridge position
by -2.4 posterior sd where the two fits differ by +0.08. The cause is the residual: the
design matrix for training rows could not be rebuilt in memory, so the ad-level columns
are missing and the residuals carry about 9% more noise variance than the fit's `sigma`.
Units with a single training ad and the channel through a unit's level relative to its
building are not measured at all.

**Sampler: c1 against b9, chain by chain.** (`B2/b2.out`, `B2/sim.out`.)

- The chains mix alike. The mean integrated autocorrelation time of the ridge coordinate
  is 15.6 sweeps in c1's chains and 15.5 in b9's.
- The scale step's slice directions are no worse in c1. At the warmup's second setting of
  the directions (sweep 333) the smallest by-axis ratio is 0.180 in c1a and 0.285 in c1b,
  against 0.202, 0.190 and 0.231 in b9a, b9b and b9c.
- The miss comes from c1a's first chain, whose halves average -0.24 and +0.17 posterior
  sd on the ridge. Split R-hat on the ridge coordinate is 1.0111 for c1, 1.0165 for c1a,
  1.0024 for c1b and 1.0038 for b9.
- Simulated chains with b9's autocorrelation exceed 1.01 in 2.1% to 2.8% of 4-chain fits
  and in 0.55% to 0.74% of 6-chain fits, while the expected R-hat stays near 1.004 for
  both. With c1's own slightly longer autocorrelation the 4-chain share is 4% to 6%. A
  value as large as c1's has a chance of 1.1% to 1.6% under b9's mixing and 2% to 4%
  under c1's.

**Model: what slows the ridge.** (`B3/pin.out`.) The ridge coordinate is unrelated to the
248 coefficients (the best linear combination of them explains none of it out of chain,
R² -0.02 to -0.07), to the trend, to the surface and to every building scale (|r| under
0.04). It correlates with `nu` at +0.3 and with the four `sigma`s at +0.25 to +0.42, and
those are drawn together with it in the scale step. By elimination the slow part is the
rows' mixing scales, which the scale step holds fixed: the split between a noisy ad and a
moving unit is renegotiated only as the mixing scales are redrawn around the new scales.
I did not confirm this with a run of the sampler.

**Verdict.** c1's miss is the 4-chain layout meeting a tail event of roughly 1 in 25 to 1
in 90, on a target no harder than b9's. Record errors do not set the ridge position, since
the t weights remove them. A single fit cannot exclude a small real difference between
the targets, and a difference large enough to show in a per-chain statistic is excluded.

- The reparameterization is withdrawn. The warmup already sets the scale step's
  directions from the draws' covariance and the curvature of the step's own density, so
  the step slices along the ridge, and a change of coordinates would leave the mixing
  scales as they are.
- Gate fits keep 6 chains. This is cheap and lowers the chance of a miss on an unchanged
  target by a factor of about 4.
- A sampler candidate for after the sprint: a second pass of steps 6, 7 and 3 of the
  sweep (unit levels, noise with the mixing scales, and the scale step) within each
  sweep. Its prediction and the pilot it needs first are in `docs/TODO.md`.

Against the first look: its conclusion stands. Its statement that more chains do not lower
R-hat holds for the expected value and not for the chance of exceeding 1.01, and its
proposed remedy is withdrawn.

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

The share of raises moves with the concession market, so I read most of them as lease
terms and few as typing. In 2020 and 2021, when most new leases came with free months,
82% to 84% of changes are raises, with a median of +11%. In 2014 to 2016 about half are. The off-day price is a multiple of $50 while the ask
before it is not in 23.6% of changes, and the reverse holds in 5.9%. That pattern fits a
lister replacing a computed net rent with the lease's round gross rent.

I tested that reading with exact arithmetic. If the ask before is a net effective rent of
a gross rent G with m months free on an L month lease, it equals G(L - m)/L. I tried L of
12 to 16, 18 and 24 months with m from 0.5 to 4 months below L/3. Of the 69,016 raises
over 0.5%, 28.3% match to within $1. Prices jittered at
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
match, from the unit's history, the building's other units and the ad text. The strata
cover the 90,843 changes of more than 0.5%. I left out the other 13,487 (5,680 raises and
7,807 cuts), since they barely move the target. Weighted by stratum size, the readers'
mechanisms and the share of rows where they judged that the renter faced the off-day price:

| mechanism | share | raises | cuts | renter faced the off-day price |
|---|---:|---:|---:|---:|
| net to gross | 40.9% | 39.1% | 1.8% | 14.3% |
| signed rent | 30.4% | 18.7% | 11.7% | 25.7% |
| ordinary change on the off day | 16.0% | 5.8% | 10.2% | 7.3% |
| recording error | 2.7% | 2.6% | 0.1% | 0.7% |
| relisting price | 2.6% | 2.5% | 0.1% | 1.2% |
| typo | 0.1% | | 0.1% | 0.1% |
| unclear | 7.4% | 7.2% | 0.2% | |

Of the 100 calls, 58 are low confidence, and the only high ones are 7 net to gross
cases. Many of the other net to gross calls rest on the ratio alone. The signed rents are mostly rented ads
that move by a negotiated amount on the rented day, like 4203881, listed at $6,850 and
rented the next day at $5,850 while the building's other 1BRs asked $6,070 to $7,600.

### Conclusion

The second look at the end of this note narrows this conclusion to the raises typed as the
ad closed.

The rewrite should stand, for every mechanism. The model's target is the ask: the last
price on the ad while a renter could still answer it. On the readers' calls, about 71% of
these off-day prices are lease terms, either the gross rent behind a net ask or a rent
signed after negotiation. The readers often judged that the renter faced that price
under the lease, in 49% of the weighted rows, but it stood on the ad for less than a day
as the ad came down, so almost no renter could have answered it as an ask. Another 16%
are asks entered on that same last day, and 5% are recording errors, relisting prices and
typos. The calls are uncertain: 58 of 100 are low confidence and 7.4% are unclear. The
conclusion holds without the mechanism calls, because it rests on the timing more than on the
mechanism. Limiting the rewrite to the exact net to gross matches would keep the signed
rents, which are not asks either, and the arithmetic finds only about 17% of raises
beyond chance.

On the readers' calls, the off-day price is a signed rent in about 30% of the 90,843
rows. Signed rents are the only record in the project of what renters pay. I would keep
the off-day price beside the closing ask in the closing dataset, as data for a study of
paid rents against asks, but not as the target.

## The 6-chain fit (c2), not launched

On 2026-11-11 Ben stopped c2 before its first container and ruled out Modal fits for the
rest of the outlier sprint. The second look at the end of this note narrows the rewrite, and
its fit c3 takes c2's place in `docs/TODO.md`. c2's design and predictions stay here as
written.

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

## Second look: narrow the rewrite (2026-11-11 18:30 ET)

Ben restarted the sprint's session and asked for the rewrite to be judged again, with less
weight on the readers' mechanism calls. I worked from the records' own event times, which the
first look had read only to the day, and from tests with no reader in them. Scripts and
tables are in `/data1/apartments/tmp/outlier-sprint/s2/A/`.

Verdict: narrow. The pre-off ask replaces the off-day price only where the off-day change is
a raise typed as the ad closed: no earlier than 5 minutes before the off-market status
event, or after it. Such a row takes the price standing on the ad before the raise. That
is 59,026 of the 104,330 rows. Cuts, and raises standing on the ad for more than 5 minutes
before the status event, go back to the off-day price. c1 was never served, so the served
data does not change.

### The basis of the two prices

I followed the six listings Ben pointed at (3138211, 4891129, 4908976, 5069010, 5115216,
5140994) through `ads.answers`, `analysis.concessions`, `analysis.latest_ask` and
`analysis.ledger_rows`. `analysis.latest_ask` holds gross prices and `analysis.ledger_rows`
the price net of free months, and I found no path netting a price twice.

The rewrite's second condition compares a row's ask with the raw last change. A row priced
net of recorded free months fails that comparison, so the rewrite left all 160,786 such rows
alone. It repriced 3 to 6 rows with terms, depending on the match tolerance; in 3133311 c1
trained on a gross $3,600 where the off-day $3,000 was the net rent. So nearly every row
the rewrite changed is an ad with no free months in its record.

The rows with recorded free months give a view of the mechanism. 4,471 of them have an
off-day change, and 2,624 of those are raises with a median of +8.8%. I netted each raised
price by the row's own recorded factor and compared it with the pre-off ask. The median
log difference is 0.000, the netted price falls within 0.2% of the pre-off ask in 12.7% of
rows and within 5% in 54%, and the quartiles of the factor implied by the raise (0.846,
0.916, 0.952) track the recorded factor's (0.846, 0.917, 0.923). In these rows the raise is
about the size of the concession: the ad ran at the net rent and took the gross rent on its
last day. The pipeline nets that gross price back, so those rows are already priced near
their pre-off ask.

### When the off-day price was typed

Each record's `priceChanges` and `statusChanges` carry times to the second. For the 104,324
repriced rows with an off-market status event on the off day, I took the first price change
on or after that day and measured it against the first off-market status event:

| first off-day price change | raises | cuts | under 0.5% either way |
|---|---:|---:|---:|
| same action: from 5 minutes before the status event to 1 minute after | 53,230 | 7,540 | 1,742 |
| 5 minutes to 1 hour before | 2,747 | 1,699 | 369 |
| more than 1 hour before | 10,157 | 10,616 | 10,934 |
| more than 1 minute after | 2,880 | 1,970 | 440 |

77% of the raises and 35% of the cuts were typed in the same action as the status. 12,423
rows have a status event stamped with the listing's creation time of day, as system events
like expiry are; I class them by the same rule (1,601 of them are same-action).

The table times each listing's first off-day change, and 6,007 listings have more than one.
The rule times the change giving the row's ask, the last of them, and compares it with the
price standing 5 minutes before the status event. The 59,026 rows it changes are:

- 57,633 whose first off-day change falls within 5 minutes before the status event or after
  it: the 53,230 and 2,880 raises of the table and 1,523 of the changes under 0.5%. They
  take the last ask before the off-market day.
- 1,393 whose lister changed the price earlier on the off-market day and then raised it as
  the ad closed. In 3257181 the ask of $2,150 was cut to $1,995 that morning and raised to
  $2,400 13 seconds before the status event. 1,388 of these rows take the earlier off-day
  price ($1,995 here), and 5 take the last ask before the day.

The first look said nearly all of these prices stood for less than a day. To the second,
31,707 of them stood on the ad for more than an hour before it closed, and those are asks a
renter could answer.

The raises carry marks of a net rent replaced by a gross one, in every timing class. Among
same-action raises the ratio of the two prices is within 0.12% of 12/11 in 4.9% of rows,
of 12/10 in 2.5% and of 14/12 in 1.6%, against 0.4% to 1.5% at ratios between them, and
the price moves from a number off the $50 grid to a multiple of $50 in 28.7% of rows
against 4.6% the other way. The cuts carry neither mark: 0.7% at 11/12 against 0.5% beside
it, and 6.4% against 5.3% on the $50 grid. The record's `rentedPrice` is set on 59 of the
104,330 rows, so it cannot say which price was agreed.

### The unit's other ads

For a test with no model in it, I compared each repriced ad with the same unit's next ad and previous
ad, where that other ad is one the rewrite left alone and lies 60 days to 3 years away. I
deflated the pair by an index of month effects fit on 870,252 pairs of consecutive
unchanged ads of a unit, and again by the building's own path, as the median deflated
change of other units' unchanged pairs in the same building within 6 months at both ends
(at least 5 such pairs; about a third of the ads have them). Listings repriced daily by a
feed (8 or more price changes) are left out. Unchanged pairs differ by a median 0.049 after
deflation.

| off-day change | pairs (next / previous) | other ad minus pre-off ask | other ad minus off-day price | pre-off ask nearer (next / previous) | same, building path removed |
|---|---:|---:|---:|---:|---:|
| raise, same action | 11,211 / 13,692 | +0.037 / +0.028 | -0.086 / -0.084 | 59% / 61% | 59% / 60% |
| raise, 5 min to 1 h before | 733 / 661 | +0.048 / +0.036 | -0.061 / -0.073 | 51% / 57% | 43% / 49% |
| raise, over 1 h before | 2,228 / 2,257 | +0.029 / +0.023 | -0.059 / -0.053 | 54% / 53% | 51% / 52% |
| raise, after the status | 719 / 803 | +0.035 / +0.028 | -0.062 / -0.057 | 53% / 52% | 53% / 58% |
| cut, same action | 1,042 / 1,507 | -0.084 / -0.079 | -0.030 / -0.032 | 34% / 34% | 40% / 41% |
| cut, 5 min to 1 h before | 394 / 480 | -0.038 / -0.042 | +0.023 / +0.021 | 43% / 51% | 40% / 51% |
| cut, over 1 h before | 2,329 / 2,522 | -0.035 / -0.029 | +0.010 / +0.013 | 44% / 49% | 46% / 46% |
| cut, after the status | 650 / 538 | -0.045 / -0.027 | +0.005 / +0.027 | 42% / 55% | 43% / 46% |

In both directions the lower of the two prices lies nearer the unit's other ads. After a
raise the other ads sit about a third of the way from the pre-off ask to the off-day
price, and after a cut they sit at the cut price or below it. For same-action raises the
pre-off ask is nearer in every era, most clearly in 2020 and 2021 (59% to 69%, with a
median raise of 14%) and least in 2022 and before 2020 (51% to 57%), and more clearly the
larger the raise (54% to 56% under 5%, 63% to 67% over 15%). The raises standing more than
5 minutes before the status event are close to even.

The same split shows on the model's scale. On the held-out repriced ads of units and
buildings with at most 5% of training rows repriced, I regressed the pre-off ask's gap to
b9's median on the change. A slope of 0 puts the pre-off ask on the model's scale and -1
puts the off-day price there. Same-action raises give -0.20 to -0.25, and cuts give -0.7 to
-1.

### Where c1's gain comes from

c1's +589.5 elpd on the 178,704 held-out ads with an unchanged target, split by the
repriced training ads of each ad's unit (SE clustered by building):

| unit's training ads | held-out ads | c1 minus b9ab | per ad |
|---|---:|---:|---:|
| a repriced raise | 9,373 | +597.2, SE 63 | +0.064 |
| a repriced cut | 3,322 | -110.1, SE 21.5 | -0.033 |
| both | | +1.9 | |
| none repriced | | +100.6, SE 61 | |

For units with a single repriced training ad, by the timing of its change:

| change | held-out ads | c1 minus b9ab | t |
|---|---:|---:|---:|
| raise, same action | 5,705 | +466.5 | 9.5 |
| raise, 5 min to 1 h before | 410 | -3.2 | -0.3 |
| raise, over 1 h before | 1,544 | +10.9 | 0.5 |
| raise, after the status | 483 | -5.1 | -0.4 |
| cut, same action | 575 | -12.6 | -1.3 |
| cut, 5 min to 1 h before | 307 | -25.1 | -2.8 |
| cut, over 1 h before | 1,815 | -36.4 | -2.5 |
| cut, after the status | 491 | -29.5 | -3.9 |

Among these units the gain comes from the same-action raises, and it grows with the raise,
from +0.007 per ad for raises under 2% (t 0.8) to +0.141 for raises over 20%. Repricing a
cut costs elpd in every timing class. Units with several repriced training ads add about
128, which I did not split by timing. The gain is spread over 35,523 buildings, and the
largest single building gives +23.7.

The 100.6 of units with no repriced training ad is close to the sum of a gain in buildings
with a repriced row and a loss in buildings with none (+303.9 and -205.7 give +98.2; the
two scripts class a few units differently, and I did not reconcile the 2.4). In the
buildings with a repriced row
(106,887 held-out ads of unrepriced units, +303.9), split by the building's repriced
training rows (`s2/A/a9.py`):

| building's repriced training rows | held-out ads | c1 minus b9ab | SE |
|---|---:|---:|---:|
| same-action raises only | 21,433 | +142.5 | 34.0 |
| same-action raises and others | 53,059 | +191.8 | 55.2 |
| earlier raises only | 4,237 | -7.7 | 6.8 |
| cuts only | 20,073 | -24.1 | 12.4 |
| others, no same-action raise | 8,085 | +1.4 | 10.9 |

So the neighbors' gain also sits in the buildings with same-action raises.

In the buildings with no repriced row (57,087 of those held-out ads) c1 loses 205.7 elpd,
175 of it in ads from 2020 to 2022, with interval widths and coverage nearly unchanged
(80% coverage 0.819 against 0.815). My first reading was that ads in those years with a
concession only in their text still carry a gross ask. A split of the 2020 to 2022 ads by
concession (`s2/A/a9b.py`) refutes it:

| concession on the held-out ad | ads | c1 minus b9ab | SE |
|---|---:|---:|---:|
| none in the record or the text | 13,127 | -159.0 | 11.6 |
| free months in the record | 2,188 | -18.6 | 4.7 |
| in the text only | 296 | +2.6 | 1.5 |

The loss falls on ads with no concession, and it is largest where the building has little
history of its own: -0.029 per ad in buildings with up to 5 training rows, -0.015 with 6
to 20, -0.005 with 21 to 100 and -0.003 above that. Their asks sit higher over c1's median
than over b9's (+0.0054 against +0.0020 in 2020, -0.0034 against -0.0051 in 2021; these
means come from `a9.py`'s group of 15,185 ads with no concession in the text, which
includes the 2,188 with recorded terms). My
account, not tested further: the rewrite lowered the 2020 and 2021 asks of the buildings
with closing raises to their net rents, their areas' time paths came down with them, and a
building with few ads of its own borrows that path, while its asks, with no concession to
net, fell less in those years. If so the loss is a cost of the rewrite, and it measures a
real difference between the two kinds of building in those years, one the model has no
term for. A concession building indicator crossed with the year is a candidate term for it.

### The causal account

Ben's target is the closing price, read from the last ask before the ad leaves the market.

- A raise typed as the ad closes. The lister marks the ad rented or delisted and in the
  same edit replaces the price. The size of the raise is that of a concession in part of
  the rows: the 12/11, 12/10 and 14/12 ratios hold 9% of them, about 6 points over the
  rate at ratios between those, the gross figures are round, the raises peak in 2020 and
  2021, and in the rows with recorded terms the raise nets back to the pre-off ask. No
  renter could answer the new price, and the unit's other ads sit a third of the way from
  the old price to the new one. For the rows with a concession mark the pre-off ask is the
  net rent the renter was offered, on the basis the pipeline uses for every ad with
  recorded terms. The rest move on the timing alone: among the changed rows 5,363 are
  raises over 30% and 4,614 are under 2%, and c1 shows no gain for the small ones. A rent
  bid up over the ask and entered as the ad closes would look the same in the record, and
  the pre-off ask would still be the last ask a renter could answer. These rows take the
  price standing before the raise.
- A raise typed after the status event (2,880 rows) was entered on an ad already off the
  market, so it was never an ask either, and it carries the same ratio marks. The other-ad
  test leans the same way but weakly (52% to 58%), and c1 shows no gain on these units. I
  include these rows on the timing alone.
- A raise standing more than 5 minutes before the status event was the ask on the ad when
  it closed. The rule keeps 15,772 raises: 15,689 of this kind, and 83 typed as the ad
  closed at or below a price already standing that day. The ratio marks are as strong there as in the same-action raises,
  so some of these are the same net to gross switch made in two steps, but the other-ad
  test is even and c1 gains nothing on their units. They keep the off-day price. This is
  the weakest cell of the verdict.
- A cut. A cut standing for hours is the last ask (12,315 cuts stood more than 5 minutes).
  A cut typed in the same action or after it (9,510) was never an ask, but it carries no
  concession mark, the unit's other ads sit at the cut price or below it, and it is most
  plausibly the rent agreed after negotiation, entered as the ad closes. An agreed rent
  below the ask is nearer the closing price than the ask it replaced. Cuts keep the off-day
  price.
- Changes under 0.5% that are not raises keep the off-day price; they move no target by
  more than half a percent.

### What this contradicts in the first look

- The first conclusion kept the rewrite for all 104,330 rows. The gain it rested on comes
  from 51% of them, and repricing the cuts costs about 104 to 110 elpd on their units.
- The first look took the off-day prices to have stood for less than a day as the ad came
  down. 31,707 of them stood for more than an hour before the status event.
- The first look's next-ad regression gave the off-day price a weight of 0.90 after a
  raise, without deflating. After deflation the unit's other ads sit a third of the way
  from the pre-off ask to the off-day price.
- c1's loss of 206 elpd in buildings the rewrite left alone was not reported.

### Weak points and what would change the verdict

- I chose the timing and direction cells while reading the same held-out split a later fit
  will be scored on. The other-ad test does not use the model or the split, and it supports
  the direction split strongly and the timing split among raises weakly.
- The 5-minute margin is a judgment. Moving it to an hour moves 2,747 raises.
- The account of same-action cuts as agreed rents rests on the other ads and the absence
  of concession marks. No record of a paid rent backs it.
- I did not time the off-day changes of the 4,471 rows with recorded terms, since their
  netted price was never in question.
- 1,533 of the changed rows have a status event stamped with the listing's creation time
  of day, so their wait is measured against a system event. I counted 40 changed rows
  reopened on the off-market day after the status event and before the raise, 5 of them
  with the raised price then standing for more than 5 minutes, and kept no script for it.
  The reviewer of #1317 counted 43 to 45 such rows, 6 to 8 with a raise standing over 5
  minutes, and 5 more with no later off-market event.
- "Already off the market" rests on the first off-market status event alone. 2,158 changed
  rows were typed more than a day after it, in 823 of them another off-market event
  follows the raise by more than a day, and in 33 (32 from 2017) an ACTIVE event shares
  the timed event's second and a feed went on repricing the ad for weeks (2092530). In
  those rows the raised price may have been an ask.
- When the closing edits straddle midnight, the price the rule falls back on can itself
  have been typed within 5 minutes of the status event. One changed row is of this kind
  (5163209, moved to $6,245 where $4,900 stood) and 4 kept rows (4119158). The rule also
  matches a dropped change to a kept one by day and price, which would admit a dropped
  change equal to a kept one; no row is affected. Too few rows to rebuild the dataset for.
- The same unit's next ad does not separate the raises the rule keeps from the ones it
  reprices as sharply as the timing does. Among raises over 10%, the next ad keeps 31% to
  40% of a raise typed as the ad closed, 37% to 39% of one standing 5 minutes to 6 hours
  (n 248 and 475) and 60% of one standing 6 to 24 hours (n 110)
  (`s2/D3/kept.py`). Two such kept rows turned up in the large-unit reading: 1458253,
  whose $7,225 stood about 9 hours while the unit's new ads opened near $5,000, and
  3208045, whose $3,895 was typed 608 seconds before RENTED over $2,675. They stay,
  because a renter was offered those prices. I did not build the baseline this needs, the
  share a next ad keeps of a raise made in the middle of a listing.
- The account of c1's loss in the buildings it left alone is untested beyond the split by
  concession.
- The verdict would move toward the full rewrite if a fit on the narrowed dataset lost to
  c1 on the unchanged ads of units with a cut training ad, or if a source of paid rents
  showed the pre-off ask nearer the paid rent after a same-action cut. It would move toward
  reverting if such a source showed same-action raises to be rents bid up over the ask,
  which the 2022 cell (51% to 57%) leaves open for that year.

### The narrowed dataset and its fit (c3)

`rentfrontier.b0closingraise` writes the narrowed dataset from the served one:
`/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise`.
c3 is b9's design on it: three containers of 2 chains, seeds 11, 12 and 13, fit-only, pooled
and compared with all 6 of b9's chains. It replaces c2 and waits for the end of the sprint.

The build of 2026-11-11 took 4 minutes and changed 59,026 rows, with a median log raise of
0.087. It left 45,304 rows at their off-day price: 34,691 whose ask stood for more than 5
minutes before the status event, and 10,613 typed as the ad closed at or below the
standing price. Against the last ask before the off-market day, 29,532 of the rows left
alone are cuts and 15,772 are raises with a median of 0.029. A first build timed each
listing's first off-day change and changed 57,633 rows. The second build gives those rows
the same ask and day, which are the `-closing` dataset's, and adds the 1,393 rows above.
Every other row equals the served dataset's (`s2/A/closingraise_verify2.py`).

Predictions (written before launch):

1. The pool passes the gate (70%).
2. On the 178,704 held-out ads with a target unchanged in every dataset, elpd gains over b9
   by more than 2 SE (85%), and by between 550 and 850 (55%).
3. On the 3,322 of those ads whose unit has a training ad with an off-day cut, where c1 lost
   110.1, c3 lies within 45 elpd of b9 (70%).
4. On the ads whose unit has a single same-action raise among its training ads, c3 gains
   0.06 to 0.10 per ad over b9 (70%).
5. In the 57,087 ads of buildings c1's rewrite left alone, c3 still loses to b9, by between
   150 and 300 (60%). I first wrote 80 to 220, on the reading the concession split refuted,
   and revised it on 2026-11-11 before any launch. c3 moves the same closing raises down
   as c1 and leaves the cuts at their lower price. It also keeps the standing raises c1
   moved down, so its summed log moves are smaller than c1's: -1,697.7 against -1,786.8
   in 2020 and -1,621.8 against -1,638.6 in 2021. Its 2020 and 2021 paths should lie
   between b9's and c1's, close to c1's.
6. On the unchanged ads, the median abs error and the 80% coverage move by under 0.0005 and
   0.003 (80%).
7. $11 to $12 for the three containers.
