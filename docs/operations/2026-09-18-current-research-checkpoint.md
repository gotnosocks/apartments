# Current research checkpoint, 22:05 EDT

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
