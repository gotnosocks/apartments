# Lease and product scope: source-led research ideas

A rental advertisement can quote a different product even when the apartment's physical features are identical. This offline review searched four new phrase families across the verified 52,712-observation description archive and read 12 distinct-unit examples. It proposes six contribution/residual hypotheses without changing any dataset, feature, price, or model.

| Seed family | Candidate observations | Units |
|---|---:|---:|
| Furnished / unfurnished | 3,199 | 2,169 |
| Short term / minimum lease / stated lease duration | 3,170 | 2,481 |
| Lease break / takeover / assignment / transfer | 401 | 373 |
| Stabilization / income requirements or ceilings / AMI | 538 | 432 |

These are overlapping wording counts, not verified product prevalence. The 12 reviewed examples deliberately include ordinary, affirmative, conditional, prohibited, and misleading meanings; their proportions are not a precision estimate.

## Twelve source-linked examples

| Ad | Reviewed meaning | Why it matters |
|---|---|---|
| 2177694 | Furnished common second-floor deck | Does not establish that the apartment is furnished. |
| 4158120 | Apartment explicitly unfurnished | Useful affirmative negative evidence; missing furnishing wording is different. |
| 1274438 | Six-month furnished rental, including linens/dishes | Furniture, services and duration are bundled; a single furnishing coefficient may mix products. |
| 5117087 | No Airbnb or short-term rentals permitted | A short-term keyword would reverse the meaning. Generic lease-break fees are also not an offered takeover. |
| 2044201 | Long or short term offered; conditional prepayment/security | The quoted ask is not unambiguously tied to one duration. Other apartments' price ranges are not this unit's ask. |
| 3028719 | Explicit net-effective rent with six weeks free over 13 months | Review target basis before treating lease length as an amenity. No gross rent was inferred. |
| 795050 | Lease break; pressurized conversion wall already up | Transfer scope and existing advertised layout can jointly explain a residual. This does not establish legal bedroom status. |
| 1436358 | Possible tenant discount for a specific takeover move-in window | Conditional, unquantified concession; not an observed rent correction. Existing lease expiry and possible renewal are described. |
| 2727948 | Source claims rent $1,000 below comparable lines until lease expiry; renewal resets to market | Potential bargain is a temporary contract opportunity, not necessarily a persistent unit-value discount. |
| 4640109 | Unit advertised as rent stabilized | Source claim only; not legal verification or a building-wide rule. |
| 4837062 | Advertised HDFC maximum 120% AMI plus a separate 40× guarantor condition | An income ceiling and an income-screening rule have different meanings. Copy also says both one and two bedrooms; unresolved. |
| 1306978 | Ordinary 40× income screening and a one-year lease | Not evidence of a maximum-income housing restriction or regulated rent. |

## Concrete tests to pursue

1. **Furnishing × duration:** compare explicitly furnished and explicitly unfurnished products within supported building/layout/size groups, separating included furniture from optional offerings and common-area furnishings. Test duration interaction and included services rather than assigning one universal furnishing premium.
2. **Temporary contract discount:** examine lease-transfer residuals using remaining offered term, documented renewal/reset wording and conditional tenant subsidies. A source-claimed below-market contract may explain a negative residual that should not persist in an apartment-quality counterfactual.
3. **Price basis before lease-length effects:** audit net-effective quotes before adding duration or seasonality terms. Free weeks change the meaning of the target. Preserve original quotes and use only separately supported basis decisions; do not manufacture gross rent from ambiguous conventions.
4. **Eligibility and advertised regulation:** assess whether unit/date-specific stabilization or maximum-income claims explain negative unit/building offsets. Keep legal verification separate, missing claims unknown, and ordinary minimum-income screening out of the income-ceiling category. Eligibility also affects whether a listing belongs in a user's feasible search set.
5. **Transfer × conversion:** jointly review partitioned-bedroom layouts and bathroom balance in large-residual transfer cases. An existing conversion wall, a proposed conversion, and a lease-transfer opportunity are different measurements.
6. **Incomplete product quote:** compare explicitly scoped lease offers with flexible-duration listings whose price depends on term or prepayment. Keep quote uncertainty visible in bargain rankings rather than assuming every ask represents the same annual unfurnished lease.

The immediate research value is better measurement and source review. These examples do not identify causal coefficients or justify blanket exclusions. Historical descriptions were captured retrospectively on the same advertisements; their wording does not prove which terms were available at the initial historical asking-price event.

## Reproducibility

Artifact: `data/model/chelsea-lease-product-scope-research-20260918`.

`examples.jsonl` preserves exactly 12 cases with audit/ad/unit/capture identities, raw/body/description hashes, source and knowledge clocks, full reviewed source text, and literal/context offset snippets. `hypotheses.json` specifies measurement requirements, proposed comparisons and false-positive meanings. Seed patterns, cohort-bound manifests and the standalone publication script are retained. Interpretation time: **2026-09-18T20:40:09+00:00**.

Publication replayed exactly. An independent check verified all 12 distinct-unit identities, description hashes, literal offsets and context offsets. No new reusable extraction module, analytical patches, model edits, image downloads, or network requests were introduced.
