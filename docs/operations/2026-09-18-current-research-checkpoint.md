# Current research checkpoint, 22:05 EDT

## September 19: main analysis now uses the 172-current fit with source reviews

Concrete progress: `config/main-analysis.json` now selects
`chelsea-bayesian-current-floor-disk-20260918` / `chelsea-reviewed-current-analysis-20260918`,
the matching refreshed description archive, and
`chelsea-current-residual-source-review-20260918`. Fit manifest SHA is
`60317e391939d509a24776c75b59c957588aed93e5b5d9278cf7e57ff13c6191`.
Selection equals the staged, tested candidate byte-for-value and input observation
checksum is unchanged. Selection command **14932** exited 0.

New `apartments.bayesian_source_review.load_source_review` verifies fit/source/
description manifest hashes, source records, saved residual values and literal
capture identities. Optional source-review selection requires its matching
archive. Page displays eight review labels, explanations and persistent conflict
warnings around bedroom scenarios. Bad review binding stops the page; no silent
fallback. Source counts, prices and model parameters are unchanged.

29 focused loader/selection/page tests pass. Real-data staged AppTest **8878**
exited 0, with **no model/evidence mocks**, validating 172 current rows, eight
notes, conflict warning and the $3,665 one-bedroom scenario. Artifact:
`chelsea-current-main-page-validation-20260919`. Its script is in
`docs/analysis/scripts/check_current_main_page.py`. The second actual selected-page
test **26175** exited 0: **1 passed in 71.30 seconds**, exercising a laundry
comparison and historical navigation (`/tmp/chelsea-selected-main-actual-test.log`).
The old hard-coded 13-row test expectation now follows the selected
cohort and table limit.

`docs/model/analysis-review-page.md` was outdated and described the prior portable
surrogate; it now documents the actual selected PyMC workflow. The later 17-floor
and one-laundry corrections remain unfitted and unsupported by frozen loaders.
GPU **30289 / PID 494915** is still running on its original frozen data/model,
last seen around 3,895/4,000 warmup. Sampler source/graph files remain unchanged.
Continue the full benchmark; no fastest-backend conclusion yet.

## September 19: current fit complete; current residual source review complete

**CPU continuation session 80187 is terminal, exit 0.** The recovered fit completed
at 03:53:23 UTC with status `exploratory_converged`; no resampling. All parameter,
derived-unit/bathroom and joint-floor gates pass. Max R-hat values are 1.00593,
1.00541 and 1.00211; minimum bulk ESS 905, 1,245 and 1,795; minimum tail ESS
1,617, 2,132 and 3,506. Zero divergences/depth hits, minimum BFMI 0.4373.
Full report verification/publication **71317** also exited 0:
`chelsea-bayesian-current-floor-review-20260918`.

The 172 current rows have median absolute log residual 0.02458 and median
absolute percent residual 2.48%; four differ by more than 10%. These are fitted
residuals, with current asks participating in the fit, not predictive accuracy.

Actual joint-posterior/source review **98610** exited 0 and published
`chelsea-current-residual-source-review-20260918`. All eight leading absolute
current residuals have literal source evidence and passing contribution
diagnostics. Biggest case **5155021 / 251 West 26th #2B**: own captured payload
has bedroomCount=0, roomCount=1, while description explicitly advertises one
bedroom. Parser agrees with structured source. No floor plan/video; photos are
said to show the same line. Do not infer the true count from model agreement.
Its zero-to-one-bedroom conditional scenario passes diagnostics: modeled median
$2,885 → $3,665, delta $780 [725,847], +27.03% [26.52%,27.54%]. Area unknown;
bedroom-specific reference-area encoding changes interpretation. Offsets remain
fixed; no refit or source correction.

A broader literal-count screen across all 172 current descriptions is published
in `chelsea-current-bedroom-claim-review-20260918`: 20 candidate rows manually
classified (13 building inventory, two fractional marketing/inventory, two
denied conversions, one alternative layout, one flex/alcove, one unresolved
count conflict). It preserves decimal 1.5 wording and is not exhaustive accuracy
validation. Source-count mismatch at 5155021 is newly identified; price/counts
remain unchanged. The other leading cases motivate explicit floor/renovation,
private terrace/elevator, loft and total-recurring-cost research.

Research scripts are saved in `docs/analysis/scripts/` and frozen in their output
artifacts. Results: `docs/analysis/chelsea-current-fit-and-residual-review-2026-09-19.md`.
The initial /tmp script launch failed to import `models`; the successful run used
`PYTHONPATH=/home/ben/code/apartments`. No scraping occurred.

**GPU session 30289 / PID 494915 is still live**, most recently around 1,564 of
4,000 warmup. Retained-sampling and speed comparison remain pending. Do not
restart it. Shared sampler/model source files remain bound to its protocol.
Main selection still points to the older fit. Next integrate/source-surface the
new current review, especially the ambiguous-bedroom case, before presenting
the newer fit as the main apartment analysis. The later floor/laundry revision
also needs loader/evidence integration and fitting. The source correction and
fit completion are progress, not a status-only goal turn.

## Follow-up: floor review applied to a new analytical revision

This continuation made concrete progress after revalidating both running jobs.
`models/reviewed_floor_revision.py` projects all 17 withheld claims through
`config/reviews/chelsea-floor-masks-20260918.jsonl`, with exact source-row targets
and separate review/correction clocks. The last ledger record is
2026-09-19T03:47:57.591531+00:00. All 37 review targets match their original rows
in the latest parent revision. The 20 retained source claims are unchanged.

Published/replayed: `chelsea-reviewed-floor-masked-analysis-20260918`, version
`reviewed-floor-conflict-projection-v1`, with parent
`chelsea-reviewed-laundry-negation-analysis-20260918`. Independent full comparison
in `chelsea-reviewed-floor-mask-verification-20260918` confirms 52,863 rows,
17 masked historical floor values, every other data field and prior review
history preserved, all 172 current rows unchanged, raw current evidence unchanged.
The actual model encoder reports 366 known floors before / 349 after. Thirteen
focused tests pass, including real ledger/replay and no propagation across other
observations of the same unit. Loader/evidence integration and fitting remain
pending; running model/benchmark inputs and bound source files are unchanged.

CPU **80187 / PID 497474** remains live in diagnostics/reporting. Its parameter
diagnostics passed at 03:44:48 UTC: max R-hat 1.00593, min bulk ESS 904.92, min
tail ESS 1617.18, zero divergences/depth hits, min BFMI 0.4373. Derived/floor
diagnostics and final manifest are still pending; do not promote the fit yet.
GPU **30289 / PID 494915** remains live; latest log around 752/4,000 warmup.
No GPU retained speed or backend ranking is available. Logs/commands remain as
recorded below. Main selection is unchanged.

## Follow-up: shared efficiency diagnostics prepared

The preceding goal turn made concrete progress (recovery, reviewed data and
production benchmarking), not a status-only wait. This continuation revalidated
both live sessions **80187** (CPU reports) and **30289** (GPU benchmark), then added
`models/sampler_efficiency.py`. It requires a completed hash-bound GPU posterior,
verifies original source/design/code, and reuses the CPU parameter, derived
unit/bathroom and joint-floor diagnostic gates. Rate tables distinguish compute,
storage, warmup and complete PyMC/write timing scopes. The command is documented
in the sampler reassessment; run it only after `sampled.json` is published.

Eleven focused timing/statistics tests pass. Actual verified CPU counters now
produce archived retained-time brackets in
`chelsea-nutpie-retained-time-brackets-20260918`. These are per-chain intervals,
not a denominator for pooled ESS. No backend ranking is established. At the last
log check GPU warmup had reached about 330/4,000; the CPU remains in diagnostics
and reports. Continue independent source/model work while they run; neither run
has been restarted. Main selection and frozen analytical/model files are unchanged.

## Superseding update, 23:37 EDT

Checkpoint **9e30dc36** saved the review, ledger revision, tested recovery and
production benchmark code. The original CPU process **479023 / session 84907**
is now terminal (exit 1 after deliberate interrupt of its stalled reader).
Recovery preparation **74774** and installation **88477** both exited 0.
All 24,000 retained posterior draws were exported with finite-value validation,
and the full raw inventory matched before/after export and again at installation.
The old process was stopped only after preparation passed. No samples were rerun.

**Current CPU continuation:** host PID **497474**, tool session **80187**, log
`/tmp/chelsea-current-floor-fit-host-report.log`. It uses the unchanged frozen
launch command and verified posterior checkpoint. At 03:36:41 UTC it had reached
the design/reload phase. Reports and final diagnostics remain pending. Run it
on the host; sandbox synchronous Zarr opening is known to stall here.

**GPU continuation:** PID **494915**, session **30289** remains live, full-model
4,000/6,000 with retained batches of 500. At the last check it was around
159/4,000 warmup; no retained speed or convergence result is available. Preserve
this run rather than restarting from elapsed time. Earlier failed GPU log is
now copied into its own artifact with explicit failure metadata.

The nutpie CPU log supplies a meaningful steady retained baseline:
17,757 draws across four chains over 480.066 seconds, **36.99 aggregate draws/sec**
(9.25/chain/sec), excluding startup/warmup/final trace opening. All four chains
contribute over 4,400 draws in this window. Artifact
`chelsea-nutpie-steady-throughput-20260918` preserves source counters; this is
raw throughput, not ESS/sec or a fastest-backend conclusion.

Floor review replay **62943** exited 0 and is identical. All 93 focused
source/recovery/storage tests and both isolated NumPyro lifecycle tests pass.
The previous update remains useful for code/artifact paths and GPU environment.

## Superseding update, 23:33 EDT

Latest user correction: 50 warmup / 50 retained draws cannot rank backend speed.
The historical Modal document now explicitly withdraws that inference. The full
GPU benchmark uses the exact 52,863-row PyMC model, four chains and 4,000/6,000.
No fastest-backend claim is established. See the sampler reassessment document.

Live jobs (verify actual state before taking action):

- Original CPU fit: session **84907**, host PID **479023**. All four chains
  finished sampling by 02:54:09 UTC, zero reported divergences. It is stuck in
  synchronous trace opening, not sampling. A read-only host probe opens the same
  trace immediately and verifies four-by-6,000 retained dimensions, coordinates
  and no warmup. Sandbox read probes stall even on opening the root group.
- Read-only recovery preparation: session **74774**, host PID **494789**,
  `/tmp/chelsea-current-floor-trace-recovery.log`, artifact
  `data/model/chelsea-current-floor-trace-recovery-20260918`. It exports every
  posterior value in bounded slabs and checks the raw inventory before/after.
  Preparation leaves the original untouched. Only after preparation succeeds,
  release/stop the original stalled reader, verify terminal state, and install
  the checkpoint under its exclusive run lock. Then resume the original frozen
  command **on the host**, without resampling. Its launch script is in the
  readiness artifact. Main-model selection remains unchanged.
- GPU batched benchmark: session **30289**, host PID **494915**,
  `/tmp/chelsea-numpyro-gpu-batched-benchmark.log`, artifact
  `data/model/chelsea-numpyro-gpu-batched-benchmark-20260918`. Warmup is live; GPU
  use was 922 MiB and 99%. No sampling-speed or convergence result yet. The first
  unbatched GPU run (session 75174) exited 1 with a recorded memory failure;
  preserve its protocol/log. Do not confuse it with the live revised run.

New source work completed:

- All 37 label-floor disagreement observations / 29 units / 57 captures reviewed
  personally against literal source descriptions. Twenty explicit claims retained,
  two media-only claims and 15 unresolved contradictions withheld. Named policy,
  exact capture evidence and reasons are published. Analytical integration remains
  pending; no blanket building offset or identity merge is justified.
- One-row laundry correction published/replayed in
  `chelsea-reviewed-laundry-negation-analysis-20260918`, version
  `reviewed-laundry-negation-projection-v1`. Exact version-targeted ledger, two
  capture bindings, correction clock and before/after history; all prices,
  membership, source clocks and 172 current rows preserved. Not yet fitted or
  accepted by loaders; do not edit live protocol-bound loaders.

New execution work:

- Isolated `.venv-sampler-benchmark`, with pinned current PyMC/Numba dependencies
  plus JAX CUDA13, NumPyro and BlackJAX; production environment unchanged.
- Full-model float64 CPU/GPU logp/gradient parity passed at three points.
  Kernel medians are 2.15 ms CPU / 21.93 ms GPU under different fused/separate
  evaluation scopes; these are not sampling-speed/ESS evidence.
- NumPyro's warmup allocates retained-size buffers even with collection off.
  Revised wrapper uses one unused warmup slot and 500-draw retained batches,
  preserving adapted state/RNG and spilling all draws/statistics to host disk.
  Two lifecycle tests pass, including exact batched/unbatched draw/stat parity
  and restoration of the library class on interruption.
- 93 source/recovery/storage tests pass. Floor review replay is in progress
  (session 62943); verify its completion. Recovery installation and final CPU
  diagnostics remain pending. Original mathematical/runner files were not edited.

## Superseding update, 22:49 EDT

This continuation makes progress: the exact-capture laundry audit is complete,
a definite extraction error is fixed in `attribute-evidence-v4`, and 71 focused
tests pass. The immediately preceding user-TODO acknowledgment was a status
restatement; this round revalidated the live fit and took independent action.

The current fit remains live on **tool session 84907** (polled successfully).
At **02:48:24 UTC**, its four chains had completed 6,777–7,115 of 10,000 total
iterations apiece, including 4,000 warmup. All chains were collecting retained
draws, with zero divergences reported. Do not restart; no final diagnostics or
accepted new fit are claimed. Protocol and mathematical code remain unchanged.

New work:

- `models/laundry_source_audit.py` joins all 724 phrase-candidate captures to
  their verified literal descriptions and own structured payloads. The original
  v3 audit and corrected v4 audit both publish and replay identically.
- Artifacts: `chelsea-laundry-capture-source-audit-20260918` and
  `chelsea-laundry-capture-source-audit-v4-20260918` under `data/model/`.
- All six reviewed hookup-only cases carry their own `WASHER_DRYER` code.
  Preserve this evidence conflict/ambiguity; a regex fix cannot resolve it.
- Advertisement 4800947 (two captures, one historical observation) incorrectly
  encoded “doesn't have on-site laundry” as a positive. V4 records scoped denial;
  private laundry remains independently possible. The two scalar replay changes
  are verified, with all source/category/provenance fields unchanged across the
  724-row comparison. This is not a corpus-wide extraction validation.
- Frozen analytical rows and the running fit remain unchanged. Apply the named
  correction in the next versioned transformation; four-level laundry work is
  still pending. Results and reproduction are in
  [the source reconciliation](../analysis/chelsea-laundry-source-reconciliation-2026-09-18.md).
- The fitting protocol does not bind/import `attribute_evidence.py`; no live
  sampler, graph, design, reporting-cache or runner code was edited.

Next: complete/verify the current fit and reports, review 172-current residuals,
then select a fit only with matching source evidence. Continue reviewed laundry
measurement and apply the extraction correction as a separate source version.

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
