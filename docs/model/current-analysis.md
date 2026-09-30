# Refit current evidence, then analyze with PyMC

The chronological model lineage, equations and promotion decisions are recorded
in the [main-model evolution report](main-model-evolution.md). This page describes
the workflow and retains contemporaneous fit instructions; the current selected
pointer is authoritative when this page's historical cohort description differs.

The main workflow is scrape → transform → fit → analyze. Since 2026-09-26,
`config/main-analysis.json` selects a frontier summary bundle
([listing estimates](listing-estimates.md)), not a PyMC posterior (Ben's choice). The
PyMC analysis commands `analyze-apartment` and `rank-current-apartments` refuse the default
selection. Pass them `--selection` with a PyMC selection, for example the last one:
`git show 3d22dc2:config/main-analysis.json > /data1/apartments/tmp/<you>/pymc-selection.json`.
Its relative paths resolve against the repository root. The old PyMC research scripts in `models/`
that default to `config/main-analysis.json` also need their `--selection`.
Feature contributions, fitted residuals and joint apartment-specific contrasts are the
primary outputs.

## Current selected fit

The accepted experiment is `chelsea-bayesian-bathrooms-long-20260918`, bound to
`chelsea-reviewed-bathroom-projection-20260918`: 52,711 fitted observations,
22,165 units, 1,134 buildings and 13 refreshed current listings. Both parameter
and derived convergence checks pass. The source-cleaned 52,704-row refit is in
progress; it will not replace this selection until its verification and
comparison are complete. The floor-increment design and skeptical parameter
audit are separate research work, not silently retrofitted into saved draws.

## Fit and select

Use a verified reviewed bathroom/source-composition analytical bundle. Current
accepted capture observations belong in the fit, before preference or budget
filtering. Historical initial asks and current capture-time asks remain explicit
sampling rules; current attributes must not be copied backward onto historical
price events. One observation per unit/month avoids duplicate price evidence.

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --locked --extra model python \
  -m apartments fit-pricing \
  data/model/chelsea-reviewed-scope-composition-projection-20260918 \
  data/model/chelsea-next-bayesian-fit
```

The main command uses the versioned PyMC runner with compiled nutpie NUTS,
lossless repeated-feature compression, four chains, 2,000 tuning steps and
4,000 retained draws per chain by default. It writes a protocol, source/code
bindings, posterior, diagnostics, residuals and contrasts. Identical reruns
verify and reuse completed artifacts. Changed evidence or settings require a
new output directory. A failed convergence gate does not produce an accepted
main selection.

After diagnostics, source review and matched research comparisons support
selection, write the explicit pointer. **`--output` defaults to `config/main-analysis.json`,
which is the app's selected model. Replacing it needs Ben's OK, and the listings site's build
refuses a PyMC selection.** For analysis, write the pointer elsewhere:

```sh
uv run --locked --extra model python -m apartments.main_analysis \
  --experiment data/model/chelsea-next-bayesian-fit \
  --dataset data/model/chelsea-reviewed-scope-composition-projection-20260918 \
  --output /data1/apartments/tmp/<you>/pymc-selection.json
```

The selection command verifies the source, fit and both convergence gates.
It does not sample or replace existing source observations.

## Interpret and iterate

Residuals deliberately include the apartment's own evidence. They are in-sample
review signals, not independent prediction scores or automatic bargain labels.
Latent median rent intervals describe conditional posterior uncertainty, not a
transaction-price interval. Mean log contributions add to E[μ]; their dollar
transformations and interval endpoints are not additive.

Counterfactuals change raw source values together and re-encode dependencies,
including bedroom-dependent area normalization and bathroom shortfall. Building,
unit and date are held fixed. Unsupported endpoints, reporting-only changes and
failed derived diagnostics withhold physical-value estimates. Estimated market
associations do not replace an individual's willingness to pay.

Use large residuals and building/unit offsets to inspect immutable source
captures. Distinguish data errors, identity conflicts, lease/price-basis changes,
omitted attributes and unexplained variation. Apply supported corrections only
through separate overlays; never invent a replacement price because it would
reduce a residual. Compare changes on the same retained cohort and inspect new
cases beyond those that motivated the iteration.

The [parameter audit](../analysis/chelsea-bayesian-parameter-audit-2026-09-18.md)
records the evidence each representation must earn, including floor increments,
reporting indicators, pooling priors, time terms and residual assumptions.
Prior robust-model experiments remain documented in the
[historical workflow](legacy-robust-analysis.md). `fit-pricing-legacy` explicitly
retains the old baseline fitting command. The existing `score-apartments`
command is a legacy robust-model search path; the verified main Bayesian page
is the current contribution/residual interface while search integration is
updated. Preference ranking remains separate from the inferred market model.
