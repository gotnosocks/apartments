# Fast screening of model changes: find_MAP and data subsets

User question, September 22: can `find_MAP` or a subset of the data stand in
for full NUTS when triaging a model change? This note tests both against a case
with a known answer and a negative control. It is the evidence behind the
backlog item "fast screening fits from the same graph".

## Test bed

All runs use `models/bedroom_time_screen.py` on
`chelsea-product-scope-analysis-20260921`. A fixed split (seed 20260922)
holds out 10% of all rows (5,264) from units with at least two observations,
each such unit keeps at least one training row. Every method fits the
identical PyMC graph on the training rows and scores the held-out rows. NUTS
uses exact posterior predictive log density; MAP uses the plug-in density at
the point estimate. Comparisons are **paired differences on identical rows**,
so absolute levels (which differ by construction between NUTS and plug-in MAP)
do not matter.

Reference answers from full-data NUTS (4 chains, 1,000 tune / 1,000 draws):

| change | ΔELPD vs shared trend | note |
|---|---|---|
| bedroom-group random-walk trend (`walk`) | **+30.0 ± 9.5** | real improvement, see [bedroom-time experiment](bedroom-time-experiment-2026-09-22.md) |
| bedroom-group linear trend (`linear`) | +6.0 ± 5.1 | 3,000 tune / 1,500 draws; not significant |
| walk curves keyed to random per-unit pseudo-groups (negative control) | −0.5 ± 1.5 | walk scale shrinks to 0.0005 |

## find_MAP

**Raw joint `pm.find_MAP` is not usable for this model.** The joint mode of a
hierarchical model is degenerate: at the optimum `sigma_building` = 0.000
(every building effect forced to zero), `sigma_unit` = 3.46 (NUTS 0.084; the
non-centered unit effects absorb the buildings) and `sigma` = 0.045 (NUTS
0.066, overfitting). Its ΔELPD for walk was +437 ± 67 and for linear +210 ± 63,
with per-row correlation to NUTS of 0.23/0.16. The ranking happened to be
right but magnitudes are ~14× inflated and it would have declared the linear
variant a large win.

**Conditional MAP works well.** Fix the variance components already estimated
by the baseline NUTS fit (`sigma`, `sigma_unit`, `sigma_building`,
`trend_scale`) at their posterior means via `pm.do`, and optimize everything
else, including any new term's own scale (`--method map --fix-scales-from`):

| change | cMAP ΔELPD | NUTS ΔELPD | per-row corr |
|---|---|---|---|
| walk | +30.9 ± 12.5 | +30.0 ± 9.5 | 0.95 |
| linear | −17.0 ± 9.3 | +6.0 ± 5.1 | 0.61 |
| negative control | +2.5 ± 2.0 | −0.5 ± 1.5 | −0.02 |

Cost: ~3 minutes of optimization on one core, measured while the machine was
fully loaded by other fits (raw joint MAP took ~1 minute), versus ~9 minutes of 4-core sampling plus
~10 minutes of diagnostics for the short NUTS screen and ~1 hour for a
protocol fit.

The linear case is the warning. Conditional MAP and NUTS reach the same
decision (do not adopt; neither is a credible gain), but cMAP puts it at
−17 while NUTS puts it at +6, about 2.3 combined standard errors apart. The
plug-in point estimate ignores uncertainty in the new slopes, and I have not
isolated why the optimum predicts worse. The first short NUTS run of this variant
(1,000 tune) had R-hat 1.25; with 3,000 tune it is 1.06, and the slow
direction is the raw slopes' common mode, which the zero-sum constraint
removes from every prediction.

## Data subsets

NUTS on a random subset of buildings or units (the held-out split is drawn on
all data first, then restricted to the subset; the design is rebuilt on the
subset training rows):

| subset | train rows | held-out rows | subset ΔELPD (walk) | full NUTS on same rows | per-row corr |
|---|---|---|---|---|---|
| 25% of buildings | 11,411 | 1,324 | +15.7 ± 4.7 | +12.7 ± 4.4 | 0.53 |
| 50% of buildings | 26,505 | 2,907 | +19.2 ± 7.0 | +19.3 ± 7.2 | 0.91 |
| 25% of units | 11,753 | 1,286 | +6.5 ± 4.1 | +4.9 ± 4.7 | 0.88 |

Subset fits are **unbiased**: they agree with full NUTS on the same rows. But
they lose power roughly in proportion to the held-out rows they keep. The
25%-of-units subset would have missed a real +30 improvement (1.6 SE), and the
25%-of-buildings result depended on which buildings were drawn (those 25% of
rows carried 12.7 of the 30 nats). Sampling time fell about 4× at 25%
(measured under shared load, so approximate). Subsets also change the model
being judged: with fewer rows the building/unit variances and sparse feature
cells (large bedroom counts, rare floors, 2010–2013) are estimated from less
data, which is exactly where most of this improvement lived.

## Recommendation

1. **Screen with conditional MAP on the full data** (`--method map
   --fix-scales-from <baseline NUTS result>`): minutes, single core, keeps full
   power, reproduced the real effect almost exactly and stayed null on the
   control. Refresh the fixed scales whenever the baseline changes.
2. **Never use raw joint `find_MAP`** on this graph; the hierarchical mode is
   degenerate.
3. **Do not use subsets as the primary screen.** They are unbiased but
   underpowered; use them only to test pipeline plumbing or for changes whose
   expected effect is large and broad.
4. Confirm any candidate that passes with a short NUTS screen on the same
   split, then a protocol fit. Treat cMAP as triage: it has no posterior
   uncertainty for the new term, and it can mislead where the new term is
   weakly identified (see the linear case above).

## Follow-up, September 23: where conditional MAP and the split mislead

- **Scale and noise models.** Conditional MAP is valid for changes to the
  *mean* (new terms with fixed or gridded scales). It is not valid for
  per-building residual scales. The MAP of a group variance is biased low for
  small groups, so held-out rows look overconfident. Building-level noise
  scales screened at −466 to −1,250 ELPD. That is an artifact of the method;
  such variants need a NUTS screen.
- **Which rows are held out.** The declared row split holds out listings of
  units that keep other training listings, so it measures within-unit and
  within-building prediction. Unit attributes (penthouse, duplex, private
  outdoor, shared bath) matter most for units *without* history, which is 47%
  of units. They were rejected on the row split (duplex −12.9, private outdoor
  −23.0) but accepted on a whole-unit split (+34.7, +53.2), where every
  listing of 10% of units is held out and the new unit's effect is integrated
  over its prior. Screen unit-level features on both splits. Also make
  text-derived flags unit-level (any of the unit's own ads): ad wording varies
  between relistings, and a toggling flag adds noise.
- **Memory.** Each conditional-MAP job uses about 1.2 GB and a NUTS screen
  about 1.5–2 GB. Eleven parallel jobs plus a protocol fit exhausted the
  15 GB machine. Run at most three screens next to a fit.
