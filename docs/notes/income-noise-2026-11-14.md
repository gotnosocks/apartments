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
smallest marked cell, phase 22-25, has 56. k is shared across the phases, so it draws on all
the marked training rows.

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
