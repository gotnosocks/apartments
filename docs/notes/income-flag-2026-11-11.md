# The income-restricted flag from the Deals caution's pattern (2026-11-11)

During the outlier sprint (`docs/notes/outlier-sprint-2026-11-11.md`) I read the 300 ads
furthest from the served model, `drift-building-b0-latest-67d14e17-b9`. The readers called 13
of the ads far under the model income-restricted, with wording like "HPD income requirements
apply", "this unit is an hpd lottery" and "maximum income 154k". The dataset's
`income_restricted` flag covered 4 of them. The flag comes from the older list in
`features.DESCRIPTION_FLAGS`. The Deals page's `income` caution (`cautions.TEXT`) uses a
pattern chosen by reading market ads on 2026-11-10, and that reading found the old flag
missed 33 of 55 income-restricted ads.

## Free checks on the served fit

`rentfrontier.b0income` writes a copy of a B0 dataset with the flag set from the caution's
pattern on each ad's last description. On the served dataset the flag goes from 1,703 rows
to 3,566: it gains 1,973 rows and loses 110 (the fee schedule "optional for income
restricted units", for the most part). On the latest split it gains 200 held-out ads and
loses 53, leaving 354 flagged.

b9 puts the flag at -0.087 (90% interval -0.093 to -0.081). I joined the change to the
served fit's diagnostics (195,423 ads):

| ads | n | mean gap | median gap | share of squared gaps | under the 10th percentile |
|---|---:|---:|---:|---:|---:|
| flagged by both | 165 | -0.027 | -0.012 | 0.28% | 27% |
| gained | 210 | -0.074 | -0.026 | 0.76% | 27% |
| lost | 54 | +0.006 | 0.000 | 0.01% | 4% |
| neither | 191,198 | -0.004 | -0.005 | 98.95% | 11% |

The gained ads sit under the model about as far as the flag's coefficient, and the lost ones
sit where an unflagged ad does. The ads flagged by both still sit low in the predictive
distribution, so the flag's coefficient may grow with more members.

## The change

The fit takes the dataset of the closing-ask comparison's winner
(`docs/notes/closing-asks-2026-11-11.md`): the closing dataset if it is served, b9's
otherwise. I rebuild it with `python -m rentfrontier.b0income SRC OUT` and fit the latest
split of `drift-building` at the base's commit, fit-only, as two H100 containers of 2 chains,
`2 500 9000 40 --seed S --no-loo --no-heldout` with seeds 1 and 2. I compare it with the
base's first four chains on the held-out ads, which both datasets share.

## Predictions (written before launch)

1. The pool passes the gate (75%).
2. The flag's coefficient sits between -0.12 and -0.07, with its 90% interval narrower than
   b9's (60%).
3. On the held-out ads, elpd gains over the base (65%), by more than 2 combined SE (20%).
4. On the 200 held-out ads the flag gains, the median absolute error of the predictive median
   falls by at least 0.02 (60%).
5. Across all held-out ads, the median absolute error and the 80% coverage each move by under
   0.001 and 0.002 (80%).
6. $7 to $8 for the two containers.
