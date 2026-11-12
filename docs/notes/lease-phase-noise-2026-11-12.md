# A noise scale by lease phase (L1, 2026-11-12)

The outlier sprint found the served fit's 80% intervals covering 84% of the asks of an
apartment advertised again 10 to 13 or 22 to 25 months after its previous ad, and 75% of
those advertised 3 to 9 months after it ("The lease cycle" in
`docs/notes/outlier-sprint-2026-11-11.md`). The fit widens a returning unit's interval
steadily with the time since its previous ad, while the realized spread peaks between the
anniversaries. L1 lets the ad-level noise follow that clock.

## The change

`drift-building-phase` (#1330) multiplies each row's noise scale, `sigma[bedroom group]`,
by a factor for its lease phase. The phase counts months from the `price_at` of the unit's
previous ad in the dataset, training or held out, to the row's own. It reads dates only.
The groups are no previous ad, 0 to 2 months, 3 to 9, 10 to 13, 14 to 21, 22 to 25 and 26
or more. I fixed the factor at 10 to 13 months to 1 and gave the other six log factors a
Normal(0, 0.3) prior. The sampler draws them with the other scales in the slice step.
Everything else is the served model, `drift-building` with `--level-dof 4`.

On the served dataset and the latest split the phases hold:

| | none | 0-2 | 3-9 | 10-13 | 14-21 | 22-25 | 26+ |
|---|---:|---:|---:|---:|---:|---:|---:|
| training | 935,396 | 81,137 | 82,440 | 147,070 | 116,391 | 87,328 | 257,062 |
| held out | 0 | 13,725 | 17,068 | 30,233 | 25,378 | 21,507 | 81,736 |

The latest split holds out a unit's last ad, so every held-out ad has a previous one. The
"none" factor changes the predictions only through the training rows.

## The fit

The dataset is c3's, `/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise`.
c3 passed the gate and gained 641.5 elpd over b9 (SE 100.7) on the 183,272 held-out ads
whose target the two datasets share (`docs/notes/closing-asks-2026-11-11.md`). The budget left
in the sprint, $8.89, covers two containers: `2 500 9000 40 --seed S --level-dof 4
--no-loo --no-heldout` with seeds 1 and 2, pooled by `drift_pool`. I compare the pool with
the first four chains of c3 (its parts c3a and c3b, pooled as `...-ae875fc6-c3ab`), on the held-out
ads both share, with the SE clustered by building.

A sweep costs about a quarter more on CPU (8 slice directions in the scale step become 14),
so each container keeps fewer draws inside its 2,520 s budget than c3's did, and four
chains are fewer than c3's six. c1, at four chains, missed the gate on the unit walk's
hyperparameters.

## Predictions (written before launch)

1. The pool passes the gate (50%).
2. The factor at 3 to 9 months is 1.15 to 1.35 (70%), and the factor at 0 to 2 months is
   1.0 to 1.2 (60%).
3. The factors at 14 to 21 and 26 or more months lie above 1 and below the factor at 3 to
   9 (60%). The factor at 22 to 25 lies within 0.08 of 1 (60%).
4. The "none" factor lies between 0.9 and 1.15 (60%).
5. elpd on the shared held-out ads gains over the base by more than 2 SE (75%), and by 400
   to 900 (50%).
6. Coverage of the 80% interval moves from about 0.75 to between 0.775 and 0.805 at 3 to 9
   months, and from about 0.84 to between 0.80 and 0.825 at 10 to 13 (60%).
7. The median's error moves by less than 0.0005 (85%).
8. $7.5 to $8.5 for the two containers.

## Results (scored 2026-11-12 10:40 ET)

l1a and l1b settled at $3.84 and $3.87, so $7.71 for both, with walls of 3,165 s and 3,191 s.
I pooled them as `drift-building-phase-b0-latest-9a7830fb-l1`: 4 chains of 2,720 draws,
68 kept a chain. The pool passes the gate. The worst split R-hat is 1.0076 on `unit_sd`,
and the least bulk ESS is 788 on `drift_tau`.

The factors, as medians with 90% intervals:

| | none | 0-2 | 3-9 | 10-13 | 14-21 | 22-25 | 26+ |
|---|---:|---:|---:|---:|---:|---:|---:|
| median | 1.636 | 1.083 | 1.602 | 1 | 1.308 | 1.034 | 1.279 |
| 5% | 1.615 | 1.068 | 1.578 | | 1.288 | 1.017 | 1.263 |
| 95% | 1.654 | 1.100 | 1.625 | | 1.327 | 1.054 | 1.295 |

The four chains' medians agree to 0.005 in every factor. With the factors in, every
`sigma` falls by about a fifth (the 1-bedroom scale from 0.0191 to 0.0148), `drift_sd`
from 0.0451 to 0.0395 and `drift_tau` from 9.5 to 6.5 years. `nu` rises from 1.72 to 1.81,
and `unit_sd` and `bld_sd` move by under 2%.

On the 189,647 held-out ads, L1 beats c3ab by 554.6 elpd (SE 63.2, clustered by building)
and all six chains of c3 by 515.5 (SE 62.1). The median's error is 0.04068 against c3ab's
0.04063. The 80% intervals cover 0.797 of the asks, against 0.807, and the 95% intervals
0.943, against 0.951. By phase, against c3ab:

| phase | n | elpd gain | SE | 80% coverage | c3ab | 95% coverage | c3ab | 80% width | c3ab |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0-2 | 13,725 | -41.6 | 18.7 | 0.760 | 0.788 | 0.926 | 0.947 | 0.129 | 0.139 |
| 3-9 | 17,068 | +108.4 | 22.1 | 0.782 | 0.752 | 0.946 | 0.930 | 0.166 | 0.153 |
| 10-13 | 30,233 | +277.8 | 27.9 | 0.810 | 0.839 | 0.945 | 0.964 | 0.147 | 0.161 |
| 14-21 | 25,378 | -3.0 | 16.8 | 0.798 | 0.803 | 0.946 | 0.950 | 0.163 | 0.163 |
| 22-25 | 21,507 | +162.0 | 20.3 | 0.810 | 0.837 | 0.948 | 0.965 | 0.159 | 0.171 |
| 26+ | 81,736 | +51.1 | 30.8 | 0.798 | 0.804 | 0.943 | 0.949 | 0.180 | 0.183 |

Most of the gain comes from narrowing the intervals at the anniversaries, where c3ab
covered too much, and widening them at 3 to 9 months, where it covered too little. The 0 to 2
month ads lose: their factor, 1.08, is set mostly by training ads, and the held-out ads of
that phase undercover at 0.76. The script is `/data1/apartments/tmp/sprint-20261112/l1/by_phase.py`.

### The predictions, scored

1. The gate passes: hit.
2. Miss. The 3 to 9 month factor is 1.60, against a predicted 1.15 to 1.35. The 0 to 2 month
   factor, 1.08, falls inside its range.
3. Hit. 14 to 21 (1.31) and 26 or more (1.28) lie above 1 and below 3 to 9, and 22 to 25 lies
   within 0.035 of 1.
4. Miss. The "none" factor is 1.64, against 0.9 to 1.15. A unit's first ad in the data has
   no earlier ask to pin its level, so I expected its noise to look like the reference
   phase's. The fit instead gives first ads a noise scale 64% larger. That would fit if a
   first ad carries more coding errors or more one-off pricing. The "none" phase holds 935,396 of the 1.7
   million training rows, so this factor is largely what lowers every `sigma`.
5. Hit on both parts: +554.6 against c3ab, above 2 SE and inside 400 to 900.
6. Hit. Coverage at 3 to 9 months moves from 0.752 to 0.782, and at 10 to 13 months from
   0.839 to 0.810.
7. Hit. The median's error moves by 0.00005.
8. Hit: $7.71.

Six of the eight hit. Both misses are factors larger than I predicted, in the direction I
predicted.

### What follows

L1 is the best latest-split fit. Serving it on the site needs its market and backtest
fits on the closingraise market datasets (#1332). A queue
(`/data1/apartments/tmp/sprint-20261112/queue-l1-market.sh`, systemd timer
`queue-l1-market`) starts at 15:50 ET and launches the six containers from the daily
budget as it covers each, at about $3.85 a container. It replaces the queue I had written
for c3's. The 0 to 2 month undercoverage and the size of the "none" factor are the next
questions. One option is a factor fitted only on held-out-like rows, the unit's last ad,
but that reads the split. A cheaper option is a free check on how first ads differ from
later ones.
