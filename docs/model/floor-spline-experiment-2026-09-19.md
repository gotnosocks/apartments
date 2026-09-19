# Regularized spline for advertised floor

This replaces the expanded model's 51 independent floor increments while
retaining its complete, reviewed floor extraction. The cohort is unchanged:
52,653 observations, 22,155 units, 1,129 buildings, and 29,907 known-floor rows.
The source remains `chelsea-label-floor-analysis-20260919`; observations,
prices, missingness, nonfloor features and priors, time effects, and building/unit
hierarchies are fixed for the comparison.

For this cohort, the natural cubic spline has knots at listed floors
1, 5, 10, 20, 35 and 52. The endpoint knots follow the observed range; the four
interior labels were specified before fitting. Six zero-sum knot heights have
five independent orthonormal contrast coordinates, each with Normal(0, 0.10)
prior. Subtracting the curve's value at floor 2 defines the reported reference.
There is no monotonicity constraint or new learned smoothness scale.

In notation, with Q an orthonormal basis perpendicular to the six-vector of
ones, h = Qθ, θ ~ Normal(0, 0.10² I), and S the natural cubic interpolant of
knot heights h:

    floor contribution(f) = S(f) − S(2)

Unknown floor has zero raw spline coordinates and the existing separate
Normal(0, 0.20) missingness coefficient. The complete feature matrix is centered
as before. Its 47 columns replace 93 columns in the independent-increment fit;
all 41 nonfloor columns are byte-for-byte unchanged in the design tests.
Interpolation inside the observed range is allowed; extrapolation is rejected.
Floor labels remain advertised-floor proxies, not measured physical height.

The knot-height prior gives any two distinct knot heights a difference with
standard deviation sqrt(2)×0.10, independent of how many intermediate labels are
observed. Relative to floor 2, the floor-52 central 95% prior interval is
approximately −22.0% to +28.3%, versus the old accumulation of independent
per-floor priors. The spline shares information across floors and cannot
represent a separate arbitrary jump at every label. Its intervals remain
conditional on this chosen smoothness, prior, and the other model assumptions.

## Validation and execution

52 focused design/experiment tests cover nonfloor invariance, boundary and
continuity conditions, floor-2 anchoring, priors, unknowns, range limits,
reconstruction and joint posterior contrasts. Reader regression checks also
preserve older fitted artifacts and expose the new floor counterfactuals.

Full-cohort direct versus compressed PyMC density/gradient verification passed
at three parameter points in
`data/model/chelsea-spline-floor-graph-parity-20260919`. Maximum absolute
log-density discrepancy was 1.46e-11; maximum gradient discrepancy was 2.39e-9.
These are numerical equivalence checks, not sampling-speed measurements.

Experiment: `data/model/chelsea-bayesian-spline-floor-disk-20260919`.
The first sampling progress record was 2026-09-19 21:18:52 UTC. It uses PyMC via
nutpie/Numba, four chains, 4,000 warmup and 6,000 retained draws per chain,
diagonal adaptation, target acceptance 0.93 and seed 20260924. The tree-depth
ceiling is 10, restoring the original ceiling rather than carrying over 14.
All retained draws and the raw warmup trace are stored, and the existing
convergence gates apply to parameters and joint floor contrasts.

```bash
UV_CACHE_DIR=/tmp/apartments-uv-cache MPLCONFIGDIR=/tmp/apartments-mpl \
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
uv run --frozen --no-sync python -m models.bayesian_floor_spline_experiment \
  --dataset data/model/chelsea-label-floor-analysis-20260919 \
  --output data/model/chelsea-bayesian-spline-floor-disk-20260919 \
  --floor-prior-scale 0.10 --maxdepth 10 \
  --chains 4 --tune 4000 --draws 6000 \
  --target-accept 0.93 --adaptation diag --seed 20260924
```

Completion, comparison, source-case review and main-model selection are pending.
The older expanded-increment/elevator run is retained as a diagnostic artifact;
it is not the replacement specification requested by the user.
