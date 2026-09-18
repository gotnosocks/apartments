# Bedroom-dependent residual scale research

The accepted shared-scale Bayesian model understates residual dispersion in
larger apartments. Conditional posterior checks on the same fitted observations
show a three-bedroom mean absolute log residual of about 0.086, against about
0.063 in replicated data. This motivates allowing observation noise to vary by
bedroom count while preserving the mean specification and source cohort.

The first experiment, `data/model/chelsea-bayesian-bedroom-noise-20260918`, finished
on September 18 at 21:58:53 UTC. It used 52,711 observations, four chains, 2,000
warmup iterations and 4,000 retained draws per chain. It is **diagnostic-only**:
maximum parameter R-hat was 1.01464, with five parameters above 1.01; minimum
bulk effective sample size was 268. There were no divergences or maximum-depth
events. Derived contrasts passed their gate, but that does not override the
failed parameter gate. Its intervals and comparisons are withheld.

The slow mixing concentrates in the new residual-scale hierarchy. The first fit
expresses bedroom-specific scale as `sigma * exp(tau * z)`, with a zero-sum
standard-normal vector `z` and a half-normal prior of scale 0.3 for `tau`.
The next computational experiment samples the zero-sum offset directly with
standard deviation `tau`. This is intended to preserve the prior and likelihood,
not change the statistical model. Equivalence requires the `(K - 1) * log(tau)`
change-of-variables term on the K-level zero-sum subspace, matching row likelihoods
and gradients. A retry must have a new frozen code/protocol artifact and pass
the same diagnostic thresholds before interpretation.

The equivalent centered implementation now passes 138 focused tests. Its
immutable proof, `data/model/chelsea-bayesian-centered-residual-proof-20260918`,
checks nine parameter points across three hierarchy scales on a six-bedroom-level
fixture. Maximum adjusted log-density error is 3.02e-14 and maximum gradient
chain-rule error is 5.33e-15; row likelihoods and bedroom scales agree exactly.
The separate `data/model/chelsea-bayesian-v3-centered-shared-parity-20260918`
rebuilds the full 52,711-row design and finds exactly zero shared-mode log-density
and gradient differences at three parameter points. These computational checks
do not establish convergence of a new sampling run. The explicit noncentered
option and its frozen failed artifact remain available.

The complete regression suite then passed 1,316 tests with two skips and nine
warnings. The centered retry was launched under
`data/model/chelsea-bayesian-bedroom-noise-centered-20260918`, with the same
52,711-row cohort, four chains, 2,000 warmup iterations, 4,000 retained draws per
chain and seed 20260920. It is running; no accepted result is claimed. Its
`progress.json` records the live phase, and final acceptance requires both
parameter and derived-quantity gates.

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  MPLCONFIGDIR=/tmp/apartments-matplotlib NUMBA_CACHE_DIR=/tmp/apartments-numba \
  PYTENSOR_FLAGS='cxx=,compiledir=/tmp/apartments-pytensor,numba__cache=False' \
  .venv/bin/python -m models.bayesian_feature_experiment_v3 \
  --dataset data/model/chelsea-reviewed-bathroom-projection-20260918 \
  --output data/model/chelsea-bayesian-bedroom-noise-centered-20260918 \
  --spec full_half_balance --chains 4 --tune 2000 --draws 4000 \
  --seed 20260920 --adaptation diag --residual-scale bedroom \
  --residual-parameterization centered \
  --graph-validation data/model/chelsea-bayesian-v3-centered-shared-parity-20260918
```

The v3 posterior checker was also run on the accepted shared-scale fit:
`data/model/chelsea-bayesian-shared-posterior-checks-20260918-v3`. Its selected
draws, cohort, slices and omitted slices exactly reproduce the corrected v2
checker. The exact comparisons are recorded in
`data/model/chelsea-bayesian-shared-checker-parity-20260918` with verified input
manifests and the frozen comparison script. The original unsafe saved-design
reload remains excluded. These are
conditional in-sample likelihood checks, not held-out prediction or evidence
that a large residual establishes a source error.
