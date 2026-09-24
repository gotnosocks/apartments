# Refit current evidence, then analyze with PyMC

The chronological model lineage, equations and promotion decisions are recorded
in the [main-model evolution report](main-model-evolution.md). This page describes
the workflow and retains contemporaneous fit instructions; the current selected
pointer is authoritative when this page's historical cohort description differs.

The main workflow is scrape → transform → fit → analyze. The main model is the
hierarchical PyMC posterior selected by `config/main-analysis.json`. Feature
contributions, fitted residuals and joint apartment-specific contrasts are the
primary outputs. The [main analysis page](main-bayesian-analysis.md) uses every
retained joint posterior draw; no surrogate regression supplies its estimates.

## Current selected fit

The accepted experiment is `chelsea-bayesian-bathrooms-long-20260918`, bound to
`chelsea-reviewed-bathroom-projection-20260918`: 52,711 fitted observations,
22,165 units, 1,134 buildings and 13 refreshed current listings. Both parameter
and derived convergence checks pass. The source-cleaned 52,704-row refit is in
progress; it will not replace this selection until its verification and
comparison are complete. The floor-increment design and skeptical parameter
audit are separate research work, not silently retrofitted into saved draws.

The main page reproduces all 13 current fitted-rent credible intervals within
$1.4e-11 of the saved fit. Tests also exercise a real joint laundry change,
all-fitted browsing, source evidence, invalid bundles and withheld comparisons.
The separate [research page](bayesian-research-page.md) compares accepted runs.

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
selection, publish the explicit pointer:

```sh
uv run --locked --extra model python -m apartments.main_analysis \
  --experiment data/model/chelsea-next-bayesian-fit \
  --dataset data/model/chelsea-reviewed-scope-composition-projection-20260918
```

The selection command verifies the source, fit and both convergence gates.
It does not sample or replace existing source observations.

**After every new selection, rebuild the residual review queue** (about two
minutes, report-only; it reads saved residuals and group effects, never the
posterior draws):

```sh
uv run --locked --extra model python -m apartments build-review-queue
```

The queue page at http://thelio.tail3983e0.ts.net:8767/ follows
`config/main-analysis.json` and picks up the rebuilt bundle with no restart.
Until it is rebuilt the page reports that no queue exists for the selected fit.
See the [review queue](review-queue.md) for the ranking and contents. The page independently
checks these bindings, rebuilds the exact feature design and opens the saved
posterior. Unsupported or mismatched states raise an explicit error.

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
