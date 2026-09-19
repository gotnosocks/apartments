# Elevator negation source review

An extraction error converted “non-elevator building” into a positive elevator
claim. Reviewing the revised Chelsea cohort's 43 buildings with opposing
elevator reports exposed the error; checking the full description archive found
109 affected captures attached to 98 retained historical observations. Replaying
their original structured payloads supports **96 negative claims and two
unknowns because the structured amenity code contradicts the description**.

The observations represent 32 units in six buildings. Repeated advertisements
and repeated marketing copy are not independent physical evidence. No current
listing is affected, and this review does not resolve all 43 building conflicts.
Other inspected minority claims explicitly describe elevator buildings or
walk-ups, while some have only structured evidence. Neither a majority vote nor
an assumed installation/removal date adjudicates those cases.

| Building | Historical observations | Units | Structured/text conflict masks |
| --- | ---: | ---: | ---: |
| 120 West 20th Street | 1 | 1 | 1 |
| 120 West 25th Street | 36 | 13 | 1 |
| 124 West 25th Street | 33 | 9 | 0 |
| 126 West 25th Street | 25 | 7 | 0 |
| 259 West 19th Street | 2 | 1 | 0 |
| 266 West 22nd Street | 1 | 1 | 0 |

The 259 West 19th Street cases are advertisements 4417318 and 4931353;
266 West 22nd Street is advertisement 5118079. The two conflicted advertisements
are 2061471 and 3027101, covering three captures. Their `ELEVATOR` amenity codes
remain in the evidence alongside the literal negative claims. They are masked,
not declared to have or lack an elevator.

## Extraction and evidence

`attribute-evidence-v5` recognizes the adjacent `non` prefix with a space or
hyphen/dash, including a space after the hyphen. Literal evidence spans retain
the denial. A structured positive assertion plus a text denial resolves to
unknown. Unrelated uses such as “non-smoking building with an elevator” remain
positive; a double negation such as “not a non-elevator building” is withheld.
All other attributes and assertions must be unchanged in the replay.

The final replay is
`data/model/chelsea-elevator-negation-replay-final-20260919`. It verifies the
analytical source and description manifests, capture membership, historical
Parquet shard hashes, original listing JSON hashes, advertisement identities,
and literal description spans. It uses original structured payloads with the
source-bound recovered description text. Every attached capture of each selected
observation is included, including any without the triggering phrase. Here all
109 attached captures contain it, and all 109 elevator outputs change. The
frozen v4 extractor and final v5 implementation are archived with the evidence.

I inspected the distinct literal denial contexts across all 109 captures and
both structured/text conflict cases. The many West 25th Street advertisements
reuse essentially the same parenthetical building description. This is a
targeted regression review, not an independent accuracy estimate for elevator
extraction or verification of physical building access.

## Reviewed patches and model status

The append-only ledger is
`config/reviews/chelsea-elevator-negation-20260919.jsonl`: 98 dated edits, each
targeting an exact analytical row hash and advertisement. Each tests the old
positive value before replacing it with false or unknown. The all-time validity
applies only to that exact row version; it does not propagate to other units,
advertisements, dates or buildings. `recorded_at` dates the correction knowledge,
not a physical change in facilities.

`data/model/chelsea-elevator-reviewed-correction-preview-20260919` records the
verified dry-run result and ledger. Each edit matches one row and changes only
the elevator field. Re-running the review script reuses the existing ledger and
identical preview without appending duplicates. The parent datasets remain
unchanged. The subsequent projection is now published as described below;
a model refit is still required before these corrections enter contribution estimates.

The completed price-basis quarantine fit uses the frozen pre-correction source.
Its matched comparison is separate from these new feature corrections.
Do not claim the new elevator coefficients are corrected
until the ledger has been projected, its inverse verified, and the model refitted.
This review strengthens the case for checking elevator measurement before fitting
floor interactions; it does not establish any interaction premium.

Validation: 96 tests pass across attribute extraction, the replay audit,
source-audit integrations, analytical transformation and the correction ledger.
The actual replay covers all selected original captures, and the ledger preview
was checked for idempotence.

Reproduce the replay with `models.elevator_negation_audit`, passing the revised
price-basis dataset, refreshed description archive, historical export and raw
Parquet archive. `--previous-extractor` can point to the final bundle's
`previous-attribute-evidence.py`; use a fresh output directory when code changes.
Run `python -m docs.analysis.scripts.review_elevator_negation` through `uv` to
verify or recreate the exact reviewed ledger/preview.

## Completed analytical projection

`data/model/chelsea-reviewed-elevator-analysis-20260919` applies all 98 dated
edits to the 52,653-row price-basis-reviewed parent. Membership, asking prices,
22,155 unit identities, 1,129 buildings and all 172 current observations are
unchanged. Source clocks remain intact; correction knowledge is stored in each
appended review-history entry. The original raw captures are untouched.

Its hashed `elevator-corrections.jsonl` sidecar reconstructs the exact ordered
parent, including prior review history. The earlier `quarantined.jsonl` sidecar
is preserved so readers can reconstruct the whole lineage back to the original
description-bound cohort. Every correction requires all attached literal captures
and the original structured/text replay. An opposing assertion cannot be forced
to false. Repeated execution reuses the identical published projection.

The model, report and description readers now accept this exact revision and
verify both inverse layers. Full-data verification confirms that all 71,813
surviving description captures remain identical. The reader verification is
`chelsea-elevator-reader-verification-20260919`; 248 focused integration tests
pass, including 21 new correction/inverse cases. The final affected runner/report
subset was rerun after a diagnostic-message adjustment: 150 tests pass.

The freshly reconstructed full/reference and compressed PyMC graphs agree on
this corrected source at three parameter points: maximum log-density discrepancy
1.46e-11 and maximum gradient discrepancy 9.32e-10. See
`chelsea-reviewed-elevator-graph-parity-20260919`. This is numerical graph
equivalence evidence; it is not a new posterior or evidence that elevator
coefficients are already corrected.

## Controlled refit launched

Run `chelsea-bayesian-reviewed-elevator-disk-20260919` started at 10:08 UTC,
September 19. Session **93301**, host PID **587751**; log
`/tmp/chelsea-bayesian-reviewed-elevator-fit.log`. It uses four chains with
4,000 warmup and 6,000 retained draws, seed 20260924, target acceptance .93,
nutpie/Numba diagonal adaptation, shared Student-t scale, the same
full/half/balance specification, building/unit prior scales .35/.25 and floor
increment scale .15. The selected main model is the completed price-basis refit.

`chelsea-reviewed-elevator-protocol-comparison-20260919` verifies every declared
model, sampler and prior setting against that reference. Only source bindings,
source-reader code and the new inverse verifier differ. All 59 feature names
and coefficient prior scales match. Elevator's observed-value center changes
from .9310854 to .9285023 and its normalization scale from .2533088 to .2576543;
raw-unit prior contrasts therefore change slightly despite equal coefficient
prior scales. This must be reported in the posterior comparison.

Keep this run's mathematical, source-reader, sampling and report-cache
dependencies frozen until it is terminal. After completion, compare on exactly
the same observations: elevator raw contrasts and missingness, floor contrasts,
category/bathroom contributions, group offsets and current residuals. Review the
largest changes and preserve source-conflict notes before considering selection.
The comparison must describe 98 feature corrections and zero exclusions; the
earlier quarantine comparison's exclusion terminology must not be reused blindly.

## Comparison prepared while sampling

`models.elevator_fit_comparison` now verifies the exact correction inverse and
matched sampling protocols, then compares the completed fits on all 52,653
identical observations. It independently reconstructs each design and refuses
changes to unrelated feature columns. It reuses the established residual,
common-reference building, category, bathroom and floor comparison calculations.
The quarantine comparison's fit-loading helper was extracted without changing
its comparison semantics; sampling and source-reader dependencies remain frozen.

The new elevator contrasts use all joint coefficient draws for known no → yes,
known no → unknown, and known yes → unknown. Unknown is a reporting state;
its contrast includes both the numeric and missingness coefficients and their
posterior covariance. Each derived interval must pass its own convergence gate.
The comparison reports each fit's raw-contrast prior standard deviation and
normalization; it never pairs independent fits' draws to create a posterior of
the change. The source-movement review accepts this comparison and will inspect
the three largest distinct current-unit movements using additive posterior mean
log contributions.

`chelsea-elevator-comparison-inputs-20260919` verifies the actual 98 corrections,
unchanged membership and prices, and unchanged unrelated design columns before
the posterior is available. The induced prior standard deviation for the
no-elevator → elevator log-price contrast is **.5921626 → .5821754**, a 1.69%
reduction from normalization alone. This is input evidence, not a posterior
result. Reproduction: `uv run --frozen --no-sync python -m
 docs.analysis.scripts.check_elevator_comparison_inputs` (one command).

Validation: **79 tests pass** across the elevator comparison, existing quarantine
comparison, joint category contrasts and source-movement review. These include
full-draw posterior covariance, failed convergence, changed prices, unrelated
features, protocol changes and posterior-coordinate mismatches.

A follow-up observer (session **10625**, script
`/tmp/chelsea-elevator-refit-followup.py`, log
`/tmp/chelsea-elevator-refit-followup.log`) watches the existing fit process. After
terminal completion and accepted diagnostics it will calculate category
contrasts, the matched elevator comparison, and the three current contribution
movement reviews. It never restarts sampling or changes the main selection.
Expected outputs are `chelsea-reviewed-elevator-category-contrasts-20260919`,
`chelsea-reviewed-elevator-fit-comparison-20260919`, and
`chelsea-elevator-current-contribution-movements-20260919`. They are pending,
not completed evidence. An observation deadline leaves the original fit untouched.

At 10:29:41 UTC the existing fit entered trace export; by 10:32:21 UTC all retained
draws were exported and diagnostics/reporting began. The process remains live;
this is not yet accepted posterior evidence. A second observer, session **21465**
(`/tmp/chelsea-elevator-source-review-followup.py`, log of the same stem), waits
for the comparison observer to exit and verifies all three completed artifacts.
Only then does it regenerate the eight existing current-source cases against
the new posterior. Changed case membership or failed diagnostics stops that
review. It does not sample, restart jobs or change the main selection. Expected
output: `chelsea-elevator-current-residual-source-review-20260919`.
