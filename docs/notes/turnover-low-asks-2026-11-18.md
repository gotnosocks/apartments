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

The gap is the log ask less the log prediction on the backtest day. Median days run from
the ad's opening to its close, or to the frame's last day for ads still open. The gradient is in
both halves of the buildings and in units with and without a training ad; the slope of the
gap on the log rate is −0.0087 (se 0.0012). The top quartile and the unknown band hold 213
of the 359 first asks below the 5% point. Q4's ads are in buildings of a median 16 units
with a median rate of 0.82 (15 units and 0.96 for its low ads), though size does not carry
it: Q4's low share is 6.7% in buildings of up to 2 units and 10.4% in those over 199. The
unknown band has no unit count by definition. The low share is highest in buildings that entered the data one to five years before (10.8% to 11.6%
inside Q4, against 6.2% for buildings over eight years in the data).

## What the low asks are

Three readings were open: net-of-concession asks the record does not code, a property of
the building that belongs in the mean, and real low prices.

- **Coded fields say nothing (`turn_net.py`).** Of the 151 Q4 ads below the 5% point on the
  day, 16.6% have coded free months against 22.2% of all Q4 ads. Asks ending in a digit
  other than 0, 5 or 9 are 16.6% against 18.0%. Ads with coded free months are no lower
  than the rest overall (2.5 free months or more: gap +0.042).
- **Ad text shows no difference at this size (`turn_texts.py`, `turn-read-codes.csv`).** A Sonnet reader coded
  60 low and 60 ordinary ads (30% to 70% points) from the two bands, one per building within a
  group (two buildings are in both groups), without knowing the group. Net wording 1 against 1, ground or garden level 13 against 8, flex
  layouts 6 against 9, new or renovated 29 against 25. At 60 ads a group no trait differs; moderate
  differences are not ruled out.
- **The unit's own last ask (`turn_prev.py`).** Of the 178 low ads in the two bands, 57%
  have a training ad of the unit. They ask a median 0.126 under that ad in logs (about
  12%), and 81% are under it by 2% or more (ordinary ads of the bands: +1.2%, 32%). The
  model prices from that ad, so this follows from the low place and is no separate
  evidence.
- **What happened next (`turn_raise.py`).** Of the 213 low first asks in the two bands, 112
  (53%) were raised later, by a median 19% (quartiles 10% and 23%). At 2246 Fulton Street
  fifteen ads opened near $2,500 and stood at $3,100 to $3,200 some weeks later, where the
  model's prediction is. Lawrence Tower has sixteen such ads, 555 West 45th Street four
  ($6,104 to $7,625). Raised and unraised low asks have the same median days from opening
  to the close, or to the frame's last day for ads still open (23 and 22).

So about half of the low first asks in these bands are opening prices that the lister
raises afterwards, by a median of a fifth. They are spread over 126 buildings; Lawrence
Tower and 2246 Fulton Street supply 31 of the 112. Part of the link is mechanical: the
model prices the later ask, so a first ask far below the prediction has likely been raised.
The flag of the next section, which reads earlier ads only, is the test. Whether they are net prices put right or teaser prices, a
renter who writes in does not get the opening ask.

## A building flag from earlier ads (`turn_flag.py`)

The flag uses only ads of the building outside the held-out set, opened in the year
before the backtest day: an ad counts when its last ask in the dataset (the ask on the day
for ads still open) is 15% or more above its first ask. No rent of the held-out ad enters it.

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

Every year from 2015 has the same order. For two or more against none: 1.65% against
0.43% in 2015 (the smallest ratio), 14.0% against 0.41% in 2018, 25.0% against 2.3% in
2020, 6.3% against 0.78% in 2022, 20.6% against 0.82% in 2024, 17.3% against 0.73% in 2025 and 17.6% against 0.66%
in 2026. The raise among raised ads has a median of 24% in flagged buildings.

This version of the flag counts closed ads at their final ask, a little stricter than the
backtest's (open ads at their ask on the day).

## The window: one year against the building's whole record (`raise_all.py`)

Ben asked why the flag reads one year and not the whole history. The same count over two
years, five years and the building's whole record, on the ads table (share of ads ending
15% or more above their first ask; 0.8% with no earlier raised ad in every window):

| Window | 2 to 4 earlier raised ads | 5 or more | Ads with 2 or more |
|---|---|---|---|
| One year | 9.3% | 19.3% | 98,702 |
| Two years | 5.8% | 13.0% | 163,113 |
| Five years | 3.5% | 6.9% | 311,967 |
| Whole record | 3.4% | 5.7% | 362,555 |

A longer window marks more ads and each mark says less, because the habit is recent. Among
ads with two or more earlier raised ads in the whole record, by the age of the newest
one: 21.7% end 15% or more above their first ask when it opened in the last 90 days
(55,376 ads), 3.1% at 90 days to a year, 1.4% at one to two years and 0.7% beyond, which
is the rate of unflagged buildings. From 2024 on, ads with two or more in the whole
record and none in the past year are raised 0.67% of the time (115,698 ads) against 18.4%
for two or more in the past year (23,589).

The held-out errors of the latest-split run (`l2bt`, 189,607 ads of every year) give the
model's side of the same test. The gap at the first ask is the held-out gap less the log
of the latest ask over the first ask.

| Earlier raised ads, one year | Ads | Mean gap at the first ask | First ask 15% or more under the prediction | Below the 5% point at the latest ask |
|---|---|---|---|---|
| None | 171,472 | +0.005 | 3.2% | 5.7% |
| One | 10,064 | −0.001 | 4.9% | 6.9% |
| 2 to 4 | 4,585 | −0.022 | 10.2% | 8.9% |
| 5 or more | 3,486 | −0.044 | 17.0% | 9.5% |

With the whole record the same rows read 3.6%, 3.4%, 3.7% and 4.2% for first asks 15% or
more under the prediction, so the whole-record flag separates nothing there. The caution
should weigh recent raised ads: a raised ad in the last 90 days is the strongest single
mark, and the rule's exact form (count and window) is to be chosen on half of the
buildings and checked on the other half when the caution is written.

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
