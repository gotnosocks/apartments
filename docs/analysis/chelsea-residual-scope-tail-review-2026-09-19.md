# Residual-scope candidate: newly exposed residual tail

The candidate's fifteen largest absolute log residuals contain eleven previously
reviewed apartments and four newly exposed cases. Exact source rows and every
attached capture match for the eleven reused reviews. Their findings are
preserved with updated ranks and residuals; a changed ranking is not new evidence.
All fifteen prices are historical initial own-advertisement asks.

The four new cases were reviewed using their full descriptions. Five raw listing
witnesses (two for 831056) were retrieved from the local archive and checked
against the capture hashes. No scraping, numerical corrections, scope exclusions
or main-model selection changes were made.

| Rank | Advertisement | Ask / fitted median | Finding |
|---:|---|---:|---|
| 12 | 831056 / 435 W23 | $18,000 / $7,383 | Generic London Terrace building marketing gives no unit-specific explanation for the high ask. |
| 13 | 2833618 / The Chelsea | $1,950 / $4,753 | Raw address/access versus description merits identity and location review. |
| 14 | 1670174 / 357 W20 | $2,395 / $5,837 | Bathroom conflict and substantial same-ad price changes expose a retrospective attribute-timing concern. |
| 15 | 3591788 / 463 W24 | $7,950 / $3,287 | Furnished, limited-term residence with service availability and an unextracted explicit floor claim. |

## Identity and access: 2833618

Raw capture 54054 identifies **160 West 24th Street #5H**, building 13058,
with elevator/doorman amenities. Its prose instead says “only 2 flights up” and
“A block away from McGolrick Park.” These are leads for resolving location and
access, not sufficient evidence to invent a replacement address or floor.
The own-ad price history supports $1,950. The advertisement was ACTIVE and
DELISTED on August 6, 2019, about fifty minutes apart; brief marketing is a
review signal, not an exclusion rule. Other advertisements' prices in its
property history are not replacements for this ad's price.

## Bathroom and timing: 1670174

Raw capture 119549 reports one full bath and zero half baths. Its recovered
description names a powder room on one interior level and a separate shower
bathroom on another. This is a composition conflict. The prose's first and
second floors describe interior duplex levels, not an advertised building floor.

The own-ad price-change history is $2,395 on November 4, 2015, $3,700 on
November 7 and $5,950 on December 4. The analytical pipeline correctly retains
the initial ask under its declared rule. However, the description captured in
2026 describes a luxury, thousand-square-foot duplex; we cannot establish that
those attributes applied at the first price event. This provides a concrete
case for testing the retrospective same-ad attribute assumption, rather than
replacing an inconvenient residual with the later price. It does not prove
that the unit changed or that the original price was erroneous.

## Offer package and floor: 3591788

Raw capture 89963 supports the $7,950 ask and 463 West 24th Street #2 identity.
The full description advertises designer furnishings, 2–12 month stays and
daily room service availability. It twice explicitly identifies a second-floor
residence, while the frozen analytical floor remains unknown. The unit label
alone was unsupported by the existing parser; this is separate explicit prose
evidence for the extraction follow-up.

Review furnished/term/service evidence at advertisement/capture scope. Available
room service is not necessarily included in the asking rent, and a restaurant
amenity does not turn an upstairs residential offer into a commercial listing.
These bundled differences do not independently identify a furnished premium.

## Reproduction and limits

Publisher: `docs/analysis/scripts/review_residual_scope_tail.py`. Input bundle:
`data/model/chelsea-residual-scope-tail-review-inputs-20260919`, manifest
`d9958d01af045de9e31802762d22e56df79b16b40942edb715e8be5c67e3f93c`.
Output: `data/model/chelsea-residual-scope-tail-review-20260919`, manifest
`422d3603470c1cae0aa07246470cb3a8091ab659659a4b504bede2edcab2528f`.
The output retains fifteen findings, literal description offsets, five raw
witnesses, exact prior-review references, source/fit bindings and the publisher.
Publication and complete file-hash verification passed.

The eleven reused findings are documented in the
[previous residual review](chelsea-expanded-fit-residual-research-2026-09-19.md).
These research findings are not applied UI source annotations. The separate
27-case movement review and candidate UI validation remain outstanding.
