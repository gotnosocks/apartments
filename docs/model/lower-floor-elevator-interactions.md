# Lower-floor elevator interaction candidates

Two **unfitted research designs** now extend the existing Bayesian floor design.
The [corrected-source support review](../analysis/chelsea-reviewed-floor-elevator-support-2026-09-19.md)
limits the initial experiment to thresholds 2, 3 and 4. No physical height is
inferred, and no interaction is added at threshold 5 or above.

Let `F` be the canonical advertised floor and `w(E)` equal −1/2 for explicit
no-elevator evidence, +1/2 for explicit elevator evidence, and zero for unknown.
For known `F`, define `z_k = w(E) * 1(F > k)`; unknown floors have `z_k = 0`.
The added term is either:

- Separate increments: `gamma_2*z_2 + gamma_3*z_3 + gamma_4*z_4`.
- One pooled coefficient: `gamma*(z_2 + z_3 + z_4)/sqrt(3)`.

All gamma coefficients have independent zero-mean Normal priors with SD 0.15
in the initial design audit. The pooled normalization matches the two candidates'
prior variance for the *difference* between the elevator and no-elevator 2→5
floor contrasts. It does not match their local prior shapes. The pooled design
assumes equal consecutive interaction increments; the separate design permits
unequal signs and sizes.

Unknown elevator status is not mapped to no elevator. Its zero interaction
weight uses the existing main floor curve as the midpoint of the two known
access curves. This is an explicit modeling convention, not an observation of
physical access or a claim that unknown buildings are average. Existing elevator
and floor missingness columns remain unchanged. The added interaction saturates
at floor 5, so it assumes no further differential increment at higher labels;
existing upper-floor main effects still vary. This assumption needs to remain
visible in counterfactual reporting.

## Prior implications

The base design and all of its priors are unchanged. Adding interaction variance
therefore widens the priors on access-specific floor contrasts relative to the
no-interaction model. This is recorded rather than described as a fully matched
prior comparison.

| Log-price contrast prior SD | Base only | Pooled interaction | Separate interactions |
| --- | ---: | ---: | ---: |
| Each 2→3, 3→4 or 4→5 floor change at fixed known access | .15000 | .15612 | .16771 |
| 2→5 floor change at fixed known access | .25981 | .29047 | .29047 |
| Elevator minus no-elevator difference in a single floor increment | 0 | .08660 | .15000 |
| Elevator minus no-elevator difference in the 2→5 change | 0 | .25981 | .25981 |

These are prior standard deviations, not estimated premiums. Posterior comparisons
must use joint base-plus-interaction draws at the same floor endpoints. An
interaction coefficient alone is not a floor premium. Sensitivity to gamma scale
and to the few influential buildings is required before assigning an effect a
renter-facing interpretation.

## Completed implementation checks

`models.bayesian_floor_elevator_design.FeatureDesign` composes the base floor
design without modifying its implementation. It requires explicit positive and
negative elevator observations at each endpoint 2, 3, 4 and 5, keeps every base
column and prior, records the added centering, and saves a separate versioned
design. Public transformation rejects floors outside the base's observed support.

On the exact 52,653-row elevator-corrected source, every base column is bitwise
unchanged. The base feature rank is 59; the pooled and separate candidates have
60 and 62 columns and ranks respectively. These rank checks exclude group and
time effects. They do not establish hierarchical identification, adequate support,
or an effect worth retaining.

| Advertised floor | No-elevator rows | Elevator rows |
| --- | ---: | ---: |
| 2 | 20 | 10 |
| 3 | 22 | 21 |
| 4 | 34 | 13 |
| 5 | 34 | 26 |

Repeated advertisements are included in these row counts; the source-support
review gives distinct-unit and within-building limitations.

Fourteen tests pass, including save/load equivalence, unchanged base columns,
unknown-status handling, saturation, induced prior calculations, unsupported
endpoints, and exact PyMC reference/compressed log-density and gradient agreement
on a small deterministic fixture for each candidate. These are correctness tests,
not sampling or speed benchmarks. The full-source design audit is
`data/model/chelsea-lower-floor-elevator-design-audit-20260919`.

The candidates have **not been sampled or integrated into the main reporting or
counterfactual loaders**. A dedicated versioned disk experiment and joint-contrast
reporting are now implemented as described below. After completing the elevator
source-refit comparison and full-cohort compiled graph parity, fit the one-term
candidate first. Evaluate the three-term alternative only as a declared complexity
comparison. Keep the accepted main selection until those results earn a change.


## Explicit experiment and reporting contract

`models.bayesian_floor_elevator_experiment` uses the existing exact PyMC compressed
graph, nutpie/Numba sampler, durable raw trace, bounded posterior export and report
cache under the new family version
`observable-bayesian-floor-elevator-experiment-v5`. Its defaults are four chains,
4,000 warmup and 6,000 retained draws. It requires a full-cohort compiled parity
bundle matching source, mode, priors, thresholds, graph settings and implementation
hashes before sampling. Sampler execution metadata remains separately versioned.
No surrogate or variational approximation is introduced.

Saved design files are flat to match the immutable fit-bundle contract:
`feature-design.json` records the base, while `interaction-design.json` records
and verifies the additional columns, means, priors and combined support. Consumers
must explicitly select the v5 wrapper; reading the base alone cannot reconstruct
this model. The fitted source design is checked for full matrix rank before fitting.

Reporting evaluates all retained joint beta draws for floor changes at each known
access state, plus the elevator-minus-no-elevator differences for 2→3, 3→4, 4→5
and 2→5. It preserves covariance between base-floor and interaction terms, records
actual endpoint support and induced contrast-prior SDs, and marks unsupported
floor/access endpoint combinations as extrapolations. Failed derived convergence
withholds that interval and prevents an accepted fit status. Parameter and existing
unit/bathroom diagnostics must also pass.

Forty-three focused tests pass across the candidate designs, protocol/contrast
contract and existing disk execution. Coverage includes changed graph proofs,
unsupported access endpoints, covariance-sensitive intervals, unmixed chains,
completed-fit reuse, required products, and reporting recovery that preserves
all existing draws without another sampling call. These tests are correctness
checks, not performance evidence.

Full-source compiled verification completed successfully in session **84178**.
The pooled candidate uses 52,653 rows, 60 feature columns and 23,426 unconstrained
gradient parameters. At three checked points, maximum full/reference-versus-
compressed discrepancies are **1.46e-11 in log density** and **7.57e-10 in any
gradient component**. Every checked value is finite. Current implementation hashes
still match the proof.

The artifact is `data/model/chelsea-pooled-floor-elevator-graph-parity-20260919`;
log `/tmp/chelsea-pooled-floor-elevator-graph.log`. Compilation and first invocation
are separated from warm evaluations. This proves numerical equivalence at the
checked points; it is not posterior evidence or a sampling-speed comparison.
No new sampler has been launched. The main model and its live reporting dependencies
remain unchanged; complete the source-refit comparison before the next model fit.
