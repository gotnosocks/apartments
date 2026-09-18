# Saved Bayesian research page

Run `.venv/bin/streamlit run pages/3_Bayesian_Research.py` from the repository. This separate page displays the accepted Chelsea baseline and half-feature-prior fits. It does not change the main reviewed model or its existing contributions/residuals page.

The page includes:

- Full- and half-bath increments, net bathroom balance, 95% credible intervals and endpoint support, with a bedroom filter.
- Named laundry, doorman, HVAC and pet-rule comparisons computed from joint coefficient draws. Recorded categories, unknown counts and shared-building/unit overlap stay visible.
- Direct bathroom and named-category prior comparisons, with both 95% credible intervals, endpoint support and descriptive median shifts. Net bathroom balance has its own log-scale table. Posterior draws are not paired across fits.
- The second-half-bath warning distinguishes two advertisements across the entire fitted cohort from one advertisement/observation at each displayed endpoint. The maximum fitted-median movement across the 13 current apartments is $7.82.
- All 13 saved current residuals for the selected fit, latent fitted-median intervals and source-record identities. Saved current status does not establish present availability.

The sidebar switches between accepted fits and accepts a directory containing the named completed report bundles. `src/apartments/bayesian_review.py` records those expected bundle names. This deliberately reviews a fixed pair of source-compatible research fits; it does not automatically select a newer experiment.

Loading verifies the report/category/comparison files against completion manifests, checks parameter and derived convergence thresholds, and binds reports to the exact saved experiment, protocol and source manifests. It also verifies small saved fit products, matches current residuals against their saved text product and checks their arithmetic. Category support and comparison identities are validated before display. The bathroom comparison additionally binds both experiment manifests, fixed protocol, exact feature/time design hashes and source identity; its intervals and support must match both saved reports. The backend streams and hashes the source observations to count distinct advertisements supporting the second-half coefficient, retaining only those rare records. Diagnostic-only, incomplete, mismatched or tampered reports fail closed.

The UI never opens `posterior.nc`, imports sampling routines, fits or scrapes. Full posterior/source verification and contrast derivation occurred when the completed reports were produced; the UI checks their bindings and displayed products. The rare-half-bath support scan also verifies the source observations hash without retaining the complete dataset. Metadata-based cache invalidation covers the report bundles and small fit files used by the page. The reload button clears the cache.

Intervals describe conditional associations under the measured data, model and priors, not causal amenity values or willingness to pay. The sparse-endpoint label means fewer than 30 observations at either endpoint; it is a review cue, not an inferential threshold. A residual prompts source and missing-feature review rather than automatically identifying a bargain.

Validation: 22 backend/UI tests passed, including real accepted artifacts, refusal of rehashed invalid statuses/bindings/current-source/median-shift values, a guard against opening posterior arrays, and Streamlit AppTest selection of HVAC, the half-prior fit, bedroom-specific comparisons and an invalid artifact directory. Additional checks reject bathroom comparison changes to protocol/design/source bindings, intervals, endpoint support or current residual movement. The real page renders eight tables and exposes all 13 current observations. No browser screenshot was taken.
