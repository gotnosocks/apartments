# L1TK with the rows' nu held at 2 (2026-11-13)

L1TK (`docs/notes/l1-unit-kap-collapsed-2026-11-13.md`) freed nu on a CPU check, but
unit_sd still moved slowly, along a direction where unit_sd, nu, sigma and the rows'
mixing scales trade the size of a unit's lasting departure against the ad's. This note
holds the rows' degrees of freedom nu at 2, the way L1T holds the units' at 3, and checks
on the same sample whether unit_sd then mixes. No fit is launched by this note.

Against L1 the model makes two changes: L1T's Student-t lasting level for each unit, and
the rows' fixed nu. Its pool can't be compared with L1 as a single change. The model
moves little from L1T's, since L1T's training posterior put nu at 1.99 (95% from 1.975 to
2.009), so its comparison with L1 measures the unit tail with a negligible second change.

## The value of nu

I took 2 as a round prior value. The rows' Student-t at 2 degrees of freedom keeps a
finite mean and has an infinite variance, which suits a tail made of typos, mislabeled
units and prices from a different lease. I chose it before reading any latest-split fit's
held-out scores. After choosing it I read the training posteriors: L1T puts nu at 1.99 and
L1 at 1.81 (1.80 to 1.83), so 2 sits inside L1T's interval.

## The change

`drift-building-phase-unitkn` (`frontier/src/rentfrontier/drift_building_phase_unitkn.py`)
is L1TK with `drift.make_sampler`'s new `row_dof_fixed=2.0`:

1. The noise step skips nu's slice update and still draws sigma with lam integrated out,
   then lam given sigma.
2. The scale step leaves log nu out of its coordinates. lam keeps its standardized logs
   and so stays where the noise step put it, while unit_sd, the drift scales, sigma and
   the phases' factors move together.
3. The run keeps nu at its value in the kept arrays and leaves it out of the traced ones,
   so the gate has no constant to measure.

`drift.py` changes only behind the new argument, and with it left at None the sweep draws
what it drew before. The pins of `drift-building`, L1, L1T, U2 and L1TK pass unchanged.
`frontier/tests/test_drift_building_phase_unitkn.py` checks that the scale step's density
with nu fixed equals the free density at nu = 2 for random scales and factors, that the
scale step and the noise step hold nu and the scale step holds lam, that sweeps keep nu at
2, and it pins the draws of a small run.

## The check on thelio

I ran the model on the 1-in-90 sample of buildings with L1T's and L1TK's harness: the
latest split's 18,441 training rows and 10,135 units, 6 chains, 300 warmup and 1,500
draws, seed 1 (`l1-row-dof-fixed-2026-11-13/sub_run.py`, model `l1tkn`). The table gives
each quantity's split R-hat, bulk ESS over the 6 chains and tau = 9,000 / ESS
(`l1-row-dof-fixed-2026-11-13/mix_stats.py`).

| quantity | L1T R-hat | tau | L1TK R-hat | tau | this model R-hat | ESS | tau |
|---|---:|---:|---:|---:|---:|---:|---:|
| nu | 1.0659 | 152 | 1.0382 | 43 | fixed | | |
| unit_sd | 1.0350 | 44 | 1.0284 | 41 | 1.0021 | 721 | 12.5 |
| drift_sd | 1.0120 | 18 | 1.0124 | 18 | 1.0043 | 595 | 15.1 |
| drift_tau | 1.0016 | 11 | 1.0033 | 9 | 1.0052 | 779 | 11.5 |
| sigma[1] | 1.0295 | 28 | 1.0184 | 17 | 1.0010 | 1,041 | 8.6 |
| sigma[2] | 1.0232 | 19 | 1.0150 | 15 | 1.0018 | 1,120 | 8.0 |
| sigma[3] | 1.0275 | 30 | 1.0170 | 14 | 1.0025 | 1,215 | 7.4 |
| phase_scale[1] | 1.0177 | 20 | 1.0122 | 11 | below 1.003 | | about 8.7 |
| mean log lam | 1.0620 | 140 | 1.0374 | 43 | 0.9997 | 6,684 | 1.3 |
| variance of log kap | 1.0224 | 37 | 1.0136 | 17 | 1.0062 | 1,061 | 8.5 |

With nu held, unit_sd's tau falls from L1T's 44 to 12.5 and the rows' mean log lam's from
140 to 1.3. The direction that held unit_sd back ran through nu, and holding nu removes
it. The worst coefficient, beta 140, stays at R-hat 1.0086 and tau 6.5 in all three runs:
none of the changes touch it.

I did not prototype the scale step with each unit's kap integrated out, option (b) of the
plan. Each of its density evaluations would integrate 935,396 kap numerically on a grid,
the slice update calls the density dozens of times a sweep, and the kap would then need
an exact draw from the same grid with a correction for its error, plus tests that the
pair leaves the posterior unchanged. That is several days of work, against a result here
that already clears the gate on the sample.

### What the full fit should expect

I scale L1T's full pool as in L1TK's note: ESS_new = ESS_L1T x tau_L1T / tau_new, and
R-hat^2 - 1 by tau_new / tau_L1T.

| quantity | L1T R-hat | ESS | expected R-hat | ESS |
|---|---:|---:|---:|---:|
| unit_sd | 1.0187 | 449 | 1.005 | 1,580 |
| drift_sd | 1.0051 | 942 | 1.004 | 1,140 |
| sigma[1] | 1.0103 | 1,250 | 1.003 | 4,100 |
| sigma[2] | 1.0090 | 1,336 | 1.004 | 3,170 |
| phase_scale[1] | 1.0090 | 1,223 | 1.004 | 2,740 |
| beta[bed=0:full>=2] | 1.0081 | 1,517 | 1.008 | 1,520 |

The highest expected R-hat is then beta[bed=0:full>=2]'s 1.008, as in L1T's pool, and the
lowest ESS is above 1,100. The ratio for unit_sd is again the least certain: on the full
data L1T's unit_sd had tau 27.3 against the sample's 44, so the full data's slow direction
is shorter, and the ratio may not carry over. I put the chance that the pool passes the
gate at 75%.

## Cost

The run shared thelio's CPU with other work, and its sweeps took 4.7 s on average. Its
quietest stretch, draws 750 to 1,125, swept at 3.1 s, against L1TK's 2.92 s alone. The
change removes a slice update and a coordinate of the scale step, so it adds no work. The
sweep budget caps each Modal container, so `cap.py` estimates each at $4.19 and 3,560 s,
as for L1T and L1TK, and I expect 3 containers to settle at about $11.

## Launch plan (no fit is launched by this note)

```sh
cd /data1/apartments/serve/master
D=/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise
IN=/data1/apartments/pipeline/datasets/rows-b3ddebf19af1dc1e.parquet
for j in "l1tkn1 1" "l1tkn2 2" "l1tkn3 3"; do
  read -r label seed <<<"$j"
  ops/modal-fit --outside-budget --gpu H100 --dataset "$D" --input "$IN" \
    --split latest --baseline drift-building-phase-b0-latest-9a7830fb-l1 COMMIT "$label" \
    drift-building-phase-unitkn b0 2 500 9000 40 --seed "$seed" --level-dof 4 \
    --no-loo --no-heldout
done
```

COMMIT is the merge commit of the PR that adds the model. The pool is compared with L1's,
`drift-building-phase-b0-latest-9a7830fb-l1`, on the held-out ads both share.

## Predictions (written before launch)

These assume the launch above, 3 containers on the latest split, compared with L1 on the
shared held-out ads.

1. The pool passes the gate (75%).
2. unit_sd's R-hat is at most 1.01 (80%), and its ESS above 800 (70%).
3. The highest R-hat belongs to a coefficient, not a scale (60%).
4. If it passes, elpd gains over L1 by more than 2 SE (90%), and lands within 300 of
   L1T's +4,095 (80%), since nu at 2 sits inside L1T's posterior.
5. The median's error and the 80% and 95% intervals' coverage on the held-out ads match
   L1T's to within 0.3 points (80%).
