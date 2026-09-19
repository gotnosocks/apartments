# Expanded advertised-floor measurement experiment

This experiment tests whether source-bound unit-label floors add useful,
interpretable floor contributions and explain building/unit residual structure.
It keeps the analytical observations, asking prices, non-floor attributes,
time construction and group priors fixed. The Thomas Eddy bedroom correction
is recorded separately and is not mixed into this floor comparison.

The reference is `chelsea-bayesian-reviewed-elevator-disk-20260919`, fitted on
`chelsea-reviewed-elevator-analysis-20260919`. The candidate source is
`chelsea-label-floor-analysis-20260919`. Original source fields, label-derived
candidates, inference decisions and exact capture provenance remain separate.
The inference's knowledge date is not a physical renovation date.

The measurement reads each own capture's structured `displayUnit`, accepts a
positive one- or two-digit prefix followed by one letter, and requires agreement
across that observation's captures. Explicit floors take precedence. Inference
is withheld in the 18 buildings from the earlier numbering-conflict review.
Candidates above any captured building `floorCount` are withheld; two-digit
candidates also require a known building count. This is a conservative
compatibility check, not a conversion from physical stories to advertised labels:
valid labels in buildings that skip numbers may remain unknown.

The floor term remains cumulative observed-level increments:

`floor_effect(F) = sum_k beta_k * 1(F > k)`

Unknown floors have a separate indicator. Adjacent increments have independent
Normal(0, 0.15) log-rent priors and unconstrained signs. Adding supported floor
levels increases the cumulative prior variance over the full range; report that
range prior and avoid interpreting unsupported individual intermediate levels.

First fit the expanded floors with the existing v4 specification. Then test the
existing pooled floor/elevator interaction on the same expanded dataset. That
interaction covers label changes 2→5 and saturates above 5; it does not establish
a distinct elevator premium at every high floor. Testing wider or separate
interactions requires a separately documented support check and comparison.

Use PyMC with the exact compressed graph, nutpie/Numba and durable posterior
storage: four chains, 4,000 warmup and 6,000 retained draws per chain, target
acceptance 0.93, diagonal adaptation, seed 20260924. These match the reference.
Verify compiled log-density and gradient parity before fitting. These are model
experiments, not a new sampler speed benchmark.

Evaluate:

- Sampling diagnostics for parameters and joint floor contrasts: R-hat below
  1.01, bulk/tail ESS at least 400, divergences, tree-depth saturation and BFMI.
- Posterior floor increments, joint cumulative contrasts and uncertainty,
  including sparse endpoint support and sensitivity to building/unit offsets.
- Residual changes on all observations, captured ACTIVE listings, newly inferred
  floors, previously explicit floors, and still-unknown floors. These are
  in-sample diagnostic comparisons, not independent predictive accuracy.
- Largest distinct unit residual movements and building/unit offset movements,
  followed by source review for bad numbering or other omitted attributes.
- The fixed eight-case development panel as a regression check, separately
  from any newly selected residual outliers.

A smaller residual alone does not earn the feature a place in the main model.
The decision must consider source plausibility, posterior stability, uncertainty
and whether floor effects are interpretable with the available building overlap.
Keep the selected main fit explicit until these checks are complete.
