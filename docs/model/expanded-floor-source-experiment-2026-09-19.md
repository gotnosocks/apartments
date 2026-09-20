# Broader floor-label source revision

This experiment changes floor measurement on the same 52,653-observation Chelsea
cohort. It keeps the selected PyMC natural-cubic-spline specification, rather
than mixing a source expansion with a GP or random-walk model change.

The parent is `chelsea-label-floor-analysis-20260919`. The new projection admits
3–4 digit numeric labels using their hundreds portion, N/S wing prefixes,
front/rear suffixes (FE, FW, RE, RW, FR, RR, FF, RF), and explicit ordinal labels
ending in FL or FLOOR. Each observation uses only its own attached captures;
every capture must yield the same candidate. The existing building exclusions
remain, and new candidates require a captured building floor count that is at
least the inferred label. This count is a compatibility check, not a numbering
or physical-height map. Missing counts and out-of-range candidates stay visible
for subsequent measurement work.

Known source floors are preserved except five reviewed photograph-reference
errors at 160 W22. Their exact source-row versions receive append-only ledger
patches masking `advertised_floor=3`; numeric label inference is recorded
separately. Raw descriptions, original projection provenance, source clocks and
the correction/review clocks remain available. The 244 W16 `1RE` explicit floor
2 is retained, and unknown observations of that conflicting unit are excluded
from the generic label expansion.

The new projection must replay deterministically and invert to the exact ordered
parent observations and original floor sidecar. All prices, identities, dates,
nonfloor attributes and cohort membership must remain unchanged. Fitting and
description readers must verify both projection layers, and the selected older
posterior must remain readable.

Before a refit, compare the two source designs: spline knots/reference and prior
scales, floor support, nonfloor columns and normalization. Verify the revised
full-cohort direct versus compressed PyMC log density and gradients. Fit four
chains with 4,000 warmup and 6,000 retained draws, target acceptance 0.93,
diagonal adaptation, nutpie/Numba, max depth 10 and seed 20260924, matching the
selected spline experiment. Preserve exact saved sources and implementations.

Assess parameter and derived-contrast diagnostics, floor curves, coefficient
uncertainty, residual changes on identical observations, the fixed development
panels and the largest unit/building effect movements. Summaries from independent
fits must not be paired draw-by-draw to manufacture between-fit uncertainty.
Promotion requires completed diagnostics and source review. A higher count of
inferred floors alone does not establish better measurement or pricing analysis.

The GP and random-walk ideas remain in the [research backlog](research-backlog.md)
for subsequent matched model-specification experiments.

## Published source

`data/model/chelsea-expanded-label-floor-analysis-20260919` is now published.
Known floors increase from 29,907 to **35,992 / 52,653 observations (68.36%)**,
and from 95 to **134 / 172 capture-time ACTIVE rows (77.91%)**. There are 13,605
units with at least one known-floor observation. The expansion adds 6,085 newly
known rows: 4,748 numeric-hundreds labels, 502 wing-prefixed labels, 834 front/rear
suffixes and one explicit ordinal label. Five additional rows replace the
incorrect floor-3 claim with separately recorded numeric-label proxies.

The ledger is `config/reviews/chelsea-expanded-floor-masks-20260919.jsonl`.
Each patch targets the complete source-row hash and preserves the full reviewed
claim, capture identities and correction clocks in the projection policy. Exact
inverse/forward checks passed before publication. All 52,653 prices, identities,
dates and nonfloor fields are unchanged. No cross-advertisement floor copying
was used, and 244 W16 `1RE` retains its correctly extracted floor 2.

Remaining unknown statuses distinguish 12,725 unsupported labels, 1,367
above-count candidates, 992 missing building counts, 1,567 observations in
previously excluded buildings, three unknown-floor rows of the conflicting
`1RE` unit, and seven missing labels. These are explicit subsequent review
queues, not claimed absences of recoverable floor information.

The selected main fit still uses the parent source until the new full fit and
matched analysis pass. Publication alone does not update posterior estimates.

## Support-dependent spline boundary

The first design preflight rejected the assumption of identical floor knots.
Ten newly inferred 3Eleven observations have labels at floors 53, 54 and 57,
within its captured 62-floor count. Under the unchanged spline policy, the
upper boundary knot therefore moves from 52 to 57. Interior knots, floor-2
reference, coefficient count and coefficient scales remain unchanged, but
the prior over common floor contrasts changes. The source/design verifier now
records those prior standard deviations and covariances explicitly. No
high-floor rows are dropped to force an identical design or a passing check.

The revised full-cohort PyMC direct/compressed graph proof completed at three
parameter points. Maximum absolute log-density discrepancy is 2.91e-11 and
maximum gradient discrepancy is 4.07e-10 over 23,413 unconstrained parameters.
Artifact: `data/model/chelsea-expanded-spline-floor-graph-parity-20260919`.
This establishes numerical equivalence, not posterior convergence.

## Full source verification and fit launch

The full source/design/evidence verifier passed and published
`data/model/chelsea-expanded-floor-source-verification-20260919`. It restores
the exact parent, verifies all 47 feature columns, checks unchanged nonfloor
values and encoding, and verifies unchanged literal evidence for 71,813
linked captures. It records the changed common-floor prior covariance instead
of claiming identical function priors. The expanded source manifest SHA-256 is
`d244ca6710e080e18059f1b3279a373e187ea38fb4219c51deff7e49f4604717`.

The prescribed four-chain, 4,000-warmup/6,000-retained fit was launched at about
00:05 UTC on September 20 (September 19 locally), with output
`data/model/chelsea-bayesian-expanded-spline-floor-disk-20260919` and log
`/tmp/chelsea-expanded-spline-floor-fit.log`. Session 1989 owns this run.
Producer dependencies are frozen from launch. No completion or convergence
claim is made here; the selected main analysis remains the prior accepted fit.

Candidate analysis should also retain the separately published unresolved
source notes in `data/model/chelsea-expanded-floor-source-issues-20260919`.
These cover four issues on three historical advertisements (furnishing,
unextracted laundry and conflicting bathroom counts). They passed publication
and independent loading against the expanded source and exact description
archive; they do not alter this fit's inputs. The existing eight-case source
review still needs regeneration against the completed candidate posterior.

The [floor/elevator support comparison](../analysis/chelsea-expanded-floor-elevator-support-2026-09-19.md)
also replayed exactly. Expanded floor coverage strengthens lower-floor
within-building support, while walk-up observations remain limited to floors
1–6. This informs the next interaction experiment, not the currently running
source-only comparison.
