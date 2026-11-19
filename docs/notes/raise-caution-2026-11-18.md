# A Deals caution for buildings that raise their opening asks (2026-11-18)

No fit and no money spent. Scripts and logs are in `docs/notes/raise-caution-2026-11-18/`.
The caution follows from `docs/notes/turnover-low-asks-2026-11-18.md`: about half of the
low first asks in high-turnover buildings are opening prices the lister raises afterwards.

## The rule, chosen on half of the buildings (`choose.py`)

The data are the 189,607 held-out ads of the latest-split run with a first ask. 7,006 of
them have a first ask 15% or more under the prediction, and 21.3% of those ended 15% or
more above their first ask. A rule marks an ad when K or more other units of its building
have an ad that opened in the W days before it, closed before it opened, and ended 15% or
more above its first ask. The criterion was fixed before any rule was scored: on half A of
the buildings (seeded), among rules whose marked low first asks were raised at least half
the time, take the rule that marks the most raised low first asks. That gave W = 365 days
and K = 1.

| Half | Marked low first asks (buildings) | Raised 15% or more | Unmarked | Share of raised low first asks marked |
|---|---|---|---|---|
| A (chosen on) | 760 (417) | 52.2% | 12.5% | 53.8% |
| B (unread) | 791 (439) | 52.1% | 12.6% | 54.4% |

Over all ads of half B, low or otherwise, 8.0% of the 106,969 marked ads were raised 15% or
more against 0.9% of the rest. Half B by period: 37.0% against 9.5% to 2019 (27 marked
ads), 62.5% against 24.8% in 2020 and 2021, 32.0% against 7.9% in 2022 and 2023, and 48.2%
against 10.8% from 2024. Tighter rules are more exact and mark fewer: three ads in 60 days
gives 72.8% on half B and marks 15.2% of the raised low first asks.

## Backtest asks are final asks

A backtest dataset (`rentfrontier.market` with `--as-of`) keeps each open ad's final ask,
so a fit is scored on asks it has not seen. The ask an open ad showed on the backtest day
is not in the dataset. Of the 9,346 open ads of the 2025-11-10 backtest, 3,025 changed
their ask after the day. Two things follow.

- `drift_deals._raised` counts an open ad of a backtest dataset at its first ask, so it
  marks no building from a raise that came after the day. In a market dataset every row's
  ask is the ask on the market day and all rows count.
- The turnover note called the backtest's held-out asks "on the day". They are final asks;
  that note now carries a correction. Its first-ask results read first asks from the ads
  table and stand.

## The page's question: is a marked ad that is low on the day raised later? (`paths.py`, `current.py`)

The history test above is about first asks at opening. The Deals page ranks current asks.
`paths.py` reads the price path of each open ad of the backtest from the records file of
its dataset, and `current.py` takes each ad's ask on 2025-11-10 from it. Buildings are
marked from what was knowable on the day (training ads, and open ads at their ask on the
day), and the ask on the day is placed in the backtest run's prediction.

| Ads on the backtest day | Marked: ads (buildings) | Raised 15% or more later | Raised 5% or more | Unmarked: ads | Raised 15% or more later | Raised 5% or more |
|---|---|---|---|---|---|---|
| All | 1,051 (258) | 10.7% | 20.7% | 8,295 | 0.5% | 3.3% |
| Below the 10% point | 225 (87) | 33.3% | 52.0% | 575 | 3.7% | 14.3% |
| Below the 5% point | 157 (67) | 42.0% | 59.2% | 283 | 4.9% | 14.1% |
| Below the 5% point, at or below the first ask | 151 (67) | 41.7% | 59.6% | 274 | 5.1% | 14.2% |

35.7% of the ads below the 5% point on the day are marked. Lawrence Tower and 2246 Fulton
Street hold 37 of the 157 marked low ads and 31 of the 66 that were raised; without them
35 of 120 were raised (29%), still six times the unmarked rate. Some marked buildings
raised nothing after the day (Bridgeview Dumbo, 9 low ads). Nearly all low ads stand at
their first ask, so limiting the caution to ads at their first ask would change little.

This is one backtest day, and the count and window were chosen on first asks. It agrees
with the unread half of the history in size (42% against 52% there, 5% against 13%).

## The caution

`cautions.raised` marks an ad when another apartment of its building has an ad opened in
the past 365 days that stands 15% or more above its first ask. `drift_deals` adds the code
`raised`, and the page labels it "building raises opening asks". Like other cautions it
changes no score, and the page hides cautioned ads unless the reader includes them.

Counts (`backtest.py`): on the backtest table 1,028 ads in 252 buildings (114 with another
caution), 20.9% of the uncautioned ads below the 5% point. On the market table of
2026-11-17 (run `range-m2`) 686 of 6,565 ads in 190 buildings, 552 with no other caution,
and 30, 51 and 90 of the first 100, 200 and 500 uncautioned ads.

A marked low ad is still not raised more often than it is raised (58% against 42% on the
backtest day), so a reader who includes cautioned ads will find real low asks among them.
