# L2: L1 with a level for each lease phase (2026-11-13)

S3 of the causal screens (`docs/notes/causal-screens-2026-11-13.md`) found that L1 widens
the noise of each lease phase and leaves its center at the unit's level. A relist within two
months asks 1.4% under L1's median on held-out ads, and a level for each phase, cross-fitted
over two halves of the buildings, gains 281 ± 29 elpd on top of a constant shift of every
held-out ad. In this note I write L2 down before any launch. I have launched, queued and
scheduled nothing for it, and the launch waits for a sprint budget from Ben.

## The change

`drift-building-phase-level` (`frontier/src/rentfrontier/drift_building_phase_level.py`)
takes L1's design and adds a 0/1 column for each lease phase other than 10-13 months:

    phase:none, phase:0-2, phase:3-9, phase:14-21, phase:22-25, phase:26+

A row's mean gains the coefficient of its phase's column. Each coefficient takes the
Normal(0, 0.5) prior that `b0.prior_arrays` gives a flag, and the sweep draws the six with the
design's other global columns (the slow block takes only `bld:` columns). As in L1, a row's
phase comes from the price_at dates of its unit's ads (`drift_building_phase.phase_index`),
so a held-out row's columns depend on dates alone. Every held-out ad of the latest split has
an earlier ad of its unit, so no held-out row is in phase `none`: its level moves the training
rows of each unit's first ad, and through them the unit levels.

L1's noise factors stay as they are, with s_i = sigma[group_i] × f[phase_i]. The sampler, the
traced quantities and the gate are L1's, with six more coefficients in `beta`.

`drift.py` is unchanged. The sha256 pins of the draws of `drift-building`, L1 and L1T pass
as before. `frontier/tests/test_drift_building_phase_level.py` checks the columns against the
phases and the columns of the rows to predict, recovers six planted levels within 0.06 log
on a simulated design, and pins the draws of a small run.

## Cost

I timed the sweeps on the CPU with `docs/notes/l2-phase-level-2026-11-13/time_sweep.py`, on
the 18,441 training rows and 10,135 units of the 1-in-90 sample of buildings from Y1's timing
(2 chains, 60 warmup and 60 draws). A sweep of L1 took 1.732 s and a sweep of L2 1.717 s. I ran
the two back to back with the machine's load average at 15 to 16, which is why both took
longer than L1's 1.037 s on 2026-11-12. The six columns join a global block of about 200, so
`cap.py` gives L2 L1's stated rate, 1.0 s a pair of chains.

L1's containers swept at 0.776 s on Modal and L1T's at 0.67 to 0.77 s. At L1's rate the
2,520 s sweep budget holds about 3,250 sweeps: 500 warmup and about 2,750 draws a chain,
68 kept at every 40th. `cap.py` estimates each container at $4.19 and 3,560 s, as it does for
L1. L1T's three containers settled at $3.57 to $3.73, $10.94 in all, so I expect about $11.50
for three.

## Launch plan (no fit is launched by this note)

Three H100 containers on L1's dataset, seeds 1 to 3, pooled by `drift_pool` into 6 chains, as
for L1T:

```sh
cd /data1/apartments/serve/master
D=/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise
IN=/data1/apartments/pipeline/datasets/rows-b3ddebf19af1dc1e.parquet
for j in "l2a 1" "l2b 2" "l2c 3"; do
  read -r label seed <<<"$j"
  ops/modal-fit --outside-budget --gpu H100 --dataset "$D" --input "$IN" \
    --split latest --baseline drift-building-phase-b0-latest-9a7830fb-l1 COMMIT "$label" \
    drift-building-phase-level b0 2 500 9000 40 --seed "$seed" --level-dof 4 \
    --no-loo --no-heldout
done
```

COMMIT is the merge commit of the PR that adds the model. I compare the pool with L1's pool,
`drift-building-phase-b0-latest-9a7830fb-l1`, on the held-out ads both share: elpd with the SE
clustered by building, the median's error and the coverage of the 50%, 80% and 95% intervals
(`python -m rentfrontier.drift_score RUN`). For the count over a constant shift I move each
pool's held-out predictive by a constant cross-fitted over the two halves of the buildings,
as S3 did for L1, and compare the two after their shifts.

## Predictions (written before launch)

All of these are for the pool of three containers on the latest split, against L1's pool on
the shared held-out ads. L1's numbers there: median error 0.04068, 80% coverage 0.797, and on
the 13,725 ads in phase 0-2 an 80% coverage of 0.760.

1. The fit passes the gate (75%).
2. elpd gains 150 to 350 over L1 (60%), and more than 2 SE (85%).
3. Counted over a constant shift of each pool, elpd gains 150 to 350 as well (60%). The gain
   over L1 and the gain over the constant differ by under 100 (70%).
4. At least half the gain comes from the held-out ads in phase 0-2 (65%). In S3, 192 of the
   281 came from them.
5. The posterior median of the 0-2 level, as exp(beta) - 1, falls between -2.0% and -1.4%.
   I took that range from S3's mean gaps, and it is the range in the costed proposal. I now
   give it 20%: a check I made after the proposal suggests a smaller level, so I also write
   my present range, -1.6% to -0.6% (70%), and score both. L1's noise has nu = 1.81, so a
   fitted level follows the Student-t location of its rows more than their mean. On L1's
   held-out ads, with each ad's predictive scale and nu = 1.81, the t location of the gap is
   -1.25% for phase 0-2 and -0.21% for 10-13, a difference of about -1.0%.
6. The other levels against 10-13, from the same t locations, each within 0.4 points of it:
   3-9 between -1.0% and -0.2%, 14-21 between -0.7% and +0.1%, 22-25 between -0.4% and +0.4%,
   26+ between -0.6% and +0.2% (50% that all four hold). I make no prediction for `none`,
   since no held-out ad is in it.
7. The median's error moves by under 0.0005 (80%).
8. 80% coverage on all shared ads stays within 0.005 of 0.797 (80%). On the ads in phase 0-2
   it rises from 0.760 by 0.005 to 0.03 (55%).
9. L1's noise factor for phase 0-2, 1.083 at its posterior median, falls by 0.01 to 0.05
   (50%), and each of the other factors moves by under 0.03 (65%).
10. Each container stops its sweeps at the budget and runs 50 to 60 minutes, and the three
    settle between $10.50 and $12.00 (80%).

The previous ad's ending is a second change for after L2. S3 puts it at 30 to 100 elpd on
top of a level per phase.

## Rehearsal on a building subsample (exploration, 2026-11-14)

I ran L2's sampler on thelio's GPU, an RTX 2060 SUPER with 8 GB, on a sample of whole
buildings, to check its convergence before a Modal fit. The run scores no held-out ad and
revises none of the predictions above. It checks the sampler alone and compares no model with
another, so it tests no feature in the sense of Ben's rule of 2026-10-07 against thelio pairs.

### The subsample

The scripts are in `docs/notes/rehearsals-2026-11-14/`. `subsample.py 100 8` permutes L1's
67,972 buildings with numpy's `default_rng(20261114)` and keeps the first 1 in 100. Only 506
buildings hold an ad flagged `income_restricted_v2`, so for I1's factor it then permutes those
and adds the first 1 in 8. The result has 741 buildings and 27,736 rows. Each copy carries the
full data's latest split as `carried_heldout`, and the run reads it with `--split carried`:
24,886 rows train, and the full fit's 2,850 held-out rows among them stay out. All five
rehearsals use these buildings. `count.py` counts the training rows in each lease phase with
`drift_building_phase.phase_index`:

| phase | none | 0-2 | 3-9 | 10-13 | 14-21 | 22-25 | 26+ |
|---|---|---|---|---|---|---|---|
| training rows | 14,339 | 1,070 | 1,250 | 1,986 | 1,731 | 1,088 | 3,422 |

Each of L2's six columns covers more than 1,000 training rows.

### Settings, time and memory

`rehearse.sh` runs `rentfrontier.run` through `ops/job gpu` as `ops/modal-fit` runs it on Modal,
with the launch plan's settings: 2 chains, 500 warmup sweeps, every 40th draw kept, seed 1 and
`--level-dof 4`. I cut the draws from 9,000 to 2,400 a chain to finish within 30 minutes. On
Modal the 2,520 s budget stops the sweeps near 2,750, and the fit pools three containers into
6 chains, against this run's single pair.

The run took 14 min 40 s: 51 s to compile, 140 s of warmup and 619 s of sampling at 0.262 s a
sweep of both chains. Host memory peaked at 3.8 GiB, and the GPU's at 1,077 MiB, 695 MiB above
the 382 MiB in use before the run.

### Diagnostics

`check.py` reads the gate table from `b0.main_run`, which applies L2's own `diagnostics` to all
2,400 draws of each chain, and computes the same split R-hat and bulk ESS for each new
coefficient with `run.split_rhat` and `run.ess`. In the table, the gap is the distance between
the two chains' medians over the pooled sd. The drift is the larger of the two chains' moves in
median from their first half to their second, on the same scale.

| coefficient | R-hat | ESS | chain 1, median [95%] | chain 2, median [95%] | gap / sd | drift / sd |
|---|---|---|---|---|---|---|
| phase:none | 1.0014 | 1,260 | -0.0015 [-0.0044, 0.0015] | -0.0017 [-0.0050, 0.0014] | 0.09 | 0.07 |
| phase:0-2 | 0.9999 | 1,539 | -0.0115 [-0.0149, -0.0081] | -0.0114 [-0.0151, -0.0079] | 0.04 | 0.05 |
| phase:3-9 | 0.9997 | 1,517 | -0.0120 [-0.0160, -0.0079] | -0.0120 [-0.0163, -0.0076] | 0.00 | 0.04 |
| phase:14-21 | 1.0024 | 1,321 | -0.0066 [-0.0101, -0.0032] | -0.0066 [-0.0101, -0.0032] | 0.02 | 0.22 |
| phase:22-25 | 1.0020 | 1,431 | -0.0021 [-0.0060, 0.0018] | -0.0023 [-0.0064, 0.0017] | 0.12 | 0.04 |
| phase:26+ | 1.0012 | 1,459 | -0.0044 [-0.0074, -0.0012] | -0.0044 [-0.0076, -0.0010] | 0.02 | 0.13 |

These medians come from about 1 in 92 of the buildings, and I list them here only to show the
chains agree. The six coefficients mix well: R-hat at most 1.0024, ESS at least 1,260 of 4,800
draws, and medians within 0.12 sd between the chains. All six multiply 0/1 columns under
normal priors with no bounds.

Eight of the other 236 quantities miss the gate in this run. The table gives each as R-hat and
ESS, beside the diagnostic run described below and L1's container `l1a`, a single pair of
chains on the full data. unit_sd and drift_sd pass here and miss in the diagnostic run.

| quantity | this run | spreads' window at 0.5 | `l1a`, full data |
|---|---|---|---|
| bld_sd[manhattan] | 1.0895, 12 | 1.0016, 491 | 1.0019, 841 |
| bld_sd[outer] | 1.0664, 17 | 1.0000, 1,169 | 1.0027, 981 |
| phase_scale[3], phase 3-9 | 1.0271, 299 | 1.0005, 559 | 1.0011, 636 |
| building_ar_sd | 1.0094, 311 | 1.0004, 769 | 1.0026, 796 |
| building_ar_rho | 1.0087, 323 | 1.0008, 822 | 1.0035, 751 |
| tau | 1.0049, 344 | 1.0028, 334 | 1.0001, 2,158 |
| sigma[1] | 1.0060, 385 | 1.0047, 338 | 1.0014, 459 |
| drift_tau | 1.0141, 445 | 1.0322, 124 | 1.0109, 408 |
| unit_sd | 1.0062, 854 | 1.0288, 113 | 1.0134, 453 |
| drift_sd | 1.0078, 580 | 1.0190, 164 | 1.0082, 563 |

The drift models' table leaves out the buildings' levels, so `check.py` also computes their
split R-hat on the 60 kept draws of each chain: 141 of 741 over 1.01 and 8 over 1.05, with a
maximum of 1.163. Independent normal draws of the same size give 141.9 and 6.3 on average, with
a median maximum of 1.078. At 60 kept draws a chain, these counts match independent levels.

### Investigating the misses

I worked through the data first, then the model, then the sampler.

In the data, the subsample keeps all the rows of a sampled building, so each building's level
rests on the same rows as in the full data, while each zone keeps about 1 in 92 of its
buildings. The posterior sd of log bld_sd here is 0.081 in each zone. In `l1a` it is 0.0084 and
0.0078, smaller by about 9.6, the square root of 67,972 / 741.

In the model, L2 adds six columns to the global block of L1's design and leaves the building
step as it is. Over the draws, neither spread correlates with another traced scale by more than
0.31 in absolute value, or with any coefficient by more than 0.12.

In the sampler, `drift.update_cells` draws each zone's log spread by slice sampling, with the
buildings' levels and paths integrated out, in a window of `SPREAD_WIDTH` = 0.05 with no
stepping out. A draw moves at most 0.05 and about a third of that on average. On the full data
the window spans six posterior sds: `l1a`'s draws moved 0.0055 a sweep against an sd of 0.0084,
with lag-1 autocorrelation 0.56 to 0.60. On the subsample the window spans 0.6 sd, and the draws
moved 0.015 a sweep against an sd of 0.081, a random walk with lag-1 autocorrelation 0.971. The
building path's sd and rho mixed at the same pace on both data sets, at lag-1 autocorrelation
about 0.65, because warmup scales the directions of their steps.

To test that explanation I ran L2 once more on the same subsample, seed and settings, with
`width.py` setting the window to 0.5, about the same multiple of the posterior sd as on the full
data.
The run took the same 14 min 40 s and 3.8 GiB. Its spreads moved 0.052 a sweep, with lag-1
autocorrelation 0.55 to 0.65, and passed at ESS 491 and 1,169. phase_scale[3], building_ar_sd
and building_ar_rho passed along with them, so the spreads' random walk had held those back as
well. The miss on the spreads comes from the subsample: on the full data the posterior is
narrow enough for the window, and L1 passed there with the same step. I changed nothing in
`drift.py`, and I count the wider window as a diagnostic alone.

The other misses fall on drift_tau, unit_sd and drift_sd, which the sweep draws as a block
along directions found in warmup, and on tau and sigma[1]. The block missed at R-hat 1.0141 in
the first run and 1.019 to 1.032 in the second, where its ESS fell to 113 to 164. In both runs
the chains' medians agree within 1.5% for unit_sd and drift_sd and within 8% for drift_tau, and
the autocorrelation falls under 0.1 by lag 50. The block is L1's slowest on the full data as
well: `l1a` missed on its own pair of chains, at 1.0134 for unit_sd and 1.0109 for drift_tau,
and L1's pool of 6 chains passed with its largest R-hat, 1.0076, on unit_sd and its least ESS,
788, on drift_tau. tau mixes more slowly here than on the full data (lag-1 0.83 against 0.37)
with steps of the same size. I expect the cause lies in the data behind tau's walk, since each
week holds about 1 in 92 of its full-data rows. At the first run's rate per draw, 6 chains
of 2,750 draws would give tau and sigma[1] an ESS above 1,100.

I found no problem in L2's six coefficients. I made no change to the module, and the
predictions above describe the model as it is.

### Refused commands

The permission check refused seven commands during these rehearsals:

1. a `for` loop calling a venv's Python from a loop variable;
2. a `sort` reading a path from a shell variable;
3. a heredoc writing a script for a single Python run;
4. a `sed` and a `grep` followed by a Python run from an empty heredoc, in one command;
5. a `for` loop calling `systemd-run` with a run directory from a loop variable, twice;
6. a Python run from an empty heredoc, too complex for the check to confirm it stayed in
   the worktree.

I reran each as plain commands with literal absolute paths, writing any script to a file
first.
