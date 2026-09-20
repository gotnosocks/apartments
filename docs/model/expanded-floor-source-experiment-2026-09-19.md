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

The analytical prior check quantifies the size of that change. For the
floor-versus-floor-2 log-price contrast, prior standard deviation changes from
0.11812 to 0.13347 at floor 45 (+13.00%, the largest proportional change on
common observed floors), and from 0.12702 to 0.11773 at floor 52 (−7.32%).
Changes at floors 10 and 20 are below 0.003% in magnitude. Matching the scalar
coefficient scale therefore does not make this a pure data-only experiment,
especially in the upper tail. These are prior spreads, not posterior premiums.

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

The live run subsequently completed sampling and entered trace export at
`2026-09-20T00:30:16Z`. Export finished and diagnostic/report generation started
at `2026-09-20T00:32:40Z`; the 4.1 GB posterior checkpoint and complete bounded
report cache are present. This records processing progress only. The final fit
manifest and convergence assessment were pending at that checkpoint.

The process subsequently exited successfully and published the completed fit at
`2026-09-20T00:48:42Z`, with status `exploratory_converged`. All convergence
gates passed: parameter maximum R-hat 1.003982 / minimum bulk ESS 820.7;
derived-effect maximum R-hat 1.002146 / minimum bulk ESS 1,129.4; floor-contrast
maximum R-hat 1.002856 / minimum bulk ESS 1,895.2. There were no divergences or
tree-depth hits. This establishes a usable completed posterior, not promotion:
the matched comparison and source/UI reviews are the next assessment steps.

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

## Post-fit assessment sequence

After the sampler, export and diagnostics finish, run
`models.expanded_floor_fit_comparison` against the selected spline and its
parent source. The candidate must pass source reconstruction and the same
sampling/contrast diagnostics before its residuals are used for decisions.
The comparison explicitly reports both the added floor evidence and the change
in the induced curve prior from moving the boundary knot.

Reuse the frozen 26-row `chelsea-floor-development-panel-20260919` with
`docs.analysis.scripts.compare_floor_development_panel`. For this source
revision the panel remains bound to the comparison's reference source;
membership, original cells, identities and prices must match. Separately
regenerate the eight current-source notes with
`docs.analysis.scripts.review_current_residual_cases` against the candidate,
retaining both floor-provenance layers. The current source observations are a
dated capture cohort, not a newly selected representative test set.

Review the largest distinct-unit fitted-price movements and the largest
unit/building effect movements using their own advertisement evidence.
`models.source_movement_review` can additionally decompose the leading
movements into additive posterior mean log contributions. Between-fit draws
must not be paired; these decompositions are not causal dollar allocations.

Check spline prior sensitivity on the completed posterior, including any
withheld results requiring a full PyMC refit. Prepare a separate candidate
selection containing the regenerated eight-case source review and the four
historical source issues. Exercise that selection in the real Streamlit page,
including a floor-only counterfactual and preserved historical warnings.
Only then assess promotion; the existing main selection stays in place until
these results have been inspected.

The adapted fixed-panel and movement-selection tests pass (15 tests), including
rejection of a panel bound to the wrong source or a changed target price.

The page verifier accepts explicit expectations in
`docs/analysis/expanded-spline-main-page-expectations-20260919.json`: 35,992
known floors, 134 known floors among the 172 current observations, exact source
and annotation hashes, and all four historical messages on three observations.
It derives prices from the completed joint posterior and checks actual UI
floor-only scenarios for advertisements 5155021 (2→3) and 4141846 (6→7), with
the respective warnings and source records preserved. The 21 verifier tests
and 13 page regression tests pass. A preexisting actual-selected-fit page test
timed out in the sandbox and was stopped; it is not claimed as passing. The
candidate's actual page run remains pending and should use the host runtime.

After creating the verified candidate selection at
`data/model/chelsea-expanded-spline-main-candidate-20260919.json`, run:

```bash
UV_CACHE_DIR=/tmp/apartments-uv-cache MPLCONFIGDIR=/tmp/apartments-mpl \
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
uv run --frozen --no-sync python -m docs.analysis.scripts.check_spline_main_page \
  --selection data/model/chelsea-expanded-spline-main-candidate-20260919.json \
  --expectations docs/analysis/expanded-spline-main-page-expectations-20260919.json \
  --output data/model/chelsea-expanded-spline-main-page-validation-20260919 \
  --timeout 300
```
