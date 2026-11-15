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

To be written after the scripts run.
