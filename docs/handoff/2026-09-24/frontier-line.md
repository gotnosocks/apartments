# Hand-off: GPU-frontier line (rentfrontier), 2026-09-24

Branch `worktree-bridge-cse_01K9cq84WLoAug2oWhaHJ425`, head `1beabab`. It is being
integrated through PR #8 (`leaderboard/unified-board`).

## (a) Goals and how they changed

- **Original brief:** build a better interpretable model of NYC asking rents from scratch,
  using GPU compute. Priorities in order: held-out ΔELPD, then interpretability (named dollar
  contributions, residuals, uncertainty), then speed and cost.
- **Changes along the way:**
  - Ben: don't write our own sampler before surveying the libraries. Done; the libraries
    failed on this model, so a custom sampler was justified afterwards.
  - "The goal is a better model that uses GPU, not a from-scratch search."
  - Start simple and hill-climb.
  - Modal budget: $25, then unlimited but reasonable, then (2026-09-24) Modal stopped, local
    compute only, experiments paused.
  - Primary axis: the row split (Ben predicts listings of in-fit units). The unit split is secondary.
  - Work now lands on master through PRs.

## (b) Model design, m0 → m8

All designs: log rent with Student-t noise, 44 base features, a month or quarterly trend,
season, building effects and unit effects. Paired ΔELPD vs the promoted model
(rows / units) for gate-passing runs:

| Design | Adds | Rows / units | Status |
|---|---|---|---|
| m0 | base | −827 / −282 | pass |
| m1 | per-building half-year walk | +70 / +137 | pass |
| m5 | per-building bedroom slope, estimated ν (≈2), quarterly curves | +272 / +502 | pass |
| m6 | per-building slopes on size and 2/3 baths | +400 / +766 | **fails the all-effects gate** (110 W 26th bimodal) |
| m7 | Student-t unit effects | +570 / +827 | pass |
| **m8 + desc-v1** | per-unit linear drift; own-ad description flags | **+602 / +933** | **current best** (`b7c196f`) |

- **Ablations** (vs m5): the bedroom slope is worth −191 rows / −347 units if removed; fixing
  ν at 5 costs −47 / −174; the bedroom curves only −16 / −18.
- **Description flags:** about +120–130 on units, ≈0 on rows.
- **Model Improvement reproduced m6 under NUTS:** +388 / +756.
- **Ruled out:**
  - BlackJAX ChEES/MEADS many-chain HMC: never mixed, R-hat 8–16;
  - Laplace/INLA: dense Hessians;
  - monthly bedroom curves: the same as quarterly at 2× the cost.

## (c) Evaluation contract

- **Splits** (seed 20260922): rows, 5,264 held-out rows of repeat units; units, 5,226 rows
  of about 10% of units. They reproduce the reference row sets exactly. Code:
  `frontier/src/rentfrontier/splits.py`.
- **References:** per-row `heldout.npz` files in
  `data/model/feature-screen-20260923/nuts-hwalk{,-units}/`. Pair on audit_id; differing row
  sets are refused.
- **Gate:** split R-hat < 1.01 and bulk ESS > 400 on scalars and traced effects, **plus**
  R-hat < 1.05 over every element of every effect (all buildings, walks, slopes, units),
  from per-chain moments.
- **Ranking:** by the row split; within 2 paired SE, the unit split decides.

## (d) Infrastructure

- **Package** `frontier/` (own pyproject and lock):
  - `data.py` (loader with parquet cache), `splits.py`, `features.py` (base-v1, desc-v1);
  - `model.py`: NumPyro model, the exact target;
  - `gibbs.py`: the sampler;
  - `collect.py`: on-device held-out lpd, moments, traces, kept draws;
  - `run.py`: provenance, dirty-tree refusal, diagnostics, scoring;
  - `leaderboard.py`, `compare.py`, `explain.py` (LMDI dollar contributions);
  - `scripts/modal_run.py`.
- **Sampler:** structured blocked Gibbs in JAX float64. Each iteration:
  - draws all latents jointly and exactly: units integrated out, building blocks by batched
    Cholesky, then a global Schur solve;
  - updates the scales by collapsed Metropolis, with warmup-tuned steps;
  - handles the Student-t noise and units as scale mixtures, with a per-unit mode hop.
  Tests: dense-solve, dense marginal-likelihood, quadrature-vs-SciPy and Gibbs-vs-NUTS agreement.
- **Runs:** `/data1/apartments/frontier/runs/<name>/` holds result.json, heldout.npz and
  posterior.npz. Tags `frontier-*` mark reported commits.
- **Hardware:** H100 m8 fit ≈ 50 min, ≈ $4. The promoted NUTS fit takes ≈ 6 h on CPU.
  Total Modal ≈ $78 billed; ≈ $134 by run-record estimates, since billing lags.
  The local RTX 2060 is poor at float64 and was never benchmarked for m8.

## (e) Open problems and the next 3 experiments

- The tdrift half of the sampler-agreement diagnostic is pending. The walk half is resolved:
  the centred NUTS reference was biased.
- The m8 unit-split rescore with exact unseen-unit quadrature (commit `ad49968`) was stopped
  when Modal was withdrawn.
- **Next experiments:**
  1. m8 + desc on local compute, to learn the real local cost.
  2. m9: floor features (expanded-floor sidecar) and a free first walk knot. The 2010 +4%
     bias sits at the pinned walk start.
  3. Port t-units and drift to the PyMC line only once NUTS can mix unit-level bimodality;
     otherwise serve frontier fits in the app.

## (f) Lessons and pitfalls

- A gate on a sample of group effects misses single-building bimodality. Check every element.
- A centred NUTS reference can be the biased one near zero scales, without divergences.
  Compare against a non-centred run.
- Heavy tails in two places (unit and row) create per-unit bimodality. It needs a
  mode-hopping move.
- `ruff format` only your own paths: once it reformatted 76 shared scripts (caught before commit).
- `/tmp` is a small shared tmpfs; keep TMPDIR under /data1.
- Stop Modal apps remotely: `modal app stop --yes <id>`.
- `modal billing report` lags by hours.
- Never rebase cited commits; squash merges need `archive/*` tags.

## (g) Key paths

- Reports: `docs/model/gpu-frontier/report-2026-09-2{3,4}.md`, `prior-art-2026-09-23.md`,
  `candidates-2026-09-23.md`.
- Board: `docs/model/leaderboard/` (after PR #8).
- Code: `frontier/src/rentfrontier/`; tests: `frontier/tests/test_gibbs.py`.
- Logs: `/data1/apartments/frontier/logs/`; stopped runs:
  `runs/m8-drift-*-units-ad49968/stopped.json`.
