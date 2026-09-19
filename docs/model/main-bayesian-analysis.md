# Main Bayesian analysis

The main Streamlit contribution/residual page reads `config/main-analysis.json`, which explicitly binds an accepted PyMC experiment to its exact source dataset and protocol/fit manifests. `pages/1_Bayesian_Model.py` links to this main analysis and the separate research comparison page. Earlier interfaces are retained under `legacy/`.

Run the application normally, then open **Contributions and Residuals**. The default selection contains 52,711 fitted observations and 13 saved current listings. Search advertisements or unit URLs, filter buildings, and rank signed or absolute asking-price residuals. The selected listing shows its posterior median latent asking rent and 95% credible interval, plus the unit's fitted history. Saved current status does not guarantee present availability.

The contribution table reports posterior **mean log terms**, which sum to E[μ]. Their intervals are calculated from joint draws and withheld when the new derived diagnostic checks fail. Components are not additive dollar premiums, and category basis terms are not category-to-category price differences. Exponentiating the contribution sum need not reproduce the posterior median rent.

The feature form uses physical source values, including separately reported full and half bathrooms, area, bedrooms, and nested amenity flags. Selected changes are submitted together. The backend recomputes interactions while holding date, building and unit effects fixed, using all retained joint posterior draws. The page shows before/after endpoint support and knownness; only an `accepted` comparison receives physical-value intervals. `reporting_change`, `unsupported_endpoint`, and `diagnostic_only` results retain their evidence and explanations while withholding estimates. These are conditional associations, not causal renovation returns or personal willingness to pay.

The optional archived-description bundle is verified against the source lineage and displayed as plain text. Source capture, interpretation and attribute-effective dates remain distinct. Invalid or mismatched selection, source, fit or evidence bundles produce an explicit error rather than a fallback model. The page never starts sampling, scrapes data, edits evidence or promotes an experiment. Resource caching uses bundle file signatures; loading independently verifies hashes. Posterior access and selected unit/building slices are managed by the Bayesian backend.

A saved selection may bind its matching description archive using
`python -m apartments.main_analysis --experiment ... --dataset ... --evidence ...`.
Selection verifies the entire evidence mapping before writing and records its
manifest hash. The page uses that selected archive as its default; changing the
selected cohort resets the default rather than keeping an unrelated old archive.
The existing selection remains valid without an explicit evidence field. The
refreshed 172-current-listing archive is prepared, but has not been selected with
a new fit yet.

`tests/test_main_bayesian_page.py` checks source-valued form defaults, simultaneous edits, literal description rendering, failed-status withholding, invalid-binding failure and the actual accepted 13-current-listing workflow with a laundry comparison. These UI checks supplement the backend's reconstruction and posterior-diagnostic tests.

## Command line

`fit-pricing` invokes the exact PyMC/NUTS model with durable disk-backed traces
and bounded reporting by default. Its inputs are a verified bathroom-count or
reviewed scope/composition source projection and an experiment output directory:

```bash
UV_CACHE_DIR=/tmp/apartments-uv-cache uv run --frozen --no-sync python -m apartments.cli fit-pricing \
  data/model/chelsea-reviewed-scope-composition-projection-20260918 \
  data/model/my-bayesian-fit
```

Defaults are four chains, 2,000 warmup and 4,000 retained draws per chain, `full_half_balance`, shared observation noise, target acceptance 0.93, diagonal adaptation and seed 20260918. `--draws`, `--tune`, `--chains`, `--seed`, `--target-accept` and `--adaptation` control sampling. `--spec`, `--residual-scale`, `--prior-multiplier`, `--building-prior-scale`, `--unit-prior-scale` and `--residual-parameterization` explicitly change recorded model settings; `--graph-validation` optionally binds a verified graph parity artifact. See `fit-pricing --help` for allowed settings. BLAS calculations run with one thread to preserve exact design reconstruction; the existing runner handles the NUTS chains, immutable protocol, checkpoint validation and diagnostic reports. A diagnostic-only result remains diagnostic-only. Fitting never changes the selected main model or substitutes another estimator. The accepted main fit still uses linear floor terms; floor-threshold research has not been promoted.

`--floor-increments` selects the explicit v4 listed-floor threshold design;
`--floor-increment-prior-scale` sets its increment prior (default 0.15). Without
that flag, the model remains the v3 linear-floor specification. Storage does not
change the likelihood, priors, retained draws or diagnostic gates.

`--execution memory` retains the older in-memory execution path for explicit
replay of existing protocols. Large runs previously exhausted memory on that
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
