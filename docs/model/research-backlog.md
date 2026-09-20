# Chelsea pricing research backlog

## Remote fit execution

- [ ] **Benchmark PyMC fitting on Modal: large CPU versus GPU** — user research
  idea, September 19, 2026. Compare local execution with a large CPU instance
  and a GPU on Modal using the same analytical dataset, model specification,
  full-length sampling protocol and convergence requirements. Prioritize the
  round-trip data burden: inventory the exact analytical inputs required for a
  reproducible fit and the fit products required for local contribution,
  residual and counterfactual analysis; measure their uncompressed and
  compressed sizes, file counts, upload/download times and transfer costs.
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
