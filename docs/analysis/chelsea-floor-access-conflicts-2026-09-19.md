# Floor-relevant elevator source conflicts

The seven conflicting buildings that contribute explicit floor observations have
409 retained historical/current rows. I reviewed **all 20 positive-elevator
advertisements plus one explicit negative example per building: 27 observations,
44 attached captures**. Each selected capture was replayed from its hash-verified
original listing payload, using its verified archived description. All 33 positive
and 11 negative capture results reproduce the stored elevator value. This review
found source contradictions, but no new demonstrated elevator extraction reversal.
It does not resolve all 42 buildings with opposing access reports.

Eleven of the 20 positive advertisements have only structured `ELEVATOR` assertions;
nine also or exclusively have literal elevator statements. Lack of a textual
statement does not negate a structured assertion. Repeated copy and repeated
captures are not independent evidence about physical access.

| Building | Positive ads reviewed | Negative example | Finding |
| --- | ---: | --- | --- |
| 142 West 17th | 7 | 4912875 | Earlier elevator copy and later explicit walk-up copy; no established change date. |
| 180 Seventh Avenue | 1 | 1359089 | Positive structured code, description says one flight; stair access alone is not elevator absence. |
| 222 West 16th | 3 | 2573624 | Repeated elevator/laundry copy conflicts with walk-up and off-site laundry descriptions; literal floors also disagree with some unit labels. |
| 259 West 15th | 1 | 2022952 | Explicit positive elevator/third-floor advertisement versus walk-up duplex descriptions. |
| 327 West 14th | 2 | 4714469 | Elevator/laundry studio copy versus later full-floor advertisement explicitly saying no elevator. |
| 340 West 17th | 5 | 3038235 | Positive copy and structured claims; one positive ad has a separate address and price-basis conflict detailed below. |
| 350 West 18th | 1 | 4067869 | Sole positive structured assertion in 2022; explicit walk-up descriptions before and after, including 2023. |

These observations do not establish an installation/removal, a physical unit move,
or a building-wide true value. The earlier support sensitivity that excludes
opposing-claim buildings remains useful; a majority vote is not a source correction.
The model's floor/access intervals must retain this measurement uncertainty as a
separate limitation. A coefficient's posterior interval does not include it.

## Advertisement 3193768: unresolved gross price and address

Both original payloads identify **340 West 17th Street #2A**, building ID 11576,
and the same canonical unit URL. Both descriptions end with **344 West 17th
Street** and call the unit a third-floor studio in an elevator building.
This is a direct structured/text address mismatch. I have not established that
these addresses share an entrance, represent a complex, or identify the same
physical apartment. No address or unit label is overwritten.

Both descriptions distinguish **$2,595 monthly rent** from **net monthly cost
2,379 with one month free**. The original structured price, sole price-change
amount, earliest own ACTIVE event and analytical target are all **$2,379**.
The ACTIVE date label is August 27, 2020; the original price-change timestamp is
also retained separately. The descriptions were captured in September 2026.
Their terms cannot be silently assigned a 2020 effective date.

The earlier complete-cohort lexical screen found this ad as a generic net mention,
but its priority rules did not recognize the dollar-sign-free `2,379` quote or
`Net monthly cost` construction. Its record is preserved in
`chelsea-literal-rent-basis-audit-v4-20260919`; no prior audit artifact is rewritten.
A scan of that verified audit's retained cases found only this advertisement with
the exact `net monthly cost` phrase. That narrow scan is not a complete recall
assessment for other dollar-sign-free pricing language.

The new exact-row recommendation is **quarantine unresolved gross price basis**.
It preserves both captures, exact quote spans, original pricing and own ACTIVE
records, and the structured address. It does not replace $2,379 with $2,595,
compute a concession-adjusted number, infer a floor, or decide which elevator claim
is true. It is an **unapplied recommendation** on the current elevator-corrected
source, so the running interaction comparison still uses identical observations
in both models. A future source revision must preserve this recommendation's
row/clock binding and reversible lineage, then be refitted before analysis.

## Evidence and validation

The immutable evidence bundle is
`data/model/chelsea-floor-access-conflict-review-20260919`. It contains the
27 reviewed rows, all 44 original-payload/capture records, per-capture elevator
claims, exact original listing/event shard hashes, seven building review notes,
and the one price-basis recommendation. Review knowledge time is
September 19, 2026, 11:24:42 UTC; original source and price clocks remain intact.
No source rows or main selection changed.

Forty-one focused tests pass across the closed recommendation and existing
quarantine contract. They reject other advertisements or targets, missing attached
captures, changed original price/address evidence, changed literal quotes, raw-hash
mismatches, failed initial-event checks and impossible knowledge clocks. The
actual replay verifies all selected original payload hashes and source identities.

Reproduce with:

```sh
UV_CACHE_DIR=/tmp/apartments-uv-cache uv run --frozen --no-sync python \
  -m docs.analysis.scripts.review_floor_access_conflicts
```
