# L1 with a Student-t unit level at 3 degrees of freedom (2026-11-12)

The reads of the 300 units furthest from their building
(`docs/notes/unit-level-reads-2026-11-12.md`) found three quarters of them to be real
apartments with real premiums, and b9 prices the ones above their building too low. That
note recommends putting U2's heavy-tailed unit level on L1 with the degrees of freedom
fixed at 3. This note writes that fit down before any launch.

## The change

`drift-building-phase-unitt` (`frontier/src/rentfrontier/drift_building_phase_unitt.py`)
takes L1's design, `drift-building-phase` with `--level-dof 4`, and gives unit k's lasting
level s_k U2's prior:

    s_k | kap_k ~ Normal(0, unit_sd^2 / kap_k),   kap_k ~ Gamma(3 / 2, rate 3 / 2)

So s_k is Student-t with 3 degrees of freedom and scale `unit_sd`. In u2a the sampled
degrees of freedom sat near 2.2 with a bulk ESS of 65 on 2 chains, and they moved with
`unit_sd` (correlation 0.78). I hold them at 3 as a prior choice: a round value with a heavy
tail and a finite variance. I did not read it off u2a, whose training rows include some of
the latest split's held-out ads.

The sampler is `drift.make_sampler` with L1's phases, `unit_t=True` and the new
`unit_dof_fixed=3.0`:

1. The scale step draws L1's 14 coordinates (the three unit scales, the four `sigma`, nu
   and the six phase factors) with u integrated out given the kap. U2's fifteenth
   coordinate, log nu_u, is left out, and so is its slice direction.
2. u and every s_k are drawn jointly by Matheron's rule, as in U2.
3. Given s, each kap_k is drawn from its Gamma conditional at nu_u = 3, then `unit_sd` and
   the kap move together along the orbit that keeps every `unit_sd^2 / kap_k`. U2's slice
   update of nu_u is skipped.

The run traces and keeps what L1's does. It drops `unit_dof`, a constant here, so the gate
covers L1's quantities and nothing more.

`drift.py` changes only behind the new argument. With `unit_dof_fixed` left at None the
sweep draws what it drew before: the sha256 pins of `drift-building`, L1 and U2
(`frontier/tests/test_drift_building_phase.py`, `test_drift_building_unitt.py`) pass
unchanged. `frontier/tests/test_drift_building_phase_unitt.py` checks the scale step's
density against the dense one with phases and `unit_t` together, with nu_u free and fixed,
checks that sweeps keep nu_u at exactly 3 while the kap move, and pins the draws of a
small run.

## Cost

On the CPU, on the 18,441 training rows and 10,135 units of the 1-in-90 sample of buildings
from Y1's timing (2 chains, 60 warmup and 60 draws), a sweep of L1 took 0.786 s and a sweep
of this model 1.205 s, 53% more. `cap.py` states 1.5 s a pair of chains against L1's 1.0.

L1's containers swept at 0.776 s on Modal, so these should take about 1.19 s a sweep. The
2,520 s sweep budget then holds about 2,120 sweeps: 500 warmup and about 1,620 draws a
chain, 40 kept, against L1's 2,720 draws and 68 kept. `cap.py` estimates each container at
$4.19 and 3,560 s, the same as L1 and U2, since the sweep budget caps all three. L1's
containers settled at $3.84 and $3.87, so I expect $7.5 to $8.5 for two.

The fewer draws are the main risk to the gate. L1's pool had its least bulk ESS at 788, on
`drift_tau`, from 4 chains of 2,720 draws. At the same mixing, 4 chains of about 1,620
draws give about 470. A miss on the gate is read as a sign of a problem in the data or the
model, so it does not lead to another container on a new seed. If the margin looks too thin
before launch, the plan can start with three containers instead, at about $12.

## Launch plan (no fit is launched by this note)

Two H100 containers on c3's dataset, seeds 1 and 2, pooled by `drift_pool`:

```sh
cd /data1/apartments/serve/master
D=/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise
IN=/data1/apartments/pipeline/datasets/rows-b3ddebf19af1dc1e.parquet
for j in "l1t1 1" "l1t2 2"; do
  read -r label seed <<<"$j"
  ops/modal-fit --outside-budget --gpu H100 --dataset "$D" --input "$IN" \
    --split latest --baseline drift-building-phase-b0-latest-9a7830fb-l1 COMMIT "$label" \
    drift-building-phase-unitt b0 2 500 9000 40 --seed "$seed" --level-dof 4 \
    --no-loo --no-heldout
done
```

COMMIT is the merge commit of the PR that adds the model. `--baseline` makes `cap.py
--check-launch` read L1's pool's `result.json` and refuse a launch on another split than
L1's `latest`. `--outside-budget` is there because Modal spend now needs a sprint budget
from Ben. I compare the pool with L1's pool, `drift-building-phase-b0-latest-9a7830fb-l1`,
on the held-out ads both share: elpd with the SE clustered by building, the median's error
and the coverage of the 50%, 80% and 95% intervals (`python -m rentfrontier.drift_score
RUN`).

## Predictions (written before launch)

These are the last section of `docs/notes/unit-level-reads-2026-11-12.md`, as written there.
In prediction 3, "this note" means that note.

These assume the degrees of freedom fixed at 3, on the latest split, compared with L1 on the
shared held-out ads.

1. The fit passes the gate (65%).
2. elpd gains over L1 by more than 2 SE (60%).
3. For the top 200 units above their building in this note, the share of held-out asks above
   the 80% interval falls from b9's 0.43 to under 0.35 (55%). L1 has no Deals columns,
   so b9 is the reference here.
4. 80% coverage on all held-out ads moves by less than 0.005 (75%).

## Results (2026-11-13)

Ben chose 3 containers rather than the 2 planned above, to give the ESS more room. I
launched them at 07:46 ET as `l1t1`, `l1t2` and `l1t3`, seeds 1 to 3, from bc8e7b95 (#1349),
fit-only on the latest split with L1 as the baseline. Modal ran `l1t2` on an H200 in
place of an H100. They settled at $3.57, $3.73 and $3.64, $10.94 in all. `drift_pool`
wrote `drift-building-phase-unitt-b0-latest-bc8e7b95-l1t` from them: 6 chains of 2,760
draws, 69 kept.

The sweeps took 0.67 to 0.77 s, about what L1's took, not the 1.19 s the CPU timing
above led me to expect. The chains got as many draws as L1's.

### The gate

The pool misses the gate on R-hat:

| quantity | L1T R-hat | ESS | L1 R-hat | ESS |
|---|---:|---:|---:|---:|
| nu | 1.0251 | 567 | 1.0030 | 956 |
| unit_sd | 1.0187 | 449 | 1.0076 | 946 |
| sigma[1] | 1.0103 | 1,250 | 1.0033 | 881 |
| drift_sd | 1.0051 | 942 | 1.0062 | 1,133 |

Every coefficient passes. The chains agree on where these quantities sit: nu's six chain
means lie between 1.989 and 1.993, and unit_sd's agree to four decimals. Inside a chain
they wander, with quarter means up to 0.4 posterior SD from the overall mean, and three
chains drift down a little over the run. At ESS 567 an R-hat near 1.011 is what the
half-chains alone would give (`docs/model/drift.md`, "What pooling buys"), so nu moves more
slowly than its ESS says. The run is not served and, by the rules, gets no further
container or seed.

The fit moved where the reads said it would. unit_sd fell from 0.060 to 0.047, drift_sd
from 0.040 to 0.030, and the ads' nu rose from 1.81 to 1.99. The heavy-tailed unit level
takes the big unit premiums that L1 spread over the row noise and the drift.

### Held-out scores (a free check, not a selection)

I scored the pool with `drift_score` and paired it with L1 on the 189,647 held-out ads both
share, the SE clustered by building (`l1-unit-t-fixed-2026-11-12/pair.py`). The chains
agree closely enough on every location that these scores should hold, but a run that
misses the gate is not compared for serving.

| group | ads | elpd gain | SE | median error L1 / L1T | 80% coverage L1 / L1T | above 80% L1 / L1T |
|---|---:|---:|---:|---:|---:|---:|
| all | 189,647 | +4,095.0 | 172.4 | 0.04068 / 0.04024 | 0.797 / 0.799 | 0.090 / 0.087 |
| top 200, above their building | 147 | +100.3 | 34.1 | 0.1090 / 0.0901 | 0.449 / 0.605 | 0.429 / 0.109 |
| top 200, below their building | 49 | +16.8 | 12.5 | 0.0687 / 0.0764 | 0.633 / 0.592 | 0.082 / 0.224 |
| ranks 201 to 2,000, above | 60 | -3.7 | 6.9 | 0.0656 / 0.0643 | 0.650 / 0.650 | 0.217 / 0.117 |
| ranks 201 to 2,000, below | 39 | -1.0 | 5.4 | 0.0459 / 0.0683 | 0.590 / 0.590 | 0.205 / 0.256 |

On all held-out ads the gain is 24 SE.
For the top 200 above their building the miss swings past zero: the median signed error
goes from +0.073 to -0.025, and 29% of their asks now fall below the 80% interval, against
12% under L1. The t level lets those units sit far from their building, and on their next
ad some of them come back part of the way.

### The predictions, scored

1. The fit passes the gate (65%). **Miss**: nu at 1.025 and unit_sd at 1.019.
2. elpd gains over L1 by more than 2 SE (60%). **Hit**, if the run had passed: +4,095,
   SE 172.
3. The top-200 share above the 80% interval falls from 0.43 to under 0.35 (55%). **Hit**:
   0.11. It overshoots: the share below rises to 0.29.
4. 80% coverage on all held-out ads moves by less than 0.005 (75%). **Hit**: +0.002.

### Next

The gain is too large to leave, so the next step is a model change that removes the slow
coupling, not another fit of this one. Following the order for a gate miss, the data
comes first: the reads found most of these units real, and the 5 ledger corrections reach
the next build. Then the model: nu and unit_sd move only through the scale step, which
conditions on the 935,396 kap. When a unit's kap is small, its level can sit far out at
little cost, and the row tail has less to explain. A step that moves nu together with the
kap, or a row tail fixed in the same way as the unit's, is what I would try first. Each
would be its own module and fit, written here first.
