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
- m carries the noise of the peers' mean and of single asks. That noise pulls a slope toward
  zero, so the slopes are lower bounds in size.

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

A slope above zero means the median sits too far from the unit's record, on the side of the
building. A slope below zero means the fit follows the record too closely.

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

To be filled in after the run.
