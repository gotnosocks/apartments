# D1: L1 with a factor for duplex rows (2026-11-13)

S7 of the causal screens (`docs/notes/causal-screens-2026-11-13.md`) found that L1 prices
duplex ads right on average and misses their spread. On the 10,331 held-out ads the pattern
marks, L1's median is off by -0.26% overall and +0.06 ± 0.08% within building. Their clipped
squared gap from the median is 0.0114 against 0.0059 for the other ads, and L1's 80% interval
covers 0.719 of them, 0.083 under the rest. The excess holds for buildings of every size, and
for a duplex whose previous ad was the same duplex with the same bedrooms (squared gap
0.0110, coverage 0.729). In part D a multiplier m on both L1's noise scale and its unit sd for
the duplex ads, picked on the other half of the buildings, came out at 1.3 and 1.4 and gained
255 ± 30 elpd. The same search on 10,000 other ads picked 1.0, and m = 1.1 lost 31 there.

`rentfrontier.b0duplex` writes the pattern into a copy of L1's dataset as the column `duplex`
(`docs/notes/duplex-column-2026-11-13.md`). In this note I write D1 down before any launch.
I have launched, queued and scheduled nothing for it, and the launch waits for a sprint
budget from Ben.

## The change

`drift-building-phase-duplex` (`frontier/src/rentfrontier/drift_building_phase_duplex.py`)
takes L1's design and gives each row a mark, 1 where its listing's `duplex` or `penthouse`
is true and 0 where both are false or missing. The `penthouse` column joined the mark before
any launch, after S14 (`docs/notes/unusual-units-2026-11-13.md`) found that asks of ads
calling the unit a penthouse in their text scatter about as much wider than L1 expects as
duplexes' asks do. `rentfrontier.b0penthouse` writes S14's text pattern into the duplex copy
of L1's dataset as that column. A marked row's noise scale gets a factor k on top of its
phase's,

    s_i = sigma[group_i] × f[phase_i] × k^m_i,

and the unit's process, the building's level and the rows' means stay as L1 has them. log k
takes the Normal(0, 0.3) prior of the phases' log factors, and the scale step draws it with
the six phase factors, the unit scales, sigma and nu.

`penthouse` marks 24,084 of the 1,896,471 rows (1.27%), and 7,669 of them are duplexes too,
so the mark covers 124,820 rows (6.58%) against `duplex`'s 108,405. Of L1's 189,647
held-out ads it marks 2,467, 765 of them duplexes, and the mark covers 12,031: 10,329
duplexes and 1,702 text penthouses without one. I compared the column with S14's text marks
listing by listing in `docs/notes/duplex-factor-2026-11-13/penthouse_check.py` (its output is
`penthouse_check.json` beside it). Both mark 2,467 held-out ads and agree on all but two of
them: the column marks one ad that S14 leaves out, and S14 marks one that the column leaves
out. For each of the two, the build's records file and S14's give the listing's latest record
a different description. Over all rows they disagree on 14 listings. Nine are the same kind of
case, and in the other five S14's record has a description of 20 characters or fewer, below
the floor the column applies as `duplex` does.

Each row's mark comes from its own listing's text, so an ad of a unit takes no mark from the
unit's other ads, and a later ad's text marks no earlier row. With k on the noise alone, a
held-out ad's location in each draw and the sd of its unit's part come out the same whatever
its own mark, and the mark widens only its noise. The predictive median pools the draws, so
it moves with the ad's own mark only through that width, when the draws' locations differ. A
marked training row weighs less in its unit's and its
building's estimates, so the medians of the other ads of its unit and building can move a
little through those weights.

I first wrote D1 with k on the unit's process as well, u_i = k^m_i × v_i, since part D's
multiplier widened both. In a unit with both kinds of ad that design gave a marked held-out ad
k times the unit's estimated v and an unmarked one v divided by k, so an ad's median moved with
whether its own text said duplex. On the latest split 6,861 held-out ads are in such units.
The fit would have tested a wider scatter and a level ratio between marked and unmarked ads at
once, and S7 screened only the scatter. Before any launch I moved k to the noise alone. S7's
part C points there: a duplex whose previous ad was the same duplex with the same bedrooms
still has a squared gap of 0.0110 against 0.0058 for other ads with the same bedrooms, so the
excess shows from one ad of the unit to the next, as row noise does. A factor on the unit's
spread would need a flag fixed for the whole unit, and to read no later ad's text for an
earlier row it could take the mark of the unit's first ad only. Such a flag marks the unit
from one ad and carries none of the ad-to-ad scatter part C counted, so I left it out, and the
model keeps a single new coefficient.

The sampler takes the cells of phase and mark as its phases. `Design.phase_map` gives each
marked cell its phase's factor times k, as Y1's map gave each cell its phase's and its year's
factors, so D1 needs no change to `drift.py`. The run keeps each cell's factor as
`phase_scale` and each predicted row's cell as `pred_phase`, and `drift_score` and
`drift_pool` read it as they read L1's.

Since `drift.py` is as it was before D1, the sha256 pins of every other model's draws stand.
`frontier/tests/test_drift_building_phase_duplex.py` checks the cells and their map, each
row's mark, and the scale step's density against a dense Gaussian as k moves. It flips the
marks of the rows to predict and finds their locations, unit sds and means unchanged, while
flipping the training rows' marks moves them. On a simulated design with a level for each
unit and the noise of marked rows widened 1.5 times, a run recovers k (median 1.3 to 1.75,
phases within 0.2 of 1), and a small run's draws are pinned.

`drift_today` prices D1's apartments today with each one keeping its last ad's mark (#1364),
so D1 can be served if it wins.

## Cost

I timed the sweeps on the CPU with `docs/notes/duplex-factor-2026-11-13/time_sweep.py`, on
the 18,441 training rows and 10,135 units of the 1-in-90 sample of buildings from Y1's timing,
754 of them marked (2 chains, 60 warmup and 60 draws). I alternated the two models under
`/usr/bin/time`, while another thread's work moved the machine's load average between 7 and 15:

| run | seconds a sweep | warmup | draws | peak resident | load average after |
|---|---|---|---|---|---|
| D1 | 1.643 | 106.4 s | 90.8 s | 3.44 GB | 11.7 |
| L1 | 1.211 | 79.7 s | 65.6 s | 3.39 GB | 12.9 |
| L1 | 1.291 | 92.8 s | 62.1 s | 3.41 GB | 14.5 |
| D1 | 1.054 | 56.2 s | 70.3 s | 3.44 GB | 9.8 |
| L1 | 0.789 | 50.6 s | 44.0 s | 3.44 GB | 7.1 |
| D1 | 0.803 | 51.4 s | 44.9 s | 3.45 GB | 7.6 |

The load moves a sweep by a factor of two, more than the models differ. Over the six runs D1
averaged 1.167 s a sweep against L1's 1.097 s, 6% more, and in the last pair, on the quietest
machine, 2% more. The seventh free factor adds a direction to the scale step's slice updates,
and nothing else in the sweep changes. Before the revision, with k on the unit's process too,
seven runs at a load of 10 to 29 had put D1 12% over L1.

I timed these before `penthouse` joined the mark. The text penthouses move rows from the
unmarked cells to the marked ones and leave the 14 cells and 7 free factors as they were, so
I expect the cost of a sweep to stay as timed and did not time it again.

`cap.py` keeps D1's stated rate at 1.1 s a pair of chains, against L1's 1.0, as an upper
figure. L1's containers swept at 0.776 s on Modal, and at 2% to 6% more the 2,520 s sweep
budget holds 3,060 to 3,180 sweeps: 500 warmup and 2,560 to 2,680 draws a chain, against L1's
2,750. So the chains end with 2% to 7% fewer draws than L1's, and the ESS of each quantity
falls about as much. `cap.py` estimates each container at $4.19 and 3,560 s, as it does for
L1, since the budget stops the sweeps. L1T's three containers settled at $3.57 to $3.73,
$10.94 in all, so I expect about $11.50 for three.

The peaks of resident memory differ by under 2%, and they include file pages, which a memory
cap can reclaim. Since #1359 L1's host peaks near 9 GB on Modal, so D1 runs in the normal
40 GiB container.

## Launch plan (no fit is launched by this note)

Three H100 containers on the duplex and penthouse copy of L1's dataset, seeds 1 to 3, pooled
by `drift_pool` into 6 chains, as for L1T:

```sh
cd /data1/apartments/serve/master
D=/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-duplex-penthouse
IN=/data1/apartments/pipeline/datasets/rows-b3ddebf19af1dc1e.parquet
for j in "dxa 1" "dxb 2" "dxc 3"; do
  read -r label seed <<<"$j"
  ops/modal-fit --outside-budget --gpu H100 --dataset "$D" --input "$IN" \
    --split latest --baseline drift-building-phase-b0-latest-9a7830fb-l1 COMMIT "$label" \
    drift-building-phase-duplex b0 2 500 9000 40 --seed "$seed" --level-dof 4 \
    --no-loo --no-heldout
done
```

COMMIT is the merge commit of the PR that adds the model. The copy has L1's rows in L1's
order with two more columns, so the held-out ads are L1's. I compare the pool with L1's pool,
`drift-building-phase-b0-latest-9a7830fb-l1`, on those ads: elpd with the SE clustered by
building, the median's error and the coverage of the 50%, 80% and 95% intervals
(`python -m rentfrontier.drift_score RUN`). I split each count between the ads the mark
covers and the rest by joining `pred_scores.npz`'s listings to the two columns, and split the
marked ads again into duplexes and text penthouses without duplexes.

## Predictions, revised for the penthouse fold (2026-11-13, 23:45 New York time)

I revised the predictions before any launch, when the text penthouses joined the mark (The
change). This set replaces the originals below, which I wrote for the duplex mark alone and
keep as they were.

I start from S14's numbers. On L1's held-out ads of the latest split, a multiplier m on L1's
noise scale and unit sd, picked by half of the buildings, gained 255 ± 31 elpd for the duplex
mark alone. A single m for the duplexes and the text penthouses together came out at 1.3 and
1.4 and gained 311 ± 33, 55 ± 13 more than the duplex mark alone. The text penthouses without
duplexes picked 1.4 in 57% of S14's resamples of buildings and the duplexes without
penthouses picked 1.3 in 92%, and their squared gaps from L1's median are 0.0113 and 0.0110.

I hold S14's 55 loosely, for these reasons:

1. I chose the penthouse pattern after reading its numbers on L1's held-out ads of the
   latest split, and S14 picked m on those ads too. D1 is scored on the same ads, so its gain
   from the text penthouses will look optimistic.
2. D1 widens the noise and leaves each row's location as L1 has it. Within building, the text
   penthouses without duplexes ask 1.7% more than L1's median (+0.0169 ± 0.0029 in S14), and
   D1 does nothing about that gap.
3. S14's m multiplied both L1's noise scale and its unit sd, while D1's k multiplies the noise
   alone. To carry the same excess k has to rise further than m did, and a Student-t noise
   widened by k puts weight in its tails differently from a predictive widened by m in both
   parts, so S14's elpd carries over to D1 only roughly.

As before, these are for the pool of three containers on the latest split, against L1's pool
on the shared held-out ads. `penthouse_check.py` gives L1's numbers there:

| ads | n | L1's 80% coverage | L1's median error |
|---|---|---|---|
| all | 189,647 | 0.797 | 0.0407 |
| marked | 12,031 | 0.718 | 0.0552 |
| duplexes | 10,329 | 0.719 | 0.0559 |
| text penthouses without duplexes | 1,702 | 0.716 | 0.0510 |
| unmarked | 177,616 | 0.803 | 0.0399 |

1. The fit passes the gate (75%). The marked rows rise from 5.7% to 6.6% of the rows, all in
   the same cells as before, and unit_sd is still the likeliest miss.
2. k's posterior median falls between 1.35 and 1.70 (60%), and above 1.2 (90%). In S14 the
   text penthouses picked about the duplexes' m and scattered about as widely, so the fold
   moves k by little.
3. elpd gains 180 to 400 over L1 (60%), and more than 2 SE (85%). I added 30 to 50 to the
   original 150 to 350 for the text penthouses, below S14's 55 for the first reason above.
4. The marked ads give 210 to 380 of it, and the unmarked ads -20 to +60 (60% that both hold).
5. The text penthouses without duplexes give 15 to 70 of it (60%), and more than 0 (85%).
   S14 put their gain alone at 56 ± 15.
6. On the marked ads 80% coverage rises from 0.718 to between 0.76 and 0.81 (60%), and above
   0.75 (80%). On the text penthouses without duplexes it rises from 0.716 to between 0.74 and
   0.81 (60%), and their gap within building keeps it a little under the duplexes' (55%).
7. 80% coverage on all shared ads stays within 0.005 of 0.797 (75%). The marked ads are 6.3%
   of the held-out ads, so a rise of 0.06 on them adds about 0.004 overall.
8. The median's error moves by under 0.0003 (70%) and by under 0.0005 (85%), and on the
   marked ads by under 0.001 (65%). On the text penthouses without duplexes it stays within
   0.001 of L1's 0.0510 (65%), and their gap from D1's median within building, measured as
   S14 measured L1's, stays above +1% (75%).
9. Each of L1's phase factors moves by under 0.02 (70%).
10. Each group's sigma falls by 0% to 5% (65%). The marked rows are now 6.6% of the rows.
11. Each container stops its sweeps at the budget and runs 50 to 60 minutes, and the three
    settle between $10.50 and $12.00 (80%). The fold adds no cell or factor (Cost).

## Original predictions, for the duplex mark alone (written before launch, revised before launch)

These are the originals. The penthouse fold replaced them before any launch, and I keep them
here unchanged.

I revised these on 2026-11-13, before any launch, when I moved k from the noise and the unit's
process to the noise alone (The change). The revision changes four of them:

1. prediction 1's shortfall in draws against L1 falls from 9% to 13% to 2% to 7%, from the
   new timings;
2. prediction 2's range for k rises to 1.35 to 1.70;
3. prediction 7 takes back its earlier chances, drops its count of the ads of mixed units,
   whose locations no longer move with their own marks, and adds a claim on the median error
   of the marked ads;
4. prediction 9's range for sigma's fall widens from 0% to 3% to 0% to 4%.

All of these are for the pool of three containers on the latest split, against L1's pool on
the shared held-out ads. L1's numbers there: median error 0.04068 and 80% coverage 0.797, and
on the 10,331 marked ads an 80% coverage of 0.719.

1. The fit passes the gate (75%). L1's pool of 4 chains reached a largest R-hat of 1.0076
   (unit_sd) and a smallest ESS of 788 (drift_tau). D1 pools 6 chains with 2% to 7% fewer
   draws each, and k changes the weight of the marked rows in the units' estimates, so
   unit_sd is the likeliest miss.
2. k's posterior median falls between 1.35 and 1.70 (60%), and above 1.2 (90%). Part D's
   1.3 and 1.4 scaled both parts of L1's predictive. On the held-out ads L1's unit part has a
   mean variance of 0.0015 of the 0.0058 squared gap of other ads, so the noise holds the rest,
   and to carry the duplexes' excess of 0.0052 alone its variance would have to about double,
   for a k near 1.5. L1's noise is a Student-t with nu near 1.8, and clipping the squared gap
   counts its tails less than its scale, which pushes k up.
3. elpd gains 150 to 350 over L1 (60%), and more than 2 SE (85%).
4. The marked ads give 180 to 330 of it, and the other ads -20 to +60 (60% that both hold).
   The other ads gain only as far as sigma and the unit scales fall once the marked rows stop
   widening them.
5. On the marked ads 80% coverage rises from 0.719 to between 0.76 and 0.81 (60%), and above
   0.75 (80%).
6. 80% coverage on all shared ads stays within 0.005 of 0.797 (80%).
7. The median's error moves by under 0.0003 (70%) and by under 0.0005 (85%). A marked
   training row only weighs less, so on the marked ads the median's error moves by under 0.001
   (65%).
8. Each of L1's phase factors moves by under 0.02 (70%).
9. Each group's sigma falls by 0% to 4% (65%). The marked rows are 5.7% of the rows, and k
   now carries all of their excess.
10. Each container stops its sweeps at the budget and runs 50 to 60 minutes, and the three
    settle between $10.50 and $12.00 (80%).

S14 (`docs/notes/unusual-units-2026-11-13.md`) screened penthouses, garden apartments and
townhouse floors against L1's spread. Of those, only the text penthouses joined D1's mark. A
shared m with the garden ads came out at -11 ± 19 against the duplex mark alone, and with the
townhouse ads at -90 ± 16.
