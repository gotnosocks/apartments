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
