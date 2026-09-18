# Source review of extreme groups in the accepted Bayesian fit

**Passing sampling diagnostics did not eliminate source-scope and identity problems.** Reviewing eight newly extreme groups found a retail listing, furnished/flexible-stay offers, net-effective pricing, conflicting geography, likely unit-label aliases and unresolved area definitions. These findings change what the offsets can mean; they do not authorize replacing prices or applying corrections automatically.

The audit uses `data/model/chelsea-bayesian-long-report-20260918`, whose parameter and derived diagnostics passed. It prioritizes six named buildings and the highest positive/negative units not reviewed in the earlier robust-model group audit. Each selected group has at most five advertisements, so all 23 advertisements and their 37 source captures were inspected. A deterministic median-ask representative is also recorded for each group.

## Estimates and findings

Intervals are 95% posterior credible intervals for conditional group adjustments in this Bayesian parameterization. Support counts refer to source unit identities, which are not independently verified physical apartments.

| Group | Offset [95% CrI] | Advertisements / source units | Source finding |
| --- | ---: | ---: | --- |
| 227 West 17th | +236.3% [+155.1, +330.5] | 5 / 4 | Furnished/flexible-stay loft offers, a net-effective PH ad, missing interior area and possible seventh-floor aliases. |
| 444 West 20th | +181.7% [+147.1, +220.1] | 3 / 3 | Large garden townhouse duplex; likely aliases, basement/outdoor-area ambiguity and optional commercial use. |
| 107 West 28th | +152.7% [+31.9, +220.2] | 1 / 1 | The only ad explicitly offers short-term retail/pop-up space, although modeled as a studio. |
| 362 West 23rd | −60.9% [−66.3, −53.9] | 2 / 2 | Two $1,200 studios with almost no descriptive evidence. Remains unresolved. |
| 109 Tenth Avenue | −54.5% [−61.0, −46.3] | 2 / 2 | Both descriptions say Washington Heights; structured addresses say Chelsea. One also conflicts on bath count. |
| 510 West 21st | −49.3% [−55.6, −41.9] | 3 / 3 | One ad says Inwood / 520 West 218 while its structured address says 520 West 21st. The other two remain unresolved. |
| 201 West 17th PHH, unit effect | +67.1% [+21.2, +97.4] | 4 / 1 | Designer penthouse, terrace, fireplace, views and bonus upper-level space; optional furnished pricing is separate. |
| 208 West 30th #403A, unit effect | −30.9% [−37.5, −20.3] | 3 / 1 | Consistent residential descriptions; no clear error or omitted disamenity established. |

## Strong source issues

At **107 West 28th**, [ad 1466532](https://streeteasy.com/rental/1466532) explicitly offers 2,000 square feet of ground-floor retail space for a short-term pop-up store. Its canonical unit label is `retail`, while the analytical row has zero bedrooms, one bath and unknown area. This is a direct residential-cohort scope review case. A single observation cannot support an interpretation of the group offset as residential building quality.

At **227 West 17th**, ads [701563](https://streeteasy.com/rental/701563), [1155670](https://streeteasy.com/rental/1155670) and [1376670](https://streeteasy.com/rental/1376670) describe a furnished 4,500-square-foot architect-designed loft under `/7thfl`, `/7th-fl` and `/7th-floor`. These may be aliases for one apartment, rather than three physical units. The latter two lack analytical square footage despite explicit text. [Ad 1951640](https://streeteasy.com/rental/1951640) states that its price is net effective. The later [PH ad 4398696](https://streeteasy.com/rental/4398696) instead describes a large renovated full-floor home with keyed elevator access. Product scope, price basis, identity and luxury omissions all require separate treatment.

At **444 West 20th**, `/gardendplx`, `/garden` and `/1` describe a similar two-bedroom garden duplex, so the three-unit support count may overstate distinct premises. [Ad 724330](https://streeteasy.com/rental/724330) has analytical area 3,150 square feet while its prose separately reports approximately 2,750 interior, 800 garden and 650 finished-basement square feet. The area definition is unresolved. Later ads offer optional showroom/office use while clearly describing a home; that does **not** establish commercial-only scope.

## Geography contradictions are within the source

Both **109 Tenth Avenue** descriptions—[2903770](https://streeteasy.com/rental/2903770) and [3050643](https://streeteasy.com/rental/3050643)—explicitly refer to Washington Heights. Original structured JSON instead identifies 508/500 West 17th Street, ZIP 10011. The latter description also advertises two bathrooms while the analytical count is one.

At **510 West 21st**, [ad 2926333](https://streeteasy.com/rental/2926333) explicitly names Inwood and “520 West 218,” but its structured address is 520 West 21st Street, ZIP 10011. [3004386](https://streeteasy.com/rental/3004386) and [3101995](https://streeteasy.com/rental/3101995) have generic residential descriptions and structured 514 West 21st Street addresses. Their true locations cannot be inferred from the first ad's conflict.

All ten archived raw-JSON captures for these five advertisements were checked against their already verified raw hashes. This establishes a disagreement between structured address and description. It does not establish a canonicalization bug, prove an uptown address or justify moving all records in either group.

## Cases that should remain uncertain

The two **362 West 23rd** descriptions contain only generic apartment wording. Low asks alone do not establish shared bathrooms, regulatory status, subsidy or a recording error.

At **201 West 17th PHH**, three $20,000 ads separately offer a furnished option at $22,500. The optional higher-priced offer is not evidence that the modeled $20,000 ask includes furnishings. Terrace, fireplace, designer finishes, views and the bedroom/library layout are plausible omissions; recorded area also changes from 2,400 to 2,216 square feet.

At **208 West 30th #403A**, the three advertisements consistently describe a one-bedroom/one-bath residence with elevator/doorman service, high ceilings and a shared roof terrace. The first explicitly says unfurnished. Nothing inspected explains the negative unit adjustment sufficiently to correct a feature or price.

## Interpretation and follow-up

Sparse building/unit divisions depend on pooling and priors. Unit effects are residual adjustments within the joint model, and their within-building average is not constrained to zero. The percentages above must **not be compared numerically with the old robust-model offsets** as though baseline, group allocation and shrinkage were unchanged.

Prioritize exact-advertisement scope/price-basis and location conflicts, then candidate unit aliases and area definitions. Keep optional furnished or commercial use distinct from a mandatory product category. Preserve unresolved cases; a large effect is a review signal, not evidence sufficient for a correction.

This audit applies no raw, analytical or model patches. Captures describe archived advertisements and do not establish physical effective dates. The selected extremes are a development review, not a population error-rate estimate.

## Reproducibility

- Selection/full source histories: `data/model/chelsea-bayesian-extreme-group-selection-20260918`.
- Classified findings, exact text spans and raw address checks: `data/model/chelsea-bayesian-extreme-group-source-review-20260918`.
- Accepted experiment protocol SHA-256: `1bb586f80ac1b8e994d03c0f9fa2713cb2e4bb7a09bc2c0f4961d8d64e6cbdde`.
- Source observations SHA-256: `6f4a05b01139d3d094ecaa2a7c305c02cb066e1c236dfe547c663a4d18b49b1f`.

Both bundles include their exact computation/publication scripts and verified input manifests. Identical replays reproduce the outputs. Source membership, capture identities, description hashes and highlighted spans are checked before publication.
