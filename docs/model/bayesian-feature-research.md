# Bayesian feature research

The [first converged results](../analysis/chelsea-bayesian-bathrooms-2026-09-18.md)
include conditional bathroom intervals, source audits and corrected residual-fit
checks. The reviewed serving model has not been replaced.
The [same-cohort prior check](../analysis/chelsea-bayesian-prior-sensitivity-2026-09-18.md)
finds stable common bathroom increments and substantial prior dependence for the
two-advertisement second-half-bath term.

This experiment targets contributions and fitted residuals on the current Chelsea
cohort. The initial projection has 52,712 observations; the source-policy revision
has 52,711 after quarantining one office advertisement. Both include the 13 refreshed
listing captures. The model estimates uncertainty jointly across features, time,
buildings and units. It does not replace the reviewed serving model.

A further [source revision](../analysis/chelsea-bayesian-source-revision-2026-09-18.md)
retains 52,704 observations, 22,158 units and 1,131 buildings after seven named
quarantines and five composition masks. It preserves all 13 current captures.
Its refit remains separate from experiments on the 52,711-row cohort.

## Construction

`models/bayesian_feature_model.py` extends the existing Bayesian time design with
identified amenity contrasts and four selectable bathroom constructions:

1. `linear_total`: one coefficient per scalar bathroom above one.
2. `incremental_total`: a separate coefficient for each half-step threshold.
3. `full_half`: separate full-bath increments and half-bath increments, using the
   original explicit source counts rather than reconstructing them from a scalar.
4. `full_half_balance`: adds `max(bedrooms − full bathrooms, 0)` to the preceding
   construction. This distinguishes eliminating a shortage of full bathrooms from
   adding bathrooms beyond the bedroom count.

The initial projection provides only 0/1 half-bath support after its source-review
flags are masked, so its second-half-bath increment is removed as constant.
The versioned source-policy revision accepts two specifically corroborated
multiple-half layouts and estimates that increment with explicit sparse support.

All four specifications use the same composition-known mask. Missing, inconsistent
or flagged bathroom composition supplies no bathroom-value contrast; the row
remains in the fit with a separate unknown indicator. The first balance design
has 42 nonconstant, full-rank feature columns and 52,522 composition-known rows;
the revised design has 43 columns and 52,508 composition-known rows. The remaining
190 or 203 rows respectively still contribute to other terms. Unflagged source counts
are not independently verified physical counts; shared facilities remain a known
measurement limitation identified in the [source audit](../analysis/chelsea-bathroom-evidence-2026-09-18.md).

Bedroom increments, bedroom-normalized log size, size missingness, the existing
amenity families, smooth time, annual drift and month-of-year effects remain
included. Category contrasts use an orthonormal zero-sum basis and known-only
frequency centering, with a separate unknown indicator. Constant or wholly
unobserved numeric magnitudes are omitted. This prevents a nominal coefficient
for an unobserved floor or constant positive-only exposure from looking identified.

The likelihood is Student-t on log gross advertised rent with five degrees of
freedom. Building effects are zero-sum normal; unit effects are normal with an
estimated shared scale. Both are estimated jointly with feature coefficients.
The spline and seasonal basis follow the existing season-separated Bayesian
implementation. These are descriptive group adjustments, not causal premiums.

Coefficient priors are zero-centered normal, allowing negative as well as positive
increments. Log-effect standard deviations are 0.25 for bedroom/full-bath
increments, 0.20 for half-bath/shortfall and reporting terms, 0.35 for log size,
and 0.15 for standardized amenity magnitudes and orthonormal category contrasts.
`--prior-multiplier` scales this feature-prior family for sensitivity experiments.
Residual, unit, building, trend and seasonal scales have proper half-normal priors;
their exact definitions are snapshotted with every run.

### Residual-scale and group-prior alternatives

`models/bayesian_feature_experiment_v3.py` adds explicit `--residual-scale`
(`shared` or `bedroom`), `--building-prior-scale` (default 0.35), and
`--unit-prior-scale` (default 0.25). The default shared graph reproduces the v2
log density and every gradient entry exactly at three tested points on all
52,711 observations, using a freshly reconstructed training design. The proof
is in `data/model/chelsea-bayesian-v3-shared-graph-parity-20260918`.

Bedroom mode uses `sigma_b = sigma * exp(tau * z_b)`, where the observed bedroom
levels have zero-sum normal offsets, `tau ~ HalfNormal(0.3)` and
`sigma ~ HalfNormal(0.25)`. Thus global sigma is the geometric mean of the
bedroom-level scales with equal level weights. This is a Student-t scale in log
rent, not a standard deviation or a price-contribution coefficient. Degrees of
freedom remain five and all mean terms retain their previous definitions.

Every run saves exact bedroom levels and support, graph settings, scale intervals
and posterior draws. Diagnostics include the bedroom-scale parameters and
deterministic scales. Reload validation checks feature, building, unit, trend,
season and bedroom coordinate order before positional reconstruction.

The v3 posterior checker reconstructs the mean with the corrected ordered design
loader, then simulates using each row's bedroom-specific scale from the same joint
draw. It rejects absent, reordered or inconsistent scale arrays instead of
substituting global sigma. Shared mode remains available for a matched comparison.
`models/bayesian_noise_sensitivity.py` requires identical source and saved mean
designs, unchanged mean priors and shared implementation dependencies. Each fit
must pass both diagnostic gates. Between-fit median changes are descriptive;
draws from separate models are not paired to invent a difference interval.

## Interpretation and checks

For a two-bedroom unit, the `1 → 2` full-bath contrast combines the second-full-bath
increment with removal of the shortfall term. The `2 → 3` contrast uses the
third-full-bath increment alone. The runner computes both from each *joint*
posterior draw, then computes their difference. Subtracting endpoints from two
independent marginal intervals would discard posterior covariance.

Contrasts hold building, unit, date, size and other observed features fixed. Each
endpoint reports rows, distinct units and buildings with that exact bedroom,
full-bath and half-bath configuration. Unsupported endpoints remain explicitly
marked; prior-driven extrapolations are not established amenity values. A half
bath does not remove a shortage of full baths under this specification.

Full-bath thresholds share their coefficients across bedroom counts; the shortfall
term supplies the bedroom-relative difference. The shortfall penalty is linear
per missing full bath. Half-bath increments are also shared across bedroom counts
and do not vary by suite access. These are explicit starting assumptions, not
evidence that the underlying relationships must have this form. Bedroom coefficient
intervals alone are not fixed-area bedroom counterfactuals: changing the bedroom
count also changes the size normalization and potentially the shortfall term.

Fitted residuals compare each advertised ask with the posterior median of its
latent conditional median rent. The saved latent-rent interval describes parameter
uncertainty for that observed unit, not a predictive interval for a future ask.
The log-Student-t model does not imply a finite arithmetic mean rent, so the
report deliberately uses a conditional median.

Interpretation requires all diagnostics to pass: maximum R-hat below 1.01,
minimum bulk and tail ESS at least 400, no divergences, no maximum-depth events,
minimum chain E-BFMI at least 0.3, and finite parameter diagnostics. Short pilot
runs are explicitly marked diagnostic-only if they fail. Diagnostic principles
follow the [Stan diagnostic guidance](https://mc-stan.org/learn-stan/diagnostics-warnings.html).
The [PyMC zero-sum distribution](https://www.pymc.io/projects/docs/en/stable/api/distributions/generated/pymc.ZeroSumNormal.html)
provides the building constraint.

Even converged intervals are conditional on measurements, priors and construction.
They do not account for all missed features, archive selection, historical
measurement changes or physical-layout ambiguity. Prior and source-policy
sensitivity remain part of the research, alongside residual review.
The [identification audit](../analysis/chelsea-bayesian-identification-2026-09-18.md)
quantifies within-unit variation, sparse endpoints, and the dependence of
feature-versus-group allocation on pooling assumptions.

## Reproduction

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
NUMBA_CACHE_DIR=/tmp/apartments-numba \
PYTENSOR_FLAGS='cxx=,compiledir=/tmp/apartments-pytensor,numba__cache=False' \
.venv/bin/python -m models.bayesian_feature_experiment_v2 \
  --dataset data/model/chelsea-reviewed-bathroom-projection-20260918 \
  --output data/model/chelsea-bayesian-bathrooms-long-20260918 \
  --spec full_half_balance --chains 4 --tune 1000 --draws 4000 \
  --adaptation diag \
  --graph-validation data/model/chelsea-bayesian-feature-graph-parity-20260918
```

Every run binds the exact source observations, source manifest, implementation,
package versions and sampling settings. The protocol and source code snapshots
are immutable. Binary posterior draws and all result files receive SHA-256 hashes
in a final completion manifest only after diagnostics and summaries finish.
A hash-bound posterior checkpoint permits report recovery without resampling;
an altered protocol requires a different output directory. The prior draws,
parameter diagnostics, posterior draws, design, bathroom contrasts, coefficients,
group effects and every fitted residual are retained.

Relevant findings: [extreme group effects](../analysis/chelsea-group-effects-2026-09-18.md)
and [bathroom evidence and varied research phrases](../analysis/chelsea-bathroom-evidence-2026-09-18.md).

## Current execution status

The initial full-cohort computational pilot completed at 20:17 UTC on September 18 in
`data/model/chelsea-bayesian-bathrooms-pilot-20260918`: two chains, 150 warmup and
100 retained draws per chain, low-rank adaptation, seed 20260918. Sampling took
1,788 seconds. It had no divergences, but failed convergence: maximum R-hat 1.313,
minimum bulk ESS 5.86 and minimum tail ESS 13.87. This is a runtime and geometry
check, not an accepted uncertainty result. Its log is `/tmp/chelsea-bayesian-pilot.log`.
The worst-mixing building had only one observation: a $42,500/month, 4,395-square-foot
townhouse advertisement at 344 West 22nd Street. This is evidence to inspect sparse
group uncertainty, not a reason to delete a row merely because it mixes slowly.

The earlier complete offline suite passed **917 tests, with two skips**. Its checks cover
full/half distinctions, exact increments, bedroom-relative joint contrasts,
unknown/contradictory composition, category rank, design reload parity, finite
initial density, posterior reconstruction across row blocks, correlated-draw
contrast arithmetic, binary checksum verification and completed-run replay.

No posterior interval has been promoted to the analysis page. The original pilot
and its implementation are retained unchanged.

The expanded suite passed **1,170 tests, with two skips and nine warnings**, in
182 seconds after adding the v3 graph, runner, scale-aware posterior checks,
report verification, source overlay and same-cohort noise comparison. This includes
rejection of reordered posterior coordinates, changed source/design bindings,
unsupported noise fallbacks and comparisons that inadvertently change mean priors.

The [source-policy revision](../analysis/chelsea-bathroom-research-revision-2026-09-18.md)
is now published separately at `data/model/chelsea-reviewed-bathroom-projection-20260918`.
It contains 52,711 rows and all 13 current captures. A design preflight in
`data/model/chelsea-reviewed-bathroom-preflight-20260918` verifies 43 full-rank
feature columns and 52,508 usable bathroom compositions. The additional feature
is the second-half-bath increment, supported by only two specifically corroborated
advertisements. Its presence is not evidence of a precise contribution estimate.

`models/bayesian_sampling.py` provides per-chain progress,
incomplete-draw rejection, and recovery from an interrupted completion-manifest
write. Four focused tests pass, alongside ten new source-revision tests. An exact
normal-normal posterior check validates the sampler path and named coordinates;
its result is retained in `data/model/bayesian-sampler-validation-20260918-v2`.

The v2 runner now uses that helper, accepts both source-policy projections, and
also checks convergence of actual unit offsets (`sigma_unit × unit_z`) and
supported joint bathroom/balance contrasts. Convergence of separate coefficients
alone does not substitute for convergence of the quantities being reported.

The equivalent graph in `models/bayesian_feature_graph.py` evaluates shared
covariate rows once and time/season effects at the calendar level, retaining every
observation and unchanged priors. Full-cohort comparison across three parameter
points found maximum log-density difference 2.91e−11 and maximum gradient
difference 3.06e−10 across 23,425 parameters. Warm median gradient evaluation fell
from 9.56 ms to 1.75 ms. The [parity artifact](../../data/model/chelsea-bayesian-feature-graph-parity-20260918/report.md)
records exact code/data/design hashes and compilation versus evaluation timings.
Five tests additionally cover all bathroom specifications and individual prior
contributions.

The four-chain, 1,000-warmup/1,000-draw run completed at 20:25 UTC in
`data/model/chelsea-bayesian-bathrooms-reviewed-20260918`. It used diagonal
adaptation and the verified compressed graph on the 52,711-row reviewed cohort.
Sampling took approximately 250 seconds, with no divergences or maximum-depth
events. It still failed the uncertainty gates: maximum parameter R-hat 1.0251,
30 parameters above 1.01, minimum bulk ESS 172.0, and minimum tail ESS 272.7.
Derived unit effects and joint bathroom contrasts also failed: maximum R-hat
1.0143, three quantities above 1.01. The first full-bath increment for one-bedroom
units was among the slow-mixing contrasts. Its intervals remain diagnostic-only.

A new four-chain run with 1,000 warmup and 4,000 retained draws per chain completed
at 20:50 UTC in `data/model/chelsea-bayesian-bathrooms-long-20260918`, retaining
the exact reviewed cohort, specification, priors and seed. Both diagnostic
families pass. Parameter maximum R-hat is1.00767 with minimum bulk/tail ESS559/966;
derived maximum R-hat is1.00333 with minimum bulk/tail ESS666/1285. The verified
report is `data/model/chelsea-bayesian-long-report-20260918`. The accepted
feature-prior multiplier0.5 retry completed at21:33 UTC and its verified
comparison is `data/model/chelsea-bayesian-prior-sensitivity-20260918`.
The bedroom-scale v3 experiment is running separately in
`data/model/chelsea-bayesian-bedroom-noise-20260918` on identical source inputs.

`models/bayesian_feature_report.py` produces a source-bound JSON and standalone
HTML review only after both diagnostic gates pass. It leads with joint bathroom
contrasts and their observed support, followed by group offsets and residual
source cases. Ten focused tests cover its gates and source integrity. En-suite
counts remain a separate [evidence investigation](../analysis/chelsea-ensuite-counts-2026-09-18.md),
with [explicit floor-plan references](../analysis/chelsea-floorplan-references-2026-09-18.md)
available for door-access review.
