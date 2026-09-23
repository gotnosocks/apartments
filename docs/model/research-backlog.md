# Chelsea pricing research backlog

## Pipeline review, September 20

Items from an end-to-end review of collection → transform → fit → analyze,
ordered by expected leverage. Numbers refer to the selected fit
(`chelsea-bayesian-expanded-spline-floor-disk-20260919`) and the
`chelsea-granular-20260917-canonical-url-v1` source unless stated.

### Residual review and model

- [x] **Report unit-level deviation as the primary review signal.** Done:
  [review queue](review-queue.md) (`apartments build-review-queue`), September 20.
  Original rationale: The
  selected fit has `sigma` 0.066, `sigma_unit` 0.086 and 47% single-observation
  units. For a singleton, the split between unit effect and residual is set by
  the variance ratio, not by data: for moderate deviations roughly 63% of a
  unit's departure from building + features + time is absorbed into the unit
  effect and only ~37% appears as "residual" (Student-t tails reverse this for
  extreme outliers). The review queue's ranking therefore depends on the
  `sigma_unit` prior and on how often a unit was listed. Add
  `unit_effect + residual` (deviation from building/features/time) to
  `residuals.jsonl` and the main page, show both components, and rank the
  queue on it. Report-only change on saved draws; no refit.

- [ ] **Use the within-advertisement price path.** 27,473 of 65,350 own
  advertisements (42%) changed price while listed; median first→last change
  is −3.5% (p10 −13.2%, p90 +6.2%). Only the initial ask is used. Publish a
  per-advertisement table (`initial_ask`, `final_ask`, `n_cuts`,
  `days_listed`, `terminal_status`) from `event_mentions`; refit on final
  ask and compare coefficients with the initial-ask fit; carry
  `days_listed`/`n_cuts` as observables for current listings. History-table
  mentions of *other* advertisements are not a separate source of new data:
  of 74,674 (unit, listing) pairs, 68,836 are own-captured and the 5,838
  mention-only listings are almost all 2007–2013 (pre-canonical-page cohort).
  Extending the trend to 2007–2013 with masked attributes is a low-priority
  option only.

- [ ] **Align current and historical price basis.** 172 current rows use
  `current_capture_gross_ask` (possibly after cuts) while 52,481 historical
  rows use the initial ask, so stale or cut current listings look cheap.
  Either use the initial ask for current rows or add the price-path
  covariates above.

- [ ] **Publish the observation funnel as a standing artifact.** Raw
  own-captured listings 68,313 / 25,119 units (2.72 per unit; 42% singletons;
  median 1.7 years between repeat listings) → v4 accepted 54,105 → fitted
  52,481. Exclusions (furnished 4,587; concession 4,509; date window 1,259;
  no dated ACTIVE event 488; layout 262; extreme ask 243; conflicting
  same-month layouts 179) are in `coverage.json` but not surfaced. Check
  whether the 4,509 concession exclusions concentrate in recent luxury
  buildings and bias the current cohort.

- [ ] **Test coefficient stability over time.** One log premium per feature
  is shared across 2010–2026 with one Chelsea-wide trend and no bedroom×time
  interaction. Refit on 2019+ only and compare coefficients; add bedroom-group
  trend deviations. If premiums move materially, use era-specific
  coefficients or a restricted serving window.
  *September 22:* bedroom-group random-walk trend deviations fitted and
  converged (held-out ΔELPD +30.0 ± 9.5; group × year bias 0.92% → 0.67%);
  not yet promoted, see [bedroom-time experiment](bedroom-time-experiment-2026-09-22.md).
  The 2019+ coefficient refit is still open.

- [ ] **Building covariates in the building-effect mean.** 25% of buildings
  have ≤5 observations and are shrunk toward the Chelsea mean, inflating their
  units' residuals. Join PLUTO (year built, floors, units, building class),
  DOB elevator devices and coordinates, and place them in the mean of
  `building_effect`. Motivation is small-building shrinkage for fitted
  buildings, not unseen-building prediction. This would also replace
  listing-derived `elevator` (70% known; posterior +0.7%, mostly absorbed by
  building effects).

- [ ] **Relabel positive-only exposure features.** `window_exposures.*` and
  `view_exposures.*` are only ever `True` or missing, so the value columns
  are constant and dropped; the `.unknown` indicators in the design actually
  mean "mentioned". Rename (`mentioned_south`) or extract negations; stop
  presenting them as tri-state.

- [ ] **Improve sampling geometry.** Minimum ESS is on `alpha` (821) and
  bathroom contrasts while median ESS is 33k, indicating a centering problem
  among the intercept, zero-sum building effects and 22k non-centered unit
  effects. Test sum-to-zero unit effects within building; target the same ESS
  with 1,000/2,000 instead of 4,000/6,000 per chain. Also consider estimating
  `nu` instead of fixing 5.

- [ ] **Fast screening fits from the same graph.** Use `find_MAP`/Laplace or
  ADVI on the identical PyMC graph to screen feature experiments; reserve
  full NUTS for candidates that pass. The main model stays exact PyMC; the
  screen is for triage only.
  *September 22:* tested in [fast screening](fast-screening-2026-09-22.md).
  Raw joint `find_MAP` is degenerate (`sigma_building` → 0) and unusable.
  MAP with baseline variance components fixed reproduced a known +30 ΔELPD
  and a null control in minutes. Data subsets are unbiased but underpowered.

### Collection and operating loop

- [ ] **Scheduled active-listing refresh.** Collection is backfill-oriented
  and the current cohort is a one-off 172-row refresh; price cuts and
  delistings are not being observed. Add a systemd timer on thelio:
  discover active in-scope listings → re-fetch active detail pages every
  3–7 days until delisted → incremental transform → fit → publish.

### Transform and extraction

- [ ] **Schema-constrained LLM extraction over the 72k description captures**
  (floor, exposure, laundry level, outdoor access/type, ceiling height,
  renovation, commercial/SRO/income-restricted/net-effective/furnished/
  short-term) returning evidence spans. Keep manual review for calibration on
  a stratified sample. Use it to finish the 667-row commercial/net-effective
  screen.

- [ ] **Consolidate scope/quarantine overlays into the corrections ledger**
  with a `scope` field (commercial, sro, net_effective, short_term,
  whole_building, income_restricted). Replace the 12 bundles in
  `config/reviews/` and the per-batch `*_projection.py` / `*_revision.py`
  modules with one overlay mechanism and one projection step.

### Codebase and artifacts

- [ ] **Collapse the model module chain.** The main fit spans
  `bayesian_floor_spline_experiment → feature_experiment_v3 → v2 →
  feature_model → rent_model` plus graph/execution/disk modules; `models/`
  has 151 scripts including `_v2/_v3/_v4` copies and eight
  `*_fit_comparison.py` variants. Since the protocol hashes implementation
  files, git SHA + protocol JSON is sufficient for reproducibility: one
  `model.py` with an explicit versioned spec, old versions in git history.

- [ ] **Artifact retention.** `data/model/` is 284 GB over 408 directories;
  the selected fit is 16 GB with unit-effect draws stored three times (zarr
  trace, `posterior.nc`, report cache). Keep the raw trace only and derive
  the rest; retain protocol + summary + coefficients + residuals for every
  run and full posteriors only for selected and last-N.

- [ ] **Documentation shape.** Keep one short README, one
  `docs/model/current.md` rewritten on promotion, and dated notes under
  `docs/log/`; `main-model-evolution.md` already notes that
  `current-analysis.md` is stale.

- [ ] **Concurrent agents.** Use worktrees or branches per agent; the working
  tree currently carries uncommitted changes from two streams.

## Remote fit execution

- [ ] **Benchmark PyMC fitting on Modal: large CPU versus GPU** — user research
  idea, September 19, 2026. Compare local execution with a large CPU instance
  and a GPU on Modal using the same analytical dataset, model specification,
  full-length sampling protocol and convergence requirements. Prioritize the
  round-trip data burden: inventory the exact analytical inputs required for a
  reproducible fit and the fit products required for local contribution,
  residual and counterfactual analysis; measure their uncompressed and
  compressed sizes, file counts, upload/download times and transfer costs.
  Make per-fit transfer burden the primary decision criterion: report bytes
  uploaded for the analytical dataset and bytes downloaded for the usable fit
  bundle separately for a cold run, an unchanged-data refit and a data refresh.
  Report total turnaround and cost, separating transfer, environment startup,
  compilation, sampling, diagnostics and export. Compare first runs with
  repeated fits using unchanged or incrementally updated data; evaluate caching
  immutable inputs and reusing unchanged artifacts by content hash. Identify
  which raw traces, caches and intermediate products can remain remote without
  compromising local analysis, complete posterior uncertainty or reproducibility.
  Verify a downloaded fit bundle loads and reproduces the same local analyses
  before recommending an execution setup. Do not judge speed from short
  warmup/draw runs dominated by startup costs.
  A [local footprint study](../analysis/modal-transfer-footprint-2026-09-19.md)
  now measures the expanded analytical input at 286.7 MB uncompressed / 45.8 MB
  with gzip, and the original spline's inferred offline analysis closure at
  4.586 GB. These are local measurements and code-inspection findings; remote
  transfers, posterior compression and a clean bundle roundtrip remain untested.
  September 22 progress: `models/modal_remote_fit.py` uploads inputs as SHA-256
  blobs (cold 291 MB in 12 s; unchanged refit 0 bytes; one-file edit 10.8 KB),
  rebuilds the dataset at its original absolute path so the remote protocol
  equals a local one, and downloads verified fit/protocol bundles. A 100/100
  smoke fit matched the local protocol except draws/tune/seed, with byte-identical
  design files, for $0.052 billed. September 23: a full-length refit reproduced
  the local protocol hash, ran in 55.4 min for $0.38, downloaded 4.39 GB in 141 s,
  and agreed with the local fit within Monte Carlo error. It narrowly missed the
  R-hat gate (1.0103 on `alpha`), so loading a converged remote bundle in
  `BayesianAnalysis` is still open. Details:
  [remote fitting record](../analysis/modal-remote-fitting-2026-09-23.md).

The items below continue the September 22 Modal sampling campaign. Probe data:
`data/model/modal-runs/probe-*-20260922`.

September 23 findings (L4, NumPyro, 4 chains, 300 warmup + 100 draws;
`data/model/modal-runs/prec{64,32}-l4-20260923`):
- float64: 511 leapfrog steps every iteration, 0 divergences, max R-hat 1.11,
  median/min bulk ESS 922/38. nutpie on CPU needs about 50-90 steps, so a
  full-length NumPyro fit would take about 4.4 h on the L4, against about
  22 min of CPU sampling.
- float32: every iteration hit maximum tree depth (1,023 steps), chains did not
  move (ESS 4, R-hat infinite). float32 fails for this model as written.
- nutpie JAX backend with PyTensor gradients (canary, early warmup): about
  4 ms per step per chain on L4, against 2.3 ms on one CPU core. The ~30 ms
  single-chain cost below comes from JAX's own autodiff of this graph.
- Current conclusion: nutpie/Numba CPU remains fastest and cheapest per fit;
  Modal's benefit is running fits concurrently at about $0.35-0.40 each.

- [ ] **Single-chain JAX gradient is ~12× slower than one CPU core** — user
  directive, September 22, 2026. The spline model's logp+gradient takes about
  30 ms for one chain on H100, A100 and L4 (22 ms on the local RTX 2060 SUPER),
  against 2.6 ms for Numba on one CPU core, yet a vmapped batch of 4 chains
  costs only about 1.3 ms. nutpie's JAX backend with PyTensor-built gradients
  measured about 4 ms per step, so the cost is concentrated in JAX's own
  autodiff (likely the transposed per-unit/per-building gathers). Profile the JAX
  graph (e.g. `jax.profiler`, HLO dumps), identify the slow ops, and test
  equivalent formulations (segment sums, sorted indices, one-hot or sparse
  matmuls) in a new graph module. Show exact log-density/gradient parity with
  the frozen graph before any sampling. This decides whether nutpie's JAX
  backend, which evaluates chains one at a time, is viable on GPU.
- [ ] **Measure nutpie JAX on GPU** — the PyMC-developer recommendation as of
  June 2026. Only a 30-draw canary has run (about 4 ms/step/chain on L4). Run nutpie `backend='jax'` with `gradient_backend` pytensor and jax,
  4 chains and nutpie's shorter default tuning on H100 and L4. Compare wall
  time and ESS per second and per dollar with nutpie/Numba CPU, and with
  NumPyro vectorized chains.
- [ ] **Many vectorized GPU chains** — NumPyro's window adaptation needed 511
  steps per draw (see above), so batched chains lose on gradient count. Next,
  test adaptation built for many chains
  (BlackJAX ChEES/MEADS, or nutpie's normalizing-flow adaptation). Report
  lockstep leapfrog cost, warmup length needed, and ESS per dollar at
  24,000 retained draws.
- [ ] **float32 sampling** — log-density error is 5e-7 relative and gradient
  error 0.07% scaled, but NumPyro float32 sampling failed (see above). Revisit
  only with a rescaled model or a different sampler, with explicit tolerances.
- [ ] **CPU multi-chain scaling** — on a 16-core Modal container, aggregate
  Numba gradient throughput plateaued at about 2 chains' worth (4 processes:
  2× slowdown each; 16: 12.8×), probably memory bandwidth on a shared host.
  Repeat on dedicated or other CPU types before ruling out more-chains CPU fits.
  Any chain-count change needs a new sampling module, since
  `bayesian_disk_sampling.py` (`cores=min(chains, 4)`) is hashed into fit
  protocols.
- [ ] **Post-sampling report stage** — about 30 of the local fit's 56 minutes
  are single-threaded diagnostics and reports after sampling. Profile it and
  parallelize it across chunks or processes, or run it as a separate remote
  job. Faster samplers alone cannot cut a fit below this floor.
- [x] **Posterior transfer** — the complete 4.39 GB bundle downloaded in 141 s
  (31 MB/s). Experiments now download summaries only by default; `complete`
  fetches the posterior for promotion candidates.
- [ ] **Marginal R-hat for `alpha` at 6,000 draws** — the remote refit reached
  1.0103 against the 1.01 gate, with the same protocol that passed locally at
  1.0036. Assess whether the intercept's slow mixing warrants more draws,
  reparameterization, or a gate that accounts for run-to-run variation.

## Floor representation

- [ ] **Gaussian process for the floor increment model** — user research idea,
  September 19, 2026. Explore correlated increments across listed-floor levels
  using a Gaussian-process prior in PyMC. Compare against the selected natural
  cubic spline on the same frozen source cohort. Evaluate joint floor contrasts,
  coefficient uncertainty, prior sensitivity, residuals and full-length sampling
  diagnostics/work. Record kernel and length-scale assumptions explicitly;
  evaluate increments versus a GP on floor-price levels as distinct choices.
  This is a research candidate, not a change to the selected main model.

- [ ] **Random walk for floor increments** — user research idea, September 19,
  2026. Let neighboring floor increments vary while encouraging each increment
  to stay near the previous one (equivalently, a joint neighbor-difference
  penalty links it to both neighbors in the interior). Explore a learned
  innovation scale and an explicit starting/anchoring prior in PyMC. Distinguish
  a random walk on increments from a random walk on the floor-price levels;
  compare both interpretations with the GP and selected spline using the same
  frozen cohort, joint contrasts, prior sensitivity and full-length diagnostics.

## Floor measurement

- [x] Audit why the selected model has only 56.8% floor coverage. The
  [complete census](../analysis/chelsea-floor-coverage-reassessment-2026-09-19.md)
  identifies omitted formats and reviews all six new-rule disagreements.
- [x] Broaden the initial label parser beyond one/two digits plus one letter.
  Audit numeric labels, wing prefixes, multi-letter suffixes and floor-only
  labels against own-advertisement evidence and building numbering. Keep
  advertised labels separate from physical height and preserve source conflicts.
  The published expanded source reaches 68.36% observation coverage and is now
  used by the selected main fit after the matched refit and source/UI review.
  See the [source experiment](expanded-floor-source-experiment-2026-09-19.md).
- [x] Project the five confirmed reference-photo floor errors at 160 W22 through
  source-bound corrections, preserving their raw claims and separate numeric
  label evidence. Keep the 244 W16 `1RE` label/prose discrepancy explicit.
- [x] Complete and assess the full matched spline refit on the expanded source,
  including residual/source reviews and the support-dependent prior change,
  before updating the selected main analysis. The selected fit passes all full
  posterior gates and actual UI checks; the fixed 26-row panel gets slightly
  worse, and this is not claimed as a uniform residual improvement. See the
  [results](../analysis/chelsea-expanded-spline-floor-results-2026-09-19.md).
- [ ] Improve explicitly scoped description-floor extraction using the three
  corroborating cases in the [expanded-source panel](../analysis/chelsea-expanded-floor-source-panel-2026-09-19.md):
  a `53RD FLOOR!` headline, `3rd floor of a walkup building`, and `this 11th floor`.
  A replay of each full description through `attribute-evidence-v6` still yields
  no advertised-floor claim. Preserve photo-reference and shared-amenity scope
  protections; the current label projection already recovers matching values.
- [x] Recover initial named-unit introductions with explicit second/third-floor
  wording at 139 Eighth Avenue. The
  [v7 replay](../analysis/chelsea-named-unit-floor-extraction-2026-09-19.md)
  changes only eight captures for four reviewed ads across all 72,065 archived
  descriptions. These reveal existing label/prose disagreements; applying a
  source projection and resolving numbering remain pending below.

## Floor–elevator interaction

- [ ] Reassess the interaction on the expanded source after its matched base fit
  passes. The [support audit](../analysis/chelsea-expanded-floor-elevator-support-2026-09-19.md)
  has walk-up data only on floors 1–6, with especially thin floor-5-to-6 support.
  Check lower-floor contrasts, unit-effect pooling and opposing elevator claims;
  do not treat high-rise walk-up extrapolation as supported by the data.

## Source leads from the expanded-floor residual review

- [ ] Audit gross versus net-effective historical asks using explicit gross
  quotes and concession terms, beginning with 2834394, 2560481, 2362330 and
  2967520. The [full-description review](../analysis/chelsea-commercial-batch-two-2026-09-20.md)
  finds one exact net-effective arithmetic match and another mismatch. Align
  own-ad price events with dated concession evidence before any correction;
  later descriptions alone do not establish historical applicability.

- [ ] Distinguish base asking rent from mandatory recurring charges in renter
  cost comparisons. The [active-listing review](../analysis/chelsea-current-commercial-match-review-2026-09-20.md)
  finds four captured ads advertising a required $90-per-resident monthly fee.
  Preserve capture timing and explicit resident-count dependence; do not infer
  household size or apply later fee prose to historical prices. Evaluate a
  separate fee-inclusive comparison without silently changing the rent target.

- [ ] Apply evidence-bound residential-scope review to high-residual commercial
  offers: 1260588 explicitly offers professional/business loft space and 937046
  a turnkey restaurant with commercial terms. Verify exact own-capture witnesses
  and historical applicability, preserve quarantined records, and reassess
  contributions/residuals after a matched PyMC refit. Do not replace their prices.
- [ ] Resolve location/access conflicts in residual-tail advertisements 4953355,
  2993341 and 609730 before attributing their gaps to amenities. The first has
  third-floor-walkup prose but a captured condo/elevator/doorman record; the other
  two name locations inconsistent with their analytical building identities.
  Preserve conflicting claims; do not infer replacement addresses from residuals.
- [ ] Decide and document the analytical treatment of explicit SRO/shared-bath
  offers such as 2221592. Distinguish offered product scope from a conventional
  apartment's bathroom count, and test a supported representation or transparent
  scope sensitivity instead of treating the low asking rent as an error.

- [ ] Screen the complete retained cohort for commercial/event-space offers
  before another scope refit. The completed 27-case movement review found four
  more explicit cases: 1543471, 2391701, 806884 and 947730. Manually distinguish
  offered commercial products from residential home offices, live/work options
  and restaurant amenities. Preserve exact-ad evidence and avoid building-wide
  exclusions. Also review the composition conflicts on 790520, 1926797,
  4210456 and 916757, and unextracted explicit floors on 3967693 and 776029.
  See the [movement review](../analysis/chelsea-residual-scope-movement-review-2026-09-19.md).
  The [complete-cohort lexical screen](../analysis/chelsea-commercial-offer-screen-2026-09-19.md)
  now covers 71,806 captures and flags 667 rows (663 ads); manual adjudication
  remains incomplete. Initial full-text follow-up identifies explicit retail
  ad 1466274 and several mixed live/work offers requiring separate treatment.

- [ ] Test the retrospective same-ad attribute assumption against dated price
  changes, beginning with 1670174: initial ask $2,395, then $3,700 and $5,950,
  with later-captured luxury-duplex prose and a powder-room/count conflict.
  Define a temporal sensitivity without silently replacing initial asks with
  later prices. Also adjudicate 2833618's location/access evidence and 3591788's
  furnished/limited-term/service package and explicit second-floor claim. See
  the [candidate tail review](../analysis/chelsea-residual-scope-tail-review-2026-09-19.md).

- [ ] Review income-restricted rental products and dated price basis, starting
  with Port10 4761346 and 4758015, which rank fourth and eighth in the selected
  fit's absolute-log-residual tail. A full own-description language screen found
  12 candidates across five buildings, including distinct HDFC/AMI wording.
  Keep unmatched rows unclassified, separate minimum-income administration from
  eligibility ceilings, and verify historical timing before a coefficient or
  scope experiment. See the [research note](../analysis/chelsea-income-restriction-research-2026-09-19.md).
  The [full-description follow-up](../analysis/chelsea-income-claim-review-2026-09-19.md)
  reviews all 23 captures for the 12 candidates: nine explicit upper-bound
  claims, two AMI statements with unspecified boundary operators, and one
  restriction with unspecified terms. Preserve those distinctions and the
  furnished/short-term/utilities package on 4276224.

- [ ] Resolve the four newly reviewed label/prose floor disagreements at
  139 Eighth Avenue (4810936, 4817705, 4902655, 4968706) and the internally
  contradictory bedroom descriptions on 4837062 and 4902655. The first three
  floor differences are plus one, but 4968706 is plus two; do not apply a uniform
  building offset. Verify exact-unit identity, address association and numbering
  before a source projection. See the
  [full-description review](../analysis/chelsea-income-claim-review-2026-09-19.md).

- [ ] Resolve Lantern House 1704 / advertisement 4828991 bathroom composition.
  The fitted record has three full and zero half baths; its own description
  explicitly names a powder room and describes en-suite Jack-and-Jill bathrooms.
  Preserve the conflict until the number of distinct full bathrooms is supported;
  do not simply add a half bath to the existing full count. Review the related
  en-suite and shared-access evidence without counting one bathroom twice.
- [ ] Review 130 W17 / advertisement 3924616, fitted as three bedrooms and three
  full baths at a $4,500 historical initial ask. Its own sparse description does
  not establish those counts or justify a replacement; investigate structured
  records, exact-advertisement layout evidence and historical price scope.
  The large negative residual is a review signal, not a correction rule.
- [ ] Resolve the price basis for 3Eleven / advertisement 4982803. The analytical
  initial ask is $9,400, while the later captured description says two months
  free on a 14-month lease and "Net Rent Shown" without an explicit gross quote.
  Check the historical price event and concession timing before converting or
  excluding it; do not assume later prose applies to the initial ask.
  The three cases and their exact capture witnesses are retained in
  `data/model/chelsea-expanded-spline-floor-movement-review-inputs-20260919`.
- [ ] Review the dated offer scope for 406 W25 1FE / advertisement 1371705:
  the description offers furnished/unfurnished and short/long-term options.
  Establish which package the $2,850 historical initial ask represents before
  excluding or adjusting it. See the
  [complete movement review](../analysis/chelsea-expanded-spline-floor-movement-review-2026-09-19.md).
