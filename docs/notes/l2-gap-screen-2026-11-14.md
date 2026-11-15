# Screen of the gap L2 leaves on held-out ads (2026-11-14, no fit)

L2 on the unitkn base (`docs/notes/l2-unitkn-level-2026-11-14.md`, pool
`drift-building-phase-unitkn-level-b0-latest-b27d1dd8-l2kn`) leaves its held-out log asks
0.37% under the predictive median in every lease phase. A constant shift of every ad,
cross-fitted over two halves of the buildings, is worth 360 elpd. This note screens five
accounts of that gap on the pool's saved predictions. Nothing is fitted and nothing is spent.

## Earlier work this builds on

S3 of the causal screens (`docs/notes/causal-screens-2026-11-13.md`) ran on L1. It measured
the gap by the previous ad's ending and price path (74 ± 19 and 67 ± 17 elpd over a level per
phase), split L1's common offset of 0.44% by the year of the ad (part C), and compared
held-out pairs of consecutive ads with training pairs of the same quarters (part D, held-out
pairs 0.27 points lower). It read the offset as selection: a held-out ad is its unit's
latest, and a unit with no later ad most likely kept its tenant. I repeat the ending and year
tables on L2 since L2 now carries the phase levels, and I add tests S3 did not run: the
price history inside the held-out ad, the unit's training record, the count of training ads,
and a test of the selection reading on training ads alone.

## Steps

All scripts are in `docs/notes/l2-gap-screen-2026-11-14/` and run on the CPU under a 3 GB
memory cap.

1. I load L2's held-out ads (`pred_scores.npz`) and take each ad's gap, its log ask less the
   predictive median. I join the dataset's rows, the `prev_ending` column of the ending
   dataset, and the per-ad process table built from the raw status and price histories
   (`/data1/apartments/tmp/outlier-sprint/s2/H/proc.parquet`: first and last status times,
   days on the market, counts of cuts and raises, first, last and highest price).
2. For each candidate I put the held-out ads into cells and tabulate the median and mean gap
   of each cell with SEs clustered by building.
3. For the elpd of a candidate I split the buildings in two by
   `zlib.crc32(building.encode()) % 2`, take each cell's median gap on one half, move the
   predictive location of the other half's ads by it, and rescore L2's exact predictive over
   its 432 kept draws (the `Draws` class of the causal screens, pointed at L2's pool). I
   report each gain with a building-clustered SE, and its difference from the gain of a
   single cell, the plain constant.
4. Candidate (a), the previous ad's ending: cells of ending, of phase by ending, and of the
   previous ad's price path (raised, cut by 5% or more, flat), read only from changes dated
   before the held-out ad opened.
5. Candidate (b), the price history inside the ad: I check which price the rows file and the
   dataset give a row (`asking_rent`, `latest_ask`, `latest_ask_how`) and whether held-out
   and training rows differ in it. Then I tabulate the gap by the held-out ad's own count of
   cuts, its days on the market and its ending, and recompute the median gap with the ad's
   first price as the target. The cuts and the first price come from the ad's own rents, so a
   model may not read them as features. They enter here only to decompose the target. Days on
   the market and the ad's ending are dates and statuses, known once the ad has closed.
6. Candidate (c), the unit's trend: I build the stand-in for the unit's training record used
   by the unit history calibration (`h1_history.py`: the unit's mean training log ask less a
   monthly index and less the other units of its building, bedroom count and year), and
   tabulate the gap by its sign and size. I also tabulate the gap by the change in log ask
   over the unit's last two training ads, net of the mean change of all pairs in the same two
   quarters.
7. Candidate (d), the split: the gap by the count of the unit's training ads, by L2's own
   predictive unit sd for the ad, and by the months since the previous ad inside 26+.
8. Candidate (e), the date: the gap by year of the ad and by the years from the ad to the
   snapshot of 2026-11-09.
9. A test of the selection reading on training ads. The split holds out 189,647 of the
   latest ads of relisted units, drawn at random, so the training rows hold the latest ads of
   the units it did not draw. For every pair of consecutive ads of a unit I take the change
   in log ask less the mean change of all pairs with the same two quarters. I compare the
   pairs ending at a unit's latest ad with the pairs ending at an ad with a successor, by the
   year of the ad, and among ads with a successor by the months until it came. Under
   selection, an ad followed after 26 months or more (a tenant who renewed) comes in lower
   than one followed at 10 to 13 months, and a training latest ad shows the same deficit as a
   held-out one.

## Predictions (written before any result was computed)

Gaps are in percent of the ask (100 times the log gap). Gains are elpd from the cross-fitted
shift on the 189,647 held-out ads.

0. My rescoring gives 340 to 380 for the plain constant (80%).
1. Main cause. I give selection of the unit's latest ad, which appears as the date pattern
   (e), 55%; the price history inside the ad (b) 15%; the split's shrinkage (d) 10%; the
   previous ad's ending (a) 10%; the unit's trend (c) 5%; something else 5%.
2. (a) After a delisting or a pause the median gap is 0.2 to 0.7 points under the gap after
   a rental (65%). Cells of phase by ending gain 20 to 80 over the constant (60%). The price
   path adds under 60 over the constant (65%).
3. (b) Every row, held-out or training, carries the ad's last kept ask (90%), so the two
   sets do not differ by rule. Among held-out ads, those with one cut or more sit 0.5 to 2.0
   points under those with none (70%). With the ad's first price as the target the median gap
   lies between -0.2 and +0.2 (50%). Cells by days on the market gain 50 to 250 over the
   constant (50%).
4. (c) The slope of the gap on the unit's training record lies between -0.01 and +0.02
   (70%). Cells by its sign and size gain under 40 over the constant (65%).
5. (d) The median gaps of units with one training ad and with five or more differ by under
   0.3 points (55%). Cells by the count gain under 40 over the constant (65%).
6. (e) Cells by year gain 80 to 250 over the constant (60%). The median gap for ads 2 to 5
   years before the snapshot is 0.4 to 0.9 points under the gap for ads of the last 6 months
   (65%).
7. Selection test. Pairs ending at a training latest ad come 0.2 to 0.6 points under pairs
   ending at an ad with a successor, same quarters (60%). Among ads with a successor, those
   followed after 26 months or more come lower than those followed at 10 to 13 months (65%).
   The deficit of training latest ads is within 0.15 points of the deficit of held-out ads
   (60%).
8. The best partition a model could read from dates and earlier ads gains 100 to 300 over
   the constant (50%).


## Results

The scripts wrote their outputs to `/data1/apartments/tmp/sprint-20261114/gap-screen/`
(`g1.json`, `g2.json`, `g3.json`, with the per-ad gains in `g2_gains.parquet`). Gaps below
are in percent of the ask, with SEs clustered by building. Gains are elpd from the
cross-fitted shift, given as the gain over the plain constant.

### The gap as a whole

Over the 189,647 held-out ads the median gap is -0.375 and the mean -0.432 ± 0.021. 52.7% of
the ads fall under their median. My rescoring of the plain constant gives 360.3 ± 32.1, the
figure in the L2 note. Cells by phase add nothing over it (-4.0 ± 4.0), since the phase
medians run from -0.30 to -0.42.

### Candidate (a), the previous ad's ending

| previous ad ended | ads | median | mean |
| --- | ---: | ---: | ---: |
| rented | 92,152 | -0.315 | -0.358 ± 0.028 |
| no longer available | 57,765 | -0.324 | -0.317 ± 0.038 |
| delisted | 22,424 | -0.744 | -0.866 ± 0.058 |
| temporarily off the market | 13,136 | -0.617 | -0.776 ± 0.073 |
| undated | 4,170 | +0.056 | -0.238 ± 0.105 |

Ads after a delisting or a pause come in 0.48 ± 0.05 points under ads after a rental. Cells of
the ending gain 64.0 ± 13.1 over the constant, and phase by ending 66.7 ± 16.8. The previous
price path gains 41.9 ± 11.1 (54.2 ± 14.6 by phase). These repeat S3's sizes on L1. After a
rental the gap stays at -0.32, close to the whole.

### Candidate (b), the price history inside the held-out ad

Held-out and training rows follow the same price rule. In both, about 97% of rows take the
ad's latest ask (`latest_ask_how` "latest": 96.6% held out, 96.8% training) and most of the
rest take the latest ask before a closing raise (3.4% and 3.1%). The latest ask equals the
process table's last price on 86.1% and 87.8% of rows. Ads with a cut make up 27.6% of
held-out ads, 30.5% of training ads and 27.8% of the training ads that are a unit's latest.
Median days on the market are 13 and 14.

Inside the held-out set the gap follows the ad's own history closely:

| held-out ad | ads | median gap |
| --- | ---: | ---: |
| no cut | 137,281 | -0.126 |
| one cut | 29,088 | -0.668 |
| two cuts or more | 23,278 | -1.588 |
| one raise or more | 28,608 | -0.034 |
| on the market 0 to 7 days | 65,808 | -0.789 |
| on the market 15 to 30 days | 41,130 | -0.004 |
| on the market 121 days or more | 4,416 | -0.848 |
| still open at the snapshot | 837 | +1.469 |

With the ad's first price as the target, the median gap turns to +0.35 (mean +0.323 ± 0.034).
An ad's opening ask sits above L2's median on average, and its cuts carry it below. Cells of
cuts gain 650.2 ± 45.9 over the constant, cuts by raises 1,102 ± 52, days on the market
281.4 ± 27.0, the ad's own ending 157.3 ± 20.1.

All of these cells read the held-out ad's own later rents or its outcome, which the leak rule
forbids a model to use. I report them only as a decomposition of the target. They locate the
residual spread inside an ad's own history and offer no term for a model.

### Candidate (c), the unit's training record

I binned the stand-in for the unit's record `m` (its mean training log ask less the monthly
index and less the other units of its building, bedrooms and year). 137,094 held-out ads have
one, with sd 0.097.

| unit record | ads | median gap |
| --- | ---: | ---: |
| under -0.15 | 6,512 | +0.78 |
| -0.15 to -0.05 | 25,131 | +0.40 |
| -0.05 to -0.015 | 22,893 | +0.05 |
| -0.015 to 0.015 | 26,342 | -0.34 |
| 0.015 to 0.05 | 22,727 | -0.73 |
| 0.05 to 0.15 | 25,206 | -1.14 |
| over 0.15 | 8,283 | -1.34 |

A unit above its building comes in under L2's median, and a unit below comes in over it. The
slope of the gap on `m` is -0.066 ± 0.003, so L2 carries a unit's premium about 6.6% too far.
On L2 this repeats the slope of -0.056 that the unit history calibration found for L1T. The
slope grows with the months since the unit's previous ad (-0.037 ± 0.014 at 0 to 2 months,
-0.057 at 10 to 13, -0.072 at 38 to 61, -0.099 ± 0.009 at 62 or more) and with the count of
the unit's training ads (-0.045 for one, -0.078 for two, -0.091 for five to nine). It sits
near zero for ads of 2014 to 2020 (-0.014 ± 0.011 and -0.008) and at -0.08 to -0.09 from 2022
on. Since units with more ads need less shrinkage, a level too loose for thin units would give
the opposite pattern by count. A premium fading as the unit's ads age fits both patterns.

Cells of the record gain 690.8 ± 49.9 over the constant (687.3 ± 50.4 by deciles). The change
over the unit's last two training ads adds 132.1 ± 19.0 alone, and record by last change gains
818.5 ± 55.4. The central bin still sits at -0.34, so the record spreads the ads around the
offset and leaves the offset in place.

### Candidate (d), the split

Units with one training ad have a median gap of -0.194 (mean -0.118), units with two to nine
-0.486 to -0.490. Cells of the count gain 40.5 ± 11.0, L2's own unit sd 7.1 ± 8.0, the months
since the previous ad 5.6 ± 6.4. Adding the count to the record cells adds 66.4 ± 21.0, as the
slope's growth with the count would lead me to expect.

### Candidate (e), the date

| year of the ad | ads | median gap |
| --- | ---: | ---: |
| 2014 to 2018 | 18,526 | -0.01 to -0.34 |
| 2019 | 8,010 | -0.10 |
| 2020 | 15,778 | -0.05 |
| 2021 | 17,472 | -0.31 |
| 2022 | 12,760 | -1.02 |
| 2023 | 19,314 | -0.77 |
| 2024 | 26,316 | -0.41 |
| 2025 | 34,531 | -0.41 |
| 2026 | 36,940 | -0.20 |

By years to the snapshot, closed ads of the last 3 months sit at -0.06, ads 3 to 5 years old
at -0.91, and ads 5 to 8 years old at -0.14. The median gap of ads 2 to 5 years old is 0.54
points under that of ads of the last 6 months. Cells of the year gain 118.2 ± 20.5, half-years
165.7 ± 27.0, years to the snapshot 111.6 ± 22.0, year by ending 187.3 ± 27.2.

Record by year gains 902.7 ± 59.4 over the constant, 784.5 ± 56.9 over the year alone and
212.0 ± 34.0 over the record alone. Adding the previous ending on top of it loses 26.3 ± 30.2.
Adding days on the market gains 59.9 ± 46.5.

### The selection test on training ads

I took 961,075 pairs of consecutive ads and netted each pair's change in log ask against the
mean change of pairs with the same two quarters:

| pair ends at | pairs | median | mean |
| --- | ---: | ---: | ---: |
| an ad with a successor | 562,978 | +0.589 | +0.168 ± 0.025 |
| a held-out latest ad | 189,647 | +0.158 | -0.221 ± 0.037 |
| a training latest ad | 208,450 | +0.145 | -0.254 ± 0.036 |

Pairs ending at a training latest ad come 0.42 ± 0.03 points under pairs ending at an ad with
a successor, and pairs ending at a held-out latest ad 0.39 ± 0.04 under. The two latest-ad
groups differ by 0.03 ± 0.03. The deficit is largest in 2022 (latest -1.3 to -1.5 against
+0.73 with a successor) and 2023, reversed in 2019 to 2020 (+0.55 to +0.59 against -0.21), and
near zero for held-out ads of 2026. It appears at every count of months since the previous ad.
Among ads with a successor, those followed within 13 months come in at +0.63 to +1.03, those
followed after 26 to 37 months at -0.28 and after 38 or more at -0.36.

### Reading

I read the constant as a property of a unit's latest ad. Training latest ads, which L2 fits,
show the same deficit against their quarter as held-out ones, and so do ads followed only
after a long gap, where the tenant most likely renewed. A unit drops out of the data after an
ad that found a tenant who stayed, so its last ad leans toward asks low enough to let, and the
cuts table points the same way. The deficit fades for ads within 3 months of the snapshot,
where the latest ad has had no time to become the last. A new ad on the Deals page sits in
that position, so I would leave the constant out of the model. It raises held-out elpd on a
split of latest ads and has no counterpart for new asks. The year pattern comes from the same
selection, heaviest for ads of 2022 and 2023.

The unit record is a separate effect, and the largest one in this screen. L2 carries each
unit's premium undiminished across years, while the held-out asks show premiums fading by
about 4% at 0 to 2 months and 10% at five years or more, more so after 2021. A model may use
it, since it comes from earlier ads and dates.

I would propose a unit level whose deviation from the building decays with the months
between the unit's earlier ads and the ad being priced: for instance the unit effect times a
fitted factor exp(-months / tau), or a unit walk in time on the unitkn base. The cross-fitted
cells give 690 to 900 over the constant at their coarse resolution, and a fitted term on a
refit should recover part of that. I expect 300 to 700 elpd over L2.

## Predictions scored

| # | prediction | result | scored |
| --- | --- | --- | --- |
| 0 | constant 340 to 380 | 360.3 ± 32.1 | hit |
| 1 | selection (e) the main cause, 55% | the constant follows selection; most of the elpd lies in (c), given 5% | hit for the constant, miss for the elpd |
| 2a | delisted or paused 0.2 to 0.7 under rented | 0.48 ± 0.05 | hit |
| 2b | phase by ending 20 to 80 | 66.7 ± 16.8 | hit |
| 2c | price path under 60 | 41.9 ± 11.1 | hit |
| 3a | every row carries the last kept ask, no rule difference | same rule in both sets, 96.6% and 96.8% latest | hit |
| 3b | one cut or more 0.5 to 2.0 under none | 0.95 ± 0.05 | hit |
| 3c | first-price median gap -0.2 to +0.2 | +0.35 | miss |
| 3d | days on market 50 to 250 | 281.4 ± 27.0 | miss |
| 4a | slope on the record -0.01 to +0.02 | -0.066 ± 0.003 | miss |
| 4b | record cells under 40 | 690.8 ± 49.9 | miss |
| 5a | one training ad and five or more under 0.3 apart | 0.29 | hit |
| 5b | count cells under 40 | 40.5 ± 11.0 | miss |
| 6a | year cells 80 to 250 | 118.2 ± 20.5 | hit |
| 6b | 2 to 5 years 0.4 to 0.9 under the last 6 months | 0.54 | hit |
| 7a | training latest 0.2 to 0.6 under ads with a successor | 0.42 ± 0.03 | hit |
| 7b | followed after 26+ months lower than at 10 to 13 | -0.28 and -0.36 against +0.63 | hit |
| 7c | training and held-out deficits within 0.15 | 0.03 ± 0.03 | hit |
| 8 | best leak-free partition 100 to 300 | record by year 902.7 ± 59.4 | miss |

12 of 19 parts hit. I could have avoided the misses on (c): I wrote prediction 4 without
reading the unit history calibration row, which already gave L1T's slope as -0.056.

`g2_elpd.py` failed on its first full run. It built each cell's key with `astype(str)` across
columns and stopped on a float column at the seventh partition. I changed it to join the
columns one at a time as strings and reran all 28 partitions. The first six gains came out the
same in both runs.
