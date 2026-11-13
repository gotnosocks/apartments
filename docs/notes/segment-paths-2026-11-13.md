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
(`docs/notes/segment-paths-2026-11-13/peak.py`). In units of the design of all rows, 102.9 MB
on the sample:

| | before | after |
|---|---|---|
| held when the sampler starts, the design of all rows included | 2.113 | 1.012 |
| peak at the split | 2.114 | 2.026 |
| added by `make_sampler` | 2.143 | 1.247 |
| peak in `make_sampler` | 4.256 | 2.259 |

The sample has fewer than 4,096 buildings, so its sampler runs a single block. On the CPU, JAX
keeps its arrays in host memory, so the 1.247 includes the blocks' 0.9 of the design, which an
H100 holds on the GPU instead. On L1's 1,896,471 rows the design with the paths takes 10.3 GB,
and its 67,972 buildings make 17 blocks. Scaled by that, the host's peak falls from about
44 GB to about 23 GB, or to about 21 GB at the split once the blocks go to the GPU. The design
build peaks near 16 GB, since `path_design` fills a preallocated array. The 40 GiB container
holds all of this with some 20 GB to spare, so the fit goes back to the normal container. L1's
own peak falls the same way, from about 16 GB to about 9 GB.

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
