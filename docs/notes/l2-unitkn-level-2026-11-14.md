# L2 on the unitkn base: a level for each lease phase (2026-11-14)

This is fit 2 of the causal sprint (`causal-sprint-2026-11-14.md`, account B: the ask is a
move in a search). I wrote the predictions below before launching anything, from L1TKN's saved
held-out predictions and the rehearsal in `unitkn-rehearsals-2026-11-14.md`.

## The change

`drift-building-phase-unitkn-level` takes L1TKN (`drift-building-phase-unitkn`, the sprint's
base, `l1-row-dof-fixed-2026-11-13.md`) and adds the six 0/1 phase columns of
`l2-phase-level-2026-11-13.md` to its design:

    phase:none, phase:0-2, phase:3-9, phase:14-21, phase:22-25, phase:26+

A row's mean gains the coefficient of its phase, with 10-13 months as the reference. A row's
phase comes from the `price_at` dates of its unit's ads, so a held-out row's columns depend
on dates alone. The Student-t unit level at 3 degrees of freedom, the rows' degrees of freedom
held at 2 and the noise factor of each phase stay as L1TKN has them.

## Evidence on the base

I tabulated L1TKN's pool on its 189,647 held-out ads by phase
(`/data1/apartments/tmp/sprint-20261114/l2pre.py`, `l2pre2.py`). The gap is log ask less the
predictive median.

| phase | ads | median gap | less 10-13's | asks under the median | 80% coverage | noise factor |
|---|---|---|---|---|---|---|
| 10-13 | 30,233 | -0.0020 | | 51.6% | 81.3% | 1 |
| 0-2 | 13,725 | -0.0121 | -0.0101 | 62.1% | 76.8% | 1.092 |
| 3-9 | 17,068 | -0.0082 | -0.0062 | 55.8% | 78.8% | 1.589 |
| 14-21 | 25,378 | -0.0053 | -0.0033 | 53.7% | 80.4% | 1.301 |
| 22-25 | 21,507 | -0.0014 | +0.0006 | 51.2% | 81.2% | 1.037 |
| 26+ | 81,736 | -0.0045 | -0.0025 | 52.8% | 79.9% | 1.297 |

L1's table has the same medians within 0.0004, so the heavy-tailed unit level took up none of
the phase pattern. On all ads L1TKN has elpd 236,911, a median error of 0.04020 and an 80%
coverage of 80.0%.

The photo check (`photo-disagreement-2026-11-14.md`) left a lead for this term: the ads with
a low ask by L1's median and a long stay were concentrated in large buildings built after
2000, where asks may open high and step down. A unit relisted within two months is one place
such a step would appear, so after the fit I split the 0-2 gain by building size.

## Launch plan

Three H100 containers, seeds 1 to 3, pooled by `drift_pool` into 6 chains, from
`/data1/apartments/serve/master` at the merge commit of the PR with the module and of this
note. The first container of the commit starts alone, and the other two follow once its log
has passed "synced" and its first sweeps.

```sh
D=/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise
IN=/data1/apartments/pipeline/datasets/rows-b3ddebf19af1dc1e.parquet
ops/modal-fit --outside-budget --gpu H100 --dataset "$D" --input "$IN" --split latest \
  --baseline drift-building-phase-unitkn-b0-latest-79dd65f8-l1tkn COMMIT l2kn-a \
  drift-building-phase-unitkn-level b0 2 500 9000 40 --seed 1 --level-dof 4 \
  --no-loo --no-heldout
```

I score the pool against L1TKN's pool on the shared held-out ads with
`python -m rentfrontier.drift_score`, and count the gain a second time after moving each
pool's predictive by a constant cross-fitted over two halves of the buildings.

L1TKN's three containers settled at $10.82. The six columns join a global block of about
250, so I expect $10.50 to $12.00.

## Predictions (written before launch)

All are for the pool of three containers against L1TKN's pool on the shared held-out ads.

1. The pool passes the gate (70%). The rehearsal on 741 buildings mixed the six phase
   coefficients at R-hat under 1.0025 and ESS above 1,300. If it misses, the miss is on
   `unit_sd`, `tau` or a drift scale (75% given a miss).
2. elpd gains 150 to 350 (60%), more than 2 SE (85%) and more than the sprint's 4 SE bar
   (65%).
3. Counted over a constant shift of each pool, the gain is within 100 of the gain in 2 (70%).
4. At least half the gain comes from the 13,725 held-out ads in phase 0-2 (65%).
5. The posterior median of the 0-2 level, as exp(beta) - 1, falls between -1.5% and -0.5%
   (70%).
6. The other levels: 3-9 between -1.0% and -0.2%, 14-21 between -0.7% and 0.0%, 22-25
   between -0.3% and +0.4%, 26+ between -0.6% and +0.1% (50% for all four together). I make
   no prediction for `none`, since no held-out ad is in it.
7. The median's error moves by under 0.0005 from 0.04020 (80%).
8. 80% coverage on all ads stays within 0.005 of 80.0% (85%). On phase 0-2 it rises from
   76.8% by 0.005 to 0.03 (55%).
9. The share of 0-2 asks under the predictive median falls from 62.1% to between 50% and
   57% (60%).
10. The noise factor of phase 0-2 falls from 1.092 by 0.01 to 0.05 (50%), and each other
    factor moves by under 0.03 (65%).
11. Among held-out ads in phase 0-2, the elpd gain for each ad is larger in buildings with 100
    or more units than in smaller ones (55%).
12. The three containers settle between $10.50 and $12.00 in all (80%).

## Accepting it

By the sprint's rule the term is accepted if the pool passes the gate and gains more than
4 SE, and it is provisional between 2 and 4 SE. A gain under 2 SE closes account B's level
term, and the previous ad's ending is then tested by a free screen before any fit.
