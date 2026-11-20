# R-hat and ESS of the kept building levels and predicted locations (2026-11-20)

No fit, no money spent. This is the second half of item F4 of
`docs/notes/deals-closingraise-2026-11-20/plan.md`. The convergence gate (split R-hat at most
1.01 and bulk ESS above 400) reads the traced scalars and coefficients, 3,600 sweeps of each
of 2 chains. It does not read the level of each building (`kept/bld`) or the location of each
predicted ad (`kept/pred_loc`), and the Deals order is made from the second. The plan counted
278 live ads with R-hat over 1.01 and asked for an audit.

`docs/notes/kept-rhat-audit-2026-11-20/audit.py` reads only each run's `posterior.npz`, its
dataset's listing and building columns, and the published `deals.json` for the cautions. It
uses the gate's own functions (`rentfrontier.run.split_rhat`, `ess`, through
`building_diagnostics`). Output: `audit.json` beside it. Runs: the live run `range-m3` (6,502
ads, 68,019 buildings) and the backtest `range-j` (9,346 ads, 66,878 buildings).

## What the files keep

Both quantities are kept with the chains apart, as (2 chains, 180 draws, items): every 20th
sweep (`keep_every` 20). So R-hat and ESS can be computed, but on 360 draws, where the gate
has 7,200. Two things follow before any number is read:

- ESS above 400 is out of reach for nearly every item, mixed or not.
- Split R-hat on four half-chains of 90 draws is noisy. The script runs the same functions on
  20,000 series of independent normal draws of the same shape (the row "independent" below).
  A perfectly mixed fit has 4.1% of its items over 1.01 and none over 1.05.

`below_share` is the mean over draws of each ad's predictive probability of a rent under its
ask (`drift_score._density`); the script diagnoses that per-draw value as well.

## Distribution

| Quantity | Run | Max R-hat | 99th pct | Over 1.01 | Over 1.05 | ESS < 400 | ESS < 100 |
|---|---|---|---|---|---|---|---|
| independent draws | | 1.046 | 1.0155 | 4.1% | 0 | 87.7% | 0.05% |
| `pred_loc` | range-m3 | 1.036 | 1.0155 | 4.3% (281) | 0 | 88.0% | 0.05% (3) |
| `pred_loc` | range-j | 1.100 | 1.0154 | 3.5% (326) | 0.02% (2) | 86.4% | 0.05% (5) |
| `below_share` draws | range-m3 | 1.039 | 1.0158 | 4.2% | 0 | 88.3% | 0 |
| `below_share` draws | range-j | 1.042 | 1.0152 | 3.5% | 0 | 87.2% | 0.03% (3) |
| `bld` | range-m3 | 9.60 | 1.0165 | 4.2% | 0.07% (51) | 87.6% | 0.27% (183) |
| `bld` | range-j | 14.05 | 1.0167 | 4.4% | 0.11% (72) | 87.5% | 0.29% (197) |

The predicted locations match independent draws at every point of the table but one: two
backtest ads over 1.05. The 281 live ads over 1.01 (the plan's 278) are the count chance
gives. 25 of them are in the lowest tenth of the order (8.9%, against the 10% an even spread
gives) and 4 in the first 100. Of the 20 ads with the worst R-hat, 4 (live) and 3 (backtest)
are in the lowest tenth, and their R-hat is 1.026 to 1.036.

The building levels are not all mixed. In the body they match independent draws, but 51 live
and 72 backtest buildings are over 1.05 (30 and 39 over 1.10, 5 and 10 over 2), and six times
as many as chance gives have ESS under 100.

## The buildings that did not mix

In the worst of them each chain sat at its own level for the whole fit: 21 Clark Street at
+1.27 in one chain and -0.04 in the other, 113 West 69th at +0.54 and -0.10. The chains' means
are a median 0.20 log apart (0.17 backtest), over 0.3 in 17 (23) buildings, and at most 1.31
(2.21).

These are buildings with few and odd training rows: a median of 1 row, at most 3 rows in 41 of
51 (55 of 72). Reading the live run's worst 14: five are a single ad coded 0 or 1 bedrooms at
$9,750 to $39,000 (147 11th Street in Gowanus, 113 University Place, 513 West 26th, 553 West
25th, 29 Leonard Street in Brooklyn), and the rest mix ordinary asks with asks many times
larger (21 Clark Street: studios at $2,050 and $2,200 in 2014, then $14,195 and $18,320 in
2021; The Dorilton: $5,495, then five bedrooms at $35,000 and $38,000). The building level has
a Student-t prior (`level_dof` 4), so such a building has two modes: a large building level,
or a level near its zone with the unit levels and the noise taking the gap. One sweep rarely
crosses between them.

None of these buildings has an ad on the live list. Two have one in the backtest:

| Ad | Building | R-hat `bld` | R-hat `pred_loc` | `below_share` by chain | Place of 9,346 |
|---|---|---|---|---|---|
| 4875635 | 22 East 18th Street | 1.11 | 1.10 | 0.554, 0.577 | 5,068 |
| 4899902 | 16 Goodwin Place, Brooklyn | 1.08 | 1.08 | 0.907, 0.964 | 8,635 |

Neither is near the low end, and their shares differ by 0.02 and 0.06 between the chains.

## Monte Carlo error against the order

The error that does reach the Deals order comes from having 360 draws, and it applies to every
ad, mixed or not. The Monte Carlo standard error of `below_share` is the sd of the per-draw
value over the square root of its ESS. The gap is the distance in `below_share` to the nearer
neighbour in the order, and "places" counts the ads whose share is within one error of the
ad's.

| Ads | Share at cut | Median error | Median gap | Error over gap | Places: median, 90th pct, max |
|---|---|---|---|---|---|
| live, uncautioned, first 100 | 0.041 | 0.0008 | 0.00015 | 7 | 5, 12, 21 |
| live, uncautioned, lowest tenth (489) | 0.152 | 0.0032 | 0.00011 | 31 | 23, 58, 115 |
| live, all, first 100 | 0.024 | 0.0004 | 0.00008 | 5 | 3, 12, 36 |
| live, all, lowest tenth (650) | 0.134 | 0.0025 | 0.00006 | 40 | 24, 70, 120 |
| backtest, all, first 100 | 0.016 | 0.0002 | 0.00005 | 5 | 3, 10, 30 |
| backtest, all, lowest tenth (934) | 0.110 | 0.0022 | 0.00004 | 55 | 39, 98, 232 |

The error is larger than the gap to the neighbour for 84% to 99% of these ads, so the exact
order among neighbours is not determined by the fit. Membership is: ordering by one chain
alone and by the other alone (Spearman 0.998), the two lists of the first 100 share 94 or 95
ads and the two lowest tenths 96% to 97%, and an ad of the first 100 sits a median 3 places
apart between the chains (at most 32 to 39). The page orders by both chains together, with
half that variance. Against what else moves the order this is small: the refresh two days
after Nov 18 replaced 20 of the first 100 uncautioned ads
(`docs/notes/market-refresh-2026-11-20.md`).

## Recommendation

1. Do not extend the 1.01 and 400 rule to these quantities. On 360 kept draws it fails 4% of
   items by chance and nearly all on ESS, and the predicted locations show nothing beyond
   chance in the live run.
2. Add a cheap check after the fit, outside the hashed modules (in `drift_deals publish`, or
   in `drift_score`): `building_diagnostics` of `kept/pred_loc`, about 10 seconds, reporting
   the ads over 1.05 (`run.GROUP_RHAT_GATE`, the bound the older models used for every element
   of an effect; independent draws give none in 20,000). Such an ad would get a caution
   and stay off the default list, and the fit would stay publishable. Today that touches 0
   live ads and 2 backtest ads. This is my proposal and is not built here.
3. The buildings over 1.05 are a data lead before a model one (data first). Most are single
   ads priced several times their zone, some plainly not an apartment's rent (a studio at
   $28,000 to $39,000). Reading the 51 and 72 buildings for the ledger is free work, added to
   the open list. They do not bear on Deals now.
4. If the order inside the first 100 should be steadier, keep more draws: `keep_every` 5
   would halve the error for a file four times the size. The Nov 16 check found that keeping
   every sweep adds 1% to 3% to sweep time. That is a sampler setting of the next market fit,
   not a model change, and I'd take it only with Ben's word since it changes the fit's record.

## Doubts

- R-hat and ESS here rest on 2 chains of 180 draws. A fault that both chains share is
  invisible, as it is to the gate.
- Buildings are named by rebuilding the fit's order (`drift_diagnostics.levels`), which checks
  the zone counts against the run's record and matched for both runs.
- "Places within one error" counts the ads whose share lies within one standard error either
  side, so it reads as a typical move and not a bound.
- The ad counts for the uncautioned list use the cautions of the table published on Nov 20
  (4,896 uncautioned of 6,502).
