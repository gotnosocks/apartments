# A caution for a high building level on few ads (2026-11-20)

No fit and no money spent. Everything here reads the outputs of fits that already exist.

`docs/notes/kept-rhat-audit-2026-11-20.md` and `docs/notes/building-level-read-2026-11-20.md`
found buildings whose level (`kept/bld`, log rent above the zone's surface) sits high on a
handful of odd training rows: a commercial space, a placeholder ad, a whole house among
studios. The model then prices the building's next ad too high, and the ad climbs the Deals
order without being cheap. The second note proposed a publish-time caution, "over 0.3 on five
or fewer" training ads, and said it must be tested on history first. This note is that test,
and the caution it supports.

## The rule

`cautions.thin_level` marks an ad when both hold:

- the posterior mean of its building's level is over 0.3 (`THIN_LEVEL`);
- the building has 5 or fewer ads among the fit's training rows (`THIN_ADS`).

The count is every training row of the building, one per ad, the ad's own apartment's earlier
ads included. That is the count the test below used (`n_bld` in `b1.py`; the variant that
leaves the ad's own unit out, `n_other`, was tabulated too and is not the rule). The level is
fitted on training rows only and the scored ad is held out, so no ask of the ad enters the
rule. A caution changes no score and no order.

## The test on held-out history

Run `drift-building-phase-unitkn-level-bedtext-b0-latest-c1ffaefd-l2bt`, the latest split:
189,647 held-out ads, each the newest ad of its unit. The buildings were cut in two halves by
a hash of the building's name (`b1.py`). The form came from the read of the live table in the
building-level note, before either half was tabulated. The search over forms that `b2.py`
also prints for half A did not pick it: it has fewer than the 100 ads that search asked for.

"Below 5%" is the share of ads whose final ask is under the model's 5% point; "gap" is the
mean of log ask less the predictive median (`logs/b2_A_n_bld_0.3_5.log`,
`logs/b2_B_n_bld_0.3_5.log`).

| half | ads | buildings | below 5% | above 95% | gap | median gap |
|---|---|---|---|---|---|---|
| A, marked | 90 | 83 | 14.4% | 2.2% | -0.070 | -0.058 |
| A, the rest | 91,977 | 18,090 | 5.8% | 4.5% | -0.004 | -0.004 |
| B, marked | 99 | 85 | 14.1% | 2.0% | -0.056 | -0.032 |
| B, the rest | 97,481 | 17,949 | 5.9% | 4.9% | -0.004 | -0.004 |

Over all 189,647 ads 5.9% are below the 5% point. A marked ad is there about 2.4 times as
often in each half, and the model's median is 6% to 7% too high for it. With each building
weighted once the mean gap is -0.076 (A) and -0.062 (B) (`logs/c1.log`). The marked ads are
0.24% of the ads below the 5% point, so the rule is narrow.

By period, marked ads only (`logs/c2.log`):

| period | ads A | ads B | below 5% A | below 5% B | gap A | gap B |
|---|---|---|---|---|---|---|
| to 2019 | 21 | 30 | 9.5% | 6.7% | -0.042 | -0.052 |
| 2020-22 | 28 | 28 | 14.3% | 10.7% | -0.031 | -0.036 |
| 2023-24 | 15 | 15 | 20.0% | 40.0% | -0.125 | -0.127 |
| 2025-26 | 26 | 26 | 15.4% | 11.5% | -0.105 | -0.043 |

The gap is negative in all eight cells. The cells are small and the shares below 5% move a
lot between them.

The marked ads below the 5% point also sat longer: a median of 30 days (A, 13 ads) and 81.5
days (B, 14 ads) against 15 days for the other ads below it. The market did not take them as
cheap.

## The form not adopted: level over 0.4, any count

| half | ads | buildings | below 5% | above 95% | gap |
|---|---|---|---|---|---|
| A | 412 | 119 | 14.1% | 6.1% | -0.026 |
| B | 413 | 135 | 13.6% | 4.6% | -0.027 |

It marks four times the ads at the same share below 5%, but most of them are in buildings
with 21 or more training ads, and there the excess is spread, not bias: 297 and 271 ads,
13.1% and 11.8% below 5% with 6.7% and 5.9% above 95%, and a gap of -0.013 and -0.015
(`logs/c1.log`, `hi4_21plus`). A caution says the model's price is too high, and for those
buildings it is not; their asks are wide on both sides. So the rule keeps the cut on the
count.

## The backtest is too small to say anything

On the backtest run `drift-building-bedtext-layout-range-b0-market-d9028c57-range-j` (as of
2025-11-10) the rule marks 12 ads in 12 buildings (`logs/a2.log`, `logs/c1.log`). One of the
12 is below the 5% point (8.3% against 4.5%), the mean gap is -0.066 against +0.010, and 2
are in the lowest tenth by first ask. Twelve ads decide nothing either way.

## On the live table

Dry run of `ops/deals-refresh publish` from this branch into a scratch folder, market run
`drift-building-bedtext-layout-range-b0-market-6cd1f12b-range-m3` with the backtest above,
compared with the published files (`dry_compare.py`, `logs/dry_compare.log`):

- 6,502 ads in the same order with the same `below_share`; every field but `cautions` equal,
  and the other cautions unchanged;
- 16 ads in 14 buildings take `thin_level`, 2 of them in the first 300 (ranks 44 and 285)
  and 3 in the first 300 uncautioned;
- 4 of the 16 already carried another caution, so the uncautioned ads go from 4,896 to 4,884;
- in the backtest's `uncautioned` table 9 more ads are cautioned (7,645 to 7,636 left) and the
  lowest tenth goes from 362 ads, 24.9% raised, to 361 ads, 24.7% raised.

The 16 are the rows with 5 or fewer training ads in the building-level note's table
`building-level-read-2026-11-20/thin_high_level_deals_ads.csv` (its other 4 rows have 7 or 8).
Nothing was published.

The deployed site has no words for the new code until this branch's `site/deals.py` is
deployed, so deploy the site before the next publish.

## Placeholder and commercial rows: no row rule follows

The building-level read blamed placeholder ads and commercial spaces for some of these levels,
so both were sized over all training rows (`t1.py`, `t2.py`, `logs/t2.log`). An ad's text is
that of its last active record. Placeholder: an empty text, a text under 10 characters, or a
stock word ("draft", "n/a", "coming soon"). Commercial: commercial wording with no residential
word. The ratio is the ask over the median ask of the same neighbourhood, year and bedrooms.

| training rows, live dataset | rows | buildings | median ratio | over 1.5x | over 2x |
|---|---|---|---|---|---|
| all | 1,894,766 | | | 7.1% | |
| empty text | 8,181 | 2,366 | 0.99 | 4.8% | 1.0% |
| short text | 50,555 | 8,102 | 0.98 | 5.7% | 0.9% |
| stock word | 23,680 | 4,391 | 0.98 | 5.9% | 1.1% |
| commercial | 759 | 456 | 1.32 | 39.4% | 29.4% |

Placeholder ads are priced like other ads: 59,240 rows, and fewer of them over 1.5 times the
median than of all rows. Commercial rows are high, and there are 759 of them.

Held-out gap on the latest split by what the building's training ads hold (ads whose own text
is a placeholder or commercial left out; 182,559 ads, gap -0.0044, 5.9% below 5%):

| building's training ads hold | ads | buildings | gap | below 5% | above 95% |
|---|---|---|---|---|---|
| a commercial ad | 2,687 | 283 | -0.0062 | 7.3% | 5.0% |
| a commercial ad over 2x | 578 | 100 | -0.0081 | 5.5% | 3.1% |
| a commercial ad over 2x, 20 or fewer ads | 82 | 46 | -0.0173 | 7.3% | 4.9% |
| a placeholder ad | 57,066 | 6,455 | -0.0038 | 6.3% | 5.2% |

None of these groups is far from the whole. Of the 189 marked ads, 4 are in a building with a
commercial training ad and 10 in one with a placeholder, 14 with either. The 12 marked ads in
a building with a commercial ad or a placeholder over 1.5 times the median have a gap of
-0.170; the other 177 still have -0.056. So dropping or flagging such rows would not remove
the miss the caution marks, and a rule on placeholder text would touch 59,240 ordinary rows.
No row rule follows from this sizing. The drafted ledger rows of the building-level note are
a separate, read-by-hand matter.

## Open question for the model

The miss is not confined to odd rows, which points at the model: it shrinks a building with
few ads too little. The low side agrees. Buildings with a level under -0.3 on 5 or fewer
training ads hold 16 held-out ads in 13 buildings, none below the 5% point, 12.5% above the
95% point, and a mean gap of +0.091 (`logs/c2.log`): the model prices them too low. A level
far from zero on a few ads is too far from zero in both directions. Whether a heavier pull to
the zone's surface for thin buildings (the Student-t prior's spread, or its degrees of
freedom) would help the held-out score is a question for a fit, and is not tested here. The
low side is 16 ads and gets no caution: a caution exists to hold back a false deal, and those
ads rank as dear.

## Files

`thin-level-caution-2026-11-20/`: `a1.py`, `a2.py` (backtest), `b1.py`, `b2.py` (latest split,
by half), `c1.py`, `c2.py` (forms compared, periods, the low side, the live table), `t1.py`,
`t2.py` (texts), `p0.py`, `p1.py` (file layouts), `dry_compare.py`, and their logs under
`logs/`. The scripts read and write parquet files in `/data1/apartments/tmp/po-thinlevel/`
that are not committed, and `c1.py` reads the live levels from
`/data1/apartments/tmp/po-bldmodes/`.
