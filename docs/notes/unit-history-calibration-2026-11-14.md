# Unit history calibration on L1 and L1T (2026-11-14)

This is free check 1 of the causal sprint (`causal-sprint-2026-11-14.md`). Of the 36 false deals
read on the Deals page, 12 were units L1 priced 14% to 39% above the unit's own 1 to 9 training
asks. Here I measure that pattern over every held-out ad of the latest split, and I measure how
much of it the heavy-tailed unit level of L1T takes away.

Nothing here is fit. Nothing runs on Modal or the GPU, and no model, feature set or data rule
changes.

## Method

The script is `docs/notes/unit-history-calibration-2026-11-14/h1_history.py`. It writes to
`/data1/apartments/tmp/unit-history-calibration-2026-11-14/`. It reads:

- the rows of `b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise`, with six columns;
- `pred_scores.npz` of the L1 pool `drift-building-phase-b0-latest-9a7830fb-l1`;
- `pred_scores.npz` of the L1T pool `drift-building-phase-unitt-b0-latest-bc8e7b95-l1t`.

Both pools saved held-out predictions for the same 189,647 ads, in the same order, so L1T needs
no rescoring. Every held-out ad belongs to a unit with at least 1 training ad: 77,037 have 1,
44,568 have 2, 55,817 have 3 to 5, 11,392 have 6 to 9, and 833 have 10 or more.

For each held-out ad I take the gap, the log ask less the model's predictive median.

For the unit's training record I wanted the mean, over the unit's training ads, of the log ask
less a fitted value without the unit's own level. Neither pool saved fitted values for training
rows (`posterior.npz` holds `pred_loc` for the held-out ads only), so I use a stand-in built
like `unit-level-reads-2026-11-12/rank.py`, from the training rows alone:

1. I take the log ask of each training ad and subtract a monthly index. The index is the mean,
   over the month's training ads, of the log ask less the unit's mean log ask.
2. Within each cell of building, bedrooms and year, I subtract the mean adjusted ask of the
   other units' training ads from the unit's mean. I keep a cell only when the other units have
   at least 3 ads in it.
3. I average the unit's cells, weighted by its ads in each. I call the result m.

A unit with no kept cell gets no m, and its held-out ads drop out of the regressions. The script
reports how many.

The stand-in differs from the measure I wanted in two ways, and both matter for reading the
slopes:

- m keeps everything the coded fields explain about a unit within its building, like the floor
  or a terrace. A fit with a perfectly calibrated unit level still shows a slope of zero on m,
  since any predictable held-out gap is a miss whatever its source. But a slope above zero says
  only that the median leaves part of the unit's record unused. It does not say whether the
  unit level or a coefficient is at fault.
- m carries the noise of the peers' mean and of single asks. The noise does not excuse a
  slope. Under a calibrated posterior the held-out gap has a slope of zero on any function of
  the training rows, a noisy m included. A slope on either side of zero is therefore a
  miscalibration, and the noise in m changes only which causes can produce it. A fit leaning
  too hard on noisy training asks gives a negative slope, because the median then follows the
  same noise m carries.

Then, for L1 and for L1T on the same ads:

1. I regress the gap on m with an intercept, over all ads, by the unit's number of training ads
   (1, 2, 3 to 5, 6 to 9, 10+), and by the months from the unit's last training ad to the
   held-out ad (under 6, 6 to 12, 12 to 24, 24 to 48, over 48). I also regress L1T's gap less
   L1's on m, since the two gaps share the ask and their difference has a much smaller SE than
   either slope. SEs are clustered by building.
2. Among units with m under -0.15 and at least 2 training ads, I report the mean gap and the
   share of asks inside the 80% interval (the 10% to 90% predictive quantiles) under each
   model. The same for m over +0.15.
3. I recompute S7's duplex figure, the duplex ads' mean squared gap less the other ads', with
   the gap clipped at ±0.4 as in `w1_within.py`, under L1 and under L1T.

A slope above zero means the median stays too close to the building, so the fit uses too little
of the unit's record. A slope below zero means the median follows the record further than the
unit's next ask does.

## Predictions

I wrote these before computing any gap. Before writing them I had read the arrays' names and
shapes, the split's dates and the counts of training ads per unit above, and nothing else.

1. The script's check passes: both pools score the same held-out ads in the same order, and the
   log asks match the dataset (97%).
2. At least 85% of the held-out ads get an m (75%).
3. L1's slope over all ads is above zero by more than 2 SEs (75%), and lies between 0.02 and
   0.12 (55%).
4. L1's slope for units with 1 training ad is larger than its slope for units with 3 to 5
   (65%).
5. L1T's slope over all ads is below L1's, with the slope of the difference more than 2 SEs
   under zero (70%).
6. L1T removes less than half of L1's slope over all ads (65%). A t level changes the
   shrinking of the far units most, and those are a small share of a slope taken over
   everything.
7. L1's slope is above zero in every band of months since the last training ad (55%), and it is
   larger over 24 months than under 6 (55%).
8. Low tail, m under -0.15 with at least 2 training ads: L1's mean gap is below zero by more
   than 2 SEs (85%), and lies between -0.07 and -0.015 (60%).
9. Low tail: L1T's mean gap is closer to zero than L1's (80%), by between 20% and 60% of L1's
   (50%).
10. High tail, m over +0.15: L1's mean gap is above zero by more than 2 SEs (75%), and L1T's is
    closer to zero (70%).
11. Coverage of the 80% interval in the low tail is under 78% for L1 (60%), and L1T's coverage
    there is higher than L1's (55%).
12. Duplex ads: my loading gives back S7's +0.0054 for L1 to within 0.0002 (90%). Under L1T
    between 85% and 100% of it remains (70%), and more than 100% with probability 10%.

## Results

Both scripts ran once, on the CPU under a 3 GB cap. `h1_history.py` wrote `h1_history.json` and
`h2_own_record.py` wrote `h2_own_record.json`, both in the output directory above.

### Coverage of the stand-in

137,094 of the 189,647 held-out ads (72%) got an m. The other 52,553 belong to units with no
cell of building, bedrooms and year holding 3 training ads of other units, so the figures
below lean toward larger buildings. The mean gap is about the same on both sides (L1: -0.0046
with an m, -0.0039 without). m has an sd of 0.100, and its 5% and 95% points are -0.146 and
+0.165. Every held-out ad is later than its unit's last training ad.

### Slopes of the held-out gap on m

Slopes with SEs clustered by building. The last column is the slope of L1T's gap less L1's.

| training ads of the unit | ads | L1 | L1T | L1T less L1 |
|---|---|---|---|---|
| all | 137,094 | -0.009 ± 0.005 | -0.056 ± 0.004 | -0.047 ± 0.002 |
| 1 | 48,392 | +0.031 ± 0.009 | -0.027 ± 0.008 | -0.058 ± 0.003 |
| 2 | 32,357 | -0.029 ± 0.007 | -0.075 ± 0.005 | -0.046 ± 0.005 |
| 3 to 5 | 45,250 | -0.047 ± 0.006 | -0.082 ± 0.005 | -0.035 ± 0.004 |
| 6 to 9 | 10,297 | -0.071 ± 0.010 | -0.083 ± 0.010 | -0.012 ± 0.002 |
| 10+ | 798 | -0.140 ± 0.038 | -0.187 ± 0.052 | -0.047 ± 0.030 |

| months since the last training ad | ads | L1 | L1T | L1T less L1 |
|---|---|---|---|---|
| under 6 | 16,220 | +0.031 ± 0.024 | -0.030 ± 0.025 | -0.061 ± 0.005 |
| 6 to 12 | 14,258 | -0.009 ± 0.014 | -0.050 ± 0.013 | -0.041 ± 0.004 |
| 12 to 24 | 39,359 | -0.010 ± 0.006 | -0.049 ± 0.005 | -0.040 ± 0.004 |
| 24 to 48 | 42,071 | -0.010 ± 0.007 | -0.052 ± 0.005 | -0.042 ± 0.004 |
| over 48 | 25,186 | -0.026 ± 0.008 | -0.086 ± 0.007 | -0.060 ± 0.005 |

L1's slope is above zero only for units with a single training ad, and there it is small: a
unit whose one ad was 20% under its neighbours asks about 0.6% under L1's median the next time.
Within that group the slope is +0.088 ± 0.041 when the ad comes back within 6 months and falls
to -0.007 ± 0.010 after 48 months (`slope_by_n_and_months` in the JSON). From 2 training ads
up, L1's slope is below zero and grows in size with the count. Units with a long record far
from their building ask closer to the building, the next time, than L1's median says.

L1T moves every slope down by 0.01 to 0.06. For single-ad units that takes +0.031 to
-0.027, past zero. For units with 2 to 5 training ads it makes a negative slope about twice as
large. Both fits have their most negative slope by months in the band over 48.

A negative slope is a miscalibration, and at least three things can produce it:

1. The fit leans too hard on noisy training asks. An ask far from the building is partly
   noise, the unit level takes up some of that noise, and the next ask comes back.
2. A unit's premium over its building truly reverts over time, faster than the fit's unit
   level lets it.
3. Survivorship. A unit comes back as a held-out ad after a history its own pricing selected.
   A unit asked far over its neighbours may return because it failed to rent, at a lower ask,
   and the latest split holds out exactly those returning ads.

This check cannot separate the three.

By this measure L1 does not use too little of a unit's record on average. The exception is the
unit with one earlier ad seen again within about 2 years, and L1T overcorrects it.

### Tails

Units with at least 2 training ads. Gap means carry building-clustered SEs.

| m | ads | mean m | L1 mean gap | L1T mean gap | L1 80% coverage | L1T 80% coverage |
|---|---|---|---|---|---|---|
| under -0.15 | 3,636 | -0.215 | +0.002 ± 0.001 | +0.007 ± 0.001 | 74.4% | 73.5% |
| -0.15 to +0.15 | 80,590 | 0.000 | -0.006 ± 0.000 | -0.005 ± 0.000 | 81.7% | 81.2% |
| over +0.15 | 4,476 | +0.234 | -0.010 ± 0.002 | -0.024 ± 0.001 | 70.8% | 70.3% |

Units with 1 training ad, for comparison:

| m | ads | L1 mean gap | L1T mean gap | L1 80% coverage | L1T 80% coverage |
|---|---|---|---|---|---|
| under -0.15 | 2,876 | -0.003 ± 0.002 | +0.010 ± 0.002 | 71.9% | 75.1% |
| over +0.15 | 3,807 | +0.015 ± 0.002 | -0.004 ± 0.002 | 69.6% | 77.9% |

On average neither fit prices the cheap units with 2 or more training ads over their asks. Their
asks come in 0.2% over L1's median and 0.7% over L1T's. The pricey units ask 1.0% under L1's
median and 2.4% under L1T's. The mean gaps in these tails therefore run from 0.2% to 2.4%, and
L1T's are the larger in both.

The intervals are the weaker part. In both tails the 80% interval holds 70% to 74% of the asks,
against 82% in the middle, and L1T leaves that as it is for units with 2 or more training ads.
For single-ad units L1T raises coverage by 3 and 8 points. Units far from their building
scatter wider around the median than the fit's interval says. A page listing the asks furthest
under the median then draws from these units more often than their count would suggest, with
the median unbiased for them on average.

### The model's median against the unit's own asks

I added `h2_own_record.py` after scoring the above, because m compares a unit with its
neighbours while the false deals were units priced over their own earlier asks. No prediction
covers it. The script carries each unit's training asks to the held-out month with the same
monthly index and takes r, the predictive median less their mean.

The index is crude. Among the 62,467 ads L1 prices more than 14% over the carried record, the
asks themselves come in 21% over it. Those asks land 1.3% under L1's median (1.2% under
L1T's), with 79% coverage. My guess, untested, is that most of r in that band is rent growth
the index misses. I did not locate the 12 false deals in these bands, so the table says
nothing about them directly.

On the other side the mean gap is larger. Where L1 prices a unit more than 14% under its carried
record (7,239 ads), the asks land 5.1% ± 0.2% over the median with 56% coverage. L1T brings
that to 2.5% ± 0.2% and 65%. For units with 2 or more training ads the asks land 2.6% ± 0.3%
over L1's median and 0.5% ± 0.2% over L1T's.

### Duplex ads

My loading gives back S7's figure. The 10,331 duplex ads' excess in the clipped squared gap is
+0.0054 ± 0.0003 under L1 and +0.0045 ± 0.0002 under L1T, so 82% of it remains. The paired
reduction is 0.0010 ± 0.0001. Coverage of the 80% interval on the duplex ads goes from 71.9% to
73.5%. The heavy-tailed unit level takes up about a fifth of the duplex scatter, and D1's
question stays open.

### Predictions scored

1. Hit. The asserts passed.
2. Miss. 72% of the held-out ads got an m, not 85%.
3. Miss. L1's slope over all ads is -0.009 ± 0.005.
4. Hit. +0.031 for 1 training ad against -0.047 for 3 to 5.
5. Hit in part. The wording holds: the slope of the difference is -0.047 ± 0.002. The reasoning
   behind it does not. I expected L1T to bring a positive slope toward zero, and it took a
   slope near zero to a negative one.
6. Miss. L1 has no positive slope over all ads for L1T to remove.
7. Miss on both parts. L1's slope is above zero only under 6 months, and it is lower over 24
   months than under 6.
8. Miss on both parts. L1's mean gap in the low tail is +0.002 ± 0.001.
9. Miss. L1T's mean gap in the low tail is +0.007, further from zero.
10. Miss on both parts. L1's mean gap in the high tail is -0.010 ± 0.002 and L1T's is -0.024.
11. Hit on the first part (74.4% under L1), miss on the second (73.5% under L1T).
12. Hit on the loading (+0.0054). Miss on the share, 82% against a band of 85% to 100%.

I expected the false-deal pattern to show as a general bias, with the median too close to the
building for units far from it. The held-out ads show a bias of that kind only for single-ad
units, and a wide scatter everywhere in the tails.

## Reading for the sprint

- Account A's case from the false deals is weaker than the sprint note has it. A heavy-tailed
  unit level moves the single-ad slope past zero and halves the gap for units priced under
  their own record, and it takes the slopes of units with 2 or more ads further below zero.
  L1TKN's predictions
  should include the slope on m by training-ad count, with zero as the target in each row.
- The tails need a wider interval more than a different median. A noise scale or unit sd that
  grows with the unit's distance from its building would address the 70% to 74% coverage, and
  L1T does not.
- The slopes below zero grow in size with the unit's ad count, and they are largest after 48
  months. Overfitting to noisy asks, a premium that reverts and survivorship all fit that
  pattern, and this check does not choose among them.

## Limits

- m is a stand-in, built from asks, a monthly index and neighbours. It is not the fit's own
  residual without the unit level, so a slope locates a predictable miss without saying which
  term is responsible. Fitted values for training rows without the unit level would remove
  the stand-in. The pools did not save them, and I did not check what the fit code would need
  in order to write them.
- 28% of the held-out ads have no m, mostly in small buildings.
- L1T missed the convergence gate on nu and unit_sd, so its figures here describe that pool as
  it stands.
- The index in `h2_own_record.py` understates rent growth, so r mixes the model's departure
  from the record with time. The low side of r is the more reliable side, since the index bias
  pushes r up.
