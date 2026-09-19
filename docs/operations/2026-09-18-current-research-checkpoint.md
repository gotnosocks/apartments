# Current research checkpoint, 22:05 EDT

## September 19: corrected-data fit launched from isolated tested code

GPU diagnostic **session 30424 remains live**. Parameter diagnostics pass:
max R-hat **1.00174238**, minimum bulk ESS **4,037.49**, minimum tail ESS
**6,252.25**. Last phase is `derived_contribution_diagnostics`; no completed
efficiency bundle or final backend decision yet. Compared with CPU minimum bulk
ESS 904.92, this is a real reminder that raw draws/sec does not rank sampler
efficiency. Await all contribution/floor gates and the per-parameter comparison.

To progress fitting without changing that process's original code, created JJ
workspace **`corrected-fit`** at **`/tmp/apartments-corrected-fit-code`**, based on
332ab874. Saved code **`dd0e8863`**, bookmark **`codex/corrected-source-fit`**;
its working change is empty. Do not alter its model/loader files during the fit.
Root workspace model files remain unchanged until GPU diagnostics complete.
Later merge this branch into the main research bookmark; preserve root checkpoint
documentation when combining the two descendant branches.

The isolated v3 loader now accepts the two correction versions only after
`reviewed_source_lineage.source_lineage` proves exact reconstruction to the
refreshed source. Its helper is included in archived implementation hashes.
V4/disk runners inherit the verified loader. **103 tests pass** across v3, v4,
disk execution and lineage (session **61626**, exit 0). Initial tests exposed
an expected archival-file inventory update and Pandas' null-to-NaN representation;
both assertions now express the intended contracts.

New reusable `models.verify_reviewed_floor_graph` command passes on all 52,863
corrected observations, comparing compressed/uncompressed log densities and all
**23,461 gradients** at three parameter points. Largest absolute differences:
log density **4.37e-11**, gradient **7.57e-10**. Artifact:
**`data/model/chelsea-corrected-floor-graph-parity-20260919`**.
Validation session **29821 exited 0**; timings are kernel checks under concurrent
workload, not a sampling-speed benchmark.

**LIVE corrected fit: session 23268**, host execution from the isolated workspace.
Output **`data/model/chelsea-bayesian-reviewed-corrections-floor-disk-20260919`**;
log **`/tmp/chelsea-reviewed-corrections-floor-fit.log`**. Source is
`chelsea-reviewed-floor-masked-analysis-20260918`. Uses PyMC/nutpie with durable
storage, four chains, 4,000 warmup, 6,000 retained, seed 20260924, target .93,
diagonal adaptation, full_half_balance, shared Student-t scale, building/unit
prior scales .35/.25, floor-increment scale .15, and the new graph proof.
Launched with `UV_CACHE_DIR=/tmp/apartments-uv-cache`, one BLAS/OMP thread,
`NUMBA_CACHE_DIR=/tmp/apartments-corrected-numba`,
`PYTENSOR_FLAGS=cxx=,compiledir=/tmp/apartments-corrected-pytensor,numba__cache=False`,
`PYTHONPATH=/tmp/apartments-corrected-fit-code/src`, and
`uv run --no-project --python /home/ben/code/apartments/.venv/bin/python python -m models.bayesian_disk_experiment`.
All source/output/proof CLI paths are absolute under the root repository.

CPU remains the provisional iteration default because its existing fit converged
and its warmup is much shorter; the GPU has better ESS per draw in the parameter
gate. Report this tradeoff, do not call CPU universally fastest. This new fit runs
alongside diagnostics and is **not** an uncontended benchmark. The lost ninth-floor
support also changes the joint 8→10 prior as documented below; this is a corrected
source fit, not a strictly prior-matched estimate of correction effects.

## September 19: complete GPU sampling recovered; full ESS diagnostics running

**Original GPU session 30289 is terminal, exit 1.** All 4×6,000 retained draws
finished before a PyMC postprocessing GPU allocation failed. Retained compute
**1,919.646632 s**, transfer/storage **8.296186 s**, total **1,927.942818 s**;
raw aggregate rate **12.448502 draws/s**. Warmup was **2,839.769692 s**.
Every retained iteration had 127 steps; zero divergences. No ESS-based winner yet.
`postprocessing-failure.log` and `.json` preserve the original failure. Do not
restart or poll the now-terminal original sampler.

`models/recover_numpyro_trace.py` recovered all draws from the 18 saved leaves
through the exact PyMC constrained graph, using CPU-only JAX and 64-draw batches.
All original raw hashes are unchanged, every output batch was read back exactly,
and 12 cross-chain/start/middle/end potential-energy checks differ by at most
**7.28e-12**. Largest transformed variable batch **45,443,072 bytes**.
Recovery **session 54795 exited 0**, artifact
**`data/model/chelsea-numpyro-cpu-conversion-recovery-20260919`**;
conversion time **133.057761 s**. **2 actual PyMC recovery tests pass** in the
isolated benchmark environment (session **55296**, exit 0), including transforms,
coordinates, every draw/statistic, and rejecting unwritten retained tails.

`models/install_numpyro_recovery.py` reverified the recovery and original raw
inventory, then installed a new posterior/completion record without overwriting
existing products. Install **session 5923 exited 0**, **13.130347 s**. Posterior
SHA **bb8bbaa29166d3a0863976c541535c4b7a7e701453dc55407186595d1fc7d16a**.
`sampled.json` marks the original PyMC call unsuccessful and binds the recovery;
it does not invent a successful end-to-end call timing. Original progress remains
at the failed postprocessing stage as historical evidence.

**LIVE: diagnostic session 30424** on the host runs
`models.sampler_efficiency` against the recovered benchmark posterior and the
original `chelsea-reviewed-current-analysis-20260918` dataset. Output:
**`data/model/chelsea-numpyro-gpu-efficiency-20260918`**;
log **`/tmp/chelsea-numpyro-gpu-efficiency.log`**. Last phase:
`parameter_diagnostics`. Keep original v3/graph/floor source files unchanged until
this completes; the helper checks their original hashes. New source-lineage and
evidence files are outside that set. Follow by running
`models.compare_sampler_efficiency` with CPU rates
`chelsea-nutpie-wall-efficiency-20260919`, GPU rates above, CPU experiment
`chelsea-bayesian-current-floor-disk-20260918`, and GPU benchmark
`chelsea-numpyro-gpu-batched-benchmark-20260918`. Choose a new comparison output.

The comparison aligns named parameters, preserves CPU wall-time bounds, separates
parameter families and refuses mismatched data/priors/code or failed gates.
**35 installer/timing/comparison tests pass**, plus the two recovery tests above.
The TODO now correctly records that the main 172-current model already uses floor
increments; corrected-source runner integration/refitting remains pending.

## September 19: corrected-source evidence lineage verified for fitting

`apartments.reviewed_source_lineage.source_lineage` now verifies the bounded
floor-mask → laundry-mask → refreshed-source chain by undoing each exact recorded
mask, preserving prior review history, checking each reconstructed source-row hash,
and checking the entire ordered parent observations hash. This detects unintended
price, identity, clock, membership or non-target feature changes even when the
derived output manifest is recomputed. Parent versions and manifest hashes,
active correction coverage, target scope and correction clocks are checked.

`bayesian_evidence.load_evidence` accepts these verified descendants of the exact
refreshed archive source. Existing literal identity/clock/coverage checks remain.
**43 lineage/evidence tests** and **36 source-review/floor/laundry tests pass**.
Actual full-data script **74207 exited 0**:
`docs/analysis/scripts/check_corrected_source_readiness.py`.
Artifact **`data/model/chelsea-corrected-source-readiness-20260919`** verifies
52,863 rows, 172 unchanged current listings and **72,065 identical literal captures**.
Exactly 17 floor masks and one laundry mask (plus their histories) differ.

Canonical floor support drops **366→349 rows**, retaining 22,189 units and
1,131 buildings. The only floor-9 observation was masked: the corrected design
has 59 features, removing `listed_floor_gt_9`. Compare the **joint 8→10 contrast**
with the old fit, not individual coefficient positions. With the existing common
observed-step prior, that gap's prior SD also changes from sqrt(2)*0.15 to 0.15;
do not attribute every posterior difference solely to the source corrections.
Any matched correction sensitivity should preserve or explicitly vary that gap
prior. No posterior was refitted or main selection changed this turn.

Production runner version integration is still pending: `bayesian_feature_experiment_v3.py`
is frozen by the live GPU benchmark and must not be edited until the benchmark
and its diagnostics have finished. New lineage/evidence files are outside its
bound implementation set. Latest durable GPU status **3,500/6,000 retained draws
per chain at 04:36:48 UTC**; host PID **494915** independently verified live.

## September 19: local floor-label calibration does not expand interaction support

Reviewed all 46 capture floor passages for 33 advertisements / 23 units across
152 W20, 312 W20, 317 W22 and 350 W18. Only 152 W20 supports prefix +1;
the other three support equal prefix/floor within their observed ranges.
`models/floor_label_calibration.py` counts distinct units, requires four units
and two prefix levels, holds out whole units with three remaining references,
abstains outside the remaining range, and preserves negative evidence from all
12 buildings with reviewed numbering/scope problems. An unreviewed comparable
disagreement also vetoes a selected rule.

Artifact **`data/model/chelsea-floor-label-calibration-20260919`**, successful
script session **90995**, binds source/label/description/review bundles and
includes exact reference capture passages. **19 whole-unit checks agree and four
abstain**. This is selected-rule consistency, not independent accuracy.
100 missing-floor rows / 39 units gain candidates; only **19 units** lack explicit
reference evidence elsewhere. Most added rows have unknown elevator status.
No new buildings have within-elevator-group floor variation across the supported
thresholds. Keep the next floor interaction experiment small and based on reviewed
explicit floor claims; calibrated labels can be a sensitivity analysis.

This remains the 52,704-row source cohort, not the refreshed current cohort.
No analytical values, model parameters, source clocks or main selection changed.
Reproduction script `docs/analysis/scripts/review_floor_label_calibration.py`;
findings in `docs/analysis/chelsea-local-floor-numbering-2026-09-19.md`.
**Eight calibration/support tests pass** in session **76904**, exit 0.

GPU session **30289** re-polled live. At **04:33:34 UTC**, batch six was 375/500;
last durable status was 2,500/6,000 retained draws per chain. Do not restart;
sampling continues on the original frozen model/source. No backend winner yet.

## September 19: long-run CPU efficiency bounds ready; GPU retained sampling live

The 50/50 run remains withdrawn as speed evidence. GPU session **30289**, host
PID **494915**, finished 4,000 warmup in 2,839.77 seconds including initialization
and JIT. Latest durable status at **04:26:09 UTC**: **1,500/6,000 retained draws
per chain**, 487.255 seconds retained compute and 2.463 seconds transfer/storage.
Keep the existing run alive; its model/source paths remain frozen.

New `retained_wall_bounds` in `models/sampler_efficiency.py` uses timestamped
all-chain callbacks, never the sum of chain runtimes. The actual CPU shared
retained interval is **600.081867–705.714876 seconds**. It spans earliest warmup
completion to last sampling completion, including overlapping slower-chain
warmup and raw writes. Minimum bulk ESS/sec: parameters **1.282–1.508**,
derived unit/bathroom contributions **1.764–2.074**, joint floors **2.543–2.991**.
Bounds are timing resolution, not uncertainty in ESS estimates. No winner yet.

Artifact `data/model/chelsea-nutpie-wall-efficiency-20260919` binds verified fit,
protocol, recovery posterior and archived callbacks; it contains all parameter
and derived bulk/tail rates. Script
`docs/analysis/scripts/measure_current_cpu_efficiency.py` completed in session
**13168**, exit 0. Initial invocation hit a CSV bytes/text conversion error before
publishing anything; fixed using BytesIO. **18 sampler-efficiency tests pass**,
including asynchronous boundaries, inverse rate bounds and invalid evidence.
The GPU diagnostics helper still awaits complete `sampled.json` and must run
after the full retained trace finishes. No model/loader changes were made.

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
