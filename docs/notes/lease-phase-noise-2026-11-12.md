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
