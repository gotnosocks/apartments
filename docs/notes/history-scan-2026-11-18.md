# Ads asked below prediction across the held-out history: checks on stored predictions, no fit

Date: 2026-11-18. Cost: no Modal or OxyLabs money.

Ben asked for the outliers below the predicted price to be reviewed on the history instead
of the live table. This note measures which classes of ad are asked below prediction on
the latest split's held-out ads, how large each gap is, and whether a low place in each
class behaves like a low price (the ad closes sooner). The scripts are in
`docs/notes/history-scan-2026-11-18/` and their printed tables in its `logs/` folder. They
read and write scratch files under `/data1/apartments/tmp/history-scan`.

## Evidence used

- The latest split: 189,647 held-out ads, each the latest ad of a unit whose earlier ads
  are in training. Stored predictions of the base model
  (`drift-building-b0-latest-67d14e17-b9`) and of the richer bed-text model
  (`drift-building-phase-unitkn-level-bedtext-b0-latest-c1ffaefd-l2bt`, called l2bt below).
  From 2022 on l2bt has 129,861 held-out ads, 5.55% of them below its 5% point and 4.17%
  above its 95% point.
- The Deals model's backtest (`range-j`): 9,346 held-out ads after 2025-11-10.
- The texts of 180,288 held-out ads (`texts.py`), and the ads file's outcomes (first ask,
  status, day taken off).

`res` is the log ask less the log of the predicted median, `low` the share of ads below
the 5% point, `high` the share above the 95% point, `sd z` the spread of the normal scores
(1 when calibrated). Buildings are split in two halves by a hash; tables give both halves,
and anything picked is picked on one half and scored on the other. Standard errors are
clustered by building.

## Ad text holds little of the remaining error

`scan.py` ranks 14,940 words and two-word phrases by the mean normal score of the ads
holding them; `ridge.py` fits a ridge of the normal score on all of them on one half of
buildings. On the other half the text score explains 0.63% of the variance (correlation
0.08). Of 5,090 ads below the 5% point there, 4,669 stay below it after the text score is
taken out and 362 other ads move below it.

Coded traits on the base model, all years (`traits.py`), `res` by half:

| trait | ads | res | low |
|---|---|---|---|
| price called net, no coded free months | 4,650 | -0.012, -0.011 | 8.7%, 9.7% |
| junior | 1,935 | -0.017, -0.010 | 9.2%, 7.7% |
| railroad | 1,421 | -0.012, -0.010 | 6.3%, 5.7% |
| asap | 2,500 | -0.010, -0.012 | 8.0%, 8.0% |
| deal words | 6,243 | -0.006, -0.008 | 6.6%, 7.1% |
| sublet or short term | 1,483 | -0.003, -0.001 | 6.9%, 8.7% |
| parlor | 1,517 | +0.038, +0.021 | 3.7%, 3.8% |
| primary bedroom | 4,707 | +0.017, +0.014 | 4.8%, 5.5% |
| gut renovated | 5,130 | +0.008, +0.011 | 4.7%, 4.6% |

Each gap is one or two percent of rent. Junior wording is the bed-text term's subject, and
on l2bt from 2022 on it no longer ranks (`scan2.py`).

Free months stated only in the text (`freetext.py`, on l2bt): 4,411 held-out ads, `res`
-0.008 and -0.009, low 9.1% and 9.4%. The gap grows with the months stated (over one to
two months -0.025 and -0.013; over two -0.034 and -0.048) and belongs to ads whose text
calls the price net (-0.014 on both halves; ads with the basis unstated +0.005 and +0.004). It is an
effect of earlier years: before 2020 -0.005 and -0.006, 2020 and 2021 -0.013 and -0.017,
from 2022 on 268 ads with no gap (-0.006 and +0.007). Wording of this kind is in 12% to
16% of held-out ads of 2017 to 2020 and in 1.2% to 2.3% of those from 2022 on, when the
coded `months_free` field took over. So grossing up net asks would clean the training
rows of 2016 to 2021 and change few current predictions.

## Changed counts and many baths hold the excess low tail

l2bt, 2022 on (`baths.py`). An ad has "counts as before" when its bedrooms and baths equal
those of every training ad of the same apartment, and "counts changed" otherwise.

| ads | full baths | n | res by half | low by half | high by half |
|---|---|---|---|---|---|
| counts as before | 1 | 84,077 | -0.005, -0.005 | 4.5%, 4.6% | 3.5%, 3.3% |
| counts as before | 2 | 16,171 | -0.010, -0.009 | 6.2%, 6.1% | 3.9%, 3.9% |
| counts as before | 3 or more | 1,791 | -0.018, -0.022 | 11.0%, 12.1% | 4.1%, 3.6% |
| counts changed | 1 | 21,243 | 0.000, +0.001 | 6.5%, 6.6% | 6.9%, 6.9% |
| counts changed | 2 | 5,917 | -0.013, -0.016 | 10.5%, 11.3% | 6.1%, 6.2% |
| counts changed | 3 or more | 661 | -0.053, -0.050 | 19.3%, 23.9% | 4.3%, 3.2% |

The held-out set has about 714 more ads below the 5% point than 5% of its size. The three
changed-count rows alone hold about 780 ads over their 5%, and the one-bath ads with counts
as before fall short of theirs. Changed-count ads with one bath are wide on both tails with
no shift, so their error is one of scale. With two or more baths the ask is also lower
than predicted.

Other classes on the same ads:

- Four or more bedrooms with counts as before: `res` -0.012 and -0.016, low 6.2% and 8.3%
  (2,228 ads).
- In the four lower tiers of predicted rent, more baths go with a lower ask against
  prediction (`tiers.py`; near $6,000 a month: one bath -0.001, two -0.009, three -0.071
  with 21.5% low), so the bath gap is no effect of the price tier. The top two tiers
  differ: one bath is below two in both (tier 4: -0.015, -0.005, -0.041; top 3%: -0.023,
  -0.004, -0.015). The top 3% of predicted rents with counts as before has low 9.9%, high
  5.6%, sd z 1.11.
- First floor by the unit label (`floors.py`; the ads file's `physical_floor` is empty, so
  the label's floor is used, known for 74.5% of these ads): `res` -0.013 and -0.015 against
  about -0.005 on other floors, low 7.5% and 9.0% (9,161 ads). Elevator buildings -0.017
  with 10.0% low, walkups -0.013 with 7.7% low. This repeats the first-floor lead of
  `docs/notes/duplex-scale-2026-11-18.md`.
- Depth of history (`regimes.py`): the low share is level across the number of training
  ads of the unit (4.6% to 5.8%) and of the building (4.9% to 6.4%). Ads within three
  months of the unit's last training ad have sd z 1.05, low 7.9% and high 5.6% (5,561
  ads): the predictive is narrow just after a unit's own ad.
- Rent-stabilized wording (`dom2.py`, last table; 3,268 ads with a text): `res` -0.016 and
  -0.021, low 8.7% and 9.8%. These close fast (below), so they are low prices, and the
  page should go on showing them.

### The two-bath gap belonged to 2022 to 2024

Counts as before, `res` by year of the ad (`bathtime.py`):

| year | 1 bath | 2 baths | 3 or more |
|---|---|---|---|
| 2020 | -0.002 | +0.008 | -0.005 |
| 2021 | -0.004 | +0.011 | +0.012 |
| 2022 | -0.011 | -0.018 | -0.013 |
| 2023 | -0.008 | -0.018 | -0.032 |
| 2024 | -0.005 | -0.012 | -0.024 |
| 2025 | -0.004 | -0.009 | -0.013 |
| 2026 | -0.002 | 0.000 | -0.017 |

The model's bath steps are constant over time. Asks of two-bath apartments ran above them
in 2020 and 2021 and below them from 2022 to 2024, and by 2026 the gap is gone. The gap of
three or more baths stays: from 2024 on, among units with history from 2022 on, -0.012 and
-0.018 by half with 8.2% low on both.

## The Deals model's backtest

`backtest.py` scores `range-j` with `drift_score.score_run`. The layout and range marks of
the Deals model cover changed counts in the mean, and the backtest shows the mean handled
and the scale still narrow:

| ads | n | res | sd z | low | high |
|---|---|---|---|---|---|
| counts as before | 5,783 | +0.003 | 0.94 | 4.2% | 4.2% |
| counts changed | 395 | +0.005 | 1.16 | 7.9% | 7.9% |
| no unit history | 3,168 | +0.023 | 1.06 | 4.7% | 9.4% |
| 1 full bath | 7,101 | +0.008 | 0.95 | 3.9% | 5.1% |
| 2 full baths | 1,944 | +0.012 | 1.09 | 6.0% | 8.4% |
| 3 or more | 301 | +0.028 | 1.32 | 11.0% | 14.3% |

Three-bath ads with counts as before have 13.8% low (145 ads). Ads with no unit history in
the top two tiers of predicted rent are asked 8.6% to 9.0% above prediction with 24% above
the 95% point, which matters for calibration and nothing for deals. Of the 425 backtest
ads below the 5% point, 31 have changed counts and 33 have three or more baths.

## Sizes by calibration on stored predictions

`calib2.py` follows `calib.py` of the duplex note: each held-out predictive is approximated
by a Student-t on its median and quartiles, a class's scale is multiplied by m and its
centre moved by d, m and d are picked on each half of buildings and scored on the other.
l2bt, 2022 on. The control class picks m = 0.9, so true factors are somewhat higher than
the picks. All years give the same picks.

| class | m picked | d picked | cross-fit elpd gain (SE) |
|---|---|---|---|
| 3 or more baths, counts as before | 1.15 | | +30 (8) |
| top 3% of predicted rent | 1.15 to 1.2 | | +51 (13) |
| counts changed, 1 bath | 1.1 | | +102 (23) |
| counts changed, 2 baths | 1.2 | | +163 (22) |
| counts changed, 2 baths | 1.2 | -0.015 to -0.02 | +270 (33) |
| counts changed, 3 or more baths | 1.5 | | +85 (16) |
| counts changed, 3 or more baths | 1.35 to 1.4 | -0.04 | +150 (20) |
| all 3 or more baths | 1.25 | | +92 (16) |
| all 3 or more baths | 1.2 | -0.03 to -0.035 | +219 (26) |
| all 2 baths | | -0.01 | +295 (28) |
| 4 or more bedrooms | | -0.015 | +45 (10) |
| control | 0.9 | -0.005 | +180 (22) |

The held-out elpd of the ads from 2022 on totals about 166,700, so every row is a small
share of it.
The two-bath shift is about -0.005 net of the control's and is fading by year.

## Does a low place act like a low price?

`dom2.py` takes closed ads from 2022 on (128,554) and places each ad's first ask in its
predictive. `gradient` is the mean log days on the market of ads whose first ask is below
the 5% point less that of ads between the 25% and 75% points. A low price closes sooner,
so a class with a gradient near zero is one where a low place is something else: an
unmodelled defect of the apartment, or noise.

| class | first asks below 5% | gradient by half (SE about) | closed in 7 days: low against middle |
|---|---|---|---|
| all | 7,662 | -0.23, -0.21 (0.02) | 36% against 29% |
| ordinary (one bath, counts as before, not first floor, duplex, top tier or 4+ bedrooms) | 3,634 | -0.30, -0.27 (0.03) | 41% against 30% |
| counts above the unit's lowest | 1,631 | -0.16, -0.16 (0.04) | 32% against 27% |
| counts below the unit's highest | 752 | -0.20, -0.16 (0.06) | 35% against 31% |
| 2 baths, counts as before | 1,017 | -0.21, -0.20 (0.05) | 29% against 22% |
| 3 or more baths | 305 | -0.43, -0.45 (0.08) | 24% against 14% |
| first floor | 792 | -0.15, -0.14 (0.05) | 34% against 29% |
| duplex wording | 559 | -0.15, -0.07 (0.07) | 28% against 24% |
| top 3% of predicted rent | 343 | -0.23, -0.23 (0.08) | 18% against 12% |
| months free coded | 623 | -0.06, +0.11 (0.07) | 19% against 17% |
| studio | 1,142 | -0.46, -0.37 (0.06) | 45% against 30% |
| 1 bedroom | 2,712 | -0.26, -0.27 (0.03) | 39% against 29% |
| 2 bedrooms | 2,380 | -0.18, -0.13 (0.03) | 33% against 29% |
| 3 bedrooms | 1,060 | -0.09, -0.14 (0.04) | 27% against 26% |
| 4 or more bedrooms | 368 | -0.02, -0.03 (0.07) | 24% against 24% |

- The model's low places are real: across all ads a first ask below the 5% point closes
  sooner, and the gradient is strongest for studios and three-bath apartments.
- The gradient falls with the bedroom count and is nil at four or more. A low place in a
  large apartment says less about price. Four-bedroom ads are also asked below prediction
  on average (above), so the model over-predicts some of them.
- Ads with changed counts, a first floor or duplex wording have about half the ordinary
  gradient, which fits a wider noise for those classes: part of their low tail is noise.
- Ads with coded free months show no gradient. A net price far below prediction closes no
  sooner than one in the middle.
- By word (same script): rent-stabilized, walk-up and "flights" ads below the 5% point
  close in a median of 7 to 8 days. Condominium, doorman and full-service wording goes with
  longer times at every place and keeps a normal gradient (-0.20 to -0.31). Ads with
  fee-disclosure wording ("refundable") have no gradient (+0.04, +0.05).

## Follow-up: which changed-count ads, and what the Deals model leaves

Five further checks, run after the sections above were merged. Scripts `nbhd.py`,
`layout.py`, `kinds.py`, `kinds_hist.py` and `down.py`; logs under `logs/`.

**Neighbourhood and period hold little.** For each held-out ad of l2bt, `nbhd.py` takes the
mean error of the other held-out ads of its neighbourhood and quarter (127,126 ads have 20
or more others). That mean has an sd of 0.0098 and explains 0.30% of the error variance
(slope 0.42, se 0.03; 0.44 and 0.39 by half). Half years and years explain 0.36% and
0.37%. In the lowest twentieth of that mean, 8.2% of ads are below the 5% point against
5.3% in the middle half.

**The misfit is in ads that differ from the unit's last training ad.** Of the 27,822
changed-count ads on l2bt (`layout.py`), 13,061 code counts that differ from the unit's
last training ad: sdz 1.19 and 1.22 by half, with 9.6% and 10.6% below the 5% point. The
other 14,761 equal the last ad and differ from an older one: sdz 0.98, with 5.9% and 5.7%
below. The misfit does not grow with the years since the last ad up to five years (sdz
1.23, 1.18, 1.23) and is 1.31 beyond five. l2bt has no mark for a change against the last
ad, and it leaves a level by kind of change, the same in both halves: a bath more -0.042,
a bath fewer +0.039, a bedroom more -0.020, a bedroom fewer +0.019 (`kinds_hist.py`).

**The Deals model already carries those levels.** `drift_building_bedtext_layout.py` marks
a row whose bedrooms or baths are above or below the apartment's previous training ad, and
the range module adds marks against the range of its earlier ads. `kinds.py` rebuilds the
marks on the 9,346 backtest ads:

| backtest class | ads | res (se) | sdz | below 5% | above 95% |
|---|---|---|---|---|---|
| differs from the previous ad | 864 | +0.010 (0.004) | 1.14 | 7.5% | 8.7% |
| range mark only | 691 | -0.006 (0.003) | 0.98 | 5.8% | 3.9% |
| no mark, unit seen in training | 5,102 | +0.004 (0.001) | 0.93 | 4.0% | 4.1% |
| no unit history | 2,689 | +0.024 (0.003) | 1.06 | 4.4% | 9.6% |

By previous-ad mark the levels are within two standard errors of the unmarked ads: more
bedrooms +0.013 (0.006, 349 ads), fewer bedrooms +0.006 (0.007, 376), more baths +0.011
(0.011, 157), fewer baths +0.004 (0.011, 187). The spread is what stays wide: sdz 1.05,
1.18, 1.24 and 1.24 in that order, and 1.49 for the 42 marked ads with three baths (16.7%
below the 5% point, 21.4% above the 95% point). Ads with a range mark alone are calibrated.

**The history agrees once a level is taken out.** `kinds_hist.py` removes from each kind of
change its mean l2bt error in the other half of buildings and recomputes each ad's place
under the Student-t approximation of `calib2.py`:

| kind against the last training ad | ads | below 5% | above 95% | sdz |
|---|---|---|---|---|
| bath fewer | 1,394 | 10.0% | 10.0% | 1.27 |
| bath more | 1,549 | 11.2% | 10.0% | 1.29 |
| bedroom fewer | 3,874 | 7.8% | 7.7% | 1.17 |
| bedroom more | 3,990 | 7.3% | 7.1% | 1.13 |
| both fewer | 999 | 7.8% | 8.7% | 1.19 |
| both more | 1,007 | 9.9% | 9.5% | 1.26 |
| mixed | 248 | 10.5% | 12.9% | 1.30 |
| same as the last ad | 116,800 | 4.1% | 3.9% | 0.94 |

Ads with fewer rooms than the last ad fall below the 5% point at 9.4% and 7.2% by half and
at 7.6% to 8.9% in each year from 2022 to 2026. Ads with more rooms: 7.1% and 10.1% by
half, 7.9% to 9.1% by year.

**Outcomes support the `rooms_up` caution and none for fewer rooms.** The Deals page
already cautions an ad with more rooms than the previous ad. `down.py` follows the
backtest's open ads by their first ask:

| backtest class | ads | first ask below 5% | later cut | median days |
|---|---|---|---|---|
| fewer rooms, no caution | 286 | 15 | 0.0% | 14 |
| `rooms_up`, no other caution | 317 | 19 | 31.6% | 23 |
| no caution, counts as previous | 8,276 | 295 | 12.9% | 26 |

Below the 10% point the three rows have 25, 30 and 496 ads, cut at 8.0%, 33.3% and 16.3%.
The counts are small. Of the 15 low asks with fewer rooms none was cut, and 2 of the 25
below the 10% point were, so nothing here marks such an ask as a false low price. Of the 19
low asks with more rooms 6 were cut, more than twice the ordinary share, and the 30 below
the 10% point agree. On the history (`dom2-l2bt.log`) both changed-count
classes have a shallower gradient of days on place (-0.16 to -0.20 against -0.27 to -0.30)
and a cut share among low first asks of 5.2% to 6.8% against 2.6% and 3.0%.

What this settles:

- No level term for a bath or bedroom change is missing from the Deals model.
- The wider spread of ads that differ from the previous ad is a noise factor of about 1.15
  to 1.25, more with three baths. It would move 20 to 30 of the 425 backtest ads below the
  5% point. The Deals market fits hold the scales fixed, and a model with noise phases
  cannot (`drift.py` refuses the pair), so the factor needs a fit with free scales. It
  stays in the list for the next refit of the base model.
- The outcomes give no ground for a `rooms_down` caution, on 15 low asks.
- Ads of units with no training ad are asked 2.4% above the Deals model's median, with
  9.6% above the 95% point and no excess below the 5% point. That gap is the one recorded
  on 2026-11-11 (`docs/notes/outlier-sprint-2026-11-11.md`, "Units with no ad in
  training"), with candidates U4, U3 and the turnover column in `docs/TODO.md`.

## What follows

No class here passes the rule for a Modal fit of its own. Each is confirmed on both halves
of buildings, and each is small: on the backtest the changed-count and three-bath classes
hold about 60 of the 425 ads below the 5% point (31 and 33, with some in both). The leads
for the next refit of the base model, with their sizes from the calibration:

1. A noise factor for ads whose counts differ from the unit's previous training ad (the
   follow-up section narrows the class to these), 1.1 with one bath rising to about 1.5
   with three or more.
2. A level near -0.03 and a noise factor near 1.2 for three or more baths.
3. A noise factor of 1.15 to 1.2 for the top 3% of predicted rents.
4. The first-floor level (about -0.01) and the duplex factor, both already recorded.
5. A level near -0.015 for four or more bedrooms.

For the Deals page without a fit: the outcome table says a low place means less for large
apartments and for ads with coded free months. A page note or an ordering that leans on
that table is a site change and needs no model.

The served Deals model has no latest-split fit, so these tables come from the base and
bed-text models plus its 9,346-ad backtest. A latest-split fit of the Deals model would
give the same 190,000-ad evidence for the model on the page. Ben declined that spend
earlier in the day; it remains the one fit this work would recommend.

## Follow-up, 2026-11-19: little of the low tail is gathered in buildings (`bybuilding.py`)

The share of held-out ads below the 5% point is 5.1% to 6.2% whatever the building's count
of held-out ads. Buildings with ten or more held-out ads and a quarter of them low number
95 and hold 386 low ads; a binomial null at the overall low share gives 132 on average and
208 at most in 200 draws. The excess is real and small: near 250 of 11,168 low ads (2%),
in buildings averaging 14 held-out ads with a mean gap of -0.047. That is too few ads for
a building-level term.

The Deals page's backtest card now carries the bedroom rows of the outcome table above
(closed in 7 days, low against middle). The free-months row is left off the page: ads with
coded free months are mostly in lease-ups, where an ad's days listed may not follow one
apartment, so its flat gradient is not read as a statement about price (untested; the
next section tests it).

## Follow-up, 2026-11-19: days listed of free-month ads do not follow price (`free.py`)

The lease-up guess above fails. Among the 128,554 closed ads from 2022 on, 11,277 have coded
free months. Their gradient (mean log days of ads below the 5% point less that of ads
between the 25% and 75% points) by the count of other units' ads the building opened in
the two years before:

| Building's ads in two years | Free months: ads, low, gradient (SE) | No free months: ads, low, gradient (SE) |
|---|---|---|
| 0 to 9 | 1,180, 66, +0.14 (0.14) | 41,923, 2,418, -0.26 (0.02) |
| 10 to 49 | 2,691, 167, +0.08 (0.08) | 42,415, 2,707, -0.19 (0.02) |
| 50 to 199 | 4,788, 245, +0.05 (0.08) | 25,635, 1,412, -0.21 (0.04) |
| 200 or more | 2,618, 145, -0.10 (0.14) | 7,304, 502, -0.47 (0.09) |

The gradient of free-month ads is flat in quiet buildings as in busy ones, so lease-ups, by
this proxy, do not explain it. Nor does the basis of the price. For the 11,229 free-month ads with a page
rent and a concession between 0.005 and 0.7 in logs, the gap can be taken on the net ask (the fit's target) or on the gross rent the page
shows (median concession 0.087 in logs). Ranked within free-month ads, the lowest tenth
against the middle half has a gradient of +0.02 and +0.03 by half of buildings on the net
gap and 0.00 and 0.00 on the gross gap. A regression of log days on the gap in logs, with
standard errors clustered by building, gives a slope of 0.11 (0.17) on the net gap for
free-month ads and 1.85 (0.06) for ads without free months.

So the days listed of an ad with coded free months show no gradient in price that these
data can detect, net or gross (the slope's interval reaches about 0.44, far under 1.85).
Such ads stay up a median 21 to 25 days outside the busiest buildings (14 to 17 there), and
days listed cannot say whether a low place among them is a low price. The model's level
is not in question: the share of free-month ads below the 5% point is 5.1% to 6.2%, as for
other ads. The likely reading is that such ads are kept up by a leasing office on its own
schedule; that is a guess. For Deals nothing changes: a free-month ad's place is computed
on its net ask, and the outcome evidence for low places rests on ads without free months.

## Follow-up, 2026-11-19: coded fields no earlier check read (`fields.py`)

No fit and no money spent. The 129,861 held-out ads from 2022 on (5.55% below the 5% point,
4.17% above the 95% point), grouped by each coded field of the ads table that the checks
above had not read: lease term, square feet given or missing, laundry, heating and cooling,
pet policy, coded views, coded window exposures, the count of floor plans, values taken from
text, an ad taken down and put back, and coded conflicts. `fields.log` has every group,
with the low share in each half of the buildings.

| Field | Groups of 500 ads or more | Low share, smallest to largest | Mean gap, smallest to largest |
|---|---|---|---|
| Lease term (coded on 11,472 ads) | 12 months, 13 to 17, 18 or more | 4.7% to 5.9% | −0.010 to +0.002 |
| Square feet | given (35,062), missing | 5.4% to 6.0% | −0.006 to −0.005 |
| Laundry | in the unit, in the building | 5.2% to 5.8% | −0.005 to −0.004 |
| Pet policy | three coded values | 5.0% to 6.0% | −0.007 to −0.004 |
| Views | eight commonest codings and the rest | 5.3% to 6.8% | −0.008 to −0.004 |
| Window exposures | seven codings of 500 ads or more and the rest | 4.7% to 7.8% (4.7% to 6.7% in groups over 1,000) | −0.011 to −0.002 |
| Short-term | coded false (11,560), not coded | 5.2% to 5.6% | −0.006 to −0.006 |
| Floor plans | none, one, two | 5.1% to 5.9% | −0.007 to −0.004 |
| Values from text | none, one | 5.2% to 5.6% | −0.006 to −0.004 |

Heating and cooling has one large group (central air, 42,398 ads, 5.8% low). Furnished,
breaks and conflicts are coded on too few held-out ads to say anything (2 to 183 ads).
 The largest low share in a group over 1,000 ads is 6.8% (views of
city, skyline and water, 1,977 ads), and it is 8.7% in one half of the buildings and 4.9%
in the other, so it does not hold. Some groups differ a little from the overall rate at these sizes: uncommon view codings
(6.5% of 9,293 ads), square feet given (6.0% against 5.4% when missing) and laundry in the
unit (5.8% against 5.2% in the building). No group over 1,000 ads has a low share more than
about a fifth above the overall rate in both halves of the buildings. These are small
shifts and no field marks the ads asked far below the prediction, which agrees with the
text check above: little of what is left of the low tail is in what an ad codes or says.

## Follow-up, 2026-11-19: buildings new to the data (`bage.py`)

No fit and no money spent. On the one backtest day the low share was highest in buildings
that entered the data one to five years before
(`docs/notes/turnover-low-asks-2026-11-18.md`: 10.8% to 11.6% inside the top turnover
quartile). The same split on the 129,861 held-out ads from 2022 on, by years from the
building's first training ad to the held-out ad:

| Years in the data | Ads | Below the 5% point (se) | Above the 95% point | Mean gap | Low share by half of the buildings |
|---|---|---|---|---|---|
| Up to 1 | 1,516 | 6.9% (0.7) | 5.8% | −0.010 | 5.5%, 8.2% |
| 1 to 2 | 2,379 | 6.5% (0.5) | 5.3% | −0.006 | 6.6%, 6.5% |
| 2 to 5 | 8,500 | 6.1% (0.3) | 4.3% | −0.009 | 6.0%, 6.2% |
| 5 to 8 | 17,909 | 6.5% (0.2) | 4.1% | −0.009 | 6.6%, 6.4% |
| Over 8 | 99,557 | 5.3% (0.1) | 4.1% | −0.004 | 5.3%, 5.3% |

Buildings under eight years in the data have about one point more of their ads below the
5% point and a mean gap lower by about 0.005. The same order holds among ads whose counts
match the unit's earlier ads (4.8% over eight years against 5.2% to 6.0%) and in buildings
with 30 or more training ads (5.3% against 6.0% to 7.0%). In the first two years the high
tail is wider as well (5.3% to 5.8% against 4.1%), which is an interval a little too narrow
for young buildings as much as a mean set too high.

The history has nothing like the backtest day's 11%. The young buildings' excess is about
300 low ads of 7,200 (30,304 ads at about 6.4% against 5.3%), and the mean shift of 0.005
is a twentieth of the distance to the 5% point. No term: a shift of that size would move
no ad on or off the Deals page. The interval for young buildings is a candidate for the
next base refit's scale terms, with the changed-count items above.
