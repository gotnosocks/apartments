# I1: L1 with a factor on the noise of income-restricted rows (2026-11-14)

S15 (`docs/notes/income-flag-2026-11-14.md`) emulated L1 reading `income_restricted_v2` in
place of `income_restricted` and found no gain. Afterwards I checked L1's coverage on the
ads the new flag marks: its 80% intervals cover 0.571 of them against 0.753 for other ads.
A multiplier m on L1's noise scale and unit sd for those ads, picked on half of the buildings
and scored on the other half, gained 63.5 ± 16.0. S15b, in the same note, put a negation
guard on the flag and read the AMI tier from each ad's text. A level by tier gained
+5.3 ± 6.8 on the 265 held-out ads the guarded flag marks, against +65.4 ± 20.2 for the
spread, since only 27 of those ads state a tier. With m on the noise scale alone the spread
gained +62.4 ± 16.6.

Both hypotheses came from a search I ran after S15 missed, on the same held-out ads of the
latest split that I1 is scored on. I chose to look at the spread after seeing L1's coverage
on these ads, and I chose the guard and the grid of m after S15's results. Splitting the
buildings in halves keeps the choice of m off the ads it is scored on, but the choice of the
change itself saw all of them. So the screen's +65.4 and +62.4 are optimistic, and I expect a
fit to gain less.

In this note I write I1 down before any launch. I have launched, queued and scheduled nothing
for it, and the launch waits for a budget from Ben.

## The change

`drift-building-phase-income` (`frontier/src/rentfrontier/drift_building_phase_income.py`)
is D1's design (`docs/notes/duplex-factor-2026-11-13.md`) with another mark. Each row gets a
mark, 1 where its own listing's `income_restricted_v2` is true and 0 otherwise, and a marked
row's noise scale gets a factor k on top of its phase's,

    s_i = sigma[group_i] * f[phase_i] * k^m_i.

The unit's process, the building's level and the rows' means stay as L1 has them, and so does
L1's coefficient for the old `income_restricted` flag. log k takes the Normal(0, 0.3) prior of
the phases' log factors, and the scale step draws it with the six phase factors, the unit
scales, sigma and nu. The column comes from `rentfrontier.b0textflags`, which wrote it with
the negation guard into the copy of L1's dataset rebuilt on 2026-11-14
(`docs/notes/text-flags-2026-11-13.md`). The copy has L1's rows in L1's order, so the
held-out ads are L1's.

The mark covers 2,698 of the 1,896,471 rows (0.14%): 2,433 training rows in 486 buildings and
265 held-out ads in 143 buildings. Every one of the 14 cells of phase and mark has rows; the
smallest marked cell, phase 22-25, has 56 rows, 41 of them training rows. k is shared across
the phases, so it draws on all the marked training rows. A k between 2 and 4 puts log k 2.3 to
4.6 prior sds from 0, and with about 2,400 marked training rows I expect the prior to pull
log k in by less than 0.01.

S15's m multiplied both L1's noise scale and its unit sd. I put k on the noise alone, as D1
does, for two reasons:

1. On the same 265 ads, m on the noise alone gained +62.4 ± 16.6 against +65.4 ± 20.2 for m
   on both (S15b, `g3_noise.py`). The noise alone needs a larger m, 3.5 against 2.5, since
   L1's unit part has about four times the variance of its noise on these ads.
2. In L1 the unit's process is shared by all of a unit's ads, so a factor on it by each row's
   own mark moves a held-out ad's location with its own mark wherever a unit has ads of both
   kinds. D1's note works through this. S15 found that 59% of the flag's held-out ads have an
   unmarked training ad in their unit, so here it would affect most of the marked ads. A
   factor on the unit's sd would need a mark fixed for the whole unit, such as its first ad's,
   and S15's pairs show that units switch between market and program ads.

With k on the noise alone, a held-out ad's location in each draw and the sd of its unit's
part come out the same whatever its own mark, and the mark widens only its noise. A marked
training row weighs less in its unit's and its building's estimates and in L1's coefficient
for the old flag, so the medians of other ads can move a little through those weights.

`frontier/tests/test_drift_building_phase_income.py` is D1's tests with the new mark. It
checks the cells and their map, each row's mark (the old flag marks nothing), a frame
without the column, the scale step's density against a dense Gaussian as k moves, and that
flipping the marks of the rows to predict leaves their locations and unit sds unchanged. On a
simulated design with a level for each unit and the noise of marked rows widened 2.5 times, a
run recovers k (median 2.0 to 3.0, phases within 0.2 of 1). The pin of a small run's draws
equals D1's, since on a design whose cells are already set the two models differ only in
the column a row's mark comes from.

The model is registered in `rentfrontier.run`, `ops/modal/app.py` and `ops/modal/cap.py`. I
left `drift_today` alone, since it serves the site. If I1 wins, serving it needs the model
added there with each apartment keeping its last ad's mark, as #1364 did for D1.

## Cost

I1's sweep is D1's: the same 14 cells, the same seventh free factor in the scale step, and
the same draws in every other step. The marks only change which cell a row falls in, so I took
D1's timing and did not time I1 again. On the CPU D1 averaged 1.167 s a sweep against L1's
1.097 s, 6% more. `cap.py` states 1.1 s for I1 as it does for D1, and estimates $4.19 and
3,560 s a container for I1, D1 and L1 alike (`cap.fit_estimate` with 2 chains, 500 warmup and
9,000 draws on an H100), since the 2,520 s sweep budget stops the sweeps. L1's containers
swept at 0.776 s on Modal, so at 2% to 6% more the chains end with 2,560 to 2,680 draws
against L1's 2,750. L1T's three containers settled at $3.57 to $3.73, $10.94 in all, so I
expect $11.00 to $11.50 for I1's three. Memory is L1's, in the normal 40 GiB container.

## Launch plan (not run)

Three H100 containers on the rebuilt `-textflags` copy of L1's dataset, seeds 1 to 3, pooled
by `drift_pool` into 6 chains, as for L1T and D1:

```sh
cd /data1/apartments/serve/master
D=/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-textflags
IN=/data1/apartments/pipeline/datasets/rows-b3ddebf19af1dc1e.parquet
for j in "ina 1" "inb 2" "inc 3"; do
  read -r label seed <<<"$j"
  ops/modal-fit --outside-budget --gpu H100 --dataset "$D" --input "$IN" \
    --split latest --baseline drift-building-phase-b0-latest-9a7830fb-l1 COMMIT "$label" \
    drift-building-phase-income b0 2 500 9000 40 --seed "$seed" --level-dof 4 \
    --no-loo --no-heldout
done
```

COMMIT is the master commit that carries this model. The copy's rows SHA-256 is
`59395e3209e14ff8a8bc235608c71a0395f2b4b18cb5f14b4eb271a7aaa30581`, and a rebuild that
changes it changes the marks. I compare the pool with L1's pool,
`drift-building-phase-b0-latest-9a7830fb-l1`, on the 189,647 shared held-out ads: elpd with
the SE clustered by building, the median's error, and the coverage of the 50%, 80% and 95%
intervals (`python -m rentfrontier.drift_score RUN`). I split each between the 265 marked ads
and the rest by joining `pred_scores.npz`'s listings to `income_restricted_v2`, as
`income-noise-2026-11-14/baseline.py` does.

## L1's numbers on these ads

`income-noise-2026-11-14/baseline.py` scores L1's `pred_scores.npz` as `drift_score.summary`
does:

| ads | n | elpd | median's error | 50% | 80% | 95% |
|---|---|---|---|---|---|---|
| all | 189,647 | 232,805.6 | 0.04068 | 0.515 | 0.797 | 0.943 |
| marked | 265 | 59.2 | 0.0725 | 0.355 | 0.562 | 0.774 |
| unmarked | 189,382 | 232,746.4 | 0.04066 | 0.515 | 0.798 | 0.944 |

The median's error is the median absolute gap between the log ask and the predictive median.
On the marked ads the mean gap is about -0.063, so they ask about 6% under L1's median, and
the mean of L1's predictive cdf at their asks is 0.40.

The script then rebuilds the marked ads' predictive from L1's 272 kept draws with each draw's
noise scale times k and the locations and unit sds as drawn. The cdf at k = 1 puts 0.574 of
them inside the 80% interval, against 0.562 from the sampled quantiles of `pred_scores.npz`.
The gains are S15b's `g3_noise.py`, summed over all 265 ads in sample:

| k | 50% | 80% | 95% | median's error | elpd gain |
|---|---|---|---|---|---|
| 1.0 | 0.355 | 0.574 | 0.781 | 0.0719 | 0 |
| 1.5 | 0.389 | 0.649 | 0.834 | 0.0719 | +31.5 |
| 2.0 | 0.426 | 0.702 | 0.860 | 0.0722 | +48.8 |
| 2.5 | 0.460 | 0.732 | 0.898 | 0.0723 | +58.0 |
| 3.0 | 0.491 | 0.766 | 0.917 | 0.0723 | +61.9 |
| 3.5 | 0.517 | 0.800 | 0.943 | 0.0723 | +62.4 |
| 4.0 | 0.543 | 0.830 | 0.958 | 0.0724 | +60.6 |

## Predictions (2026-11-14, 02:00 New York time, before any launch)

I start from the table above and hold it loosely, for these reasons:

1. The search after S15's miss chose the change on these ads, as I wrote at the top.
2. A fit draws k from the 2,433 marked training rows, and the held-out ads only receive it.
   Part of the held-out scatter comes from a unit's level moving between its training ads and
   the held-out ad: in 3 of S15's 10 pairs a market rental became a program ad. The training
   rows show the same excess only where their units and buildings place them badly. S15
   found that 43% of the flag's training rows have another row in their unit, so for most of
   them k trades off with the unit's own level.
3. With wider noise, the marked training rows weigh less in their units' and buildings'
   levels. The marked held-out ads ask about 6% under L1's median, and every one of them has
   a training row of its unit. Where a unit's training rows are all marked, its level moves
   toward its building's, which can raise the marked ad's median and widen its gap. The
   table above leaves this out.

The predictions are for the pool of three containers against L1's pool on the 189,647 shared
held-out ads.

1. The fit passes the gate (70%). k is a seventh scalar drawn from 2,433 rows, and unit_sd
   is still the likeliest miss, as for L1.
2. k's posterior median falls between 2.0 and 4.0 (60%) and above 1.5 (85%). Its 90%
   interval spans less than a factor of 1.3 (70%).
3. elpd gains 15 to 70 over L1 (60%), more than 0 (80%), and more than 2 SE (45%). The SE
   of the difference falls between 10 and 35 (60%).
4. The marked ads give 20 to 65 of the gain (60%), and more than 0 (85%). The unmarked ads
   give -30 to +30 (70%), mostly from the Monte Carlo difference between two pools.
5. On the marked ads 80% coverage rises from 0.562 to between 0.68 and 0.82 (60%), and above
   0.65 (80%). 95% coverage rises from 0.774 to between 0.86 and 0.96 (60%).
6. On all ads 80% coverage stays within 0.002 of 0.797, and 95% coverage within 0.002 of
   0.943 (80%). The marked ads are 0.14% of the held-out ads, so even a rise of 0.25 on them
   adds 0.0004.
7. The median's error on all ads stays within 0.0003 of 0.04068 (80%). On the marked ads it
   stays within 0.004 of 0.0725 (60%), and rises rather than falls (55%), for the third
   reason above.
8. L1's coefficient for the old `income_restricted` flag, -0.083 with a 90% interval from
   -0.089 to -0.078, moves by under 0.01 (65%), toward 0 if it moves by more than 0.003
   (60%).
9. Each of L1's phase factors moves by under 0.02 (75%), and each group's sigma by under 1%
   (80%). The marked rows are 0.14% of the training rows.
10. Each container stops its sweeps at the budget and runs 50 to 60 minutes, and the three
    settle between $10.50 and $12.00 (80%).

## Rehearsal on a building subsample (exploration, 2026-11-14)

I ran I1's sampler on thelio's GPU, an RTX 2060 SUPER with 8 GB, on a sample of whole
buildings, to check its convergence before a Modal fit. The run scores no held-out ad and
revises none of the predictions above. It checks the sampler alone and compares no model with
another, so it tests no feature in the sense of Ben's rule of 2026-10-07 against thelio pairs.

### The subsample

The scripts are in `docs/notes/rehearsals-2026-11-14/`, and L2's note
(`docs/notes/l2-phase-level-2026-11-13.md`) describes how `subsample.py` drew the buildings.
At 1 in 100, the 506 buildings with an ad flagged `income_restricted_v2` would give about 5
with the flag, so `subsample.py` adds the first 1 in 8 of them in a permutation of their own.
All five rehearsals use the resulting 741 buildings: 27,736 rows, 24,886 of them training rows
and 2,850 the full fit's held-out ads, which the run carries and leaves out. The run reads the
`-textflags` copy of the sample, with the column of the rebuilt copy of L1's dataset. `count.py`
counts the marked training rows with `drift_building_phase_income.mark_index`: 282 in 64
buildings, 1.1% of the training rows against 0.14% of the full data's rows, and 34 held-out ads.
By phase:

| phase | none | 0-2 | 3-9 | 10-13 | 14-21 | 22-25 | 26+ |
|---|---|---|---|---|---|---|---|
| marked training rows | 199 | 8 | 11 | 8 | 14 | 10 | 32 |

k is shared by the phases, so it draws on all 282 rows. A marked cell's factor is k times its
phase's factor, and the phases' factors rest mostly on their unmarked rows.

### Settings, time and memory

`rehearse.sh` ran I1 with the settings of the launch plan above, except for the draws: 2
chains, 500 warmup sweeps, every 40th draw kept, seed 1 and `--level-dof 4`, with 2,400 draws
a chain in place of 9,000 to finish within 30 minutes. On Modal the 2,520 s budget stops each
container at 2,560 to 2,680 draws by the estimate under Cost, and the fit pools three
containers into 6 chains.

The run took 14 min 45 s: 52 s to compile, 142 s of warmup and 620 s of sampling at 0.263 s a
sweep of both chains. Host memory peaked at 3.8 GiB, and the GPU's at 1,077 MiB, 695 MiB above
the 382 MiB in use before the run.

### Diagnostics

`check.py` reads the gate table that `b0.main_run` computed with I1's own `diagnostics` on all
2,400 draws of each chain, and takes k from the module's `factors` on the traced cell factors.
The columns are those of D1's rehearsal (`docs/notes/duplex-factor-2026-11-13.md`), with the
share of draws under 1% of the median last.

| parameter | R-hat | ESS | chain 1, median [95%] | chain 2, median [95%] | gap / sd | drift / sd | under 1% |
|---|---|---|---|---|---|---|---|
| k | 1.0060 | 402 | 2.584 [2.110, 3.089] | 2.637 [2.142, 3.162] | 0.21 | 0.07 | 0.000 |

This value comes from 282 marked rows in 64 buildings, a share of the rows eight times the
full data's, and I list it only to show the chains agree. k passes the gate, with ESS just over
400. Its lag-1 autocorrelation on the log scale is 0.78 to 0.82 and falls to 0.08 or less by
lag 20. Its draws stay between 1.82 and 3.57 in both chains, and over blocks of 200 draws its
median moves between 2.52 and 2.75 in each. log k takes a Normal(0, 0.3) prior, with no bound
for it to stick at. Over the draws log k correlates with each of the step's other scales, the
phases' factors, sigma, nu and the unit scales, by 0.11 or less in absolute value.

The run misses the gate on 14 of its 243 quantities, two of them marked cells' factors. The
trace keeps a factor for each of the 14 cells of phase and mark, with the cell of phase 10-13
without the mark held at 1, and k as the factor of the same phase with the mark.

| quantity | R-hat, ESS |
|---|---|
| bld_sd[manhattan] | 1.0972, 11 |
| bld_sd[outer] | 1.0835, 15 |
| building_ar_sd | 1.0131, 526 |
| building_ar_rho | 1.0129, 520 |
| sigma[0] to sigma[3] | 1.0092 to 1.0122, 346 to 439 |
| nu | 1.0107, 367 |
| tau | 1.0087, 342 |
| drift_tau | 1.0064, 315 |
| unit_sd | 1.0059, 361 |
| phase_scale[7], phase 3-9 with the mark | 1.0080, 384 |
| phase_scale[3], phase `none` with the mark | 1.0036, 381 |

The other eleven cell factors, k's among them, pass at R-hat 1.0099 or less and ESS 431 or more. drift_sd
passes at 1.0024 and 452.

`check.py` also computes the buildings' levels' split R-hat on the 60 kept draws of each chain:
138 of 741 over 1.01 and 7 over 1.05, with a maximum of 1.0657, against 141.9, 6.3 and a median
maximum of 1.0795 for independent normal draws of the same size.

### Investigating the misses

I worked through the data first, then the model, then the sampler.

1. In the data, every phase holds 8 or more marked training rows, and k draws on all 282. The
   column is neither sparse nor constant within the sample.
2. In the model, k joins the scale step as a seventh free factor beside the six phases', as D1's
   k does, and the marked cells' factors are products of a phase's factor and k. Its draws
   hardly correlate with the other scales, as above.
3. In the sampler, the zones' spreads crawl on the subsample, and the scale step mixes the
   unit scales at an ESS close to 400.

The zones' spreads crawl as in L2's rehearsal, with lag-1 autocorrelation 0.96 to 0.98 and
moves of 0.013 a sweep against posterior sds of 0.08. L2's note traces that crawl to the
subsample and the spreads' slice window, `drift.SPREAD_WIDTH` = 0.05, which spans about six
posterior sds on the full data and 0.6 here. Over blocks of 100 draws, building_ar_sd's mean
moves with log bld_sd[outer]'s at -0.74 and building_ar_rho's at -0.63, so the path's sd and
rho follow the outer zone's spread. Both passed in L2's rerun with the window at 0.5.

In every block of 200 draws both chains put unit_sd at 0.061 to 0.063 and drift_tau at 3.2 to
4.4 years. Both chains began in the long-tau region of D1's runs and left it early in the
warmup: their drift_tau stood at 14.9 and 11.1 at sweep 100 and at 3.1 and 3.0 at sweep 200.
So warmup set the scale step's directions at sweep 333 with both chains out of the region.
After draw 1,000 the step moved log drift_tau by 0.115 a sweep against a posterior sd of 0.27,
and the final directions give it a scale of 0.68, close to the 0.64 of L2's rerun. Over all
4,800 draws unit_sd came to ESS 361, drift_tau to 315, and sigma, nu and tau to 342 to 439.
L2's note finds tau slower on the subsample than on the full data, and here its lag-1
autocorrelation is 0.81 to 0.83.

The two marked cells' factors under 400 are k times the factors of phases `none` and 3-9, and
both pass on R-hat. I found no problem in k or in the module, I made no change to it, and the
predictions above describe the model as it is. I1's sweep is D1's with other rows in the
marked cells, so I also use this run in D1's note, to separate D1's structure from the timing
of its warmup.
