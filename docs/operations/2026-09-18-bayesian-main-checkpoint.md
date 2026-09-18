# Bayesian main analysis and floor audit checkpoint

The main contribution/residual UI and `fit-pricing`/`analyze-apartment` commands
now use the verified PyMC posterior. The selected baseline is explicitly bound
in `config/main-analysis.json`; no alternative fit was silently promoted.
The previous fit command and pages have explicit legacy locations.

Validation completed September 18, 2026:

- Full suite: **1,471 passed, 3 skipped, 9 warnings**, 334.42 seconds, exit 0.
  The skips include optional environment/large-artifact tests; actual 13-current
  posterior reconstruction and the real main-page workflow were separately run.
- Main backend: all 13 current fitted intervals reproduced from 16,000 joint
  draws within $1.4e-11; all 13 contribution diagnostic gates passed. Artifact:
  `chelsea-main-bayesian-analysis-verification-20260918-v2`.
- Main UI: eight AppTests, including real current-listing analysis and a laundry
  comparison. Artifact: `chelsea-main-bayesian-page-check-20260918`.
- Floor design/publisher: 31 focused tests and identical full-cohort publication
  replay. Artifact: `chelsea-listed-floor-increment-design-20260918`, manifest
  `e14e71fd7f654391d1ea7e6a4bd2cd8ead0067f619109680d602b0e077904b8c`.
- `uv build --wheel` succeeded; the wheel contains the main backend and `models`
  modules. `threadpoolctl` is explicit in the model extra and uv lockfile.
- `git diff --check` passed. Changed source files were checked against credential
  values without printing them; no matches. Data artifacts and `.env` stay ignored.

Commands use uv. This sandbox uses `UV_CACHE_DIR=/tmp/apartments-uv-cache` because
the default cache is read-only. Research verification uses `--frozen --no-sync`
to retain the installed, recorded inference environment. The dependency lock
was updated with `uv lock` for the explicit threading dependency.

The full-suite invocation was:

```sh
MPLCONFIGDIR=/tmp/apartments-matplotlib \
PYTENSOR_FLAGS='cxx=,compiledir=/tmp/apartments-pytensor-tests,numba__cache=False' \
NUMBA_CACHE_DIR=/tmp/apartments-numba-tests OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
UV_CACHE_DIR=/tmp/apartments-uv-cache timeout 500 \
  uv run --frozen --no-sync python -m pytest -q
```

The [parameter audit](../analysis/chelsea-bayesian-parameter-audit-2026-09-18.md)
and floor-threshold construction are research groundwork. No new floor posterior
exists yet. The centered bedroom-noise fit passed both gates; its comparison
improves larger-bedroom dispersion checks but leaves tail mismatch. The matched
source-cleaned shared-scale fit is still running at this checkpoint. Main-model
selection, floor specification fits, broader simplification experiments and
Bayesian preference-frontier integration remain separate pending work.
