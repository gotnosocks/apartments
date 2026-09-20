# Complete-cohort commercial-offer language screen

The retained source was screened without using residual size, price, or building
effect as a selection criterion. This expands the review beyond the four
commercial ads found in the movement panel. No exclusions, corrections, model
features or selection changes were applied.

| Coverage | Count |
|---|---:|
| Retained analytical observations | 52,649 |
| Attached own captures scanned | 71,806 |
| Rows without attached evidence | 0 |
| Empty-description captures | 547 |
| Out-of-cohort evidence records skipped | 259 |
| Candidate rows | 667 |
| Distinct candidate advertisements | 663 |
| Distinct candidate units | 394 |

All four movement-review commercial ads (1543471, 2391701, 806884, 947730)
are recovered. Candidate counts overlap by pattern: commercial wording 120,
event-space wording 369, office-space wording 169, retail/showroom wording 16,
and one each for business use, recording studio and daily/weekly rental.

This is **complete coverage of the attached descriptions under declared lexical
patterns**, not proof that all nonresidential offers were found. Empty prose,
unmatched language and historical changes remain unresolved. Each candidate
retains its exact analytical row, all attached full descriptions, capture hashes
and literal match offsets, including nonmatching captures for that same row.

## Initial full-description follow-up

Seven additional advertisements were selected from commercial/product wording
for full-description review. This is a first adjudication batch; the other
screen candidates have not all been manually reviewed.

| Ad | Finding from full own description | Next treatment |
|---|---|---|
| 1466274 / 109 W28 | Explicit 2,000-square-foot ground-floor retail lease for a pop-up store, with visible store frontage. | Verify exact raw witness and prepare exact-ad nonresidential quarantine. |
| 3261015 / 525 W29 | Explicit commercial loft, but says it can have space for two bedrooms. | Resolve offered use and potential versus existing bedrooms; do not automatically reclassify as a two-bedroom home. |
| 3065554 / 227 W20 | Studio for professional use, with tub/shower, cooking gas and laundry. | Ambiguous offered-use language despite residential equipment; preserve for scope adjudication. |
| 1337652 / 106 W28 | Commercial space explicitly offered for living and working, subject to landlord acceptance of the work. | Keep separate mixed live/work category for sensitivity; no blanket commercial-word exclusion. |
| 668834 / 106 W28 | Work/live loft with commercial lease, described as ideal for home or small business. | Review mixed use and lease/product basis. |
| 613436 / 805 Sixth | Work/live loft, commercial lease, explicitly marketed to residents working from home. | Review mixed use and lease/product basis. |
| 1540611 / 520 W27 | Commercial condo with living/dining facilities, explicitly usable as live/work. | Review mixed use; a commercial label alone does not resolve offered residential use. |

The three live/work cases with explicit permission are not evidence of legal
residential occupancy; this review records marketing claims without making a
legal determination. No replacement rents, counts or addresses are established.

## False-positive burden and review method

The event-space matches are dominated by repeated amenity lists, including
The Chelsea's conference room, extended living room, event space and espresso
bar. Commercial-grade appliances, former industrial building uses, neighborhood
retail, home offices and explicit prohibitions on solely commercial use also
match broad patterns. Those contexts explain why this screen cannot safely
drive automatic exclusions. Matching snippets are triage evidence; complete
descriptions remain necessary for final scope decisions.

Next, group repeated descriptions/contexts to make manual review manageable,
while retaining every ad and capture association. Review the remaining unique
commercial and office/event contexts, then batch confirmed exact-ad exclusions
through the reversible scope projection and refit. Leave ambiguous mixed-use
offers visible in a separate sensitivity group.

### Completed priority batch

Exact full-text grouping is now published at
`data/model/chelsea-commercial-review-groups-20260919` (manifest
`49d393e968f3c0ae81e087b0c5f23c1087296621b65de40c46a2d6fcb324d29f`).
It retains all 944 capture associations across 546 distinct descriptions.
The candidate rows comprise 662 historical asks and five capture-time ACTIVE
observations; ACTIVE does not establish live availability.

All 37 priority descriptions have been read in full, covering 38 ads. The bound
manual review at `data/model/chelsea-commercial-priority-review-20260919`
(manifest `55b6cc4cccc474c3d39fc824a30c0cfd9161c4af21d8edddc3d245157b4243dc`)
records five explicit nonresidential offers, two ambiguous uses, eleven mixed
live/work offers and twenty incidental commercial references. The five explicit
cases are the four movement-review cases plus retail ad 1466274. The other
509 description groups remain unreviewed by this batch.

The mixed-use category preserves home/live-work marketing, including explicit
prohibitions on solely commercial use. Incidental references include historic
building uses, another ground-floor commercial unit, loft styling and a
noncommercial-use data disclaimer. These classifications concern offer language,
not verified legal occupancy or historical effective dates. No exclusions were
applied. Fifteen screen/grouping tests pass, including preservation of distinct
ad/capture associations, nonmatching attached captures, negation and rejection
of corrupted identity/hash/span evidence.

## Reproduction and validation

Run `uv run --frozen --no-sync python -m
docs.analysis.scripts.screen_commercial_offer_language` with `--dataset`,
`--evidence` and `--output`. This run uses the residual-scope source
`data/model/chelsea-residual-scope-analysis-20260919` and evidence
`data/model/chelsea-refreshed-bayesian-descriptions-20260918`.

Output: `data/model/chelsea-commercial-offer-screen-20260919`, manifest
`cd15f51866365e5f7ad68f4f517a031120e049c42bebc1edbe6da7b62c9c43d9`.
Publication and full artifact hash verification passed. Eight tests cover known
commercial leads, Unicode offsets, preserved negation/amenity context and the
absence of automatic classification. The scan binds the source and evidence
manifests and rejects mismatched own-ad identity or changed description hashes.

## Separate UI failure

Diagnostic UI session 96503 terminated with exit 139. Its only stack fragment
was in Python JSON encoding; that fragment does not establish the cause.
The earlier session 30395 timed out while selecting the candidate. Neither run
passed, and no completed candidate page-validation artifact was published.
Investigate loading/lineage verification in isolation before another UI run;
do not treat the failure as posterior nonconvergence or relax numerical gates.
