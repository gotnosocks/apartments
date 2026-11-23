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

(to be filled in after the fits)
