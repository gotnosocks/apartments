# Main Bayesian analysis

The main Streamlit contribution/residual page reads `config/main-analysis.json`, which explicitly binds an accepted PyMC experiment to its exact source dataset and protocol/fit manifests. `pages/1_Bayesian_Model.py` links to this main analysis and the separate research comparison page. Earlier interfaces are retained under `legacy/`.

Run the application normally, then open **Contributions and Residuals**. Cohort and current-listing counts come from the bound selection. Search advertisements or unit URLs, filter buildings, and rank signed or absolute asking-price residuals. The selected listing shows its posterior median latent asking rent and 95% credible interval, plus the unit's fitted history. Saved current status does not guarantee present availability.

The contribution table reports posterior **mean log terms**, which sum to E[μ]. Their intervals are calculated from joint draws and withheld when the new derived diagnostic checks fail. Components are not additive dollar premiums, and category basis terms are not category-to-category price differences. Exponentiating the contribution sum need not reproduce the posterior median rent.

The feature form uses physical source values, including separately reported full and half bathrooms, area, bedrooms, and nested amenity flags. Selected changes are submitted together. The backend recomputes interactions while holding date, building and unit effects fixed, using all retained joint posterior draws. The page shows before/after endpoint support and knownness; only an `accepted` comparison receives physical-value intervals. `reporting_change`, `unsupported_endpoint`, and `diagnostic_only` results retain their evidence and explanations while withholding estimates. These are conditional associations, not causal renovation returns or personal willingness to pay.

The optional archived-description bundle is verified against the source lineage and displayed as plain text. Source capture, interpretation and attribute-effective dates remain distinct. Invalid or mismatched selection, source, fit or evidence bundles produce an explicit error rather than a fallback model. The page never starts sampling, scrapes data, edits evidence or promotes an experiment. Resource caching uses bundle file signatures; loading independently verifies hashes. Posterior access and selected unit/building slices are managed by the Bayesian backend.

A saved selection may bind its matching description archive using
`python -m apartments.main_analysis --experiment ... --dataset ... --evidence ...`.
Selection verifies the entire evidence mapping before writing and records its
manifest hash. The page uses that selected archive as its default; changing the
selected cohort resets the default rather than keeping an unrelated old archive.
The existing selection remains valid without an explicit evidence field. The
current Chelsea selection binds its matching description archive and source-case
review notes; research reports record the specific cohort and fit decisions.

`tests/test_main_bayesian_page.py` checks source-valued form defaults, simultaneous edits, literal description rendering, failed-status withholding, invalid-binding failure and the actual accepted 13-current-listing workflow with a laundry comparison. These UI checks supplement the backend's reconstruction and posterior-diagnostic tests.

## Command line

`fit-pricing` invokes the exact PyMC/NUTS model with a regularized natural cubic
floor curve, durable disk-backed traces and bounded reporting by default. Its
inputs are a verified analytical source projection and a new experiment output
directory. The expanded Chelsea projection includes the reviewed label-derived
floor data:

```bash
UV_CACHE_DIR=/tmp/apartments-uv-cache uv run --frozen --no-sync python -m apartments.cli fit-pricing \
  data/model/chelsea-label-floor-analysis-20260919 \
  data/model/my-bayesian-fit
```

CLI defaults are four chains, 2,000 warmup and 4,000 retained draws per chain,
`full_half_balance`, shared observation noise, the spline floor curve, target
acceptance 0.93, diagonal adaptation and seed 20260918. These sampling defaults
are **not the settings of the matched production experiment**, which uses 4,000
warmup and 6,000 retained draws per chain with seed 20260924. The explicit
production specification is:

```bash
UV_CACHE_DIR=/tmp/apartments-uv-cache uv run --frozen --no-sync python -m apartments.cli fit-pricing \
  data/model/chelsea-label-floor-analysis-20260919 \
  data/model/my-matched-spline-floor-fit \
  --floor-model spline --floor-prior-scale 0.10 --maxdepth 10 \
  --chains 4 --tune 4000 --draws 6000 --target-accept 0.93 \
  --adaptation diag --seed 20260924
```

The spline uses observed endpoints and prespecified interior knots at floor
labels 5, 10, 20 and 35, retaining only knots inside the observed range. It is
anchored at floor 2 when supported by that range, with a separate unknown-floor
indicator. `--floor-prior-scale` defaults to 0.10 for orthonormal knot-height
contrasts; `--maxdepth` defaults to 10 for this model. Floor labels remain
advertised labels rather than measured height. Interpolation inside the fitted
range is allowed, while extrapolation is rejected. See the
[spline experiment specification](floor-spline-experiment-2026-09-19.md) for
the prior, source support and diagnostic requirements.

`--floor-model increments` or the legacy `--floor-increments` flag selects the
v4 threshold design; `--floor-increment-prior-scale` sets its prior (default
0.15). `--floor-model linear` or `--linear-floor` selects the v3 linear design.
Do not combine `--floor-model` with either legacy flag. Legacy disk fits omit an
explicit tree-depth setting unless `--maxdepth` is supplied, preserving the
earlier protocol behavior. `--graph-validation` is available for legacy models;
the spline rejects these earlier graph proofs instead of treating them as
validation of a different specification.

`--draws`, `--tune`, `--chains`, `--seed`, `--target-accept` and `--adaptation`
control sampling. `--spec`, `--residual-scale`, `--prior-multiplier`,
`--building-prior-scale`, `--unit-prior-scale` and
`--residual-parameterization` explicitly change recorded model settings. BLAS
calculations use one thread to preserve exact design reconstruction. The runner
handles NUTS chains, immutable protocols, checkpoint validation and diagnostic
reports. A diagnostic-only result remains diagnostic-only. Fitting never changes
the selected main model or substitutes another estimator. Changing the CLI
default therefore does not promote an unreviewed spline fit.

`--execution memory` retains the older in-memory execution path only with an
explicit linear or increment specification. The spline requires disk execution,
and `--maxdepth` is rejected for memory execution. Large runs previously exhausted memory on that
path. The default `--execution disk` records its storage protocol separately and
requires its own output directory; it cannot silently resume an in-memory run as
though the execution protocol were unchanged. Keep traces and reporting caches
on a sufficiently large workspace disk, not a small `/tmp` tmpfs.

`analyze-apartment` reads the main selection and prints JSON containing the source-bound detail and, optionally, one joint counterfactual. Changes use physical source values; full and half bathrooms are separate, and supported nested amenity flags use dotted keys.

```bash
UV_CACHE_DIR=/tmp/apartments-uv-cache uv run --frozen --no-sync python -m apartments.cli analyze-apartment \
  'capture:refresh:7c2385c6c3686e78:1' \
  --selection config/main-analysis.json \
  --changes '{"bedrooms":2,"full_bathrooms":2}'
```

Omit `--changes` for detail only. Selection defaults to the repository's `config/main-analysis.json`; unknown identities, invalid bindings and unsupported changes fail explicitly. The backend withholds counterfactual estimates for unknown starting attributes, unsupported endpoints or failed joint diagnostics, preserving that status in the JSON. This command does not fit, scrape, patch observations or promote a model. The earlier robust/ridge fitting command is available explicitly as `fit-pricing-legacy` with its original `--holdout-fraction` and `--ridge` options.

For a preference frontier over the selected fit's current observations, use
[`rank-current-apartments`](bayesian-candidate-ranking.md). It keeps user-supplied
monthly dollar preferences separate from PyMC latent-price intervals and fitted
residuals. The older `score-apartments` command remains explicitly legacy robust
scoring; it is not the main Bayesian ranking path.
