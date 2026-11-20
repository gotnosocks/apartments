# Dating concessions in `first_net` cannot be built from the price history (2026-11-20)

No fit, no money spent. Item F2 of `docs/notes/deals-closingraise-2026-11-20/plan.md` and an
item in `docs/TODO.md` proposed that `drift_deals.first_net` date an ad's concession from
`pricing.priceChanges`. The data does not allow it, and this note records the check so the
item is not tried again. The scripts and their output are in
`docs/notes/first-net-concessions-2026-11-20/`; they read scratch files under
`/data1/apartments/tmp/po-firstnet/`, and `val.json` holds the simulated validation tables.

## What the data holds

`pricing.priceChanges` is a list of `changedAt` and `price` and nothing else. In a 1% sample
of the records of build `941f4a6588cbd8cc` (23,266 records, 59,262 entries) every entry has
exactly those two keys, and every record has the list, in each year of the sample (2011 and 2013 to 2026).
`monthsFree` and `netEffectiveRent` are single values on the record, the ad's concession at
the time it was collected. No field says when a concession began.

The only concession history is in repeat collections of the same ad, which began on
2026-10-15 and give at most 7 snapshots per ad (`scan.out.txt`, `an1.out.txt`).

- The backtest ads of `range-j` (9,346 open on 2025-11-10) have no usable history: 34 have
  more than one snapshot and none of the 34 changes its months free. 2,254 of the 9,346 have
  free months.
- The live ads of `range-m3` (6,502) have more: 5,926 have two or more snapshots, with a
  median span of 10 days between first and last.

## How much concessions move

Among the 5,926 live ads with two or more snapshots, 1,331 carry a concession now
(`an2.out.txt`). Of those, 31% had a different one at the first snapshot: 227 had none then
and 186 had another size. 39 more ads had one at the first snapshot and have none now. For
snapshots 26 to 40 days apart (528 ads with a concession now) 48% differ. The median shift
among ads that differ, the 39 included, is 4.5% of the rent. Only 1,654 of the 5,926 first
snapshots fall within 3 days of the ad's opening, so the 31% is a lower bound on changes
since opening.

## What the simulation shows

`first_net` reads a concession as present from the first day. If some concessions were added
after opening, the first ask of those ads should stay gross, and the ads placed low by first
ask would show a larger share raised. `val.py` replays `validate` on `range-j` with a random
share of the 2,254 concessions treated as added after opening (`val.json`). The 0% row is the
published table.

| Added late | Low tenth, ads | Low tenth, raised | High tenth, ads | High tenth, cut |
|---|---|---|---|---|
| 0% (current) | 604 | 36.3% | 1,694 | 61.9% |
| 25% | 580 | 37.1% | 1,986 | 69.7% |
| 50% (two seeds) | 558, 557 | 37.8%, 37.3% | 2,252, 2,288 | 74.6%, 75.1% |
| 100% | 507 | 39.1% | 2,826 | 83.4% |

The lowest tenth's share raised moves by 2.8 points at most. The highest tenth's share cut
moves by 21.5 points, and its ads grow from 1,694 to 2,826: an ad whose first ask is read
gross looks cut against its net final ask and is placed higher. So for ads with free months
the published tenths rest on the assumption that the concession was there from the first day,
and the high end of the table is the part that depends on it.

## The live table

Only 6 of the 6,502 live ads carry the `net_ask` caution, and `first_net` is not used on the
live table. 51 live ads had a concession coded in an earlier snapshot and have none now; 37 of
them have a page price below the first ask.

## What a real fix needs

A snapshot-dated `months_free` at the ad's open, in the ads table (`rentfrontier.market`), so
that `first_net` can use the concession the ad showed when it opened. It exists only for ads
first collected after 2026-10-15, so it works only for backtest days after that date. A
backtest on 2025-11-10 cannot have it, and `first_net` and the backtest's `net_ask` caution
read the final page price and months free, which a reader on that day could not know
(`docs/model/drift.md`). Until a later backtest day exists, `first_net` stays as it is, and
its docstring points here.
