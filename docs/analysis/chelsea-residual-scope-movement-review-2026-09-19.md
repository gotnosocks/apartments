# Residual-scope candidate: full movement-panel review

All 27 selected cases were reviewed using every distinct full own-advertisement
description. This panel comprises the 25 largest distinct-unit fitted-price
movements plus examples for the five largest unit-effect and common-reference
building-effect movements, with overlaps. It is a diagnostic selection, not a
representative sample or a residual-tail ranking. One building example cannot
adjudicate all its apartments.

The review finds **four further explicitly commercial offers**, composition
conflicts and useful feature/extraction leads. No source values, scope decisions,
posterior or main selection were changed. The converged candidate remains an
intermediate experiment; promotion is deferred while the broader commercial
screen and UI loading issue are addressed.

## Residential-scope findings

| Ad | Raw own address | Own-description finding |
|---|---|---|
| 1543471 | 163 West 23rd Street #3F | Explicitly offers all commercial uses and space to start a business. |
| 2391701 | 148 West 24th Street #2B | Fully built recording studio, commercial co-op, employee/client space and commercial lease terms. |
| 806884 | W #4 | Daily/weekly event and office venue; prose says price unavailable. Canonical building association is not a substitute for the malformed own address. |
| 947730 | 520 West 27th Street #303 | Explicit gallery/office commercial condo for showroom and retail events. |

Seven exact raw captures corroborate these descriptions and identities. Raw
prices are preserved: 1543471 changes from $6,000 to $6,500, 2391701 reports
$10,000, 806884 changes from $2,500 to $2,000, and 947730 reports $15,125.
These are source quotes, not verified monthly residential rents. Prepare
exact-ad scope exclusions after a complete cohort screen; do not convert
commercial recording studios into zero-bedroom apartments or exclude whole
buildings based on these advertisements.

This is especially relevant to building-effect interpretation: 2391701 is the
selected example for 148 W24, whose candidate common-reference building-effect
median is about +0.805 log units. It does not establish a residential amenity
premium. At 133 W14, by contrast, the reviewed retained ads 4811825, 3967693,
4189081 and 3883529 describe residential condos consistently; a previously
excluded location-conflict ad is not evidence against all siblings.

## Composition and floor findings

- **790520:** one reported full bath versus three baths in prose; five reported
  bedrooms versus configurable, build-to-suit loft space. Explicit second/third
  floors describe a multilevel apartment, not a single floor to insert blindly.
- **1926797:** two reported bedrooms versus a currently one-bedroom layout with
  possible conversion to two or three; preserve actual versus potential layout.
- **4210456:** four reported bedrooms versus three bedrooms and a dedicated
  office in the description. Label 5AE is not an explicit floor statement.
- **916757:** bedroom prose mixes two bedrooms, a convertible den and a fourth
  bedroom upstairs; review distinct present rooms before changing the count.
- **3967693:** explicitly “FLOOR TWO, UNIT ONE” and the entire second floor,
  while analytical floor is unknown. This directly illustrates why unit number
  and advertised floor must remain distinct. Virtual staging is not furnished
  availability.
- **776029:** explicitly a first-floor walkup, while analytical floor is unknown.
  Add to extraction follow-up alongside the second-floor claim in the tail review.

## Feature and product leads

1376670 explicitly offers furnished accommodation for 3–24 months; 754637 has
vacant or semi-furnished alternatives; 2021775's furnished offer is already
annotated in the candidate. Establish the package attached to each historical
price before assigning permanent attributes.

4153172 includes valet parking; 3865188 has a private attached garage reached
by a car elevator as well as passenger access. 3915487 and 2976274 have private
pools and terraces. 5083167 describes two en-suite baths for the primary suite.
These are bundled feature leads, not separately identified marginal premiums.
Future-tense services at Soori and One High Line must remain anticipated claims.

Whole-townhouse and duplex descriptions (4892020, 4316485 and others) reinforce
the need to distinguish interior levels from a single advertised floor. Numeric
building height in 610152's description is not unit-floor evidence. Remaining
cases and literal spans are included individually in the published queue; no
reviewed case is silently treated as verified physical truth.

## Evidence and next action

Inputs: `data/model/chelsea-residual-scope-movement-review-inputs-20260919`,
manifest `fee67720a2e5d9d6dfb4d163f6d2760a45c36fced708de26205b00396238867c`.
Output: `data/model/chelsea-residual-scope-movement-review-20260919`, manifest
`26a6949af94a168aa5f8f4a930dcb5b8b1dd10d0273209d91b0d09dd5069e70d`.
Publisher: `docs/analysis/scripts/review_residual_scope_movements.py`.
Publication verifies exact input binding, all 27 identities, every quoted span,
description hashes and seven raw witness hashes; complete bundle verification
passed. Findings remain research records, not applied UI annotations.

Next, screen the entire retained cohort for commercial/event-use wording and
manually adjudicate candidates before batching another source revision and fit.
Preserve residential home-office, live/work, guesthouse and restaurant-amenity
cases unless their own offered product establishes nonresidential scope.

UI session 30395 ended with an AppTest 300-second timeout while switching to
the candidate selection. It did not pass. A diagnostic rerun uses a 600-second
limit and periodic stack traces; no posterior or expected-value checks were
relaxed.
