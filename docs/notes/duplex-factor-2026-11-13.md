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
the floor the column applies as `duplex` does. Those five are recent listings, with ids of
5,171,339 or more, and S14's text for them runs 0 to 6 characters, so S14's records file
likely holds them from before their descriptions were scraped.

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

S14 (`docs/notes/unusual-units-2026-11-13.md`) screened penthouses, garden apartments and
townhouse floors against L1's spread. Of those, only the text penthouses joined D1's mark. A
shared m with the garden ads came out at -11 ± 19 against the duplex mark alone, and with the
townhouse ads at -90 ± 16.

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

A wider scale for other unusual units (penthouses, garden apartments, a townhouse floor) is
the next screen in this direction, and it is free.

## Rehearsal on a building subsample (exploration, 2026-11-14)

I ran D1's sampler on thelio's GPU, on the building subsample of L2's rehearsal
(`docs/notes/l2-phase-level-2026-11-13.md`), to check its convergence before a Modal fit. The
run scores no held-out ad and revises none of the predictions above. It checks the sampler
alone and compares no model with another, so it tests no feature in the sense of Ben's rule of
2026-10-07 against thelio pairs.

### The subsample

`subsample.py` in `docs/notes/rehearsals-2026-11-14/` cuts L2's 741 buildings out of the
duplex and penthouse copy of L1's dataset, with their 27,736 rows. The run reads the full
data's latest split as it is carried in the copy: 24,886 rows train, and the full fit's 2,850
held-out rows among them stay out. The mark covers 1,788 of the rows. Of those, 1,626 train,
in 237 buildings, and 162 are held out. `count.py` counts the marked training rows in each
phase with the model's `mark_index`:

| phase | none | 0-2 | 3-9 | 10-13 | 14-21 | 22-25 | 26+ |
|---|---|---|---|---|---|---|---|
| marked training rows | 1,095 | 58 | 78 | 74 | 85 | 48 | 188 |

k multiplies the factor of every marked cell, so all 1,626 rows bear on it.

### Settings, time and memory

`rehearse.sh` ran D1 with the settings of the launch plan above, except for the draws: 2
chains, 500 warmup sweeps, every 40th draw kept, seed 1 and `--level-dof 4`, with 2,400 draws
a chain in place of 9,000 to finish within 30 minutes. On Modal the 2,520 s budget stops each
container near 2,560 to 2,680 draws, and the fit pools three containers into 6 chains.

The run took 15 min 2 s: 52 s to compile, 141 s of warmup and 622 s of sampling at 0.263 s a
sweep of both chains. Host memory peaked at 3.8 GiB, and the GPU's at 1,077 MiB, 695 MiB above
the 382 MiB in use before the run.

### Diagnostics

`check.py` reads the gate table that `b0.main_run` computed with D1's own `diagnostics` on all
2,400 draws of each chain, and takes k from `factors` on the traced cell factors. The columns
are those of L2's rehearsal, and the last gives the share of draws under 1% of the median.

| parameter | R-hat | ESS | chain 1, median [95%] | chain 2, median [95%] | gap / sd | drift / sd | under 1% |
|---|---|---|---|---|---|---|---|
| k | 1.0010 | 581 | 1.831 [1.655, 2.017] | 1.822 [1.654, 2.012] | 0.10 | 0.06 | 0.000 |

This value comes from 1,626 marked rows in about 1 in 92 of the buildings, and I list it only
to show the chains agree. k mixes well, with lag-1 autocorrelation 0.76 to 0.78 on the log
scale, and its draws stay between 1.52 and 2.17 in both chains. Its log-normal prior has no
bound for it to stick at. Over the draws, log k correlates with the logs of sigma's four groups
at -0.16 to -0.24, with nu at -0.20, and with each of unit_sd, drift_sd and drift_tau by 0.16
or less in absolute value. The 13 cell factors of the trace, the phases' and the marked cells',
pass at R-hat 1.0035 or less and ESS 417 or more.

The run misses the gate on seven quantities. The table gives each as R-hat and ESS, beside L2's
rehearsal on the same buildings, seed and settings, and quantities at ESS under 400 in either:

| quantity | this run | L2's rehearsal |
|---|---|---|
| bld_sd[outer] | 1.0749, 23 | 1.0664, 17 |
| bld_sd[manhattan] | 1.0700, 19 | 1.0895, 12 |
| drift_tau | 1.0512, 67 | 1.0141, 445 |
| drift_sd | 1.0407, 79 | 1.0078, 580 |
| unit_sd | 1.0361, 93 | 1.0062, 854 |
| building_ar_rho | 1.0105, 441 | 1.0087, 323 |
| building_ar_sd | 1.0078, 418 | 1.0094, 311 |
| tau | 1.0070, 384 | 1.0049, 344 |
| sigma[0] | 1.0040, 370 | 1.0037, 517 |
| sigma[1] | 1.0029, 323 | 1.0060, 385 |
| sigma[2] | 1.0041, 328 | 1.0042, 536 |
| nu | 0.9997, 340 | 1.0030, 565 |

`check.py` also computes the buildings' levels' split R-hat on the 60 kept draws of each chain:
147 of 741 over 1.01 and 8 over 1.05, with a maximum of 1.0675, against 141.9, 6.3 and a median
maximum of 1.0795 for independent normal draws of the same size.

### Investigating the misses

The zones' spreads miss as they did in L2's rehearsal, at about the same R-hat and ESS. L2's
note traces that miss to the subsample: each zone keeps about 1 in 92 of its buildings, so the
spreads' posterior is about 9.6 times as wide as on the full data, and the spreads' slice
window of `drift.SPREAD_WIDTH` = 0.05 then spans 0.6 posterior sd in place of six. A rerun of
L2 with the window at 0.5 passed on both spreads. D1 draws the spreads with the same step from
the same buildings and changes nothing in it.

The unit scales miss by more than in L2's rehearsal, so I worked through them in order.

1. In the data, the marked rows are 6.5% of the training rows, close to their 6.6% share of
   the full data's rows, and every phase holds 48 or more of them.
2. In the model, k enters the scale step as one more coordinate beside the six phase factors,
   sigma, nu and the three unit scales. Its draws hardly correlate with the unit scales, as
   above. The unit scales correlate with each other as they did in L2's rehearsal: log unit_sd
   with log drift_sd at -0.86 against -0.81, log unit_sd with log drift_tau at -0.85 against
   -0.79, and log drift_sd with log drift_tau at 0.82 against 0.82. The two chains' medians
   agree within 0.7% for unit_sd, 2% for drift_sd and 8% for drift_tau, as in L2's rehearsal,
   so the chains explore the same region and do so slowly. Lag-1 autocorrelation of the logs
   runs 0.78 to 0.96, against 0.47 to 0.73 in L2's rehearsal.
3. In the sampler, `drift.update_scales` draws the unit scales, sigma, nu and the cell
   factors together. It integrates out the units' processes and the buildings' levels, holds
   the rows' mixing scales and the global coefficients fixed, and takes a slice step along
   each of a set of directions in turn. Warmup sets the directions from the curvature of the
   step's density at the chains' state. Per sweep, log drift_tau moved by an sd of 0.069 in
   D1's run, against 0.136 in L2's rehearsal and 0.112 in L2's diagnostic rerun, while its
   posterior sd was 0.31, 0.25 and 0.30. log drift_sd moved by 0.019, against 0.043 and
   0.034. Over blocks of 100 draws, the mean of log drift_tau moves with log unit_sd's at
   -0.94, with log drift_sd's at +0.90, with the four sigmas' at +0.54 to +0.63 and with the
   factors of phase 0-2 at -0.49 to -0.52. With k's cells it moves at under 0.34 in absolute
   value. Measured in the step's own coordinates, the moves along this axis come out as large
   as in L2's two runs, so the step samples the density warmup set it for, and in D1's run
   that density is narrower along the axis.

From this pair of chains I can't tell whether D1's mark narrows the step's density along the
axis, or the state at which warmup set the directions does. L2's two runs on the same data
mixed the unit scales at ESS 445 to 854 and at 113 to 164, so the step's speed varies by a
factor of four between runs of the same model. The block is L1's slowest on the full data as
well: L1's container `l1a` missed on its own pair of chains at 1.0134 for unit_sd and 1.0109
for drift_tau, and L1's pool of 4 chains passed.

### A second run, with the spreads' wider window

To separate the two explanations, I ran D1 once more on the same buildings, seed and settings,
with `width.py` setting the spreads' slice window to 0.5, as in L2's diagnostic rerun. The
wider window changes the chains' path from the first sweep, so warmup sets the directions at
another state. The run took 14 min 57 s: 52 s to compile, 143 s of warmup and 630 s of
sampling at 0.266 s a sweep. Host memory peaked at 3.8 GiB, and the GPU's at 1,077 MiB.

The spreads passed, at ESS 653 and 976, and the unit scales missed by far more than before:

| quantity | R-hat, ESS |
|---|---|
| unit_sd | 1.5925, 4 |
| drift_tau | 1.5725, 4 |
| drift_sd | 1.5626, 4 |
| sigma[0] to sigma[3] | 1.0969 to 1.1248, 21 to 30 |
| nu | 1.0961, 30 |
| k | 1.0228, 348 |
| the six other cell factors | 1.0175 to 1.0555, 87 to 452 |
| tau | 1.0039, 364 |

Chain 1 spent the whole warmup and its first 700 draws in another region of the scales:
unit_sd 0.019 to 0.023, drift_sd 0.066 and drift_tau 25 to 27 years, with the first group's
sigma at 0.0163 and k at 1.78. Over the next 200 draws it crossed to chain 2's region, with
unit_sd 0.061, drift_sd 0.035, drift_tau 3 to 5, sigma 0.0145 and k 1.84, and stayed there.
Chain 2 left that region once, for a block of 200 draws at a median drift_tau of 9.4. In the
long-tau region a unit's drift changes so slowly that it acts as a second level, and the rows'
noise takes the changes within a unit. Both regions give a unit's deviation about the same
total sd, 0.070. k's chain medians, 1.825 and 1.820, agree, and its R-hat comes from chain 1's
lower k in the long-tau region.

Every run of these rehearsals starts chain 1 in the long-tau region. At sweep 100 of the warmup,
its drift_tau stood at 15.7 and 18.6 in L2's two runs and at 23.0 and 21.2 in D1's. Warmup sets
the scale step's directions at sweeps 166 and 333, each time from the sixth of the warmup
before and from the curvature at the chains' state. L2's chain 1 left the region by sweep 200
in one run and by sweep 300 in the other, before the second setting. D1's chain 1 was still in
it at sweep 300 in the first run and through the whole warmup in this one, so in both of D1's
runs warmup set the directions with chain 1 in the long-tau region. After draw 1,000, with both
chains in the main region, the step moved log drift_tau by 0.059 a sweep in this run and 0.069
in the first, against 0.135 and 0.112 in L2's runs, and the unit scales came to ESS 33 to 47
and 45 to 54, against 256 to 659 and 85 to 120.

So the slow step of both D1 runs follows from the state at which warmup set its directions,
and in both runs D1's chain 1 left the starting region late. Four runs leave open whether D1's
mark holds chain 1 in the long-tau region or the timing differed by chance.

### I1's run and LN1's

I1 shares D1's sweep and differs only in its mark: in both models k joins the scale step as a
seventh free factor (`docs/notes/income-noise-2026-11-14.md`). I ran I1 on the same buildings,
seed and settings. Both of its chains had left the long-tau region by sweep 200, its step
moved at L2's pace, and its unit scales came to R-hat 1.0064 or less and ESS 315 to 452. LN1
adds log line_sd to the step in place of k (`docs/notes/line-level-model-2026-11-13.md`). Its
chain 1 stood in the region at sweeps 300 and 400, and its step came out slow, as in D1's runs.

The table gives each run's drift_tau at the warmup's reports, the scale of log drift_tau along
the final directions and its move a sweep after draw 1,000, both in posterior sds of log
drift_tau after draw 1,000, and the unit scales' R-hat and ESS on all draws:

| run | chain 1 at sweeps 100, 200, 300, 400 | chain 2 | directions' scale | move a sweep | unit scales' R-hat | ESS |
|---|---|---|---|---|---|---|
| L2 | 15.7, 13.2, 5.7, 3.0 | 11.2, 3.2, 4.3, 2.8 | 4.7 | 0.53 | 1.0062 to 1.0141 | 445 to 854 |
| L2, wider window | 18.6, 2.6, 4.0, 4.0 | 9.0, 4.3, 3.5, 3.6 | 2.3 | 0.40 | 1.019 to 1.032 | 113 to 164 |
| I1 | 14.9, 3.1, 4.1, 4.3 | 11.1, 3.0, 2.8, 2.6 | 2.6 | 0.43 | 1.0024 to 1.0064 | 315 to 452 |
| D1 | 23.0, 24.4, 18.8, 4.8 | 9.6, 4.0, 2.8, 4.3 | 1.1 | 0.21 | 1.0361 to 1.0512 | 67 to 93 |
| D1, wider window | 21.2, 23.9, 28.5, 23.6 | 7.0, 4.1, 3.2, 3.8 | 1.1 | 0.21 | 1.5626 to 1.5925 | 4 |
| LN1 | 10.7, 6.6, 11.3, 12.8 | 10.6, 5.8, 5.4, 18.8 | 1.1 | 0.18 | 1.4703 to 1.5115 | 4 to 5 |

Where a chain stood in the long-tau region at the second setting, the directions gave log
drift_tau a scale close to its posterior sd, and the step moved it by about a fifth of that sd
a sweep. In the other runs the scale came to 2.3 to 4.7 sds and the move to 0.40 to 0.53.

### A larger subsample

To test whether the small subsample itself causes the misses, I drew one twice as large.
`subsample.py 50 8` takes the first 1 in 50 of the
permuted buildings and adds the same flagged buildings, so it holds L2's 741 buildings and 680
more. Its 1,421 buildings hold 46,225 rows, 41,576 of them training rows and 4,649 the full
fit's held-out ads, which the run carries and leaves out. The mark covers 2,923 training rows
in 429 buildings, 7.0% of the training rows, and every phase holds 92 or more of them. I ran D1
on it with the settings above and 2,400 draws a chain. The run took 20 min 17 s: 59 s to
compile, 201 s of warmup and 882 s of sampling at 0.373 s a sweep. Host memory peaked at 4.0
GiB, and the GPU's at 1,605 MiB, 1,223 MiB above the 382 MiB in use before the run.

Chain 1 started in the long-tau region again and left it between sweeps 200 and 300: its
drift_tau stood at 15.2, 16.0, 5.7 and 5.9 at sweeps 100 to 400, and chain 2's at 8.9, 5.3,
4.6 and 5.3. Both chains stood outside the region when warmup set the directions at sweep 333.
The final directions give log drift_tau a scale of 2.0 posterior sds, and after draw 1,000 the
step moved it by 0.35 sd a sweep, in line with L2's and I1's runs.

The run misses the gate on 10 of its 255 quantities:

| quantity | R-hat, ESS |
|---|---|
| unit_sd | 1.1054, 16 |
| drift_sd | 1.0916, 17 |
| drift_tau | 1.0882, 23 |
| bld_sd[manhattan] | 1.0531, 26 |
| bld_sd[outer] | 1.0267, 126 |
| k | 1.0204, 460 |
| phase_scale[7], phase 3-9 with the mark | 1.0138, 625 |
| phase_scale[3], phase `none` with the mark | 1.0111, 638 |
| sigma[1] | 1.0057, 366 |
| nu | 1.0015, 252 |

The unit scales miss because chain 2 entered the long-tau region after the warmup. Over its
first 400 draws its block medians put drift_tau at 12.7 and 9.8 years, unit_sd at 0.048 and
0.052 and drift_sd at 0.052 and 0.048. Every later block of either chain puts them at 5.0 to
6.8, 0.058 to 0.061 and 0.038 to 0.041. With 1 in 50 of the buildings the posterior still
keeps mass in the region, 9.5% of the run's drift_tau draws lie above 9 years, and the step
crosses into the region and out of it slowly. From draw 1,000 on, the unit scales come to R-hat 1.0023 or less and
ESS 136 to 160 on 2,800 draws.

k's chain medians, 1.955 and 1.944, differ by 0.16 posterior sd, its draws stay between 1.73
and 2.19, and its lag-1 autocorrelation on the log scale is 0.75 to 0.77. Its split R-hat
comes from a rise in both chains: their medians went from 1.944 and 1.931 over the first 1,200
draws to 1.967 and 1.956 over the second, about a third of a posterior sd. Over blocks of 200 draws its mean moves with log unit_sd's at +0.48, log
drift_tau's at -0.54, log nu's at -0.46 and the four log sigmas' at -0.41 to -0.43, while over
single draws it correlates with each of them by 0.19 or less in absolute value. So k's slow
component follows the unit scales and the noise, and the two marked cells under the gate carry
k's factor. The buildings' levels come to 275 of 1,421 over 1.01 and 12 over 1.05, against
274.1 and 12.1 for independent normal draws of the same size, with a maximum of 1.1978 against
a median maximum of 1.0855.

### The full data

On the full data L1's posterior holds the unit scales far tighter. Over L1's pool of 4 chains
the logs of unit_sd, drift_sd and drift_tau have sds of 0.007, 0.014 and 0.045. After draw
1,000 in the L2, I1 and D1 runs on the subsample, with both chains out of the long-tau region,
they have sds of 0.03 to 0.04, 0.07 to 0.09 and 0.25 to 0.33. All 10,880 of L1's drift_tau
draws lie between 5.56 and 7.84 years. Its chains left the starting region early: drift_tau
stood at 12.8 and 9.8 in `l1a` and at 8.1 and 10.0 in `l1b` at sweep 100, and between 6.2
and 7.3 at every later report. I also read the warmup logs of the 37 full-data containers of
drift models with buildings and a warmup of 500 sweeps. In every chain, drift_tau at sweep 300
lay within a factor of 1.2 of its value at sweep 500. In chain 1 of D1's first run on the
subsample the factor was 5.9.

So I put D1's misses down to the subsample. With 1 in 100 or 1 in 50 of the buildings the
posterior keeps mass in the long-tau region, a chain crosses into it and out of it slowly, and
directions set while a chain stands there slow the step for the rest of the run. L1's draws on
the full data stay far from that region, and L1's chains settled by sweep 200. D1's k mixed
well in the first rehearsal and followed the unit scales in the larger one, so I expect it to
pass with them on the full data, though none of these runs tests that. For D1's Modal fit the
remaining risk is in the warmup: a chain still far from the main region at sweep 333 would
leave the step slow, as here. The start and the warmup's schedule are set in `drift.py`, which
every drift model shares and which I left unchanged. I changed nothing in D1's
module, and the predictions above describe the model as it is.
