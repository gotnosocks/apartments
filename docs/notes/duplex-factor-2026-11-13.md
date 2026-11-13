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
takes L1's design and gives each row a mark, 1 where its listing's `duplex` is true and 0
where it is false or missing. A marked row's noise scale gets a factor k on top of its
phase's,

    s_i = sigma[group_i] × f[phase_i] × k^m_i,

and its unit's process gets the same factor, u_i = k^m_i × v_i, with v the process L1 draws
for the row's unit. A marked row's whole distance from its building's level is then k times
as wide as an unmarked row's in the same phase. Since a row's mark comes from its own
listing's text, an ad of a unit takes no mark from the unit's other ads, and the unit's
marked and unmarked rows share v. log k takes the Normal(0, 0.3) prior of the phases' log
factors, and the scale step draws it with the six phase factors, the unit scales, sigma and
nu. The design and the rows' means are L1's.

The sampler takes the cells of phase and mark as its phases. `Design.phase_map` gives each
marked cell its phase's factor times k, as Y1's map gave each cell its phase's and its year's
factors, and the new `Design.unit_factor` names k's column, so the sweep scales u by each
marked row's k. With gains g_i on u, the unit kernel of a bucket becomes G K G. For the
marginal likelihood of the unit scales I divide each remainder by its gain and multiply its
weight by the gain squared, which gives the same density up to a term in the gains that
cancels against the change in the rows' noise weights. A row to predict takes its gain from
its own cell. The run keeps each cell's factor as `phase_scale` and each predicted row's cell
as `pred_phase`, so `drift_score` and `drift_pool` read it as they read L1's.

`unit_factor` is None for every other model, and the sha256 pins of the draws of
`drift-building`, L1, L1T, Y1, L2, the segment model, `drift-building-phase-unitk` and
`drift-building-phase-unitt` pass as before. `frontier/tests/test_drift_building_phase_duplex.py`
checks the marginal likelihood and the scale step's density against a dense Gaussian as k
moves, the moments of u's draw and of the predictive under gains, recovers a planted k of 1.5
(median 1.3 to 1.75, phases within 0.2 of 1) on a simulated design, and pins the draws of a
small run.

`drift_today` refuses every phased model but L1, so if D1 wins, serving it needs a
change there first.

## Cost

I timed the sweeps on the CPU with `docs/notes/duplex-factor-2026-11-13/time_sweep.py`, on
the 18,441 training rows and 10,135 units of the 1-in-90 sample of buildings from Y1's timing,
754 of them marked (2 chains, 60 warmup and 60 draws). I alternated the two models, with the
machine's load average at 21 to 29 from another thread's fit and the test suites:

| run | seconds a sweep | warmup | draws |
|---|---|---|---|
| L1 | 2.534 | 151.5 s | 152.5 s |
| D1 | 2.964 | 192.8 s | 162.8 s |
| L1 | 2.826 | 163.9 s | 175.2 s |
| D1 | 3.214 | 205.4 s | 180.3 s |
| L1 | 2.844 | 163.4 s | 177.9 s |

The load makes every sweep slower than L1's 1.7 s on a quieter machine. Over both stages D1
took 13% longer than L1, 3.089 s a sweep against 2.735 s. Most of that is warmup, at 25% more,
while the draws took 2% more. The seventh free factor adds a direction to the scale step's
slice updates, and the warmup likely spends more of them while k moves away from 1. A third
D1 run was killed at its 2.5 GB memory cap, and I reran it at 3.2 GB.

`cap.py` gives D1 a stated rate of 1.1 s a pair of chains. L1's containers swept at 0.776 s on
Modal, and at 13% more the 2,520 s sweep budget holds about 2,870 sweeps: 500 warmup and about
2,370 draws a chain, against L1's 2,750. If the extra time stays in warmup, the draws come to
about 2,570. So the chains end with 6% to 14% fewer draws than L1's, and the ESS of each
quantity falls about as much. `cap.py` estimates each container at $4.19 and 3,560 s, as it
does for L1, since the budget stops the sweeps. L1T's three containers settled at $3.57 to
$3.73, $10.94 in all, so I expect about $11.50 for three.

Memory is L1's. The rows' cells take the place of their phases, and the sweep computes the
gains of u from the cells, so D1 runs in the normal 40 GiB container.

## Launch plan (no fit is launched by this note)

Three H100 containers on the duplex copy of L1's dataset, seeds 1 to 3, pooled by
`drift_pool` into 6 chains, as for L1T:

```sh
cd /data1/apartments/serve/master
D=/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-duplex
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
order with one more column, so the held-out ads are L1's. I compare the pool with L1's pool,
`drift-building-phase-b0-latest-9a7830fb-l1`, on those ads: elpd with the SE clustered by
building, the median's error and the coverage of the 50%, 80% and 95% intervals
(`python -m rentfrontier.drift_score RUN`). I split each count between the ads the column
marks and the rest by joining `pred_scores.npz`'s listings to the column.

## Predictions (written before launch)

All of these are for the pool of three containers on the latest split, against L1's pool on
the shared held-out ads. L1's numbers there: median error 0.04068 and 80% coverage 0.797, and
on the 10,331 marked ads an 80% coverage of 0.719.

1. The fit passes the gate (75%). L1's pool of 4 chains reached a largest R-hat of 1.0076
   (unit_sd) and a smallest ESS of 788 (drift_tau). D1 pools 6 chains with 6% to 14% fewer
   draws each, and k moves the unit scales of the marked rows, so unit_sd is the likeliest
   miss.
2. k's posterior median falls between 1.25 and 1.45 (60%), and above 1.15 (90%). Part D's
   1.3 and 1.4 scaled L1's predictive, and the fit's k also widens the unit levels of marked
   rows in training, which takes some of the spread S7 counted.
3. elpd gains 150 to 350 over L1 (60%), and more than 2 SE (85%).
4. The marked ads give 180 to 330 of it, and the other ads -20 to +60 (60% that both hold).
   The other ads gain only as far as sigma and the unit scales fall once the marked rows stop
   widening them.
5. On the marked ads 80% coverage rises from 0.719 to between 0.76 and 0.81 (60%), and above
   0.75 (80%).
6. 80% coverage on all shared ads stays within 0.005 of 0.797 (80%).
7. The median's error moves by under 0.0003 (70%) and by under 0.0005 (85%). k changes a
   marked ad's weight against its unit's other ads, and the column moves no mean.
8. Each of L1's phase factors moves by under 0.02 (70%).
9. Each group's sigma falls by 0% to 3% (65%). The marked rows are 5.7% of the rows.
10. Each container stops its sweeps at the budget and runs 50 to 60 minutes, and the three
    settle between $10.50 and $12.00 (80%).

A wider scale for other unusual units (penthouses, garden apartments, a townhouse floor) is
the next screen in this direction, and it is free.
