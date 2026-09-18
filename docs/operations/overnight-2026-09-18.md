# Overnight modeling and maintenance — September 18, 2026

## Authorization and window

User requested approximately six hours of autonomous project work on Bayesian
modeling/ablations and repository cleanup, with separate branches if useful.
Run locally on the Thelio (prior explicit preference). Started 03:20 UTC;
stop launching work by **09:20 UTC / 05:20 America/New_York**. User expects to
check back around 11:20 UTC. Do not spend time merely waiting to fill the window;
advance substantive experiments and cleanup. Do not alter raw source data,
review annotations or the review dataset. No Modal compute. Preserve working
report until a checked successor is ready.

Heartbeat: `overnight-apartment-modeling-and-cleanup`, every 30 minutes, currently
expires 09:20 UTC. Pause once completed; ensure a final collection/report before
expiry. Tools may require targetThreadId or destination=thread for heartbeat updates.

## Repository workspaces

Base deployed revision: `0cf7952634a96fe53e64f0e28798762b038aaa6b`.

- Modeling: `/tmp/apartments-bayesian-20260918`, bookmark
  `overnight-bayesian-20260918`, initial JJ change `xwptvlnn`.
- Maintenance: `/tmp/apartments-maintenance-20260918`, bookmark
  `overnight-maintenance-20260918`, initial JJ change `lxtmwoxo`.
- Deployed repo: `/home/ben/code/apartments` (JJ; do not mutate while experiments
  run except explicitly checked integration).
- Conversation workspace: `/home/ben/.codex/worktrees/b20f/apartments`; this work
  log lives here. Preserve its accumulated prior edits. New modeling/maintenance
  edits belong in the isolated /tmp workspaces above, then JJ snapshot/merge.
- Python: run `uv sync --locked --extra dev --extra model` in each isolated
  workspace before experiments, then use `uv run --locked --extra model python`.
  Use `uv run --no-sync python` for an already prepared environment while jobs
  are active. 12 logical CPUs, 15 GiB RAM (~10.7 GiB available).
  Limit sampler to 4 cores and BLAS to 1 thread; one substantial fit at a time.

## Inputs and baseline

Completed transform:
`/data1/apartments/archive/datasets/chelsea-granular-20260917-canonical-url-v1`.
Latest incremental robust point fit:
`/data1/apartments/archive/fits/chelsea-minimal-canonical-20260917-incremental`.
Prepared `model_data.parquet`: 53,899 unit-month observations from 54,800 listing
IDs, 22,424 canonical units, 1,141 buildings, 2010-01 through 2026-08.
Cleaning retained 83.9% of transformed listing IDs; missing area is kept.
Temporal baseline: train through 2025; 2,801 2026 rows, median absolute error
7.1021%, 90.8247% within 20%, median signed bias -3.8936%.
Source attributes are from each listing's own archived captures; validation is
retrospective, not a fully as-of-date forecast. Do not relabel rents as leases.
Incremental bedroom thresholds are user-mandated: >0, >1, >2, >3, >4.

Current mobile report:
http://thelio.tail3983e0.ts.net:8766/model-report
Served by REVIEW_MODEL_REPORT in apartments-review.service; only repoint after
verification. Review dataset remains chelsea-granular-20260917-canonical-units.

## Plan

1. Bayesian robust hierarchical log-rent model with incremental bedrooms,
   bathrooms, optional size, monthly smooth trend, seasonality, building effects;
   evaluate addition of unit effects. Proper priors, prior checks, NUTS diagnostics,
   posterior predictive intervals and calibration. Compare using a validation
   period (2025) before final 2026 evaluation; avoid tuning repeatedly on 2026.
2. Local pilots to establish runtime/convergence; full selected-data fits where
   feasible. Compare no-unit/no-size or residual-family ablations as time allows.
   Save frozen source, inputs, settings, posterior, diagnostics, predictions.
3. Maintenance baseline pytest, then focused refactors/cleanup with meaningful
   regression tests. Avoid giant unrelated formatting sweeps and dependency churn.
4. Integrate tested independent changes, prepare readable experiment comparison
   and maintenance notes, publish a mobile-accessible morning report. Record
   inconclusive/failed fits honestly. No claim of success from sampler completion
   alone: assess R-hat, ESS, divergences, intervals, and held-out errors.

## Current status

- 03:20–03:25 UTC: read installed APIs; PyMC 6.2, Nutpie 0.16.11, ArviZ 1.2
  return xarray DataTree. `arviz.summary` and `arviz_stats.summary` are available.
- Two isolated JJ branches created; periodic continuation heartbeat active.
- Maintenance baseline full pytest launched, output
  `/tmp/apartments-maintenance-baseline.log` (check process/log before relaunching).
- Bayesian runner not yet implemented/launched.

Update this log with exact job paths/status and next steps before yielding.

### 03:33 UTC update

- Bayesian runner implemented in modeling workspace with 2 passing tests.
  Pilot `/tmp/overnight-bayes-pilot` completed in 21 seconds; no divergences,
  but deliberately short chains fail convergence (not an inferential result).
- Full building-only Student-t validation fit launched, training through 2024,
  evaluating 2025, 4 chains × 1,000 tuning + 800 posterior draws. Output:
  `/data1/apartments/archive/fits/chelsea-bayesian-20260918-building-validation`.
  Log `/tmp/overnight-bayes-building-validation.log`, tool session 49144,
  timeout 3,600 seconds. Frozen source in
  `/data1/apartments/archive/model-sources/chelsea-bayesian-20260918-v1`.
- Baseline full repository tests: **321 passed, 2 skipped**, 35 seconds.
  Log `/tmp/apartments-maintenance-baseline-unrestricted.log`.
  Initial sandbox run could not use local network and was interrupted; rerun
  allowed local test networking. No cloud compute used.
- Maintenance target: extract transform finalization into named helpers, preserve
  compatibility entry point, reject unexpected/mismatched shard files before
  marking a dataset complete. Add corruption regression tests.

### 03:40 UTC update

- Building-only full validation run completed in 243 seconds. It is **not
  converged**: max R-hat 1.177, minimum bulk ESS 17.9, zero divergences. Main
  mixing problem is time/season hierarchical scale parameterization. Its 9.20%
  validation MdAPE is exploratory only; do not publish its intervals as reliable.
- Equivalent centered time/season parameterization implemented; 2 tests pass.
  Also fixed seen-unit stratification for building-only ablations (the first
  run mislabeled all validation rows unseen; aggregate metrics are unaffected).
- Refitting building-only model, 4 × 1,500 tune + 2,000 draws. Output
  `/data1/apartments/archive/fits/chelsea-bayesian-20260918-building-centered-validation`,
  log `/tmp/overnight-bayes-building-centered-validation.log`, session 50184.
  Source freeze `/data1/apartments/archive/model-sources/chelsea-bayesian-20260918-v2`.
- Maintenance refactor complete in its isolated branch: named finalization helpers,
  exact file/checkpoint/count reconciliation, 11 corruption/recovery regression
  cases, shared fixture, local-run documentation. Full suite **332 passed, 2 skipped**.
  Snapshot `lxtmwoxo cf65f73b` bookmark overnight-maintenance-20260918.
  Log `/tmp/apartments-maintenance-final.log`. No production deployment yet.

Prior inspection: broad intercept prior puts central 95% median asks roughly
$1,162–$22,028 (80 simulated draws); trend index across all sampled periods spans
28–589 at pooled central 95%, reflecting a deliberately weak long-history prior.
First run posterior scales: residual 0.095, building 0.283, season 0.008, trend
0.057 (exploratory because nonconverged). Check trend/season separation and
forecast behavior after centered refit; do not silently treat pilot statistics
as final estimates.

### 03:48 UTC update

- Centered-time building refit also fails convergence: 461 seconds, max R-hat
  1.198, min ESS 14.5, two divergences; strongest slow directions mix season and
  trend. Longer chains alone did not resolve it. Not eligible for final inference.
- Launched same centered model with Nutpie's experimental low-rank mass matrix
  adaptation to capture correlated posterior directions, target acceptance .95,
  1,500 tune + 2,000 draws × 4. Output suffix `building-lowrank-validation`;
  log `/tmp/overnight-bayes-building-lowrank-validation.log`, session recorded by
  tools. Frozen source v3 includes strict finite/BFMI/tail-ESS acceptance checks,
  holdout-unit option, streaming artifact hashes, and analysis helper.
- If low-rank still fails, simplify/identify trend-vs-season decomposition:
  inspect exact seasonal overlap of the quarterly spline basis, orthogonalize
  seasonal directions or use fewer knots; consider fixed weak seasonal scale.
  Do not spend the entire window extending nonmixing chains.
- Matched 2025 robust baselines saved in
  `/data1/apartments/archive/fits/chelsea-bayesian-20260918-baselines`.
  Existing robust unit baseline: MdAPE 7.993%, log RMSE .15019, bias -5.802%.
- Modeling documentation `docs/model/bayesian-local.md`, analysis helper and
  prediction/diagnostic tests added in Bayesian workspace. One new assertion
  initially used exact float equality; corrected to numerical tolerance.

### 03:52 UTC update

- Found an exact identifiability problem in the original time design: quarterly
  spline + intercept + season matrix has 78 columns but rank 75 (three pure
  annual seasonal patterns are duplicated). Six-month knots still duplicate one;
  annual knots avoid it but lose useful time resolution.
- Implemented season-separated basis (`basis_version=season-separated-v2`): find
  pure seasonal directions in whitened spline coefficient space and condition
  them to zero. Keeps quarterly resolution, January 2022 anchor, and proper prior.
  Regression test verifies full rank, including the partial final year.
- New sampler/prediction/controller tests: **8 passed**. Controller
  `models/bayesian_experiments.py` freezes its runner, respects an explicit deadline,
  runs ablations sequentially, and stops on failed diagnostics. It is NOT launched
  yet; the prior low-rank comparison is still running (session 47393).
- Next: once that fit ends, freeze current v4 source and run season-separated
  building/unit/no-size/normal 2025 batch, preferably low-rank adaptation. Stop and
  diagnose if it still fails. Final 2026 test/full fit and report remain undone.
- Maintenance branch final description and snapshot: `lxtmwoxo bf4ea7bd`.
- Heartbeat expiry extended to 09:50 UTC solely to permit a final collection tick
  after the unchanged **09:20 UTC work deadline**. Pause after final reporting.

### 03:57 UTC update — durable batch running

- Superseded original low-rank fit stopped after finding the exact seasonal
  overlap. It has no complete posterior and must be labeled interrupted/superseded.
- Corrected season-separated batch launched as a durable local systemd user unit:
  **apartments-bayes-overnight-20260918.service**. Limit 4 CPU equivalents, 10 GiB
  memory, nice 5, runtime cap 18,500 seconds. Batch deadline **09:00 UTC**, leaving
  report/integration time before 09:20. No cloud compute.
- Output root:
  `/data1/apartments/archive/fits/chelsea-bayesian-20260918-season-separated`.
  Read `progress.json`, active `<variant>.log`, and completed variant diagnostics.
  Sequence: building, unit, unit-no-size, unit-normal; stops on any failed diagnostic.
  Each fit: low-rank adaptation, 4 chains, 1,500 tune + 2,000 draws, target .95.
- Frozen source v4 under `/data1/apartments/archive/model-sources/chelsea-bayesian-20260918-v4`;
  controller additionally freezes its runner inside the output root.
- Model/report/controller/analysis source and tests formatted. Added report generator
  `models/bayesian_model_report.py`; inconclusive preview builds at
  `/tmp/overnight-report-preview/report.html`. Do not publish this preview.
- Final report must have a diagnostic-passing **full-data fit** and separate
  2026 temporal test; report refuses an unaccepted or subset full fit. Later review
  actual findings and adjust explanatory text before publishing.
- Next continuation: inspect batch. Resolve any remaining sampler issue before
  proceeding; otherwise compare 2025 ablations, choose model, run final 2026 test,
  full-data fit and optional whole-unit holdout. Integrate tested branches, verify
  report, repoint existing /model-report route only after checking; keep review data.

### 04:01 UTC handoff/checkpoint

- Corrected batch is still sampling its first building model (started 03:56 UTC).
  Check service/progress before launching anything. Existing model files were
  frozen before formatting; continuing source edits do not change this batch.
- Bayesian branch full suite **329 passed, 2 skipped**, 45 seconds. Log
  `/tmp/apartments-bayesian-full-tests.log`. Maintenance branch full suite **332
  passed, 2 skipped**. Combined integration should have 340 passing tests (321
  baseline + 11 maintenance + 8 modeling), subject to later additions.
- Model extras now require ArviZ >=1.2 and Nutpie >=0.16.11 (APIs used), and include
  Plotly for report generation. `uv lock` updated metadata only; runtime venv was
  not synced or modified. It also reconciled an existing migration extra missing
  from the old lockfile (zstandard 0.25). No other package upgrades.
- Temporary formatting used Black 25.1 in /tmp caches; new code is formatted.
  Restricted formatter/test processes that lingered were stopped; no unrelated
  process was stopped. Live review app was not restarted or changed.
- Report generator still needs final-result wording/visual review once fits exist;
  template includes responsive tables, embedded Plotly, and trace resizing on
  expanding details. Prior preview is not published.
- Next priority is statistical convergence, then ablations/final 2026/full fits,
  then integration and morning publication. If the corrected low-rank fit fails,
  inspect worst parameters and simplify seasonal hyperprior or improve building
  intercept parameterization; exact seasonal overlap has already been removed.

### 04:26 UTC continuation

- Season-separated v4 building fit finished in 769 seconds but still failed:
  max R-hat 1.135, minimum ESS 22.5, zero divergences, BFMI .632+. Batch stopped.
  Worst directions are time coefficients and overall intercept/building location.
- Improved geometry in v5: rotate/scale time coefficients using a weighted SVD
  of the training design, preserving the exact trend prior covariance (tested).
  Center time/season at training observations. Centered zero-sum building effects
  remove the redundant global building level. Unit effects stay noncentered.
- New gated batch active: **apartments-bayes-rotated-20260918.service**, output
  `/data1/apartments/archive/fits/chelsea-bayesian-20260918-rotated`, frozen source v5.
  Same four variants, 4 chains × 1,500 tune + 2,000 draws, now diagonal adaptation.
  Limits 4 cores/10 GiB; deadline still 09:00 UTC. First fit started 04:24.
- Reusable design serialization added after source freeze (will be v6 for final
  fits): saves exact matrix arrays in design.npz and Design.load reconstructs
  frozen transforms without learning from prediction data. Roundtrip and prior
  covariance tests added. **10 modeling/controller tests passed**.
- Integration workspace created at `/tmp/apartments-integrated-20260918`, bookmark
  `overnight-integration-20260918`, merge of both isolated branches. Full combined
  suite running, log `/tmp/apartments-integration-tests.log`. No live deployment.

### 04:27 UTC milestone

- Rotated/centered building model **passes all diagnostic gates** in 136 seconds:
  max R-hat 1.00605, min bulk ESS 553, min tail ESS 989, zero divergences,
  BFMI .934–.988, no maximum-depth hits. Ordinary diagonal adaptation is sufficient.
- 2025 validation (3,785 rows): MdAPE 8.808%, log RMSE .15706, median bias -6.327%,
  80% coverage 83.487%, 95% coverage 96.301%, mean log predictive density .53704.
  Seen units MdAPE 8.346%; unseen 10.292% (same seen definition for all ablations).
- Batch automatically advanced to the unit model at 04:26 UTC. Detailed building
  summaries being saved in `.../chelsea-bayesian-20260918-rotated/building-analysis`.
- This resolves the initial sampling bottleneck. Continue matched ablations;
  final selection and 2026 evaluation still pending.

- Combined integration suite completed: **342 passed, 2 skipped**, 53 seconds.
  Integration change `rsykvxyn 3ba510e0` at creation (JJ may rebase it if a parent
  changes later; run `jj workspace update-stale` before using the integration
  checkout after parent edits). No conflicts or deployment.
- Descriptive input audit: 11,949 of 22,424 units have multiple observations;
  1,684 units have reported bedroom or bathroom changes (1,462 bedroom; 441
  bathroom); 180 have reported area range >20%. These may reflect condition,
  classification or source changes, not automatically bad identities. Useful
  for the later attribute-shift review pass; no exclusions/annotations changed.
- Matched robust building-only 2025 MdAPE is 8.737%, close to the Bayesian building
  fit's 8.808%. Do not claim point-prediction improvement from that first fit;
  Bayesian contribution includes predictive uncertainty and partial pooling.

Next check after this continuation: current rotated batch should either be on
later ablations or stopped with a specific diagnostic. Its building model is
accepted, so keep that successful reference. Do not restart the failed v4 batch.
Code changes after v5 freeze are serialization/formatting only; freeze v6 before
final full-data/test fits so exact design matrices are retained. If all four
validation models pass, select using 2025 predictive density plus calibration and
point-error comparisons, explicitly record the choice before opening new 2026
Bayesian results, then run final 2026 and full-data fits. A whole-unit holdout and
attribute-change sensitivity remain useful if time permits. Final report generator
exists but still needs results-specific findings and checks before publication.

### 04:56 UTC continuation

- Rotated unit model accepted in 490 sec: max R-hat 1.00868, minimum ESS 457,
  tail ESS 736, zero divergences, BFMI .438+. 2025 MdAPE 8.948%, log RMSE .16091,
  bias -7.818%, 80% coverage 78.283%, 95% 94.267%, mean log score .53290.
  Building-only remains slightly better overall, chiefly less downward bias.
- No-size version was marginal: max R-hat 1.01275, minimum ESS 379, zero divergences.
  It is still NOT accepted. Original batch stopped before the normal ablation.
  Systemd reported 7.1 GiB peak for the earlier batch.
- Added an explicit annual drift alternative (Normal(.03,.05) log/year) and
  removed its exact linear direction from the nonlinear spline to retain
  identifiability. This is a validation-year modeling improvement, not 2026 tuning.
- Diagnostics now chunk the parameter axis into at most 512 coefficients while
  retaining all chains/draws. Exact equivalence to full diagnostics is tested;
  this reduces temporary memory for >20,000 unit traces. Saved-design roundtrip
  still works. **12 targeted tests pass**.
- Frozen source **v6** includes drift option, diagnostic memory fix, and exact
  design.npz serialization. Durable service **apartments-bayes-drift-20260918**
  launched, output `/data1/apartments/archive/fits/chelsea-bayesian-20260918-drift`.
  Four matched variants: unit-drift, building-drift, unit-drift-no-size,
  unit-drift-normal. 4 × 2,000 tune + 3,000 draws; diagonal adaptation, target .95.
  Bounds: 4 CPU equivalents, 11 GiB, deadline 08:40 UTC. Check progress before
  any new sampler. This batch also stops on failed diagnostics.
- No Bayesian 2026 test has been run or inspected yet. Record selection only after
  these 2025 comparisons. Full/test/whole-unit holdout fits and final publication
  remain pending. Successful no-drift building/unit references are retained.

Additional diagnostic: after subtracting each validation month's median log error
(a descriptive residual-spread diagnostic, NOT a usable forecast score), median
absolute residual spread is 6.96% building-only vs 6.31% with units; for previously
seen units, 6.60% vs 5.76%. This supports investigating common time extrapolation
bias rather than discarding unit information. Do not report these centered values
as held-out prediction accuracy; they use the held-out month for centering.

At the next scheduled check inspect the drift batch, then finish model selection
and final evaluation. No need to rerun the old failed/accepted references. Current
integration tests predate the last two diagnostics/drift tests; rerun combined
suite once the final modeling code is settled (expected 344 passes, 2 skips).

### 05:25 UTC continuation

- v6 unit-drift preliminary 2025 scores improved substantially (MdAPE 6.577%,
  log RMSE .13383, bias -3.382%, log score .71023), but **not accepted**: max
  R-hat 1.0499, min ESS 73, slow annual-drift/spline directions, zero divergences.
  The gated batch stopped. Peak memory 7.7 GiB with 3,000 draws; chunked diagnostics
  kept this practical on the 15 GiB machine.
- v7 changes the nonlinear prior definition: after removing exact linear/seasonal
  overlap, project the nonlinear curve orthogonal to linear time under training
  observation weights, re-anchor at January 2022, then rotate/scale as before.
  This gives annual drift an identified interpretation. This is a deliberate
  prior change, not merely an equivalent sampler reparameterization. **13 targeted
  tests passed**, including weighted orthogonality and full-rank tests.
- Active durable batch: **apartments-bayes-orthogonal-20260918.service**.
  Frozen source v7; root `/data1/apartments/archive/fits/chelsea-bayesian-20260918-orthogonal`.
  Same four matched drift variants; 4 × 2,000 tune + 3,000 draws, diagonal NUTS,
  target .95, 4 CPU/11 GiB, deadline 08:35 UTC. Starts with unit-drift.
- Heartbeat interval shortened to **15 minutes** to reduce idle time between
  bounded fits; stop-work deadline remains 09:20 UTC, final collection allowed
  through the existing 09:50 UTC automation expiry.
- Selection protocol before reading new results: compare diagnostic-passing
  candidates on 2025 mean log predictive density (higher better), reporting
  point errors and interval calibration alongside it. Quantify paired differences
  by building-cluster bootstrap where useful; do not present a tiny difference
  as decisive. Record selected configuration before running any 2026 Bayesian
  test. Keep robust point baseline even if it remains better on point accuracy.
- If v7 passes, finish the matched ablations and proceed promptly to final test,
  all-data fit, and whole-unit holdout. Avoid spending the entire window tuning
  validation. v5 no-drift building and unit fits remain accepted fallbacks.

### 05:41 UTC continuation — drift models accepted

- v7 unit-drift accepted in 648 seconds: max R-hat 1.00552, min ESS 704, tail
  ESS 1,160, zero divergences, minimum BFMI .449. 2025 MdAPE **6.767%**, log RMSE
  .13584, bias -3.963%, 80% coverage 85.310%, 95% 95.905%, log score .68777.
- v7 building-drift accepted in 175 seconds: max R-hat 1.00465, min ESS 952,
  zero divergences. MdAPE 7.020%, log score .64507, 80% coverage 87.239%.
- Active batch advanced to unit-drift-no-size; normal-residual ablation follows.
  Do not interrupt or launch another sampler. Main code is now statistically
  workable; finish comparisons, choose configuration, and move to final evaluation.
- New `models/bayesian_comparison.py` provides paired building-cluster bootstrap
  comparisons. Two tests pass (row-order invariance and cohort/price mismatch
  rejection). Saved `.../orthogonal/comparison-unit-vs-building.json`:
  unit-model log-score improvement .04270, 95% bootstrap interval [.01445,.07024]
  across 652 buildings / 3,785 rows. MdAPE difference -0.253 pp, interval
  [-0.687,+0.188], so do not claim a decisive point-error difference.
  These are conditional validation-year bootstrap intervals, not posterior or
  future-year uncertainty statements.
- Report polish underway: show size effect for 10% greater area; include annual
  drift and intercept in hidden chain traces. Full-data report still awaits final
  fits. Expected combined suite now 347 passes, 2 skips.

### 06:04 UTC — selection locked, final evaluation running

- All four v7 drift variants passed diagnostics. Unit-drift won 2025 mean log
  predictive density (.68777); building-drift .64507, no-size .67328, normal
  residuals .53460. Corresponding median absolute errors: 6.767%, 7.020%, 6.857%,
  7.224%. Building-cluster paired log-score gains for retained size: .01449
  [95% bootstrap .00581,.02418]; Student-t versus normal: .15317 [.05255,.32613].
  All comparisons are conditional on this validation year, not guarantees.
- Selection was recorded **05:57:07 UTC before starting the 2026 test** in
  `/data1/apartments/archive/fits/chelsea-bayesian-20260918-final/selection.json`.
  Selected: units + buildings + optional size + annual drift + Student-t errors.
- Active service: **apartments-bayes-final-20260918.service**. Frozen v7 runner,
  4 chains × 2,000 tune + 3,000 draws, target .95, diagonal adaptation, local
  4 CPU/11 GiB. Controller deadline 08:40 UTC. Root `.../chelsea-bayesian-20260918-final`.
  Runs `temporal-2026`, then `full-data`, then `unit-holdout`, stopping on failed
  diagnostics. Current phase temporal-2026 (training 51,098, test 2,801 rows).
  No tuning against final-year results. Whole-unit holdout is exploratory because
  selection used 2025 observations that can overlap these units.
- Integrated tests: **347 passed, 2 skipped**, 52 seconds; log
  `/tmp/apartments-integration-final-tests.log`. Integration revision d65c643c,
  modeling parent 610e05e0, maintenance parent 88dd05f5.
- Deployed repository remains unchanged at base 0cf79526 (rxkpzsov); its listed
  working-copy files are precisely that existing committed JJ change, not new
  edits. No app restart/publication yet. Report still serves the robust baseline.
- Next: inspect final results, run analysis helper into new analysis directories,
  finish substantive morning report, integrate branches and point existing report
  route at checked HTML. Preserve review dataset and all annotations.

Additional preparation at 06:06 UTC:
- Validation analysis saved under `.../chelsea-bayesian-20260918-analysis/validation-unit-drift`.
- Report code now includes paired bootstrap comparison tables, a monthly 2026
  forecast check, and optional `--holdout-fit` with explicit exploratory caveat.
  Black formatted. This report-only edit occurred after the 347-test run; render
  against final outputs and verify before publication. Fit runner remains frozen.
- Modeling workspace snapshot advanced (9f1ac490 before the latest docs edit);
  integrated workspace needs `jj workspace update-stale` after final snapshot.
- Final test still sampling at 06:05, no result yet. Do not start another sampler.

### 06:12 UTC — final 2026 test accepted, predictive limitation established

- Temporal test finished 06:09:03 UTC, 713 seconds. Diagnostics pass: max R-hat
  1.00922, min bulk ESS 712, tail 1,238, zero divergences, min BFMI .400.
- **2026 Bayesian median error 9.410% versus point baseline 7.102%**; median
  bias -8.392%, within-20% 87.397%, 80% coverage 75.295%, 95% coverage 92.788%,
  log score .49523. Known units: 9.083% error (2,147 rows); unseen: 11.013%
  (654 rows). Do not retune against this final test. Retain point model as the
  prediction benchmark; Bayesian posterior remains useful for descriptive work.
- Paired building-bootstrap point-error difference: +2.308 pp, 95% interval
  [+1.475,+3.232], 523 buildings / 2,801 matched observations. No predictive
  density was invented for the point model. Saved `point_comparison.json` in
  `.../chelsea-bayesian-20260918-analysis/temporal-2026`.
- Subgroup analysis also saved there. Signed bias worsens from -3.09% January
  to -14.15% August; larger-bedroom and missing-size groups fare worse. This
  suggests investigating extrapolation, but does not prove the cause.
- Final controller automatically started **full-data** at 06:09:03; whole-unit
  holdout will follow. Same model, no parameter/likelihood/data changes.
- Report now prominently says point model remains prediction benchmark, states
  actual final-test coverage, includes monthly bias and optional holdout caveat.
  Rendering a test-only preview succeeded at `/tmp/bayesian-report-finaltest-preview/report.html`.
  Full report still pending accepted full fit. No publication/deployment yet.
- Next: collect full/holdout results; validate artifact hashes; run full-fit
  analysis; write final narrative and report; snapshot/update integrated workspace
  and deploy checked report while preserving review dataset and decisions.

### 06:29 UTC — full fit accepted, report prepared

- Full-data fit finished 06:20:59 UTC; accepted max R-hat 1.00638, min bulk ESS
  626, tail 1,024, zero divergences, BFMI .421. All 53,899 rows included.
- Current final-controller phase: **unit-holdout**, started 06:20:59; do not
  duplicate it. Full and temporal artifact hashes verified (10 and 11 files).
- Full-data analysis saved under `.../chelsea-bayesian-20260918-analysis/full-data`:
  adjusted Aug2025–Aug2026 change 6.089% [4.917,7.254]; two years 14.359%
  [13.124,15.636]; five years 35.967% [34.424,37.499]. These describe observed
  periods, not forecast accuracy. Model assumptions condition the intervals.
- Added `docs/analysis/chelsea-bayesian-2026-09-18.md` to modeling branch with
  data, selected/failed ablations, held-out loss to baseline, posterior results,
  maintenance details, artifacts, and future work. Add whole-unit results once
  available. Report now includes observed-market growth intervals and an explicit
  benchmark decision. Full-fit preview rendered at `/tmp/bayesian-report-full-preview/report.html`;
  latest growth-table addition still needs final rendering.
- Modeling bookmark currently ac6e47cc (xwptvlnn). Integrated workspace needs
  update-stale before final use. No new fit runner changes since frozen v7.
- CUA now has an available in-app browser (id 1, no tabs), unlike earlier checks.
  Use it after publication for real desktop/mobile-friendly page inspection.
  No screenshot or visual QA has yet occurred.
- Remaining: holdout diagnostics/results/hash; finish final narrative/report;
  integrate branches into deployed repo (base unchanged at 0cf79526); change only
  REVIEW_MODEL_REPORT to new checked HTML, restart review service, verify report
  hash and unchanged review dataset via /api/overview; inspect in browser.

### 06:44 UTC — completed and published

- All final phases completed and accepted. Whole-unit holdout: 11,060 rows,
  MdAPE 7.040%, bias +.305%, 80% coverage 82.568%, 95% coverage 93.978%;
  max R-hat 1.00814, min bulk ESS 775, tail ESS 674, zero divergences, BFMI .417.
  Its analysis is saved under `.../chelsea-bayesian-20260918-analysis/unit-holdout`.
  All 11 holdout artifact hashes verified; no running modeling job remains.
- Final report: `/data1/apartments/archive/fits/chelsea-bayesian-20260918-final/report/report.html`.
  Published at **http://thelio.tail3983e0.ts.net:8766/model-report**.
  HTTP SHA256 matches artifact:
  `6d844c924897cd352cbbb7efed200ab3d420f6f839fef7747701018cad388edc`.
- Both service configs now point REVIEW_MODEL_REPORT at that file. Review dataset,
  review state paths, listener/allowlist settings unchanged. Restart succeeded.
  /api/overview is exactly equal before/after (including review counts, ledger,
  exclusions, dataset); / and /units return 200. Old model/report artifacts kept.
- Browser verified actual page and chart rendering; phone viewport had no page
  horizontal overflow (375px client and scroll widths), tables scroll locally,
  expandable trace charts render correctly, no console errors. Restored viewport.
- Modeling branch final ff736907, maintenance 88dd05f5, integration 0742f918.
  Deployed repository advanced from 0cf79526 to a new child of integration,
  change popwqwvp, with report-service path update. No user changes overwritten.
- Written analysis includes final holdout results and next research priorities.
  Combined tests: 347 passed, 2 skipped. Report-only additions subsequently
  rendered and checked in the browser. Frozen fit runner and tested maintenance
  implementation unchanged. Input/source/artifact hashes preserved.
- Intended overnight work is complete early; do not launch more experiments to
  fill the remaining time. Pause heartbeat after saving these notes. Retain the
  robust point model as the prediction benchmark; next optional research is
  rolling-origin time-extrapolation studies and separate attribute-shift review.
