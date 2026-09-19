# Reported same-floor laundry experiment

This experiment splits **239 historical observations, 138 units and 15 buildings**
from accepted `in_building` laundry to `on_floor`. Every attached source capture
must explicitly report shared laundry on the same floor, without conflicting or
uninstalled-equipment evidence. All 172 current observations remain identical.
The complete fitted cohort stays at 52,863 observations, 22,189 units and 1,131
buildings. The accepted main model has not changed.

The question is whether **explicitly reported same-floor access** contributes
useful conditional price information beyond generic building laundry. Generic
building laundry can already be on the same floor. This is not an estimate of
the physical value of moving a laundry room, nor evidence of an installation
date. The [source overlap review](chelsea-laundry-identification-2026-09-19.md)
explains the distinction and the weak support for an explicit no-laundry effect.

## Source and model controls

`models/laundry_floor_projection.py` publishes an idempotent analytical projection
over the accepted floor/laundry-corrected source. It preserves raw captures and
all prices, identities, observation dates and other attributes. The appended
evidence records literal description offsets, capture/payload hashes, the
measurement manifest, and a separate interpretation time. The inverse verifier
reconstructs every parent row and the entire ordered source hash. The fit and
report readers verify this lineage and archive its implementation.

The full-data design check establishes:

- All non-laundry model columns, centering values and prior scales are identical.
- Floor support and increment priors are identical; the previous floor 9 masking
  comparison's induced prior change does not recur here.
- The saved time design is byte-identical.
- Feature count rises from 59 to 60; both matrices have full column rank.
- Every pairwise laundry contrast retains log-price prior SD
  `sqrt(2) × 0.15 = 0.212132`. The joint laundry prior nevertheless has an extra
  dimension and different category centering; it is not entirely unchanged.

The measurement time is `2026-09-19T06:10:30Z`. Repeating the projection with that
same time verified and reused identical output. Focused integration checks passed
147 tests; downstream fit, disk, analysis, evidence and floor-design checks passed
127 with one skip. Four additional withholding tests passed with the other 19
projection tests (23 total).

## Evidence concentration and accepted baseline

The exact restricted split has generic-building overlap in **13 buildings** and
38 units observed in both categories. Only five buildings contain distinct units
that consistently report each category across their observed histories. The
Thomas Eddy contributes 103 of 239 same-floor rows and 101 West 23rd Street
contributes 94: together **82.4%**. Adding 135 West 24th Street brings the share
to 88.3%. This concentration warrants inspecting these buildings' residual and
group-effect movements before interpreting the added coefficient broadly.

The accepted corrected main fit's in-unit versus generic building-laundry
association is **+2.413% [2.068%, 2.761%]** (95% conditional posterior interval).
Its joint contrast passes diagnostics: R-hat 1.00038, bulk ESS 8,649, tail ESS
12,068. Endpoint overlap is 284 buildings and 1,412 repeatedly observed units.
This remains an association conditional on the fitted building/unit/time and
other features, not the return from installing a washer/dryer.

The category analysis now reconstructs the exact V4 source and design and checks
all transitive design dependencies, without demanding that an unused sampling
launcher still match the local checkout. Frozen source/protocol/posterior
integrity and convergence checks remain enforced. Real baseline reconstruction
and all 16 category contrasts pass; 18 category-analysis/sensitivity tests pass,
including rejection of rehashed design, prior, source and mathematical-code
changes. No baseline resampling was needed.

## Fit and interpretation plan

The launched fit uses the same PyMC Student-t specification and priors as the accepted corrected
fit, nutpie/Numba on CPU, four chains, 4,000 warmup and 6,000 retained draws per
chain, seed 20260924, target acceptance .93, diagonal adaptation. Exact
compressed/reference graph parity passed at three points across 23,462 gradient
parameters (maximum log-density difference 5.82e-11, gradient difference 8.50e-9).
The first sandbox attempt failed on a read-only compiler cache; the host rerun
completed successfully, without changing the graph. Require
the existing parameter, contribution and joint-floor convergence gates before
interpreting intervals.

Compare jointly sampled laundry contrasts, uncertainty, residual movements and
building/unit effect movements against the accepted fit. Inspect the largest
changes in the original source, including buildings supplying most of the new
category. A small in-sample residual improvement alone is insufficient to promote
the factor. The main selection remains unchanged pending this assessment.

The [preselected residual source review](chelsea-laundry-residual-source-review-2026-09-19.md)
examined eight units / ten original captures. It finds an explicit net/gross
target-basis issue, a studio/one-bedroom conflict, a short-term offer, and two
missed same-floor phrases. These require a separate source revision and limit
what the current reported-detail coefficient can establish.

Artifacts:

- Source: `data/model/chelsea-reported-laundry-floor-analysis-20260919`.
- Measurement: `data/model/chelsea-full-cohort-laundry-v3-20260919`.
- Full design check: `data/model/chelsea-laundry-floor-split-design-20260919`.
- Numerical graph check: `data/model/chelsea-laundry-floor-graph-parity-20260919`
  (complete).
- Support concentration: `data/model/chelsea-laundry-floor-split-support-20260919`.
- Accepted baseline contrasts: `data/model/chelsea-corrected-main-category-contrasts-20260919`.
- Running fit: `data/model/chelsea-bayesian-laundry-floor-disk-20260919`.

Reproduction scripts: `models/laundry_floor_projection.py`,
`docs/analysis/scripts/verify_laundry_split_design.py`, and
`models/verify_reviewed_floor_graph.py`. The main source remains
`data/model/chelsea-reviewed-floor-masked-analysis-20260918` until a later explicit
selection step.
