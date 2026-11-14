# Segment paths: L1 with a path in time for each bedroom group in each zone (2026-11-13)

S1 of the causal screens (`docs/notes/causal-screens-2026-11-13.md`) found that studios,
family units, Manhattan and the other boroughs moved through 2020 to 2023 on paths of their
own. On L1's held-out ads of 2019 to 2023, a cross-fitted path per bedroom group gained
180 ± 20 elpd over a static offset, a path per zone 177 ± 32, and a path per cell of bedrooms,
zone and lift 452 ± 50. L1 moves every ask in the city along one citywide walk, so a gap that
opens and closes between segments shows up in it only through each building's own path, shrunk
toward zero on its own. In this note I write the segment model down before any launch, with
the timing check the proposal asked for. I have launched, queued and scheduled nothing for it,
and the launch waits for a sprint budget from Ben.

## The change

`drift-building-phase-segment` (`frontier/src/rentfrontier/drift_building_phase_segment.py`)
takes L1's design and adds a path for each of eight segments: the bedroom groups studio, 1,
2 and 3+, each in Manhattan and in the other boroughs. A row's segment comes from its bedroom
group and its site's zone, and the path is piecewise linear between the starts of calendar
quarters. For a row i in segment s_i at time t_i, with h_j(t) the hat weight of quarter start
j, the design gets a column for each segment k and quarter start j:

    x_kj(i) = h_j(t_i) * (1[s_i = k] - p_kj)

Here p_kj is segment k's share of the rows, weighted by h_j. A row's mean then gains its
segment's path less the share-weighted mean of the eight paths, so the citywide walk keeps the
market's average and each path holds its segment's deviation from it. The columns read a
row's date, bedroom group and site, so a held-out row's columns take no rent.

Each segment's coefficients get a Gaussian process prior over the quarter starts: a squared
exponential covariance, held at 0 on 2024-01-01, since a unit's level carries its segment's gap
on that date and the path moves it in other years. The covariance's nugget leaves the
2024q1 coefficient a prior sd of a tenth of the amplitude. The squared amplitude has an
InvGamma(2, 7e-4) prior, a median amplitude of about 2% in log rent, and the log lengthscale in
years a Normal(0, 0.5) prior, a median of a year. The sweep draws the path coefficients with
the design's other global columns, and the eight amplitudes and lengthscales with the floor
curves'.

The screens note proposed walks with one shared step size. Here each segment gets its own
amplitude and lengthscale, since S1 found the zone paths about half again as wide as the
bedroom paths (0.63% against 0.40%).

The data leave one direction to the prior alone. Adding the same c_j to every segment's
coefficient at quarter start j changes no row's mean, since the shares p_kj sum to 1 over the
segments. The Gibbs step draws that direction from its full conditional every sweep, so the
coefficients mix well along it, but the eight amplitudes follow it. If an amplitude misses the
gate, a sum-to-zero constraint over the segments' paths is the model change to try first.

`drift.py` is unchanged. `drift_pool` now takes the convergence table a model's module
carries, as `b0.main_run` does, so this model's pool checks the paths' amplitudes and
lengthscales too. A module carrying drift's table, as every earlier drift model does, pools as
before. The sha256 pins of the draws of `drift-building`, L1
and L2 pass as before. `frontier/tests/test_drift_building_phase_segment.py` checks the
columns against the hat weights and shares, checks the columns of the rows to predict and the
order of the processes, recovers planted paths (correlation over 0.8 with the planted effect,
RMS error under half its sd) and pins the draws of a small run.

## Weekly or quarterly steps

I timed sweeps on the CPU with `docs/notes/segment-paths-2026-11-13/time_sweep.py`, on the
18,441 training rows and 10,135 units of the 1-in-90 sample of buildings from Y1's timing,
2 chains, 60 warmup and 60 draws. The machine's 1-minute load average stood at 14.4 to 22.6
through the runs, from the other thread's work.

| design | global columns | path columns | CPU sweep |
|---|---|---|---|
| L1 | 198 | 0 | 1.725 s |
| quarterly paths | 628 | 430 | 2.688 s |
| weekly paths | 5,260 | 5,062 | killed at its 6 GB memory cap 86 s in |

The weekly design doesn't fit as dense columns. On L1's 1,896,471 rows it would hold about
5,630 global columns, 85 GB for the design alone, more than the 40 GiB container and the
H100's 80 GB. Forming the global block's system would take about 1.1e14 flops a sweep for a
pair of chains, some 4 s at 25 TFLOPS of fp64, five times L1's whole sweep of 0.776 s. Weekly
steps would need sparse path columns in `drift.py`'s global step, its prior and its
predictions, which is a rewrite of the sampler's global block. The prior also gives weekly
knots little to add: with a median lengthscale of a year, and 95% of the prior between 0.4 and
2.7 years, a path bends little within a quarter, and linear interpolation between quarter
starts follows it closely. So the fit uses quarterly steps.

## Cost

On the CPU the quarterly paths take a sweep 56% longer than L1's, so `cap.py` states the
segment model's rate as 1.6 s a pair of chains against L1's 1.0. The GPU should add less. On
L1's data the paths take the global block from about 250 columns to about 680, and forming
its system rises from about 2e11 to 1.6e12 flops a sweep for a pair of chains, about 0.06 s at
25 TFLOPS of fp64. I expect an H100 sweep of 0.83 to 0.95 s against L1's 0.776 s. A drift fit
stops its sweeps at the 2,520 s budget, so the paths cut the sweeps to about 2,650 to 3,050
from L1's 3,260, still over 2,000 draws a chain, and leave the wall time where L1's was.

Host memory set the container in the first version of this note. `b0.main_run` kept the
design of all rows, the training rows' copy and the held-out rows' copy alive through the fit,
and the training design carries its own copy of the held-out rows to predict.
`drift.make_sampler` then reordered the training rows and dropped the intercept column in one
step (`d.x[order][:, others]`), which held two more copies of the training rows while it set
up the sampler. With the paths, those arrays alone came to about 40 GB, the size of the
40 GiB container (42.9 GB).

A follow-up PR leaves the host only the training design and its rows to predict, and every
pinned draw of the drift and B0 models passes as before:

1. `main_run` counts the held-out rows from the split's mask. It reads the fields the run
   record needs from the design of all rows, then deletes that design before the sampler
   starts.
2. `make_sampler` gathers each block's rows and columns straight from the training design
   (`d.x[np.ix_(order[r0:r1], others)]`), so the host never holds a sorted copy of the whole
   training design.

I measured the host's numpy memory with `tracemalloc` on the 1-in-90 sample with this model's
design, from the end of the design build through `make_sampler`
(`docs/notes/segment-paths-2026-11-13/peak.py`). The counts are in units of the design of all
rows, 102.9 MB on the sample. The script starts `tracemalloc` after the design build, so its
counts leave that design out, and I added 1.0 to each count taken while the design was still
alive:

| | before | after |
|---|---|---|
| held when the sampler starts, the design of all rows included | 2.113 | 1.012 |
| peak at the split | 2.114 | 2.026 |
| added by `make_sampler` | 2.143 | 1.247 |
| peak in `make_sampler` | 4.256 | 2.259 |

The sample has fewer than 4,096 buildings, so its sampler runs a single block. On the CPU, JAX
keeps its arrays in host memory. If it reads the numpy blocks in place, the 1.247 includes the
blocks' 0.9 of the design, which an H100 holds on the GPU instead. `tracemalloc` misses
buffers JAX allocates itself, so a copy would come on top. On L1's 1,896,471 rows the design
with the paths takes 10.3 GB, and its 67,972 buildings make 17 blocks. Scaled by that, the
host's peak falls from about 44 GB to about 23 GB in `make_sampler` as counted on the CPU, or
to about 21 GB at the split once the blocks go to the GPU. The frame and the other tables come
on top of these counts. The design build peaks near 16 GB, since `path_design` fills a
preallocated array. The 40 GiB container (42.9 GB) holds the larger count with about 15 to
20 GB to spare, so the fit goes back to the normal container. L1's own peak falls the same
way, from about 16 GB to about 9 GB.

`cap.py` estimates $4.19 and 3,560 s a container, the same as for L1. L1T's three containers
came to $10.94 at the H100's $4.36 an hour, and the path design takes a little longer to build
than L1's, so I expect $11 to $12.50 for three, against the proposal's $11.50.

## Launch plan (no fit is launched by this note)

Three H100 containers on L1's dataset, seeds 1 to 3, pooled by `drift_pool` into 6 chains,
as for L1T and L2:

```sh
cd /data1/apartments/serve/master
D=/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise
IN=/data1/apartments/pipeline/datasets/rows-b3ddebf19af1dc1e.parquet
for j in "sega 1" "segb 2" "segc 3"; do
  read -r label seed <<<"$j"
  ops/modal-fit --outside-budget --gpu H100 --dataset "$D" --input "$IN" \
    --split latest --baseline drift-building-phase-b0-latest-9a7830fb-l1 COMMIT "$label" \
    drift-building-phase-segment b0 2 500 9000 40 --seed "$seed" --level-dof 4 \
    --no-loo --no-heldout
done
```

COMMIT is the merge commit of the PR that adds the model. The proposal runs this fit after L2,
on the best model at its launch. If L2 wins its comparison first, the paths go on L2 instead,
through a small module that adds the path columns to L2's design, and the predictions below
then count against L2's pool. I compare the pool with the base's pool on the held-out ads both
share: elpd with the SE clustered by building, the median's error and the coverage of the 50%,
80% and 95% intervals (`python -m rentfrontier.drift_score RUN`).

## Predictions (written before launch)

All of these are for the pool of three containers on the latest split, against L1's pool on
the shared held-out ads. L1's numbers there: median error 0.04068 and 80% coverage 0.797. On
its held-out ads of 2020 to 2022, 80% coverage is 0.736.

1. The fit passes the gate (50%, as in the proposal). The likeliest miss is a segment's
   amplitude.
2. elpd gains 250 to 600 over L1 (50%), the proposal's range, and more than 2 SE (75%). S1's
   452 came from 24 cells of bedrooms, zone and lift, and bedroom and zone paths overlap, so
   my present range is 200 to 500 (60%). I score both.
3. At least half the gain comes from held-out ads priced in 2020 to 2023 (65%).
4. From 2019q4 to 2021q1 the mean of the four Manhattan paths falls 2 to 8 points against the
   mean of the four outer paths (65%). By 2023q1 the difference between the two means is back
   within 2 points of its 2019q4 value (55%).
5. Each path's posterior median amplitude falls between 0.5% and 5% (70%), and each median
   lengthscale between 0.5 and 3 years (70%).
6. The median's error moves by under 0.0005 (80%).
7. 80% coverage on the held-out ads of 2020 to 2022 rises from 0.736 by 0.005 to 0.015 (45%),
   the proposal's range, and on all shared ads it stays within 0.005 of 0.797 (80%).
8. Each container gets through `make_sampler` (95%), stops its sweeps at the budget after
   2,600 to 3,200 sweeps (65%), and runs 50 to 60 minutes. The three settle between $10.50 and
   $13 (75%). I revised this prediction before any launch, when the fit moved from the large
   container to the normal one; it first read $14.50 to $17 for three large containers.

## Rehearsal on a building subsample (exploration, 2026-11-14)

I ran the model's sampler on thelio's GPU, an RTX 2060 SUPER with 8 GB, on a sample of whole
buildings, to check its convergence before a Modal fit. The runs score no held-out ad and
revise none of the predictions above. They check the sampler alone and compare no model with
another, so they test no feature in the sense of Ben's rule of 2026-10-07 against thelio pairs.
The first run missed the gate on a path's amplitude and lengthscale. I traced the miss to the
model, added a level column for three of the segments, and ran the rehearsal again. In the
rerun the chains agreed on every path, and the gate missed on a lengthscale, outer:studio's
worst of all, which I trace to the subsample's thin data.

### The subsample

The scripts are in `docs/notes/rehearsals-2026-11-14/`, and L2's note
(`docs/notes/l2-phase-level-2026-11-13.md`) describes how `subsample.py` drew the buildings.
All five rehearsals use the same 741 buildings: 27,736 rows, 24,886 of them training rows and
2,850 the full fit's held-out ads, which the runs carry and leave out. `count.py` counts each
segment's training rows, and the quarter starts at which the segment's training rows weigh
less than 20 in the hat weights of `hat_weights`:

| segment | training rows | quarter starts under 20 |
|---|---:|---:|
| manhattan:studio | 2,579 | 3 |
| manhattan:1br | 4,983 | 2 |
| manhattan:2br | 3,486 | 3 |
| manhattan:3br+ | 1,194 | 21 |
| outer:studio | 1,881 | 14 |
| outer:1br | 4,201 | 3 |
| outer:2br | 3,953 | 4 |
| outer:3br+ | 2,609 | 9 |

The 54 quarter starts run from 2013-10-01 to 2027-01-01, and the design keeps 430 of the 432
hat columns.

### The first run

`rehearse.sh` runs `rentfrontier.run` through `ops/job gpu` as `ops/modal-fit` runs it on Modal,
with the launch plan's settings: 2 chains, 500 warmup sweeps, every 40th draw kept, seed 1 and
`--level-dof 4`. I cut the draws from 9,000 to 2,400 a chain to finish within 30 minutes. On
Modal the 2,520 s budget stops the sweeps after 2,600 to 3,200, and the fit pools three
containers into 6 chains, against this run's single pair.

The first run, of the module as committed with the predictions, took 27 min 51 s: 53 s to
compile, 259 s of warmup and 1,189 s of sampling at 0.499 s a sweep of both chains, against
0.262 s for L2 on the same buildings. Host memory peaked at 4.1 GiB, and the GPU's at
1,599 MiB, 1,217 MiB above the 382 MiB in use before the run.

It missed the gate. `check.py` gives each path's amplitude and lengthscale with the R-hat and
ESS of `run.split_rhat` and `run.ess` over all 2,400 draws, and each chain's median:

| segment | amplitude R-hat, ESS | chain medians | lengthscale R-hat, ESS | chain medians |
|---|---|---|---|---|
| manhattan:studio | 1.0123, 274 | 0.017, 0.018 | 1.0403, 94 | 1.04, 1.27 |
| manhattan:1br | 1.0080, 239 | | 1.0959, 31 | 0.48, 0.45 |
| manhattan:2br | 1.0422, 67 | | 1.1519, 23 | |
| manhattan:3br+ | 1.0379, 58 | 0.20, 0.23 | 1.0194, 214 | 2.0, 2.1 |
| outer:studio | 1.0279, 184 | | 1.4332, 12 | 0.37, 0.33 |
| outer:1br | 2.1534, 1 | 0.134, 0.027 | 2.8260, 1 | 2.34, 0.31 |
| outer:2br | 1.0018, 700 | | 1.0344, 73 | |
| outer:3br+ | 1.0036, 255 | | 1.0065, 74 | |

Of the 430 hat coefficients, the worst was outer:1br's at 2024q1, with an R-hat of 1.5771.
The buildings' levels over the 60 kept draws of each chain gave 143 of 741 R-hats over 1.01
and 9 over 1.05, with a largest of 1.0974. Independent draws of that size give 141.9 and 6.3
on average and a median largest of 1.0795, so the levels mixed.

### Investigating the miss

1. The data. outer:1br has 4,201 training rows, and its hat weight falls under 20 at only 3
   of the 54 quarter starts, so the segment is neither sparse nor degenerate in the sample.
   The thinnest segments, manhattan:3br+ and outer:studio, missed by less.
2. The model. The note above expected an amplitude to miss through the direction the data
   leave to the prior, a shift c_j added to every segment's coefficient at quarter start j.
   I subtracted the eight segments' mean at each quarter from each path. outer:1br's
   deviations from that mean still gave an R-hat of 1.537, so the chains disagreed on
   outer:1br's own path, and a sum-to-zero constraint would not have changed it. Chain by
   chain, `notch.py` compares each path at 2024q1 with the mean of its two neighbors:

   | segment | chain | path's mean | 2023q4 | 2024q1 | 2024q2 | amplitude | lengthscale |
   |---|---|---|---|---|---|---|---|
   | outer:1br | 1 | +0.009 | +0.014 | +0.020 | +0.016 | 0.135 | 2.34 |
   | outer:1br | 2 | +0.006 | +0.014 | +0.002 | +0.014 | 0.027 | 0.31 |
   | manhattan:3br+ | 1 | +0.091 | +0.036 | +0.020 | +0.033 | 0.201 | 1.99 |
   | manhattan:3br+ | 2 | +0.094 | +0.041 | +0.023 | +0.040 | 0.227 | 2.11 |

   Around 2024, outer 1-bedroom units on these buildings asked about 1.5% more than the
   bedroom steps and the outer buildings' levels gave, and outer:1br's path carried that gap
   on both sides of 2024q1. The prior holds each path at 0 on 2024-01-01 with an sd of a
   tenth of its amplitude. Chain 2 kept a narrow path and dropped it to 0 at 2024q1 in a
   notch one quarter wide, with a lengthscale of 0.31 years to allow it. Chain 1 found a
   wide, slow path instead, whose amplitude of 0.135 loosens the hold at 2024q1 to an sd of
   0.013, and neither chain crossed to the other's mode in 2,400 draws. manhattan:3br+ bent
   the same way at 2024q1. Both of its chains agreed, on a path averaging 9% over the
   quarters and an amplitude ten times the prior's median.

   The note above assumed a unit's level would carry its segment's gap on 2024-01-01. In L1
   a unit's level shrinks toward its building's, and most buildings hold units of several
   bedroom groups, so the units' levels carry only part of the gap. L1 gives each bedroom
   group a level through its bedroom steps, shared by the zones, and each zone a level
   through its buildings' levels. The rest of a segment's lasting gap, the zone by bedroom
   interaction, fell to the paths, where the hold at 2024q1 fights it.
3. The sampler. The two modes of outer:1br come from the model's density, so I left the
   sampler's settings as they were.

### A larger subsample

A subsample can split chains where the full data would not, so I tested that explanation
before changing the module. `subsample.py 50 8` keeps the first 1 in 50 of the same
permutation, 1,421 buildings holding all 741 of the first sample's, with 41,576 training rows
and 4,649 held-out ads carried. Every segment has 2,312 or more training rows. I ran the module
as committed with the predictions on it, with 1,200 draws a chain in place of 2,400 to finish
within 30 minutes.

The run took 25 min 30 s: 76 s to compile, 391 s of warmup and 901 s of sampling at 0.760 s
a sweep. Host memory peaked at 4.4 GiB, and the GPU's at 2,635 MiB, 2,253 MiB above the
382 MiB in use before the run. It missed the gate again, on another segment:

| segment | amplitude R-hat, ESS | chain medians | lengthscale R-hat, ESS | chain medians |
|---|---|---|---|---|
| manhattan:2br | 1.3622, 7 | 0.102, 0.090 | 1.3283, 5 | 3.79, 3.12 |
| manhattan:3br+ | 1.0062, 436 | 0.354, 0.365 | 1.0014, 712 | 2.11, 2.14 |
| outer:1br | 1.0139, 314 | 0.025, 0.026 | 1.0024, 273 | 0.26, 0.26 |

Both chains put outer:1br in the first run's narrow mode, with a notch of 0.020 at 2024q1
below neighbors at +0.020 to +0.025. manhattan:2br's path averaged +0.034 and +0.031 over
the quarters and dipped by 0.007 at 2024q1. Chain 2's amplitude ranged from 0.019 to 0.144
in its 95% interval and its lengthscale from 0.22 to 6.05 years, so it moved between a narrow
mode and a wide one, and chain 1's median moved by 2 pooled sds between its halves.
manhattan:3br+'s path averaged +0.130 and its amplitude grew to 0.35, 18 times the prior's
median. With twice the buildings the split moved from one segment to another, and the
amplitudes grew with the lasting gaps the paths carried, so the subsample does not explain the
miss.

### The fix

I gave the remaining three segments' lasting gaps a place of their own in the module. The
design now carries a level column for each bedroom group past studios in the outer zone,
`level:outer:1br`, `level:outer:2br` and `level:outer:3br+`, 1 on the segment's rows and 0 on
the others (`level_columns`). With the bedroom steps and the zones' building levels, they give
every segment a level, and each path holds only its segment's movement about that level, with
0 on 2024-01-01 as before. The columns take the Normal(0, 0.5) prior that `b0.prior_arrays`
gives a flag, and the sweep draws them with the design's other global columns. The new tests
check the columns, check that they and the bedroom steps span the eight segment levels, plant
a lasting gap in outer:1br and check that it goes to the level column with the path near 0,
and check the new draws of a small run. The module's tests pass.

### The predictions and the fixed model

"The change" above and the predictions describe the module before the fix, and I left both as
they were. The fixed model adds to L1 a static interaction of zone and bedroom group as well as
the paths. S1 measured its gains for paths against a static offset, so the 250 to 600 of
prediction 2 counted no gain from a static interaction, and a pool of the fixed model against
L1's would mix the two. Prediction 5 was reasoned for paths carrying lasting gaps: in the
first run manhattan:3br+'s amplitude came to 0.20 and 0.23, and the level columns should move
such a path's amplitude down toward its movement in time alone. Predictions 3, 4, 6, 7 and 8
read the same for both models. So predictions 2 and 5 no longer describe the model as it
stands, and I have flagged that for the project thread.

### The rerun

I ran the rehearsal once more on the module with the fix, commit 94728efd, with the same
buildings, seed and settings. The run took 27 min 56 s: 55 s to compile, 260 s of warmup and
1,189 s of sampling at 0.500 s a sweep. Host memory peaked at 4.1 GiB, and the GPU's at
1,599 MiB, 1,217 MiB above the 382 MiB in use before the run.

The chains no longer split. Every amplitude came to between 0.015 and 0.030 in both chains,
close to the prior's median of 0.02. By `notch.py`, each path's chain medians lie within 0.004
of its neighbors' mean at 2024q1, and each path's mean over the quarters lies within 0.02 of 0.
No scale has a draw under 1% of its median.

| segment | amplitude R-hat, ESS | chain medians | lengthscale R-hat, ESS | chain medians |
|---|---|---|---|---|
| manhattan:studio | 1.0078, 353 | 0.020, 0.020 | 1.0425, 110 | 1.05, 1.24 |
| manhattan:1br | 1.0064, 334 | 0.015, 0.015 | 1.1125, 34 | 1.19, 1.04 |
| manhattan:2br | 1.0004, 345 | 0.016, 0.017 | 1.0413, 37 | 0.59, 0.48 |
| manhattan:3br+ | 1.0142, 100 | 0.030, 0.030 | 1.0318, 72 | 0.86, 0.79 |
| outer:studio | 1.0095, 125 | 0.021, 0.021 | 1.2464, 3 | 0.26, 0.83 |
| outer:1br | 1.0100, 328 | 0.027, 0.028 | 1.0306, 44 | 0.34, 0.35 |
| outer:2br | 1.0003, 974 | 0.026, 0.026 | 1.0177, 89 | 0.37, 0.41 |
| outer:3br+ | 1.0032, 480 | 0.018, 0.018 | 1.0354, 82 | 0.67, 0.64 |

| level column | R-hat, ESS | chain medians |
|---|---|---|
| level:outer:1br | 1.0035, 481 | +0.030, +0.029 |
| level:outer:2br | 1.0021, 905 | +0.002, +0.000 |
| level:outer:3br+ | 1.0131, 187 | -0.099, -0.103 |

The run still missed the gate, with its largest R-hat, 1.2464, and its least ESS, 3, on
outer:studio's lengthscale. outer:studio's hat coefficients gave the eight worst R-hats among
the 430, up to 1.1925. Every lengthscale missed, at ESS 3 to 110, and six amplitudes missed on
ESS. level:outer:3br+ missed at R-hat 1.0131 and ESS 187, beside bed>=3 at ESS 190, and the
two correlate at -0.67 over the draws. Outside the segment model's own parameters, the zones'
building spreads missed at R-hat 1.073 and 1.062, from the slice window L2's note traces to
the subsample, and tau and drift_tau missed on ESS alone, at 382 and 327. Of the buildings'
levels, 141 of 741 came over 1.01 and 6 over 1.05, as independent draws give. The largest,
1.268, belongs to a building with a single training row, and its level correlates with no
lengthscale by more than 0.25 in absolute value.

### The remaining miss

outer:studio's lengthscale moved slowly between two ranges. In blocks of 300 draws, chain 1
spent six of its eight blocks at medians of 0.20 to 0.38 years and one at 1.01, and chain 2
spent six at 0.80 to 1.04 and two at 0.33 and 0.35. Each chain crossed to the other's range,
so neither stuck, but a crossing took hundreds of sweeps. I worked through the data, the
model and the sampler in turn.

1. The data. outer:studio holds 1,881 training rows, with a hat weight under 20 at 14 of the
   54 quarter starts. `inform.py` divides the median within-chain sd of a path's coefficients
   by the chain's median amplitude, the coefficients' prior sd. For outer:studio the ratio
   comes to 0.68 and 0.61, the largest of the eight, so the data narrow its path little from
   the prior. Its chain medians stay within 0.036 of 0, against sds of 0.009 to 0.020. The
   other seven paths come to ratios of 0.47 to 0.66, and their lengthscales mixed slowly as
   well.
2. The model. The sweep draws a segment's amplitude and lengthscale by slice sampling given
   the path's coefficients, and the coefficients given the amplitude and lengthscale. While
   the data leave the coefficients close to their prior, the 53 coefficients of a path hold
   its lengthscale in a narrow band at each sweep, though its posterior spans a wide range, so
   the lengthscale moves in small steps. While the data fix the coefficients, the draw of the
   lengthscale given them comes close to a draw from its posterior. The three runs show both
   cases. In the first run and in the larger subsample, manhattan:3br+'s path carried a
   lasting gap, the data fixed it at ratios of 0.10 and 0.06, and its lengthscale's ESS came
   to 214 of 2,400 draws and 712 of 1,200. Leaving out the paths split between two modes,
   every path with a ratio of 0.46 or more gave its lengthscale an ESS of 273 or less, and
   outer:studio's came to 12, 14 and 3 in the three runs.
3. The subsample. The full data hold about 92 times the subsample's buildings. At a ratio of
   0.6 the data add about 1.8 times the prior's precision to each coefficient. If that
   precision grows with the buildings, the ratio falls to about 0.08 on the full data, the
   range in which manhattan:3br+'s lengthscale mixed here. thelio can't test this with a
   larger subsample: in the largest that fits, 1 in 50, outer:studio's 2,385 training rows
   gave ratios of 0.49 and 0.55 and a lengthscale ESS of 14 in 1,200 draws, still in the slow
   range.

I expect the miss to come from the subsample's thin data and to clear on the full data, but no
run here confirms it. I made no second change to the module and ran no third rehearsal. If the
Modal fit misses on a lengthscale, a non-centered draw of each segment's amplitude and
lengthscale, holding the coefficients' whitened values fixed, is the sampler change to try.
