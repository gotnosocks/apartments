# Explicit dwelling-floor wording from residual review

Attribute evidence v8 adds two bounded description rules prompted by the
residual movement review:

- Advertisement 3967693 starts `FLOOR TWO, UNIT ONE`. The explicit floor is 2;
  the unit label supplies no floor number.
- Advertisement 776029 says `This first floor walk-up apartment`. The explicit
  advertised floor is 1, without inferring physical elevation.

The new rules accept a leading floor/unit headline using cardinal words one
through twenty, or “this” plus an ordinal floor and dwelling noun, optionally
with “walk-up.” They reject reference-media, shared-space, hypothetical and
negative language in the surrounding sentence. Wrapped lines do not reset
that sentence scope. Literal source spans and the rule identifier are retained.
Conflicting structured floor values remain visible as conflicts rather than
being overwritten.

All 163 focused attribute/named-floor/direct-floor tests pass. The fixtures
preserve complete, hash-checked own descriptions for both reviewed ads (three
captures), including later virtual-staging language on 3967693. Tests also
cover reference claims, questions, hypothetical offers, shared amenities,
independent unit labels, exact spans and structured/text disagreement.

The full description-only v7-to-v8 replay passed with
`docs/analysis/scripts/audit_direct_floor_offers.py`. It checks every archived
description, verifies source/capture identities, and requires every nonfloor
attribute, evidence item, warning and conflict to remain unchanged. It preserves
all changed captures for manual review. Output is published at
`data/model/chelsea-direct-floor-offer-replay-20260920` (session 96520, exit 0).
It scanned 72,065 captures and 40,531 distinct description inputs. Floor evidence
changed in 60 captures across 41 advertisements; all nonfloor interpretations
were unchanged. The two original reviewed ads are included. Other changes need
full-description adjudication before projection or coverage claims.

This is an extraction improvement under evaluation, not an applied source
projection. The running PyMC fit's frozen input is unchanged. Additional matches
and any source conflicts require review before claiming a coverage increase or
fitting a source revision. Historical effective dates and physical floors remain
separate questions.

## Full-description and raw-capture adjudication

All 41 distinct changed full descriptions have now been manually reviewed.
Each identifies the offered dwelling; none substitutes a reference photograph's
floor or a shared amenity's floor. The review preserves all 60 capture
associations. All 58 historical raw payloads were reloaded and hash-verified;
the two refresh bodies were decompressed, body-hash verified, reparsed and
checked against their exact raw-listing hashes. Complete-payload extraction
agrees with the description floor in every case.

There are 14 observations corroborating an existing floor, two disagreements,
and 25 previously unknown floors. Of the latter, 24 have unsupported label
syntax; the other is 5155202, already masked for a reviewed unit-numbering
issue. Do not remove that mask merely because the parser now recognizes its
known first-floor claim. A future projection can consider the 24 unmasked
observations after preserving the existing source policy and temporal scope.

The two disagreements are 4439603 (344 West 17th #1B) and 3332499 (433 West
24th #1C): both explicitly describe second-floor apartments while existing
label proxies give floor 1. The first ad separately says pictures are of a
similar unit but video is exact; that does not turn its independent explicit
“This second floor apartment” sentence into a photo-reference floor claim.
Neither description establishes a building-wide numbering offset or physical
height. Preserve both claims pending numbering review.

Secondary leads remain distinct: 3203696 describes a duplex, so its advertised
second floor does not summarize every level; 4165480 places laundry on floor 2
and the apartment on floor 5; 3809608/4398107 offer paid wash-and-fold service,
which is not an in-unit washer; 998539 advertises a six-month rental. These
findings motivate later feature/scope research without changing this floor review.

`docs/analysis/scripts/review_direct_floor_offers.py` publishes the full manual
review, original rows, extracted claims and all raw witnesses to
`data/model/chelsea-direct-floor-offer-review-20260920`. Publication, identical
replay and full artifact verification pass. The first attempt stopped because
refresh capture IDs are not historical integer IDs; the final helper explicitly
uses each capture's correct archive and verifies both paths. No source or fit
values changed.

The 24 unmasked additions are now prepared in
`data/model/chelsea-direct-floor-prepared-policy-20260920`. The preparation
verifies exact original rows and every attached capture, records literal claims
and capture clocks, and preserves all 17 other reviewed observations. Publication
and identical replay passed. The policy is explicitly unapplied; a reversible
source projection and reader validation are still required before fitting it.

## Reversible projection implementation

`apartments.direct_floor_projection` now limits this revision to additions of
previously unknown `listed_floor` and `advertised_floor` values. It preserves
independent label proxies, physical-height fields, existing masks, prices and
all other attributes. Each change records its complete original row, exact
reviewed decision, source index and new provenance. Validation replays every
addition forward and reconstructs the complete parent observations hash,
including unchanged siblings and row order.

Fifteen focused tests pass, covering the exact round trip, input immutability,
known-floor/mask rejection, typed and complete capture membership, future-dated
evidence, contradictory claims, and nonfloor tampering even when outer file
hashes have been recomputed.

The full 52,644-row projection has been launched with `models.project_direct_floors`
against the nine-ad scope-reviewed source and the exact prepared policy. Output:
`data/model/chelsea-direct-floor-analysis-20260920`; review clock:
`2026-09-20T05:19:23Z`. Completion, identical replay and public reader integration
remain to be verified before fitting. The selected model is unchanged.

The first full projection completed successfully: all 52,644 rows remain, and
canonical known advertised floors increase from 35,989 to **36,013**. The exact
parent inverse passed for the complete dataset. Output manifest:
`2a92f7a593895bcb9389742ef1378ddaf729ef73a9325f96bff4e975d05699fd`.
The 24 additions are a measured incremental improvement; the other reviewed
conflicts and masks remain unchanged.

The fit loader, report loader, evidence reader and full lineage verifier now
recognize this bounded revision and archive its contract with fit implementation
code. **354 focused tests pass**, including a complete synthetic ancestry with
the floor addition, rejection of unintended changes, preservation of older
source readers, and historical scope-comparison checks against their actual
archived implementations. The original scope comparator remains specific to its
completed experiment; it has not been broadened to certify the new floor refit.

`verify_direct_floor_readers` is running against the complete new source and
its parent to check unchanged literal evidence, ordered fit membership, full
ancestry and matched spline design. Output:
`data/model/chelsea-direct-floor-reader-verification-20260920`. Full-data reader
completion, identical projection replay, and a dedicated matched-fit comparison
remain outstanding. No new sampling has started.

The complete projection replay has now finished with the identical manifest
`2a92f7a593895bcb9389742ef1378ddaf729ef73a9325f96bff4e975d05699fd`,
confirming idempotent publication. The full reader verification has progressed
through literal-evidence checks to fit-loader and design checks and remains live.

`models.direct_floor_fit_checks` establishes the new comparison's protocol and
archived-code boundaries. It requires the same source population, floor support,
knots, priors and full 4-chain/4,000-warmup/6,000-draw schedule as the nine-ad
reference fit. Only the source bindings and exact reviewed loader plumbing may
differ; changed mathematical code is rejected. Fifteen additional tests pass,
including checks against the actual archived reference loaders and deliberate
model/population/loader mutations. These are preconditions, not evidence of a
completed fit or posterior comparison.

Full-cohort spline graph parity has been launched at
`data/model/chelsea-direct-floor-spline-graph-parity-20260920`. Sampling remains
pending successful reader/design and numerical graph validation.

## Full-data validation and refit launch

Both prefit checks completed successfully. Reader-verification manifest
`cd83bc53e4d45ad71bfdd1ceee82b7fcdaa0b86b12d6ca16066fc0f3ee6e4139`
confirms all 71,797 literal captures are identical, both designs have 47 columns
and rank 47, numeric normalization is identical, and knots remain
`[1, 5, 10, 20, 35, 57]` with reference floor 2.

Graph-parity manifest
`4402011b6c3210fc8075a2e62a411fdb458278db524a6c6734d3f1e6c24e99b0`
verifies three points and 23,403 gradient parameters. Maximum absolute log-density
difference is `4.37e-11`; maximum absolute gradient difference is `1.17e-9`.
All evaluated quantities are finite. These are numerical equivalence checks,
not evidence of posterior convergence or a sampling-speed benchmark.

The full matched PyMC fit is now launched at
`data/model/chelsea-bayesian-direct-floor-spline-disk-20260920`, using four chains,
4,000 warmup and 6,000 retained draws per chain, seed 20260924, diagonal adaptation,
target acceptance .93, maximum depth 10, shared residual scale and the same
building/unit/floor priors. Sampling and posterior checks remain pending.

`models.direct_floor_fit_comparison` now prepares the subsequent comparison of
floor curves, induced priors, residuals and unit/building contribution movements.
It checks exact parent restoration and separates newly known floors, previously
known floors, remaining unknown floors and capture-time active observations.
Seventeen comparison/guard tests pass, including canonical floor aliases and
rejection of rehashed source tampering and incomplete residual membership.
No fit comparison result or main-model promotion is claimed yet.

The emitted candidate protocol has been checked against the actual archived
nine-ad reference protocol. Only the two expected loader files changed, and
their exact syntax-tree changes match the reviewed addition. The new floor
contract is archived byte-for-byte. Check manifest:
`829bbfecf212f534020095d64384c8b61464d49fb6f84b12f21866b56fcc22dc`;
candidate protocol manifest:
`d5815edac0e47f2bb12d0b460bfccbfd10a35b13640743875966a017feac0252`.
All four chains have begun warmup; no posterior conclusion follows yet.

## Access support among the additions

The 24 additions are all historical initial-offer observations: five on floor 1,
nine on floor 2, seven on floor 3 and three on floor 4. Four have elevator=true,
two elevator=false and **18 unknown**, spread across six buildings. Their own
descriptions contain no elevator/walkup/flight/stair wording in the targeted
screen; absence of those terms is not evidence of elevator absence.

Full cached building descriptions were reviewed across ten captures. Three
buildings explicitly describe themselves as walk-ups:

- 162 Ninth Avenue: affects added-floor advertisement 3460328.
- 322 West 22nd Street: affects advertisement 3203696.
- 421 West 22nd Street: affects advertisement 998539.

The other three buildings (326 West 20th, 412 West 20th and 508 West 29th) remain
unresolved. Low height and family-count categories do not determine access;
encoded amenity references need separate recovery. These source claims do not
establish historical installation dates, and no elevator values were changed
in the running floor-only fit.

The exact raw building records, snapshot URLs/body hashes/capture times, literal
walkup spans and corresponding unit descriptions are saved in
`chelsea-direct-floor-access-support-20260920`, manifest
`34ebbadb89f6ad71251a5049eb893dfc0fbeb72bb0a9e13e8c9d4b9ec7efd963`.
Publication and identical replay pass. This is a concrete lead for later access
evidence integration; these 24 low-floor additions alone cannot establish the
high-floor walkup penalty or justify a floor–elevator interaction.

### Recovery of encoded building fields

All ten reviewed building bodies now have hash-verified recovery of their
`amenities`, `additionalDetails` and `nyc` fields. The recovery first finds the
exact original building object in the decoded body, then resolves only these
fields. Cyclic/missing references and excessive nesting fail closed; raw records
remain unchanged. Six focused tests and an identical ten-capture replay pass.

The recovered literal class descriptions are:

| Building | Captured class | Captured description |
| --- | --- | --- |
| 162 Ninth Avenue | C6 | Walk Up, Cooperative |
| 322 West 22nd Street | C6 | Walk Up, Cooperative |
| 326 West 20th Street | C0 | Three Families |
| 412 West 20th Street | C3 | Four Families |
| 421 West 22nd Street | R1 | Condominiums – Residential Unit in 2-10 Unit Building |
| 508 West 29th Street | C4 | Old Law Tenement |

The C6 descriptions corroborate two already reviewed walkup prose claims. The
other literal labels do not themselves specify elevator access. No elevator
absence is inferred from the recovered amenity lists or null values, and no
historical access correction is applied. A broader class interpretation would
need a separately documented classification rule and temporal qualification.

Recovery artifact: `chelsea-direct-floor-building-field-recovery-20260920`,
manifest `914cab66f74b9d72453e5cf94653418ea267bdad7d5e2f31a54e190a289ca035`.
The running fit and its frozen source are unchanged.
