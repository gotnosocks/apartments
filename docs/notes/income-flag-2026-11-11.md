# A wider income-restricted flag (2026-11-11)

During the outlier sprint (`docs/notes/outlier-sprint-2026-11-11.md`) I read the 300 ads
furthest from the served model, `drift-building-b0-latest-67d14e17-b9`. The readers called 13
of the ads far under the model income-restricted, with wording like "HPD income requirements
apply", "this unit is an hpd lottery" and "maximum income 154k". The dataset's
`income_restricted` flag covered 4 of them. The flag comes from the older list in
`features.DESCRIPTION_FLAGS`. The Deals page's `income` caution (`cautions.TEXT`) uses a
pattern chosen by reading market ads on 2026-11-10, and that reading found the old flag
missed 33 of 55 income-restricted ads.

The caution's pattern is too loose for the model, though. Reviewing the first version of this
change, I found that about half of the 1,973 rows it added were market ads: "40x rent annual
income requirement", "income range of 36x-40x", "this affordable unit is in move-in
condition". So `rentfrontier.b0income` uses its own pattern, `INCOME`. It drops the caution's
income requirement, qualification, range and affordable-unit phrases, and adds the program
wording the readers met: "restricted unit", "hpd lottery", "maximum income", "low income",
"median income", "housing connect". It also skips "optional for income restricted units",
the fee schedule market ads copy. A Sonnet reader judged 80 of the rows it adds, drawn at
random: 76 income-restricted units, no market ads, and 4 whose text was too short to tell.
It catches 11 of the 13 reader quotes.

## Free checks on the served fit

`rentfrontier.b0income` writes a copy of a B0 dataset with the flag set from `INCOME` on
each ad's last description. On the served dataset the flag goes from 1,703 rows to 2,590: it
gains 997 rows and loses 110 (the fee schedule, for the most part). On the latest split it
gains 106 held-out ads and loses 53, leaving 260 flagged.

b9 puts the flag at -0.087 (90% interval -0.093 to -0.081). I joined the change to the
served fit's diagnostics (195,423 ads):

| ads | n | mean gap | median gap | share of squared gaps | under the 10th percentile |
|---|---:|---:|---:|---:|---:|
| flagged by both | 165 | -0.027 | -0.012 | 0.28% | 27% |
| gained | 116 | -0.111 | -0.034 | 0.69% | 34% |
| lost | 54 | +0.006 | 0.000 | 0.01% | 4% |
| neither | 191,292 | -0.004 | -0.005 | 99.02% | 11% |

The gained ads sit under the model further than the flag's coefficient, and the lost ones
sit where an unflagged ad does. The ads flagged by both still sit low in the predictive
distribution, so the flag's coefficient may grow with more members.

## The change

The fit takes the dataset of the closing-ask comparison's winner
(`docs/notes/closing-asks-2026-11-11.md`): the closing dataset if it is served, b9's
otherwise. I rebuild it with `python -m rentfrontier.b0income SRC OUT` and fit the latest
split of `drift-building` at the base's commit, fit-only, as three H100 containers of 2
chains, `2 500 9000 40 --seed S --no-loo --no-heldout` with seeds 1 to 3. I compare it with
the base's pool of six chains on the held-out ads, which both datasets share.

The design first written here had two containers. I raised it to three on 2026-11-12,
before any launch, after the closing fit c1 missed the gate with 4 chains: at b9's mixing a
4-chain pool misses by chance 2.1% to 2.8% of the time and a 6-chain pool 0.55% to 0.74%
(`docs/notes/closing-asks-2026-11-11.md`, "The gate miss, second look"). Predictions 1 and 6
are revised to match, and the others stand as written.

## Predictions (written before launch)

1. The pool passes the gate (90%; 75% for the two-container design).
2. The flag's coefficient sits between -0.12 and -0.07, with its 90% interval narrower than
   b9's (60%).
3. On the held-out ads, elpd gains over the base (65%), by more than 2 combined SE (20%).
4. On the 106 held-out ads the flag gains, the median absolute error of the predictive median
   falls by at least 0.02 (60%).
5. Across all held-out ads, the median absolute error and the 80% coverage each move by under
   0.001 and 0.002 (80%).
6. $10 to $12 for the three containers ($7 to $8 for two).
