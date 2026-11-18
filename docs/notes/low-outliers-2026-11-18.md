# Ads priced far below the model's prediction: a broker read and a layout-change term

Written at 9:55 AM ET on 2026-11-18, before the fit below is launched.

Ben asked for a review of the ads asking far less than the model predicts, and for features
or data fixes for what the review finds. Every such ad shows on Deals as a bargain, so a
trait the model lacks puts a false bargain at the top of the table.

## The read

`build.py` in this note's folder drew four sets and wrote them into 13 shuffled groups of
about 20 ads. Readers on a small model answered the brief in `READER.md` for each ad without
knowing its set.

| Set | Ads | Source |
|---|---|---|
| below | 110 | held-out ads of the base model's latest-split pool `b9` since 2024-07 with `cdf` under 0.01, in the read half of the buildings (the halves of 2026-11-15), income-flagged ads left out |
| control | 55 | the same pool with `cdf` between 0.25 and 0.75 |
| deal | 60 | the top of the live Deals file of 2026-11-17 among ads with no caution, at most two a building |
| dealctl | 30 | live Deals ads with no caution and `below_share` between 0.25 and 0.75 |

Each packet carried the ad's text, coded fields, amenity tags, the apartment's earlier ads
with dates and asks, and the text of the previous ad. Twelve packets of the below set went
out without their coded fields, and the readers reported those ads as having no coded ask.
The ads table holds an ask for each of them. `build.py` looked each ad up in the ads table by
the dataset's unit id, and 13 ads of the below set and 9 of the control set carry the "~1"
ending the dataset gives a later piece of a unit's history, which the ads table lacks. Those
packets went out with the text alone, without coded fields or earlier ads.

`tally.py` gives the share of each set carrying each reason code (percent):

| Reason | below | control | deal | dealctl |
|---|---|---|---|---|
| quick cut after sitting | 13 | 5 | 25 | 20 |
| earlier ads describe a different apartment | 12 | 0 | 10 | 3 |
| bedroom count above what the text supports | 12 | 5 | 17 | 3 |
| concession gone or added | 12 | 2 | 3 | 10 |
| restrictions | 11 | 2 | 3 | 10 |
| earlier ad sold a renovation or furniture | 10 | 2 | 7 | 7 |
| regulated rent | 9 | 2 | 0 | 0 |
| basement or ground floor | 9 | 7 | 18 | 10 |
| income program | 8 | 0 | 2 | 0 |
| condition | 8 | 0 | 2 | 3 |
| high floor of a walkup | 8 | 4 | 3 | 3 |

The readers called 18% of the below set and 18% of the top deals a sound apartment asking
less than its history or neighbours for no reason they could find, against 4% and 0% of the
two control sets. They found a reason for the low ask in 55% of both.

Regulated and income wording explains about a sixth of the below set and almost none of the
top deals. The text flags of 2026-11-13 and the Deals `income` caution already cover it
(`docs/notes/text-flags-2026-11-13.md`, `docs/notes/income-flag-2026-11-14.md`), so I took it
no further.

The codes recurring in both the below set and the top deals are a bedroom count the text does
not support and earlier ads describing a different apartment. The readers' notes on those ads
keep describing one situation: the apartment's earlier ads coded fewer rooms. A studio
returns as a one-bedroom, a dining room becomes a fourth bedroom, a second bath appears in
the fields. The model adds its whole step for the extra room on top of the level it learned
from the apartment's earlier asks, and the landlord's ask rises by less.

## The trait, coded without the rent

For each ad I compare its coded bedrooms, and its baths with a half bath as 0.5, against the
apartment's previous ad: the latest training row of the same building and unit priced on an
earlier day. `rentfrontier.drift_building_bedtext_layout.changes` writes four marks:
`ad:beds_up_prev`, `ad:beds_down_prev`, `ad:baths_up_prev`, `ad:baths_down_prev`. The unit id
is read without the "~1" ending the dataset gives a piece of a unit's history after a jump of
two or more bedrooms, so an ad after such a jump still finds the ad before it. No mark reads
a rent.

`free.py` runs the free check on b9's 189,647 held-out ads, income-flagged ads left out. For
each mark it gives the mark's rate in the far-below, control and far-above sets, the mean gap
(log ask minus the model's median) of marked ads, and the share of the squared standardized
gap a level for the mark explains out of fold, against the 95th percentile of the same share
under 200 shuffles of the mark (seed 20261118, folds by building).

| Half | Mark | Ads | % of far below | % of control | % of far above | Mean gap | Explained | Shuffled 95% |
|---|---|---|---|---|---|---|---|---|
| unread | beds up | 2,228 | 8.3 | 1.9 | 3.4 | -0.029 | 0.00188 | 0.00002 |
| unread | beds down | 2,247 | 4.4 | 1.8 | 10.4 | +0.025 | 0.00336 | 0.00001 |
| unread | baths up | 1,792 | 6.8 | 1.2 | 5.2 | -0.037 | 0.00325 | 0.00000 |
| unread | baths down | 1,633 | 3.5 | 1.1 | 9.4 | +0.039 | 0.00538 | 0.00001 |
| read | beds up | 2,191 | 7.4 | 1.8 | 3.5 | -0.028 | 0.00168 | 0.00001 |
| read | beds down | 2,194 | 4.4 | 1.8 | 10.1 | +0.023 | 0.00278 | 0.00002 |
| read | baths up | 1,635 | 9.2 | 1.0 | 5.3 | -0.039 | 0.00352 | 0.00001 |
| read | baths down | 1,558 | 4.6 | 1.2 | 8.7 | +0.039 | 0.00480 | 0.00001 |

Every mark passes on the unread half, which the readers never met. The four together explain
0.0117 of the unread half's squared gap. An unmarked ad's mean gap is -0.004 to -0.006.

Marked ads sit in both tails more often than control ads: a change of layout widens the gap
as well as shifting it. The four levels address the shift only.

A level change of about a tenth of a room step moves no ad out of the far-below set by
itself. Shifts fitted on one half and applied to the other, with each ad's own predictive
scale and a Student-t of 4 degrees of freedom, give about +462 elpd on the unread half
(SE 41, 6,995 marked ads) and +370 on the read half (SE 40). The fitted shifts are -0.019
and -0.020 (beds up), +0.021 and +0.025 (beds down), -0.031 and -0.029 (baths up), +0.039
both ways (baths down).

Square footage differing by 15% or more from the previous ad fails the same check, and I
dropped it.

## The marks on Deals and on the backtest

Among live Deals ads with no caution, 8.0% of the 87 with `below_share` up to 0.02 code more
bedrooms than the apartment's previous ad and 10.3% code more baths, against 2.3% and 0.9%
of ads between 0.25 and 0.75. Of the 60 top deals the readers saw, 7 carry one of those two
marks, and the readers called none of the 7 a sound deal (5 with a reason for the low ask, 2
ordinary) against 11 of the other 53.

`place.py` puts the marks on the backtest as of 2025-11-10 under the served model's backtest
run `heldbed-j`. Of the 9,346 open ads, 864 carry a mark (9.2%).

| Open ads | Ads | Mean place of first ask | In the lowest tenth | Final-ask elpd an ad | Lowest-tenth ads later cut |
|---|---|---|---|---|---|
| all | 9,346 | 0.597 | 598 (6.4%) | 1.069 | 17.2% |
| no mark | 8,482 | 0.599 | 508 (6.0%) | 1.109 | 15.9% |
| beds up | 349 | 0.492 | 46 (13.2%) | 0.821 | 23.9% |
| beds down | 376 | 0.650 | 23 (6.1%) | 0.634 | 17.4% |
| baths up | 157 | 0.445 | 31 (19.7%) | 0.494 | 45.2% |
| baths down | 187 | 0.652 | 14 (7.5%) | 0.611 | 7.1% |

An ad coding more baths than the apartment's previous ad is three times as likely as an
unmarked ad to be a Deals candidate, and the landlord later cut the ask on 45% of those
candidates against 16%. A later cut on an ad the model called cheap says the model's price
was too high.

## Model

`drift-building-bedtext-layout` (`rentfrontier.drift_building_bedtext_layout`) is the served
model's design followed by the four marks as global columns with the flag prior. The sampler,
priors and settings are the served model's.

Inside a fit the previous ad of a training row is the row before it in the unit's training
history, so a mark falls on the first ad after a change and later ads of the changed layout
carry none. The unit's drift takes up the rest. For held-out ads every row is compared with
the unit's last training row, as on the Deals page.

## Fit

A held-scales fit on the backtest, the same settings as `heldbed-j`, one H100 container,
about $2, launched from `/data1/apartments/serve/master` at the merge commit of this note:

```sh
IN=/data1/apartments/pipeline/datasets/rows-ddd2fe8f5da041b8.parquet
J=/data1/apartments/frontier/datasets/b0-ddd2fe8f5da041b8-alldata-dense-nyc-asof-20251110
ops/modal-fit --outside-budget --gpu H100 --dataset "$J-bedtext" --input "$IN" --split market \
  --baseline drift-building-b0-market-67d14e17-j9 COMMIT layout-j \
  drift-building-bedtext-layout b0 2 200 3600 20 --seed 1 --level-dof 4 --scales-fixed base-j9 --no-loo --no-heldout
```

The paired reference is `drift-building-bedtext-b0-market-f288a423-heldbed-j`, compared with
`place.py ADS heldbed-j layout-j`.

## Predictions

1. The fit passes the gate. Each mark sets about 20,000 to 56,000 training rows.
2. Coefficients: beds up -0.020 (between -0.035 and -0.010), beds down +0.020 (+0.010 to
   +0.035), baths up -0.030 (-0.045 to -0.015), baths down +0.035 (+0.020 to +0.050). Inside
   the fit the unit's drift competes for the same gap, so I expect the smaller half of each
   range more often than the larger.
3. Final-ask elpd over the 9,346 open ads rises by about 45 (between 20 and 75), with a
   clustered SE near 12. The 8,482 unmarked ads move by less than 10 either way.
4. Marked ads in the lowest tenth of first-ask places fall from 90 to about 72 (65 to 82):
   beds up from 46 to about 37, baths up from 31 to about 23. Beds down and baths down
   together rise from 37 to about 42.
5. At least 95% of `heldbed-j`'s lowest tenth stays in the new run's lowest tenth.

If the gate passes and the elpd gain is above two SEs with unmarked ads no worse than one
SE, I run the market twin (about $2, `--scales-fixed base-n9`) and publish Deals from it.
If the marks still fill the top of the table after the shift, I add a Deals caution for an
ad coding more bedrooms or baths than the apartment's previous ad.

## Other traits checked while the fit ran

`dub.py` compares the readers' doubts about the bedroom count with the bed-text flag the
served model already reads. Of the 10 top deals with a doubted count none carries the flag,
against 5 of 13 in the below set. The wording in those 10 ads is vaguer than the flag's
patterns: a flexible layout, an extra room offered as an office or guest room, a sleeping
loft, a wall not yet installed, a railroad layout.

`vague.py` codes eight such patterns from the latest description of each of b9's held-out
ads without the bed-text flag and runs the free check on each (100 shuffles).

| Pattern | Unread ads | Mean gap | Explained (unread) | Shuffled 95% | Read half |
|---|---|---|---|---|---|
| flexible layout or space | 1,416 | +0.006 | 0.00005 | -0.00005 | fail |
| "can be divided", wall not installed | 407 | -0.000 | -0.00017 | -0.00007 | fail |
| office or den offered as a bedroom | 883 | +0.006 | -0.00004 | -0.00005 | fail |
| sleeping loft, ladder | 604 | +0.003 | -0.00012 | -0.00007 | fail |
| railroad | 720 | -0.014 | -0.00001 | -0.00006 | pass |
| "studio" in an ad coded with a bedroom | 4,785 | +0.003 | 0.00022 | -0.00007 | pass |
| windowless or interior room | 102 | -0.012 | -0.00010 | -0.00006 | fail |
| roommates, shares | 1,563 | -0.006 | -0.00013 | -0.00006 | fail |

The largest share explained is 0.0002, a fiftieth of the layout marks' 0.0117, and only the
"studio" wording passes on both halves, with a gap of +0.003. I dropped the vague wording.
The doubts the readers raised on the top deals are mostly layout changes against the
apartment's earlier ads, which the four marks cover.

`chg.py` runs the same check on free months gained, lost or kept against the apartment's
previous training ad (`months_free` of the ads table). The gap is -0.003 where an ad gained
free months and -0.008 to -0.011 where it lost them, and no mark explains more than 0.0004
of either half. Furnished and short-term ads are outside the dataset, so the readers'
"earlier ad was furnished" has no previous training ad to compare with.

`word2.py` runs the check on fifteen more wordings the readers leaned on, coded from the same
descriptions: as-is condition, a renovation named or absent, no pets, no guarantors, ground
floor or basement, small or cozy, price-cut talk, a walkup, no laundry, a shared bath, a tub
in the kitchen, an owner on site, lease dates, a tenant in place. The largest share explained
on the unread half is 0.0002 (a renovation named, gap -0.001 against -0.005 elsewhere). The
rarest wordings carry the largest gaps, -0.030 for a shared bath (49 ads) and -0.032 for a
tub or shower in the kitchen (93 ads), and neither passes on both halves. The building and
apartment levels already hold what these words say about an apartment advertised before.

`feat.py` builds the served design of b9's dataset and saves its 129 unit, ad, doorman,
elevator, gym and flag columns. `featchg.py` compares each column of a held-out ad with the
same column of the apartment's previous training ad, marks the ad where the column rose or
fell, leaves out ads with a layout mark, and runs the check on each mark with at least 150
ads (40 shuffles). The marks with the largest share explained on the unread half:

| Mark against the previous ad | Unread ads | Gap (read) | Gap (unread) | Explained (unread) |
|---|---|---|---|---|
| in-unit laundry gained | 3,862 | +0.010 | +0.010 | 0.0014 |
| dishwasher gained | 9,451 | +0.001 | +0.002 | 0.0008 |
| bed-text flag gained | 929 | -0.025 | -0.026 | 0.0007 |
| in-unit laundry lost | 2,600 | +0.002 | +0.003 | 0.0003 |
| free months lost | 6,557 | -0.010 | -0.009 | 0.0002 |

Every other mark explains 0.0002 or less, among them size up or down by 15%, a floor number
changed, outdoor space, views, the lister's channel and the photo count. The largest is a
ninth of the layout marks' 0.0117 and concerns asks above the prediction: an apartment
gaining a washer since its previous ad asks 1% more than the model expects, which reads as a
renovation between tenancies. An ad gaining the bed-text flag still asks 2.6% under the
prediction with the flag's own term in the model. Neither is large enough for a fit of its
own under the sprint's budget, and both are leads for a later model with a renovation term.

`word3.py` ran five more wordings on the same pool: basement or lower level, a duplex with a
lower level, any duplex, several options in one ad, and heat paid by the tenant. None
explains anything on either half (all at or below zero).

## Results

`layout-j` finished at 10:27 AM ET on 2026-11-18 after 1,539 s of fitting and $1.95. The run
is `drift-building-bedtext-layout-b0-market-45f39590-layout-j`.

1. Gate: hit. Across 264 quantities the largest R-hat is 1.004 and the smallest ESS is 680.
   The marks set 54,788 (beds up), 56,289 (beds down), 22,361 (baths up) and 19,800 (baths
   down) training rows.
2. Coefficients: hit, all four inside their ranges. Beds up -0.013 (90% interval -0.0139 to
   -0.0126), beds down +0.028, baths up -0.026, baths down +0.025.
3. Elpd: the total is inside its range and under the point prediction, and the unmarked ads
   miss. Final-ask elpd over the 9,346 open ads rises by 22.8 (SE 13.8). The 864 marked ads
   gain 39.4 (SE 12.3) and the 8,482 unmarked ads lose 16.6 (SE 6.9), where I predicted a
   move under 10.
4. Lowest tenth: mixed. Beds up falls from 46 to 31 and baths up from 31 to 22, at or past
   the predictions. Beds down rises from 23 to 41 and baths down from 14 to 29, far past
   the predicted 42 for the pair, so the marked ads in the lowest tenth stay at 90.
5. Overlap: narrow miss. 561 of `heldbed-j`'s 598 lowest-tenth ads (93.8%) stay there.

The gain is 1.7 SEs and the unmarked ads are 2.4 SEs worse, so the decision rule fails on
both counts. No market twin of this model is run and the served model stays. The `rooms_up`
caution (`docs/notes/rooms-up-caution-2026-11-18.md`) is how Deals handles these ads.

### The unmarked loss

`after.py` splits the unmarked open ads by the marks on their apartment's training rows.

| unmarked open ads | ads | elpd, layout-j minus heldbed-j |
|---|---|---|
| apartment has no training row | 2,689 | +0.7 (SE 2.5) |
| training rows, none marked | 5,102 | -3.7 (SE 2.8) |
| training rows marked up only | 244 | -5.7 (SE 2.1) |
| training rows marked down only | 176 | -2.6 (SE 3.9) |
| training rows marked both ways | 271 | -5.4 (SE 3.3) |

The 691 ads of apartments with a marked training row lose 13.7 of the 16.6. In those
apartments the count changed in an earlier ad and stayed. The mark took part of the gap on
the first ad after the change, the apartment's level was fitted with that part removed,
and the later ads at the changed count carry no mark. The Model section above expected the
unit's drift to take up the rest, and it did not.

## A second model: marks against the apartment's earlier range

`persist.py` codes the persistent version on the base model's latest-split pool, again
without the rent: the ad's count against the lowest and the highest count among the
apartment's earlier training ads. An ad marked against its previous ad is marked here too,
and the later ads at the changed count keep the mark.

On the unread half, ads with no previous-ad mark:

| mark | ads | mean gap | explained | shuffled 95% |
|---|---|---|---|---|
| beds above the lowest earlier count | 4,537 | -0.009 | 0.0001 | 0.00003 |
| beds below the highest earlier count | 4,374 | +0.001 | 0.0002 | 0.00002 |
| baths above the lowest | 1,480 | -0.016 | 0.0003 | 0.00002 |
| baths below the highest | 1,431 | +0.005 | 0.0002 | 0.00000 |

Each passes the shuffle rule on the unread half, and by a small margin. Jointly on the
unread half, the four previous-ad marks explain 0.0117, the four range marks 0.0093, a
coding against the apartment's first ad 0.0071, and the previous-ad and range marks
together 0.0129. The range marks do less than the previous-ad marks alone and add a tenth
on top of them.

`drift-building-bedtext-layout-range` (`rentfrontier.drift_building_bedtext_layout_range`)
is the layout model's design followed by the four range marks: `ad:beds_above_low`,
`ad:beds_below_high`, `ad:baths_above_low`, `ad:baths_below_high`. On the backtest's rows
they set 90,296, 88,861, 35,013 and 32,457 training rows. Of the 9,346 open ads, 1,555
carry a range mark, and 691 of those carry no previous-ad mark: the same 691 ads as the
last three rows of the table above.

The fit is `layout-j`'s command with the model `drift-building-bedtext-layout-range` and
the name `range-j`, about $2. The single change against the served model is the layout
history term, here in its eight-column coding. `place.py ADS heldbed-j range-j` scores it,
and `after.py heldbed-j range-j` gives the 691 followers.

### Predictions for `range-j`

1. The fit passes the gate.
2. Range coefficients: beds above low -0.010 (-0.020 to -0.004), beds below high +0.005
   (0 to +0.012), baths above low -0.015 (-0.028 to -0.006), baths below high +0.008 (0 to
   +0.020). The previous-ad coefficients shrink toward zero: beds up -0.006 (-0.011 to
   -0.001), beds down +0.022 (+0.015 to +0.027), baths up -0.014 (-0.022 to -0.006), baths
   down +0.018 (+0.010 to +0.024).
3. Against `heldbed-j`, final-ask elpd over the 9,346 open ads rises by about 38 (20 to
   60), SE near 14. The 864 ads with a previous-ad mark gain 30 to 50. The 691 followers
   move from -13.7 to about +3 (-5 to +12). The 7,791 ads with no mark of either kind move
   by less than 6 either way.
4. Ads in the lowest tenth stay within 10 of `layout-j`'s counts for each of the four
   previous-ad marks (31, 41, 22, 29).

If the gate passes, the gain over `heldbed-j` is above two SEs and the 7,791 ads with no
mark are no worse than one SE, I run the market twin (about $2, `--scales-fixed base-n9`)
and publish Deals from it, keeping the `rooms_up` caution. Otherwise the served model
stays, and the layout history is recorded as a term the apartment levels mostly absorb.

### Results for `range-j`

`range-j` finished at 11:17 AM ET on 2026-11-18 after 1,601 s of fitting and $2.04. The run
is `drift-building-bedtext-layout-range-b0-market-d9028c57-range-j`. I scored it with
`place.py` and `after.py` against `heldbed-j`.

1. Gate: hit. The largest R-hat is 1.0042 (`beta[ad:features_unstated]`) and the smallest
   ESS is 676 (`beta[bed=0:full>=2]`). The range marks set 91,002 (beds above low), 89,563
   (beds below high), 35,315 (baths above low) and 32,775 (baths below high) training rows.
2. Coefficients: miss on all eight. The sampler put nearly the whole effect on the range
   marks, where I predicted that the previous-ad marks would keep most of it.

   | Column | Mean | 5% to 95% | Predicted |
   |---|---|---|---|
   | `ad:beds_above_low` | -0.0224 | -0.0233 to -0.0214 | -0.010 (-0.020 to -0.004) |
   | `ad:beds_below_high` | +0.0301 | +0.0292 to +0.0310 | +0.005 (0 to +0.012) |
   | `ad:baths_above_low` | -0.0408 | -0.0422 to -0.0394 | -0.015 (-0.028 to -0.006) |
   | `ad:baths_below_high` | +0.0228 | +0.0214 to +0.0241 | +0.008 (0 to +0.020) |
   | `ad:beds_up_prev` | -0.0002 | -0.0009 to +0.0007 | -0.006 (-0.011 to -0.001) |
   | `ad:beds_down_prev` | +0.0104 | +0.0096 to +0.0113 | +0.022 (+0.015 to +0.027) |
   | `ad:baths_up_prev` | +0.0039 | +0.0025 to +0.0053 | -0.014 (-0.022 to -0.006) |
   | `ad:baths_down_prev` | +0.0073 | +0.0059 to +0.0086 | +0.018 (+0.010 to +0.024) |

   An ad with a previous-ad mark carries the matching range mark too, so its total step is
   the sum of both rows: -0.023 for beds up, +0.041 for beds down, -0.037 for baths up and
   +0.030 for baths down. Each sum is larger than `layout-j`'s coefficient for the same mark.
3. Elpd: hit on every set, with a wider SE than predicted.

   | Set | Ads | Elpd, `range-j` minus `heldbed-j` | SE | Predicted |
   |---|---|---|---|---|
   | All open ads | 9,346 | +48.3 | 18.9 | +38 (20 to 60), SE near 14 |
   | Previous-ad mark | 864 | +39.7 | 16.7 | +30 to +50 |
   | Range mark only (the followers) | 691 | +4.8 | 5.2 | +3 (-5 to +12) |
   | No mark of either kind | 7,791 | +3.8 | 5.8 | within 6 of zero |

   `after.py` splits the 7,791 unmarked ads by the marks on their apartment's training rows.
   No group loses: +0.9 (SE 4.4) on the 2,689 ads with no training row, +2.9 (SE 3.6) on the
   5,102 with unmarked training rows. The loss `layout-j` had on the followers is gone.
4. Lowest tenth: hit. The four previous-ad sets hold 25, 46, 20 and 32 ads in the lowest
   tenth, against `layout-j`'s 31, 41, 22 and 29. Against `heldbed-j` the ads coding more
   rooms than before fall from 46 to 25 (beds) and from 31 to 20 (baths), and the ads coding
   fewer rooms rise from 23 to 46 and from 14 to 32. In all, 552 of `heldbed-j`'s 598
   lowest-tenth ads stay there.

The decision rule is met: the gate passes, the gain is 2.6 SEs, and the 7,791 unmarked ads
are 0.7 SEs better. I run the market twin and, if it passes the gate, publish Deals from it
with `range-j` as its backtest, keeping the `rooms_up` caution.

### Predictions for `range-m`

`range-m` is the same model on every ad to date with the market pool's scales, launched
from `/data1/apartments/serve/master` at the merge commit of this section:

```sh
IN=/data1/apartments/pipeline/datasets/rows-ddd2fe8f5da041b8.parquet
M=/data1/apartments/frontier/datasets/b0-ddd2fe8f5da041b8-alldata-dense-nyc-market
ops/modal-fit --outside-budget --gpu H100 --dataset "$M-bedtext" --input "$IN" --split market \
  --baseline drift-building-b0-market-67d14e17-n9 COMMIT range-m \
  drift-building-bedtext-layout-range b0 2 200 3600 20 --seed 1 --level-dof 4 --scales-fixed base-n9 --no-loo --no-heldout
```

1. The fit passes the gate, in 1,300 to 1,800 s of fitting and about $2.
2. Each of the eight layout coefficients is within 0.004 of its `range-j` mean, with the
   same sign for the four range columns.
3. On the staged Deals table, 60% to 85% of the first 100 uncautioned ads are also in the
   first 100 of the live table from `heldbed-m`. Among uncautioned market ads, the ones
   coding fewer bedrooms or baths than their apartment's highest earlier count take a
   larger share of the first 200 than they have in the live table.
