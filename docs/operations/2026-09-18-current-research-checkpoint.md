# Current research checkpoint, 22:05 EDT

## Superseding update, 22:34 EDT

The earlier floor process is terminal. It completed sampling, export, both large
diagnostic passes and ordinary reports, then exited **1** on a floor-report
coordinate-name collision. The three-name reporting fix and a real-diagnostics
regression test are saved. Report-only recovery completed at **02:24:00 UTC**,
without resampling or altering preserved products; the floor fit is now verified
`exploratory_converged`. The matched comparison is complete in
`data/model/chelsea-bayesian-floor-sensitivity-20260918`. See
[the results and recovery record](../analysis/chelsea-bayesian-floor-increments-2026-09-18.md).

**New active job:** host PID **479023**, tool session **84907**, verified live at
**02:34:09 UTC**. It is compiling the disk sampler for the **52,863-row / 172-current**
reviewed cohort. No result is claimed yet.

- Experiment: `data/model/chelsea-bayesian-current-floor-disk-20260918`
- Source: `data/model/chelsea-reviewed-current-analysis-20260918`
- Readiness: `data/model/chelsea-current-floor-fit-readiness-20260918`
- Protocol SHA: `aec28bb8eb83f8435d2907a8f5df41f0fe07aeb803c5bb708fbdf7aa1246c8ff`
- Graph proof: `data/model/chelsea-current-floor-graph-parity-20260918`
- Log: `/tmp/chelsea-current-floor-fit.log`
- Resources: `/tmp/chelsea-current-floor-fit-resources.log`
- Four chains, 4,000 warmup / 6,000 retained, seed 20260924, target acceptance
  0.93, diagonal adaptation, shared Student-t noise, v4 floor increments with
  scale 0.15. This is an expanded-cohort fit, not a matched source-only comparison.

Do not modify the new protocol's bound mathematical/runner/report-cache files
while the process is live. Verify its actual PID/session before acting. The new
graph proof passes at three points over 23,462 gradient coordinates: maximum
absolute density/gradient differences **4.37e-11 / 1.16e-9**. Warm compressed
gradient evaluation is 0.876 ms versus 7.053 ms for the reference in this check.
An initial proof attempt failed writing a read-only home compiler cache; the
successful proof used writable `/tmp` compiler caches. The fit's exact cache
environment is frozen in its launch script.

Additional saved changes:

- `49bd9fdb`: refreshed literal description archive, exact reader binding and
  complete capture coverage. Publication/replay pass; 48 evidence/page tests pass.
  Artifact: `chelsea-refreshed-bayesian-descriptions-20260918`, covering 72,065
  captures / 52,863 observations / 172 current captures.
- `061a5f24`: optional verified description archive in main-model selection; page
  follows the selected archive. Sixteen selection/page tests plus the new archive
  default test pass. The existing main selection remains unchanged.
- `892d84da`: `fit-pricing` defaults to durable disk execution and bounded reports;
  explicit `--execution memory` preserves old replay, and `--floor-increments`
  selects v4. Thirty-one CLI tests and actual help output pass.
- `a2ec9fd6`: completed floor fit recovery/comparison. Seventy-five focused checks
  pass, including the new actual floor-diagnostics regression.
- `45253974`: v3/v4 loader and report reader accept reviewed current refreshes,
  continuing to reject the unreviewed refresh version. 149 focused tests pass.

After the active fit completes, verify every diagnostic gate and the new
172-current residual/contribution workflow before selecting a main fit. Selection
can bind the matching description archive with `--evidence`. Floor coefficients
remain sparse and most intervals include zero; the earlier matched comparison
does not justify interpreting the two upper-floor standouts as physical premiums.
The model simplification, source-feature validation, group-prior sensitivity and
Bayesian preference/frontier integration work in `docs/TODO.md` remains active.

The remainder of this file is the earlier checkpoint, retained as history.

The main model selection remains unchanged. The active Chelsea modeling goal is
unfinished; the latest user research directions are tracked in `docs/TODO.md`.

## Live floor fit

At **02:05:17 UTC September 19** (September 18 locally), host process **464334**
is live in diagnostics/reporting. Sampling and posterior export have completed.
The process has about 1.6 GiB resident memory at this check; that is not a final
peak-memory measurement. The report-cache completion marker exists. Parameter
and derived diagnostics and the final fit manifest are still pending.

- Experiment: `data/model/chelsea-bayesian-floor-increments-disk-20260918`
- Readiness: `data/model/chelsea-floor-disk-readiness-20260918-v2`
- Protocol SHA: `0bec75ab2693b5089bb1f4604ed8aca8b44bf32141a4955f8da0e75a74d2b22f`
- Log: `/tmp/chelsea-floor-disk-fit.log`
- Resources: `/tmp/chelsea-floor-disk-resources.log`
- Original tool session: `10581`; a lost session handle is not evidence of failure.

Do not modify the bound runner, graph/design, reporting-cache or mathematical
dependencies until this process exits. Verify its actual state before resuming;
do not restart based on elapsed time. After completion, check all diagnostic
gates and run `models.bayesian_floor_sensitivity` against
`chelsea-bayesian-source-shared-disk-long-20260918` on
`chelsea-reviewed-scope-composition-projection-20260918`, with single-thread BLAS.
The latter source fit and its matched source comparison are complete and verified.

## Completed independent work

- `e277ab35`: joint-posterior decomposition of the three largest source-refit
  movements. All six case diagnostic checks pass; five tests pass. The largest
  movement is primarily a weak single-observation building effect. See
  [the review](../analysis/chelsea-source-movement-review-2026-09-18.md).
- `5dc72ab8`: reviewed refreshed cohort, source-bound policy and deterministic
  overlay. Publication and identical replay pass; 29 focused tests pass. The
  unchanged model bathroom encoder sees exactly 170 known and two masked current
  compositions, advertisements 5124842 and 5116119.
- `d5ca1ec2`: floor/elevator support audit, four tests passing. Explicit-floor
  thresholds 2–5 have both groups on both sides; 13 higher-floor interaction
  products duplicate main-effect columns. Source elevator claims vary in 43
  buildings. No interaction fitted or inferred floor integrated.
- `3cd1327e`: laundry evidence policy for the later four-level experiment.
  Existing in-unit versus in-building contrast is +2.399% [2.051%, 2.741%];
  explicit none/on-floor levels remain untested. Spatial candidates already
  exist for 172 current listings / 85 buildings; no spatial fit yet.

The new reviewed input is
`data/model/chelsea-reviewed-current-analysis-20260918`, version
`reviewed-capture-refreshed-analysis-v1`: **52,863 rows / 22,189 units /
1,131 buildings / 172 current rows**. Historical rows are unchanged; prices,
reported counts and cohort membership are preserved. Seven current rows retain
explicit residual-review tags. This is a limited source review for exploratory
fitting, not a certification of all attributes.

After the matched floor comparison, integrate that new dataset version into the
v3/v4 loader and verified report reader, with tests. Original and unreviewed
refresh versions must remain distinct. The expanded cohort needs its own graph
readiness/proof, PyMC fit and verified analysis. The description-evidence loader
also needs an explicit refreshed-cohort lineage path before updating the main
page's evidence attachment; do not pretend the older 13-current archive covers
all 172 current listings. No main-model promotion has occurred.

Use `uv run --frozen --no-sync python` with `UV_CACHE_DIR=/tmp/apartments-uv-cache`,
`MPLCONFIGDIR=/tmp/apartments-mpl`, `OPENBLAS_NUM_THREADS=1` and `OMP_NUM_THREADS=1`.
Large caches belong on the workspace disk, not `/tmp` tmpfs. No new scraping was
performed in this work; all source review used verified captured evidence.
