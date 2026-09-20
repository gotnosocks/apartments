# Full review of income-screen candidates

The two large Port10 residuals motivated a broader screen. I have now read all
**23 attached captures, containing 12 distinct full descriptions**, for its
12 advertisements in five buildings. Every candidate contains an own-offer
eligibility claim, but their terms differ. This completes the full-description
review that was still pending in the [initial screen](chelsea-income-restriction-research-2026-09-19.md).
It does not establish historical eligibility or a common price discount.

## Eligibility findings

| Ads | Own-description finding | Remaining ambiguity |
|---|---|---|
| 4758015, 4761346 / Port10 | Explicit minimum income, household maximum ranges, no guarantors. | Preserve the awkward ranges; do not assign a separate maximum to each household size from their order alone. |
| 4276224 / 228 W17 | Explicit one-tenant ceiling below $163,150; a two-tenant amount of $186,540. | The two-tenant sentence omits the comparison operator. |
| 4160254 / 425 W18 | Minimum $105,000 and one-person maximum $176,220. | Other household sizes and historical applicability unknown. |
| 4488024 / 456 W17 | 165% AMI, explicit one/two-person ceilings, claimed rent-stabilized lease. | Source claims have not been independently established as legal classifications. |
| 4968706, 4817705, 4837062, 4902655 / 139 Eighth Avenue | Explicit 120% AMI maximum and HDFC wording. | No dated AMI schedule or quantitative price effect established. |
| 4810936 / 139 Eighth Avenue | HDFC wording and requirement to meet 120% AMI. | No explicit maximum/minimum/equality operator. |
| 4780384 / 139 Eighth Avenue | Requirement to meet 120% AMI and use a guarantor. | No explicit operator; this description itself does not name HDFC. |
| 3705384 / 425 W18 | Explicit reference to restrictions for this unit. | No program, threshold or direction supplied. |

Thus nine ads contain an explicit upper-bound claim, two contain an AMI
eligibility statement without an explicit boundary operator, and one leaves the
restriction terms unspecified. Five of the six 139 Eighth Avenue descriptions
name HDFC; all six mention 120% AMI. This refines the initial screen's grouped
description rather than copying one ad's language across its building.

Five 139 Eighth Avenue ads condition guarantor use on income below 40 times the
rent. Advertisement 4780384 instead requires a guarantor without stating that
condition. These application requirements are separate from upper eligibility
ceilings. None of the twelve is merely a conventional minimum-income screen,
and none explicitly negates its own eligibility requirement. Unmatched ads in
the wider cohort remain unclassified; this review does not establish recall.

All price observations are historical initial asks, dated October 2021 through
February 2026; descriptions were captured September 9–11, 2026. The source does
not independently date these terms to those initial asks. Numerical thresholds
cannot be treated as durable building/unit attributes or silently backdated.

## Additional source findings

Full review also found four disagreements between the fitted label proxy and
explicit prose about the named apartment:

| Advertisement | Named unit in prose | Fitted label floor | Prose floor |
|---|---|---:|---:|
| 4810936 | 1A | 1 | 2 |
| 4817705 | 2D | 2 | 3 |
| 4902655 | 1b | 1 | 2 |
| 4968706 | 1C | 1 | 3 |

These offers are associated analytically with 139 Eighth Avenue, while their
descriptions name 300 West 17th Street. This review does not decide whether the
addresses are aliases or establish physical-floor numbering. The fourth case
prevents treating all four as evidence for one uniform plus-one offset. Preserve
label and prose claims separately, verify exact-unit identities and numbering,
and then make an explicit source projection if justified. The existing fitted
`listed_floor` values are documented label proxies, not verified physical floors.

Ads **4837062 and 4902655** each call the same offer both one bedroom and two
bedroom in adjacent sentences; both fitted records contain two bedrooms.
Neither phrase alone justifies a correction. Ad 4780384's studio that could be
flexed to one bedroom and ad 4810936's one-bedroom that could be flexed to two
are different: their hypothetical conversions should not increase the current
bedroom count.

Ad **4276224** is furnished, short-term only until April 30, with utilities
included; no year is stated for that end date. Its offered package is another
potential price factor. Eligibility alone should not be credited for its price.
Ad 4488024's description of three flights up remains distinct from a floor
number; this review does not convert stair flights into a replacement floor.

## Recorded review and next experiment

`docs/analysis/scripts/publish_income_claim_review.py` publishes **19 unresolved
annotations on the 12 exact source observations**: twelve eligibility findings,
four floor disagreements, two bedroom conflicts and one furnishing/term/package
finding. Each records complete attached captures, literal spans, source-row
identity, observed fitted values and review clock `2026-09-20T01:56:00Z`.
The artifact is `data/model/chelsea-income-claim-review-20260919`. Publication
and independent public-reader verification completed successfully, and a
subsequent full bundle hash check confirmed all 19 issues on 12 observations.
The manifest SHA-256 is
`b35c848066a967b47618c19a8738a0292c3ad10a90b2b090eb78c1a9ce5dc564`.
All reviewed literal phrases were checked against the complete captures before
publication. No full identical replay of this new 19-issue publication was run.

The observations and initial lexical queue remain bound to source manifest
`d244ca6710e080e18059f1b3279a373e187ea38fb4219c51deff7e49f4604717`,
evidence manifest
`79308dfdbefd7fe8a03630bdd048fa742d0f7cd3335b82f25da0575a9d9b7e08`,
and screen manifest
`d78ffa03d01381754a4a52f538cbab5ec81a96f5c3c005f06b289ba0b3bc1f10`.

The ongoing four-ad residential-scope fit is unchanged. No eligibility
coefficient, correction, exclusion or main-page annotation selection is applied
by this review. After that fit is assessed, use the dated source issues to
prioritize identity/floor resolution and a separately specified eligibility
sensitivity. Within-building and repeated-unit support must be examined before
claiming a common marginal restriction effect. Small residuals for most of these
ads do not resolve the source problems or show an absence of eligibility effects.
