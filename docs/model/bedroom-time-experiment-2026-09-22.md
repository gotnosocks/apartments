# Bedroom-group time-trend deviations

Research fit, September 22. **Not selected**: `config/main-analysis.json` is
unchanged. Promotion needs the reader changes listed at the end, plus Ben's
decision.

## Motivation

The selected model (`chelsea-bayesian-product-scope-spline-disk-20260921`)
gives every apartment one Chelsea-wide trend for 2010–2026. Its saved
deviations from building + features + time (unit effect + residual) are
systematically signed by bedroom count and era:

| years | studio | 1BR | 2BR | 3BR+ |
|---|---|---|---|---|
| 2010–2013 | −1.9 to −3.8% | −1.4 to +0.2% | +4.0 to +5.8% | +3.5 to +10.5% |
| 2017–2024 | mostly ±1% | ±0.5% | ±1% | −2.3 to +2.5% |
| 2026 | −2.1% | +0.6% | +1.5% | +3.3% |

Relative prices of unit sizes moved over time: studios got relatively more
expensive into 2020, then relatively cheaper, and large units the reverse.
With one shared trend, those movements land in the bedroom coefficients,
building effects and residuals. That includes the current listings the
product serves.

## Specification

Added to the latent median, with everything else identical to the selected
spline model (same source, feature design, priors, Student-t likelihood,
sampler settings 4 × 4,000 tune / 6,000 draws, target accept 0.93, maxdepth
10):

    mu_i += f_{g(i)}(t(i)),  g ∈ {studio, 1BR, 2BR, 3+BR}

`f_g` is piecewise-linear between January knots (plus the final month). Knot
values are a Gaussian random walk per group with a shared yearly step scale
`tau ~ HalfNormal(0.05)`, non-centered. Curves are zero-sum across the four
groups at each month, so the common trend stays the equal-weight group
average. Each group's curve is also centered over that group's own training
months, so the bedroom increments keep their meaning as period-averaged
premiums. Code: `models/bayesian_bedroom_time_graph.py` (graph) and
`models/bayesian_bedroom_time_experiment.py` (protocol runner, reusing the
spline runner's source, design, disk-sampling and report stages; residuals
and fitted rents include the curve). The exact hashed code of the fit is
archived in its `protocol/` directory; afterwards the graph gained a
backward-compatible `group_column` argument, used only by the screen's
negative control. There are 18 knots × 4 groups plus one
scale, next to 22,144 unit effects.

A linear-per-group alternative was also screened (below) and rejected.

## Held-out screen (declared before fitting)

`models/bedroom_time_screen.py` holds out 10% of rows (5,264) from
repeat-listed units, each keeping at least one training row (split seed
20260922). It fits each variant on the same training rows and scores exact
posterior-predictive log density:

| variant | ΔELPD vs shared trend | notes |
|---|---|---|
| random walk | **+30.0 ± 9.5** | R-hat ≤ 1.02, 0 divergences |
| linear per group | +6.0 ± 5.1 | not credible; slopes mix slowly |
| negative control (walk on random per-unit pseudo-groups) | −0.5 ± 1.5 | tau shrinks to 0.0005 |

The screen is conservative: held-out rows belong to repeat units whose unit
effect is already estimated, while 47% of units are single-listing.

## Full protocol fit

`data/model/chelsea-bayesian-product-scope-bedroom-time-20260922`, from
`chelsea-product-scope-analysis-20260921` (52,638 rows, 22,144 units, 1,129
buildings, 172 current). Status `exploratory_converged`: max R-hat 1.0074,
min bulk ESS 787, min tail ESS 1,409, 0 divergences, 0 depth hits, min BFMI
0.445. Derived, floor and bedroom-time diagnostics are all acceptable.

Matched comparison (`models/bedroom_time_fit_comparison.py`, same source
observations):

- Row-weighted mean |group × year deviation| falls from 0.92% to **0.67%**.
- `sigma` 0.0657 → 0.0653; `sigma_unit` 0.0856 → 0.0854; `sigma_building`
  0.274 → 0.273. `tau` = 0.0143 ± 0.0021 per year.
- Feature coefficients are stable. The largest shift is +0.0085 log on the
  sparse `full_bathrooms_gt_4`; bedroom increments move ≤ 0.0024.
- Current-listing fitted rents: 3+BR +1.95% on average (range +1.0 to
  +3.8%, 9 rows), 2BR +0.8%, 1BR −0.2%, studios −0.5%.

Latest month (2026-09) minus January 2017, log deviation, median [95%]:

| studio | 1BR | 2BR | 3+BR |
|---|---|---|---|
| −2.1% [−3.2, −0.9] | −0.7% [−1.7, +0.3] | +0.4% [−0.8, +1.6] | +2.4% [+0.8, +4.0] |

January curve medians (%), relative to each group's own average:

| | 2010 | 2013 | 2016 | 2019 | 2020 | 2021 | 2023 | 2025 | 2026-09 |
|---|---|---|---|---|---|---|---|---|---|
| studio | −5.2 | −3.2 | −0.8 | +0.5 | +2.0 | −0.5 | +1.5 | +0.4 | −1.8 |
| 1BR | −0.9 | −1.6 | −0.7 | −0.4 | +0.3 | +1.9 | +0.4 | +0.7 | −1.3 |
| 2BR | +3.7 | +1.7 | +0.0 | −0.8 | −1.3 | +1.4 | −0.8 | −0.4 | +0.2 |
| 3+BR | +2.4 | +3.1 | +1.5 | +0.8 | −1.1 | −2.8 | −1.0 | −0.7 | +3.0 |

## What it does not fix

- 3+BR still sits above the fit in several years (+8.2% in 2010 on 47 rows,
  about +2.4% in 2016–2019). The curve is shrunk by design, and 3+ pools
  three-, four- and five-bedroom units. A separate 4+ group or a bedroom ×
  building-class interaction is the next thing to test, screened with
  conditional MAP first (see [fast screening](fast-screening-2026-09-22.md)).
- Seasonality stays shared across groups.
- These are conditional associations in asking rents, not causal effects.

## Promotion checklist (not done)

1. `models/bayesian_feature_report.py`: add this experiment version to
   `EXPERIMENT_VERSIONS` and its contract. apartments-c5 recently changed that
   file (lineage cache), so coordinate before editing.
2. `src/apartments/bayesian_analysis.py`: add a `bedroom_time` term to
   `_terms` (draws `[sample, group(row.bedrooms), period]`) and load it in
   `_draws`. Bedroom counterfactuals then move the group curve with the
   bedroom count, which is the intended joint change. Until then, the page's
   parity check against the saved residuals rejects this fit rather than
   silently omitting the term.
3. Run `apartments.main_analysis --experiment ... --dataset ...`, then
   `build-review-queue`.
