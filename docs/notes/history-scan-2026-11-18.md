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
calls the price net (-0.014 on both halves; ads with the basis unstated +0.005). It is an
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
changed-count rows alone hold about 774 ads over their 5%, and the one-bath ads with counts
as before fall short of theirs. Changed-count ads with one bath are wide on both tails with
no shift, so their error is one of scale. With two or more baths the ask is also lower
than predicted.

Other classes on the same ads:

- Four or more bedrooms with counts as before: `res` -0.012 and -0.016, low 6.2% and 8.3%
  (2,228 ads).
- Within each tier of predicted rent, more baths go with a lower ask against prediction
  (`tiers.py`; near $6,000 a month: one bath -0.001, two -0.009, three -0.071 with 21.5%
  low), so the bath gap is no effect of the price tier. The top 3% of predicted rents with
  counts as before has low 9.9%, high 5.6%, sd z 1.11.
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
| control | 0.9 | -0.005 | +164 |

The held-out elpd of these ads totals about 237,600, so every row is a small share of it.
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
  close in a median of 7 days. Condominium, doorman and full-service wording goes with
  longer times at every place and keeps a normal gradient (-0.20 to -0.31). Ads with
  fee-disclosure wording ("refundable") have no gradient (+0.04, +0.05).

## What follows

No class here passes the rule for a Modal fit of its own. Each is confirmed on both halves
of buildings, and each is small: on the backtest the scale changes would move about 60 of
the 425 ads below the 5% point. The leads for the next refit of the base model, with their
sizes from the calibration:

1. A noise factor for ads whose counts differ from the unit's training ads, 1.1 with one
   bath rising to about 1.5 with three or more.
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
