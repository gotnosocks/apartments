# A caution for bedroom or bath counts new to the unit (2026-11-20)

No fit and no money spent. Nothing was published and the site was not deployed. Everything
here reads the outputs of fits that already exist.

`docs/notes/changed-counts-read-2026-11-20.md` found a group of held-out ads that is wide on
both tails: ads whose bedrooms and baths are new to the model's unit. A scale term for them
waits for the next base refit. Until then, can the Deals page mark such an ad, and how much
of the table does the mark change?

## The rule

`cautions.new_counts` marks an ad when both hold:

- the model's unit (building and full unit id) has a training row dated strictly before the
  ad;
- no such row has both the ad's bedrooms and its baths (full baths plus half of the half
  baths).

This is the "counts new to the unit" class of the earlier note. When no earlier ad has the
ad's counts, the most recent earlier ad has other counts, so the class needs no second
condition. An ad with an unknown unit, a unit with no earlier training row, or a missing
count is not marked. The rule reads coded counts and dates only. No ask and no ad text
enters it. A caution changes no score and no order; the page leaves cautioned ads out of its
list unless asked for them, as it does for every other caution.

The dataset starts a new piece of a unit ("~1", "~2") where its ads' bedroom count changes
(`data.split_unit_histories`), and the model reads a piece as a unit of its own. So most
bedroom changes give a unit with no history, which this rule leaves alone. The marked ads
are mostly bath changes and the bedroom changes the split does not cover.

## The backtest

Run `drift-building-bedtext-layout-range-b0-market-d9028c57-range-j`, the Deals backtest as
of 2025-11-10, 9,346 held-out ads. The mark is the publish code's own
(`drift_deals._new_counts`), and it gives the 161 ads of the earlier note's `factor.py`.
Low and high are the shares of final asks below the model's 5% point and above its 95%
point. m is the scale factor needed (Student t with 4 degrees of freedom, as in the earlier
note), with a standard error from 200 resamples of buildings (`backtest.py`,
`logs/backtest.log`).

| ads | n | buildings | low | high | m (se) |
|---|---|---|---|---|---|
| marked | 161 | 151 | 11.2% | 12.4% | 1.52 (0.13) |
| the rest | 9,185 | | 4.4% | 6.0% | 0.99 (0.01) |
| the rest with unit history | 6,017 | | 4.3% | 4.2% | 0.94 (0.01) |

By half of buildings (the halves of the history scan):

| ads | n | low | high | m (se) |
|---|---|---|---|---|
| A, marked | 84 | 14.3% | 14.3% | 1.72 (0.22) |
| A, the rest | 4,430 | 4.5% | 5.7% | 0.99 (0.02) |
| B, marked | 77 | 7.8% | 10.4% | 1.32 (0.14) |
| B, the rest | 4,755 | 4.4% | 6.3% | 0.99 (0.02) |

161 ads split in two is small. On half B the low share is 6 ads of 77, which alone would
decide nothing. The high share and the factor are above the rest on both halves.

**What happened to the marked ads placed low.** `drift_deals.validate` places each ad's
first ask in the predictive distribution and follows it to its close. Of the 161 marked ads,
18 have a first ask below the 5% point (11.2% against 3.7% of the rest) and 26 are in the
lowest tenth.

| first ask in the lowest tenth | n | median days | cut | raised |
|---|---|---|---|---|
| marked | 26 | 26.5 | 38.5% | 23.1% |
| the rest | 578 | 26.0 | 15.9% | 36.9% |

The marked ads placed low stayed as long as the others and were cut more than twice as
often (10 of 26). A low place followed by a cut is an ask the market did not take as cheap.
26 ads is few.

**Overlap with the other cautions.** 114 of the 161 already carry another caution on the
backtest, mostly `rooms_up` and `beds`. The caution adds 47 cautioned ads there (1,710 to
1,757), and 3 of them are in the lowest tenth. Those 3 are too few to describe.

## On the live table

Staging run of `ops/deals-refresh publish` from this branch into a scratch folder, market
run `drift-building-bedtext-layout-range-b0-market-6cd1f12b-range-m3` with the backtest
above, compared with the published files (`dry_compare.py`, `logs/dry_compare.log`):

- 6,502 ads in the same order; every field but `cautions` equal, `below_share` and the
  model's bounds included; the other cautions unchanged;
- 108 ads in 103 buildings take `new_counts`: 4 of the first 100 ads of the whole table and
  13 of the first 300;
- 84 of the 108 already carried another caution (59 `rooms_up`, 38 `beds`, 15 `off_market`,
  14 `raised`), so the uncautioned ads go from 4,884 to 4,860;
- of the first 100 uncautioned ads 1 takes the caution (place 24 of that list), and of the
  first 300 the same 1;
- `meta.json` differs in the caution counts, the publish time and the two file hashes;
- `validation.json` differs only under `uncautioned`: 47 more backtest ads are cautioned
  (7,636 to 7,589 left) and the lowest tenth goes from 361 ads, 24.7% raised, to 358 ads,
  24.3% raised.

The caution is narrow. Most ads it marks were already held back by `rooms_up` or `beds`,
and it removes one ad from the first 300 of the page's default list.

The deployed site has no words for the new code until this branch's
`src/apartments/site/deals.py` is deployed (it would show "a caution this page has no words
for"), so deploy the site before the next publish.

## Caveats

- The mark was chosen in the earlier note with both halves of the buildings in view, first
  as fresh or back and then as counts new to the unit. The halves are no independent test
  of it.
- There is one backtest day, 2025-11-10, with 161 marked ads. The latest-split evidence
  (3,823 ads, factors of 1.68 and 1.71 by half) is on a model without the Deals model's
  layout terms.
- The group is wide on both sides with no mean shift, so a marked ad placed low can still
  be a deal. The caution says the place is less reliable. It does not say the model's
  price is too high, which is what `thin_level` and `rooms_up` say.
- The page hides a cautioned ad from its default list. For a caution about width that is a
  blunt tool, and it follows what every other caution does. A wider range for these ads is
  the model's job at the next base refit.
- On a market dataset every held-out ad has the market day's date, so a training row of the
  unit dated on that same day does not count as earlier.

## Files

`new-counts-caution-2026-11-20/`: `backtest.py` (it imports `half`, the run name and the
factor from `changed-counts-read-2026-11-20/`), `dry_compare.py`, and their logs under
`logs/`. The staged files are in `/data1/apartments/tmp/po-newcounts/staging` and are not
committed.
