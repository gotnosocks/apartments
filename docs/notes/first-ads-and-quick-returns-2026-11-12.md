# First ads and quick returns under L1 (2026-11-12)

L1 (`drift-building-phase`, run `drift-building-phase-b0-latest-9a7830fb-l1`) gave a
unit's first ad in the data a noise factor of 1.64 against the 10 to 13 month reference,
and its 13,725 held-out ads that come within 3 months of the unit's previous ad covered
only 0.76 at 80% (`docs/notes/lease-phase-noise-2026-11-12.md`). I ran two free checks on
the run's outputs and the c3 dataset to see where each comes from. The scripts are in
`/data1/apartments/tmp/sprint-20261112/none-check/`: `peek.py` builds the frame with each
row's phase, `check.py` and `extra.py` do the breakdowns, and `check.out` and `extra.out`
hold their output.

## First ads

The run saves the predictions of held-out ads only. It keeps no unit levels for the
training rows, so I could not compute their standardized residuals. I used two proxies
instead, both on log asks:

1. A row's residual from the mean of the other training rows of its building, bedroom
   count and calendar year, for cells of at least three rows. I measured spread as 1.4826
   times the median absolute deviation, and the tail as the share of rows more than 3 or
   6 of those scales from the median.
2. The jump from a unit's ad to its next one, grouped by the months between them, comparing
   jumps that start at the unit's first ad with jumps that start at a later ad.

The bulk of first ads is no wider than that of later ads. Their cell residuals have a
robust scale of 0.077, against 0.083 for all later phases and 0.078 for 10 to 13 months.
Jumps that start at a first ad are smaller than jumps that start at a later ad, in every
gap band: 0.033 against 0.038 under 3 months, 0.061 against 0.073 at 10 to 13 months, and
0.158 against 0.181 at 26 months or more. So a first ad does not stray further from its
unit's next ask than any other ad does.

The excess lies in the tails, and mostly in units with a single ad:

| training rows | n | robust scale | beyond 3 scales | beyond 6 scales |
|---|---:|---:|---:|---:|
| later phases | 771,428 | 0.0825 | 0.0468 | 0.0031 |
| first ad, more ads follow | 398,097 | 0.0790 | 0.0530 | 0.0051 |
| first ad, the unit's only ad | 537,299 | 0.0750 | 0.0649 | 0.0082 |

Units with a single ad hold 57% of the "none" rows and show 2.6 times the later phases'
share of rows beyond 6 scales. First ads of units with later ads show 1.6 times. The model
has no way to split a single-ad unit's distance from its building between the unit's
normal lasting level and the row's Student-t noise, so it seems plausible that these
outlying single ads push the "none" factor up. The factor scales a noise of about 0.024
against a `unit_sd` of 0.060, so it changes the tails of these rows far more than their
bulk.

Most of the other splits show no clear excess. I compared the "none" rows' robust scale with
the later rows' in each group:

- Bedrooms: 0.88 to 0.94 in every group.
- Ask source: 0.93 for `latest`, 0.89 for `latest, before closing raise`. The 1,007 rows of
  other sources reach 1.17.
- Square feet given or missing: 0.98 and 0.93. The pipeline's ads table has no square feet
  for 75% of the rows.
- Description known or not: 0.93 and 1.04.
- The only unit seen in its building: 1.25, on 14,113 rows. The group is too small to drive
  the factor.
- Borough, from the building's slug: in Brooklyn 0.060 (more ads follow) and 0.059 (only ad)
  against 0.066 for later rows, and in Manhattan 0.079 and 0.087 against 0.085.
- First-seen year: 1.20 for 2014 and earlier (86,253 rows), 1.10 for 2015 to 2016, 0.97
  for 2017 to 2019, 0.82 for 2020 to 2022 and 1.02 for 2023 on. The tail share runs 1.3
  to 2.2 times the later rows' in every period except 2020 to 2022. Left censoring may add
  a little in the first two years, but the tail excess is there in 2023 too.

The data have no column for the listing's source site or broker.

## Quick returns

I matched the held-out ads to rows as `by_phase.py` does, through the run's held-out mask,
and checked that the listing ids and asks agree. Every row of the dataset is its own
listing, so none of the 13,725 ads is a price change within the previous ad's run. I split
them by the change in log ask from the unit's previous ad. The change reads the target, so
this describes the misses rather than offering a feature.

| change since the previous ad | n | 80% coverage | median residual | misses |
|---|---:|---:|---:|---:|
| cut over 10% | 1,537 | 0.380 | -0.090 | 953 |
| cut 3 to 10% | 3,339 | 0.699 | -0.042 | 1,005 |
| cut under 3% | 1,425 | 0.881 | -0.016 | 170 |
| same ask | 5,007 | 0.909 | -0.002 | 457 |
| raise under 3% | 758 | 0.879 | 0.010 | 92 |
| raise 3 to 10% | 1,156 | 0.736 | 0.036 | 305 |
| raise over 10% | 503 | 0.372 | 0.101 | 316 |

Moves of more than 3% make up 48% of these ads and hold 2,579 of the 3,298 misses. Cuts
outnumber raises about three to one, so the misses fall below the interval 16.5% of the
time and above it 7.5%, with a median residual of -0.012. A repost at the same ask covers
0.91, slightly over the target. Other splits follow the same pattern:

- An ad whose own run held a cut covers 0.68 (4,135 ads).
- An ad listed after the previous listing ended covers 0.74, against 0.80 for one listed
  while the previous was still up.
- An ad with a different bedroom count from the previous covers 0.37, but there are only
  179 of them.
- Coverage falls from 0.83 within a week to 0.72 at 61 to 91 days.

The 3 to 9 month held-out ads show the same shape: cuts of over 10% cover 0.57 there.

The training rows of the 0 to 2 month phase move almost as often as the held-out ones: 13.1%
of them move more than 10%, against 14.9%, and the robust scale of their jumps is 0.034
against 0.040. The held-out ads are a unit's last ad, and a quick relist that ends a unit's
run in the data moves a little more than one followed by further ads. The phase's factor,
1.08, comes from the training rows, so it falls short for the held-out ads.

The undercoverage looks only loosely related to the "none" factor. With that factor at 1.64,
every `sigma` fell by about a fifth, and the 0 to 2 month interval narrowed from 0.139 to
0.129. That narrowing exposes the mixture of repeats and real repricings in quick returns.
The ads that miss are ordinary relistings at a new price.

## What could follow

The single change I would try next is to split the "none" phase in two: first ads of units
with only one ad, and first ads of units with later ads. If the excess comes from outlying
single ads, the first group's factor should land well above the second's, and the second
should fall toward 1.2 to 1.4. Then the `sigma` of the other phases can widen back. U2's
Student-t unit level (`docs/notes/unit-t-level-2026-11-12.md`) offers another route for the
same tail, and once U2 is scored the "none" factor under L1 with U2's levels would show how
much of it the unit level absorbs. As a data check, the few thousand single-ad rows more
than 6 scales from their cell are worth a read for miscoded asks or wrong unit links.

For quick returns, a noise scale that mixes a near-repeat with a repricing would match the
pattern better than a single factor. The phase factor already has little room left to
widen without overcovering the 5,007 same-ask ads.
