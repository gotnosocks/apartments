# A caution for a net rent shown with no coded free months (2026-11-18)

The broker read of the first page (`docs/notes/first-page-read-2026-11-18.md`) found two
ads whose page price is a net-effective rent: 3,618 at 308 Eldert Street is 4,100 less 2
months of 17, and 6,783 at 555 West 45th Street is 7,400 less 1 month of 12. The record
codes no free months for either, so the dataset's ask stays net while the model's rent is
gross, and the ad looks 8% to 12% cheaper than it is.

## The rule

`cautions.net_ask` marks an ad when all of these hold:

- the record codes no free months;
- the ad's first ask is a multiple of 25 and above the page price;
- the page price's last digit is none of 0, 5 and 9;
- the page price is within a dollar of the first ask less 1, 2 or 3 months spread over a
  lease of 12 to 18 or 24 months.

It reads the two prices and never the model's estimate. A caution changes no score.

## Counts

On the live table of Nov 18 (6,565 ads, 5,479 uncautioned):

| step | ads |
|---|---|
| no coded free months | 5,148 |
| and an odd page price below a round first ask | 18 |
| and the price fits a lease (`net_ask`) | 11 |
| of those, uncautioned before | 8 |
| of those, among the first 100 uncautioned | 3 |

The 11 include both ads the readers named, a second apartment at 555 West 45th Street at
the same two prices, and 30 Lefferts Place, whose text carries the same line as 308
Eldert's ("Please inquire about the pricing structure"). Two are in buildings that
reprice daily (The Capitol, Ruby Chelsea) and sit mid-table, where a caution costs
nothing. The last step is loose alone: it also fits 244 of 769 ordinary cuts to a round
price. The first three conditions carry the rule, and the 7 ads they keep that fit no
lease stay unmarked.

On the backtest `range-j` (`net-ask-caution-2026-11-18/backtest.py`) the rule marks 2 of
the 8,564 open uncautioned ads, neither in the lowest tenth, so the backtest's tables do
not move. Across all 2.2 million ads of that build it marks 4,857, nearly all closed. A
gross-up of those asks in the dataset would change the model's targets and belongs in a
data rule with its own fit; the backlog keeps it.

## After the merge

Deals is republished from `range-m2` with `range-j` as its backtest, the same pair as
now. Expected: 11 ads gain `net_ask`, the uncautioned count goes from 5,479 to 5,471, and
3 ads leave the first 100.
