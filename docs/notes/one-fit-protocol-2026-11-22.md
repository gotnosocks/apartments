# One fit instead of three (2026-11-22)

Ben, 2026-11-22: the Diagnostics and Deals pages need three fits of a model: one on the
latest split (selection elpd, Diagnostics), one on the market split (Deals), and a backtest
on the market dataset as of 2025-11-10 (deal-score validity). That multiplies the cost of a
model by 2 to 3, and he is open to changing the model to remove it.

## Proposal

One fit on the market dataset, with held out = the open ads ∪ the latest-split rows of the
closed ads. From that one fit:

- selection and Diagnostics read the latest rows, as they read the latest fit now;
- Deals reads the open ads, as it reads the market fit now;
- validity (`drift_deals.validate`) reads the latest rows, whose final asks, days on the
  market and cuts are known, in place of the open ads of a strict as-of backtest. Its
  docstring already allows "a backtest dataset, or the latest split". A strict backtest
  becomes an occasional check, not a fit per model.

The cost is that the Deals fit trains on about 10% fewer rows. Variant C draws the latest
rows only from apartments with no open ad, so no open ad loses its own apartment's newest
history.

## Test (k5 screen, `screen-mkt-k5`, as of 2025-11-10)

Same commit (1d62c667), model `drift-building-phase-unitkn-ablate --variant
layrng,size,sv_gp_mo,marks`, screen settings `2 250 400 10`, seed 1:

| arm | held out | rows held |
|---|---|---|
| A `of-a-mkt` | open ads (`screen-mkt-k5`) | 1,891 |
| B `of-b-both` | open ∪ latest(closed) (`onefit-b-k5`) | 36,765 (404 latest rows share a unit with an open ad) |
| C `of-c-both` | open ∪ latest(closed, units with no open ad) (`onefit-c-k5`) | 36,409 |

Datasets: `/data1/apartments/tmp/one-fit-2026-11-22/datasets/`. The open ads of this
backtest dataset carry their final asks, so every arm scores them.

## Predictions (written before launch)

1. Open-ad elpd, summed over the 1,891 open ads: B − A between −25 and 0 nats, C − A between
   −20 and 0. Withholding 10% of rows, almost none of them the open ads' own apartments,
   costs Deals little.
2. Open-ad median error (RMSE of log median) within 0.003 of A in B and C; 80% and 95%
   coverage within 1.5 points of A.
3. Validity on the latest rows of B by tenth of first-ask place: median days on the market
   rises from the bottom tenth to the top, and the share cut rises; both orderings agree
   with the open-ad table of A (Spearman ≥ 0.8 across tenths). The latest table has ~18×
   the ads, so it is tighter.
4. Convergence of B and C no worse than A (the same model; more held-out rows do not add
   parameters).

If 1 and 2 hold, recommend the one-fit protocol (variant C if it is the cheaper in elpd)
and make it the default for full fits.

## Results

Scored with the scratch scorer on the open ads (1,891, paired against A) and the latest rows.
None of the screens passes the gate (screens at `2 250 400 10` never do): A max R-hat 1.040
(drift_tau), min ESS 53; B 1.144 (unit_sd), 25; C 1.040 (phase_factor[7]), 46.

| arm | open elpd | Δ vs A | open RMSE | open 80% / 95% | latest rows | latest elpd | latest 80% / 95% |
|---|---|---|---|---|---|---|---|
| A | 1963.6 | — | 0.1132 | 0.755 / 0.938 | — | — | — |
| B | 1910.8 | −52.9 ± 14.6 | 0.1151 | 0.768 / 0.937 | 34,874 | 43,685.8 | 0.801 / 0.947 |
| C | 1927.6 | −36.0 ± 10.7 | 0.1142 | 0.763 / 0.935 | 34,518 | 43,177.6 | 0.798 / 0.948 |

Validity by tenth of first-ask place, Spearman across tenths: open ads of A 0.97 (median
days) and 0.99 (share cut); latest rows of B 0.99 and 1.00, with median days rising from 12
to 27 and the share cut from 0.07 to 0.51, about 18× the ads of the open-ad table.

Against the predictions:

1. Missed. B − A = −52.9 and C − A = −36.0, both past the predicted bounds (−25, −20). C
   costs about 0.019 nats an open ad, 3.4 SE.
2. Held. RMSE within 0.002; coverage within 1.3 points.
3. Held. The latest-row validity table is monotone, agrees with A's open-ad table, and is
   much tighter.
4. Not testable at screen length; no worse in A and C, worse in B.

Why the miss: the latest split holds each relisted unit's newest ad, so it takes the recent
market disproportionately. In C the held latest rows are 26.5% of the closed ads of the
last 90 days and 29.1% of the last year's, against 10% overall (median age 894 days, against
2,056 for training rows). The Deals fit then loses a quarter of the year it leans on most.

## Variant D (predictions written before launch)

D holds out the open ads and C's latest rows whose `price_at` is 365 or more days before
2025-11-10 (`onefit-d-k5`: 28,298 held, 26,407 latest). The last year stays whole in
training; selection and validity read older ads.

1. Open-ad elpd D − A between −20 and 0 (most of C's cost came from the recent rows).
2. Open RMSE within 0.002 of A; 80% and 95% coverage within 1.5 points.
3. Latest-row validity monotone, Spearman ≥ 0.95 for median days and share cut.
