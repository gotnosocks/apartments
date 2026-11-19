# Low asks in high-turnover buildings: opening asks that are raised later (2026-11-18)

No fit and no money spent. Scripts, logs and the reader's codes are in
`docs/notes/turnover-low-asks-2026-11-18/`. Everything is measured on the Deals model's
backtest, run `drift-building-bedtext-layout-range-b0-market-d9028c57-range-j`: 9,346 ads
open on 2025-11-10, held out, with what happened to each ad afterwards.

## The question

Screen S13 (`docs/notes/turnover-screen-2026-11-13.md`) found that asks fall with a
building's turnover (other units' ads opened in the two years before the ad, per
residential unit and year). No fit reads that column. Does the Deals model show the same
gradient, and what are the low asks behind it?

## Turnover on the Deals backtest (`turn.py`, `turn_who.py`)

The bands are S13's: quartiles of the rate with cuts 0.123, 0.223 and 0.417, buildings with
no other ad in two years, and lots whose unit count PLUTO does not give.

| Band | Ads | Mean gap (se) | Below the 5% point | Above the 95% point | First asks below the 5% point | Of those, later raised | Median days |
|---|---|---|---|---|---|---|---|
| None | 378 | +0.055 (0.010) | 2.9% | 11.6% | 12 (3.2%) | 25.0% | 40 |
| Q1 | 2,139 | +0.021 (0.003) | 3.8% | 7.4% | 43 (2.0%) | 16.3% | 41 |
| Q2 | 2,156 | +0.011 (0.002) | 3.3% | 6.3% | 45 (2.1%) | 37.8% | 45 |
| Q3 | 2,150 | +0.007 (0.003) | 4.0% | 4.9% | 46 (2.1%) | 23.9% | 24 |
| Q4 | 2,144 | −0.008 (0.003) | 7.0% | 4.8% | 173 (8.1%) | 51.4% | 21 |
| Units unknown | 379 | +0.010 (0.009) | 7.1% | 6.6% | 40 (10.6%) | 57.5% | 38 |

The gap is the log ask less the log prediction on the backtest day. The gradient is in
both halves of the buildings and in units with and without a training ad; the slope of the
gap on the log rate is −0.0087 (se 0.0012). The top quartile and the unknown band hold 213
of the 359 first asks below the 5% point. Their buildings are small (median 16 units, rate
0.82) or new large rentals whose lot PLUTO still counts at a few units, and the low share
is highest in buildings that entered the data one to five years before (10.8% to 11.6%
inside Q4, against 6.2% for buildings over eight years in the data).

## What the low asks are

Three readings were open: net-of-concession asks the record does not code, a property of
the building that belongs in the mean, and real low prices.

- **Coded fields say nothing (`turn_net.py`).** Of the 151 Q4 ads below the 5% point on the
  day, 16.6% have coded free months against 22.2% of all Q4 ads. Asks ending in a digit
  other than 0, 5 or 9 are 16.6% against 18.0%. Ads with coded free months are no lower
  than the rest overall (2.5 free months or more: gap +0.042).
- **Ad text says nothing (`turn_texts.py`, `turn-read-codes.csv`).** A Sonnet reader coded
  60 low and 60 ordinary ads (30% to 70% points) from the two bands, one per building,
  without the group. Net wording 1 against 1, ground or garden level 13 against 8, flex
  layouts 6 against 9, new or renovated 29 against 25. No trait separates the groups.
- **The unit's own last ask (`turn_prev.py`).** Low ads in the two bands with a training ad
  of the unit ask a median 12.6% under that ad, and 81% are under it by 2% or more
  (ordinary ads of the bands: +1.2%, 32%). The asks are low against the unit's own record.
- **What happened next (`turn_raise.py`).** Of the 213 low first asks in the two bands, 112
  (53%) were raised later, by a median 19% (quartiles 10% and 23%). At 2246 Fulton Street
  fifteen ads opened near $2,500 and stood at $3,100 to $3,200 some weeks later, where the
  model's prediction is. Lawrence Tower has sixteen such ads, 555 West 45th Street four
  ($6,104 to $7,625). Raised and unraised low asks close in the same time (medians 23 and
  22 days).

So a large part of the low asks in these buildings are opening prices that the lister
raises by a fifth afterwards. Whether they are net prices put right or teaser prices, a
renter who writes in does not get the opening ask.

## A building flag from earlier ads (`turn_flag.py`)

The flag uses only ads of the building outside the held-out set, opened in the year
before the backtest day: an ad counts when its ask on the day is 15% or more above its
first ask. No rent of the held-out ad enters it.

| Flag | Ads (buildings) | First asks below the 5% point | Of those, raised 15% or more later | Below the 5% point on the day |
|---|---|---|---|---|
| Two or more such ads | 428 (86) | 22.2% | 57.9% | 9.1% |
| The rest | 8,918 | 3.0% | 11.7% | 4.3% |
| Two or more, and a tenth of the year's ads | 206 (59) | 34.5% | 77.5% | 8.3% |
| The rest | 9,140 | 3.2% | 10.8% | 4.5% |
| One or more | 1,025 (249) | 13.0% | 45.9% | 8.5% |
| The rest | 8,321 | 2.7% | 11.1% | 4.1% |

By half of the buildings, for two or more such ads: first asks below the 5% point 19.4%
and 25.4% of flagged ads against 3.1% and 2.9%; raised by 15% or more afterwards (all
flagged ads) 16.7% and 27.9% against 0.8% and 0.7%. The flag was chosen after looking at
both halves, so the halves show stability and are no unread test.

Of the 428 flagged ads, 299 are in Q4 and 42 in the unknown band. Without them Q4 still
has 6.5% of its ads below the 5% point on the day (7.0% with them) and 5.5% of its first
asks (8.1% with them, about 2.1% in Q1 to Q3). The flag takes out under half of Q4's
excess of low first asks and little of its excess on the day, so the turnover gradient
stays.

## The flag over the whole history, with no model (`raise_hist.py`)

The backtest is one day. The flag's claim about price paths needs no model, so it can be
tested on every ad in the ads table with a first ask and a latest ask (1,985,235 ads).
For each ad the count is of ads of other units of the building that opened in the 365
days before it, closed before it opened, and ended 15% or more above their first ask.
The outcome is the ad itself ending 15% or more above its first ask.

| Earlier raised ads | Ads | Buildings | Ended 15% or more above the first ask | 8% or more | Cut by 5% or more |
|---|---|---|---|---|---|
| None | 1,781,572 | 73,542 | 0.84% | 2.3% | 12.2% |
| One | 104,961 | 6,543 | 3.5% | 7.2% | 11.2% |
| Two or more | 98,702 | 2,917 | 13.7% | 20.8% | 7.3% |

Every year from 2015 has the same order. For two or more against none: 14.0% against
0.41% in 2018, 25.0% against 2.3% in 2020, 6.3% against 0.78% in 2022 (the lowest
ratio), 20.6% against 0.82% in 2024, 17.3% against 0.73% in 2025 and 17.6% against 0.66%
in 2026. The raise among raised ads has a median of 24% in flagged buildings.

This version of the flag counts closed ads at their final ask, a little stricter than the
backtest's (open ads at their ask on the day).

## What follows

1. A Deals caution for ads in flagged buildings ("ads in this building often open low and
   are raised"), computed from the ads table at publish time. It needs no fit. The
   threshold (two ads, 15%, one year) was chosen on the one backtest day; the history
   table above supports it on the price paths of every year.
2. The opening asks that were raised are in training as the unit's record only at the
   latest ask, so they do not pull the model down. No data fix is needed there.
3. The rest of the turnover gradient (Q4 at 6.5% low without flagged buildings, the
   +0.055 gap of buildings with no other ad) is still a candidate mean term, with S13's
   caveat that the latest split shows no gradient.
