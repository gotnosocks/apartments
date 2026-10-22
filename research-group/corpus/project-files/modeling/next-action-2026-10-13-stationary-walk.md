# Proposed next modeling action: a stationary building deviation in place of C's 2010-origin walk

*2026-10-13. Proposal only, nothing launched. Built on PR #723 (docs/model/newbuilding-clustered-2026-10-13.md), the held-data ceiling (branch held-data-ceiling), docs/plan next-actions-2026-10-13, and one free read-only check on thelio (scratch at /data1/apartments/tmp/nbvar on thelio, no tracked files changed). Scored under the evaluation framework (Fable review §3 and §10 preamble, as adopted in §8 of research-review-2026-10-08.md). Predictions are written before any fit: median, with an 80% interval in brackets. The counterfactuals below reuse C's draws with no refit, so they are diagnostics, not results.*

## The action

Fit C once with its half-year building walk replaced by a stationary AR(1) building deviation on the same knots (persistence rho per half-year, stationary SD), in a new model module so the hashed models stay untouched. CPU test, reviewed PR, then one full Modal fit, scored on the board and with the per-building new-building scorer from #723.

This is the plan's conditional "walk fit" in its fixed-form AR(1) variant, with rho estimated rather than fixed. Its gate (a within-bin year gap of 3 pp or more that tracks calendar time) is now met: the gap is +5.2 pp.

## Why: what the free check found

- C has no building time slope and no per-building noise scale. Its only time-varying building term is the walk, pinned at 0 at 2010 H1, so a new building's prior variance from it is walk_scale² × half-years since 2010 (walk_scale 0.0309, 0.0305-0.0312).
- The walk's share of a new building's predictive variance grows from 8% (2010-13) to 38% (2024-26). The 80% half-width on the log scale grows from 0.273 to 0.343.
- In the data, the cross-building variance of the fitted building part is flat at 0.034-0.035 in every band from 2010-13 to 2024-26. Individual buildings drift, but the spread across buildings does not grow. The walk assumes it does, and that is why recent rows are covered 93-95% at a nominal 80%.
- Counterfactuals on C's draws (row-weighted 80/95; building-weighted 80/95; 80% year gap):
  - C as is: 90.7/98.2; 86.5/96.1; +5.2 pp
  - walk origin at each building's first knot: 88.8/97.6; 83.2/94.7; +6.0
  - walk origin at the panel midpoint: 87.2/97.1; 82.6/94.7; +3.7
  - walk variance held constant (walk_scale² × 8): 87.7/97.2; 83.2/95.0; **+1.2**
  - removing slope variance or pooling yearly noise does not close the gap (+6.6 to +8.0; +5.2)
- Any time-constant walk variance closes the gap from 5 pp to about 1.2 pp. A stationary AR(1) is the parsimonious model with that property: one extra parameter, and an interpretable one (how fast a building's premium decays back to its level).

## Predictions

| Measure | Prediction |
|---|---|
| Paired PSIS-LOO vs C, shared rows | +20 (-20 to +60): a tie at the 2 SE bar |
| New-building 80/95 coverage, row-weighted | 87.5/97.2 (86-89 / 96.5-98) |
| New-building 80/95 coverage, building-weighted | 83.5/95.2 (82-85 / 94.5-96) |
| 80% gap, 2024-26 minus 2014-16 rows within bins | +1.5 pp (0.5 to 2.5) |
| Building-weighted new-building lpd vs C (lot-clustered SE) | +60 nats (+20 to +120) |
| New-building miss (median) | unchanged, ±0.1 pp |
| rho per half-year; stationary SD | 0.95 (0.90-0.98); 0.08 (0.06-0.11) |
| Descriptive share | within ±0.4 pp of C's (inferred; building-over-time shrinks, building level absorbs some) |
| New-unit coverage | unchanged (not a rent-derived term, so no time-split requirement) |

**What counts as a miss.** The year gap stays at 3 pp or more; PSIS-LOO falls by more than 2 SE; rho's posterior sits above 0.99 (the data want a walk after all); or the fit fails the convergence gate after one retry.

## Cost

Modal about $1.80 for the fit plus about $0.13 for the score, inside one day's $10 budget. Modeling about 1-1.5 days (new module, CPU test, reviewed PR). Oxylabs and LLM $0.

## Why it beats the alternatives

- **Photo screen (#3).** Still worth running, and it does not compete: it is Data improvements work, needs your costed OK (about $45 of LLM), and has P(pass) about 0.25. It runs in parallel. But any photo fit would be read against intervals that are 7-11 pp too wide, where about half of an lpd gain is width rather than centre. Fixing the width first makes its later score clean.
- **Leave-East-Village-out refit (#4, about $2.5).** More interesting now that removing labels raises the in-area miss to 13.75%, not 13.0-13.4%. But its coverage read is meaningless until the width is fixed. It goes next, on the AR(1) model if that wins.
- **Serving lines.** It is the strongest generalization result on record (+83.9 nats, 5.8 lot-clustered SE on building-weighted new-building lpd), and an autoselect dry run picks it. It costs no fit. It is a serving decision blocked only by your 03:16Z hold, not a new modeling action.
- **More held-data building families.** Ruled out by #2: the best compact linear sets reach -0.31 pp with a lower bound of 0.21, inside the dead band.
- **This action** fixes the one proven range defect on new buildings, the board's only generalization number. It does so with a simpler, more interpretable term, and it is the cheapest fit on the list.

## Follow-on, not proposed now

The miscalibration that remains follows building size. With a constant walk variance, 80% coverage is 75.1 for buildings with 1-5 rows and 88-89 for those with 21 or more. A building scale that varies with PLUTO residential units and class is the natural second fit, once the AR(1) result is in.
