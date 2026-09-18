# Chelsea building and unit effects: source review

The largest fitted group offsets identify useful omissions even when their residuals are modest. The strongest new finding is **bathroom access**: all 16 modeled advertisements at 333 West 29th Street explicitly describe shared bathrooms or toilets, while the analytical bathroom total is 1 or 1.5. Treating these totals as private apartment bathrooms would misinterpret both the building discount and the bathroom contribution.

This audit uses the unchanged reviewed v3 model: 52,712 observations, 1,135 buildings and 22,166 units. It ranks building and unit offsets separately, selects the three largest positive and negative offsets in each family, and reviews deterministic median-ask, largest-residual and latest cases. Deduplication leaves 34 advertisement cases across 12 groups. All selected source descriptions were read, plus every advertisement at 333 West 29th Street. Findings do not apply corrections, exclusions or replacement prices.

## Building offsets

| Building | Conditional offset | Rows / units | Period coverage | Source finding |
| --- | ---: | ---: | --- | --- |
| Walker Tower | +60.3% | 26 / 11 | 2014–2023 | Elaborate finishes, en-suite bathrooms, views, private terraces/fireplaces and wellness amenities. Median fitted residual remains +32.4%. |
| The Cortland | +57.1% | 43 / 27 | 2022–2026 | Pools, wellness, concierge and luxury interiors. Latest 11EE description reports 786 square feet, absent from analytical size. |
| One High Line | +50.4% | 47 / 41 | 2023–2026 | Pool/spa, hotel services, luxury finishes and en suites. W7G advertises two bedrooms and three full plus one half bath; ask $17,000 versus fit $24,499. |
| 216 Seventh Avenue | −34.6% | 36 / 30 | 2015–2025 | Four advertisements contain rent-stabilization wording, including the latest representative case. This does not establish legal status for every unit or period. |
| 416 West 25th Street | −27.5% | 74 / 43 | 2010–2026 | Median-ask and largest-residual examples explicitly describe basement apartments. Seven advertisements mention basement. |
| 333 West 29th Street | −26.8% | 16 / 15 | 2015–2019 | Every advertisement describes shared bathrooms/toilets; two distinguish a private shower from shared toilets. Many include utilities. |

These are offsets within the existing parameterization, not causal building premiums. The high-end buildings bundle many features that the current model does not separate. The low-end examples identify accommodation/access, regulation claims and below-grade position that should be measured before interpreting their offsets as quality discounts.

## Unit offsets

| Unit | Conditional unit offset | Ads | Source finding |
| --- | ---: | ---: | --- |
| Irvin House PHA | +17.9% | 7 | One-bedroom penthouse with over 1,000 square feet of private outdoor space; a separate shared building roof deck is also described. |
| Chelsea Club 902 | +17.4% | 7 | Two private terraces totaling over 1,000 square feet, private elevator access and included parking. These are bundled omissions. |
| 100 Eleventh Avenue PHB | +17.4% | 7 | Full-floor luxury penthouse, panoramic views and two terraces. One 4BR advertisement describes three bedrooms plus a possible fourth/office. |
| 316 West 19th Street 1E | −17.6% | 11 | Usually described as a true 2BR/2BA duplex; the largest-residual advertisement markets a flex 3BR. |
| 317 Tenth Avenue 3 | −11.7% | 9 | A 4BR advertisement explicitly lists two private and two railroad bedrooms. Later ads use 2BR; the latest distinguishes retail laundry downstairs from a building amenity. |
| 147 West 14th Street 14 | −11.3% | 5 | Studio with storage loft; latest description specifies fifth-floor walk-up and no building laundry. Interior area is unknown. |

Unit offsets are residual adjustments **within building**, conditional on other modeled features. They are not standalone market premiums. Repeated advertisements also do not constitute independent physical measurements. The observations support testing bedroom privacy/flexibility, below-grade and walk-up position, private outdoor area, parking inclusion and private elevator access. They do not justify rewriting bedroom counts or assigning physical conversion dates without stronger source evidence.

## Support and shrinkage

The rankings retain rows, distinct units, advertisements, months, date range, residual summaries and final Huber-weight totals. For example, Walker Tower has 26 observations but only 17.22 summed Huber weights; 19 rows are downweighted. PHB has seven observations and 3.43 summed weights, with six downweighted. Large fitted offsets and large remaining residuals can coexist when robust fitting and regularization resist outlying prices.

The reported conditional shrinkage factor is `sum(final Huber weights) / (sum(final Huber weights) + group ridge penalty)`, holding other coefficients and weights fixed. It is **not** an effective sample size, posterior uncertainty or the marginal shrinkage of the joint model. Current penalties are 10 for buildings and 8 for units. Coupled building/unit effects and omitted amenities make a Bayesian joint uncertainty analysis useful, but it must not reinterpret these existing point estimates as posterior results.

## Next modeling priorities

1. Separate private apartment baths from shared bathroom/toilet access before interpreting full/half or bedroom-relative bathroom increments. Preserve unknown access where no source supports it.
2. Compare incremental bath effects and bed–bath interaction for supported layouts; One High Line W7G is a useful high-bath-count case, not grounds for a model-driven correction.
3. Measure flexible/railroad bedrooms, basement position and included parking/private elevator access. Use the source cases as development cases and reserve additional cases for evaluation.
4. Audit same-advertisement interior area recovery, keeping building amenities and private outdoor area separate. Do not carry later descriptions backward across advertisements.

## Reproducibility

- Runner: `models/group_effect_audit.py`.
- Exact inputs: `data/model/chelsea-reviewed-analysis-20260918-v3/{model,dataset,protocol}` and `data/model/chelsea-analysis-descriptions-20260918`.
- Immutable rankings and 34 source cases: `data/model/chelsea-group-effects-20260918`.
- Immutable findings and full-building scope evidence: `data/model/chelsea-group-effects-source-review-20260918`.
- Rankings SHA-256: `13306c93a5b607582a351c7b11b58ac91436cb990d424f49e24f7df61cb67da9`.
- Runner SHA-256: `fbdcb621a198cf28152715854090311f6707f0b5c00d4dd3762cf55213945253`.

Both inputs and description hashes/identities are checked; protocol settings must belong to the exact model. Deterministic replay reproduced the ranking bundle. Four focused tests cover support weighting, separate tails, representative selection/deduplication and rejection of mismatched source identity/hash/protocol.
