# Expanded-fit residual research: full-cohort tail review

This review ranks the selected expanded spline fit by decreasing absolute log residual, breaking ties by audit ID, and takes the first fifteen distinct units. It is a **true residual-tail selection**, not the earlier floor-movement panel. All fifteen selected observations are **historical initial own-advertisement asks**; none belongs to the 172 captured-current rows. “Remain in the current cohort” here means the currently selected fitting dataset, not current availability.

Every full own-advertisement description was read, with duplicate descriptions compared across attached captures. The frozen inputs bind the selected fit, source, evidence and residual hashes. This review changes no price, attribute, scope, fit or UI annotation.

## Ranked queue

Priority 0 means a source/scope issue to adjudicate before adding explanatory coefficients; priority 1 is an interpretable product/feature research lead; priority 2 needs genuinely new evidence. Prior review references below identify the named September 18 Bayesian residual review, not an exhaustive claim about every archived experiment.

| Rank | Ad / building | Ask / fitted median | Log residual | Priority and finding | Prior review |
|---:|---|---:|---:|---|---|
| 1 | 2477915 / 21-chelsea | $46,917 / $7,324 | +1.857 | P2: unresolved price | unresolved price |
| 2 | 652674 / 134-west-29-street-new_york | $28,681 / $5,387 | +1.672 | P2: unresolved price or scope | unresolved price or scope |
| 3 | 4953355 / 500-west-21st-street-new_york | $2,200 / $8,900 | -1.398 | P0: unit building access conflict | unit or building identity review |
| 4 | 4761346 / port-10 | $1,556 / $5,952 | -1.342 | P1: advertised income restricted | advertised income restricted |
| 5 | 4979243 / 225-west-23-street-new_york | $999 / $3,693 | -1.307 | P2: unresolved low price | unresolved low price |
| 6 | 1260588 / 163-west-23-street-new_york | $9,995 / $2,888 | +1.242 | P0: explicit nonresidential | Not found in named prior residual review |
| 7 | 937046 / 267-west-15th-street-new_york | $15,500 / $4,557 | +1.224 | P0: explicit nonresidential | Not found in named prior residual review |
| 8 | 4758015 / port-10 | $1,192 / $4,032 | -1.219 | P1: advertised income restricted | advertised income restricted |
| 9 | 4023400 / 305-west-20-street-new_york | $13,000 / $3,958 | +1.189 | P2: insufficient description | Not found in named prior residual review |
| 10 | 761202 / 299-10-avenue-new_york | $5,300 / $1,682 | +1.148 | P2: missing description | Not found in named prior residual review |
| 11 | 2221592 / 214-west-20-street-new_york | $767 / $2,100 | -1.007 | P0: explicit sro shared bathroom | Not found in named prior residual review |
| 12 | 609730 / the-cass-gilbert | $11,000 / $4,062 | +0.996 | P0: within source location conflict | Not found in named prior residual review |
| 13 | 3813894 / 181-9-avenue-new_york | $1,650 / $4,422 | -0.986 | P2: uninformative description | unresolved low price |
| 14 | 2993341 / 133-west-14-street-new_york | $1,875 / $4,902 | -0.961 | P0: within source location conflict | Not found in named prior residual review |
| 15 | 661080 / 151-west-17-street-new_york | $29,000 / $11,252 | +0.947 | P1: luxury terrace duplex bundle | Not found in named prior residual review |

## 4953355: strengthened existing identity concern

Ad 4953355 was **already reviewed**, contrary to the initial “unreviewed” working assumption. The September 18 review recorded the third-floor walkup versus 500 West 21st Street association as unresolved. That prior finding was retained deliberately; the new residual rank does not by itself supply a correction.

Both exact own raw captures (20401 and 62246) corroborate the following:

- `listingAddress` and structured street: **502 West 21st Street #2**; `buildingId=10801`; canonical `urlPath=/building/500-west-21st-street-new_york/2`.
- Full prose: “3rd floor walkup” and “Photos are of similar unit”. Structured own-listing amenities simultaneously include **ELEVATOR, DOORMAN, CONCIERGE, GYM and PARKING**.
- Advertised price, price-change history, own ACTIVE/DELISTED history and security deposit all say **$2,200**. There is no alternative supported replacement rent.
- Same-ad status became ACTIVE at 17:00:57 and DELISTED at 17:07:07 on January 22, 2026: **six minutes ten seconds**. The September captures preserve an already delisted historical offer, not a live apartment.

The captured building record (snapshot 1267) explicitly identifies building 10801 as a **Condo building**, eight floors, 32 residential units, built 2014, with building address 500 West 21st Street. This classification is observed in archived data, not inferred from the building name. Its exact raw-building hash is `912531ceed97c19d253d1bf0dd55e756a57dab94b96bc4f8237b2262be72e4d8`.

This strengthens an internal access/identity conflict. It does **not** prove that 502 is an invalid alternate address, that the prose or amenities must be the false claim, or where the apartment actually belongs. Recommended next action: preserve an exact-ad unresolved source issue and adjudicate a bounded identity/access sensitivity quarantine. Resolve parcel/address association and possible stale/copied listing content before assigning a different building, elevator status, floor or price. Short marketing duration is a further review signal, not an automatic exclusion rule.

## Port 10: intentional retention of an unmodeled product distinction

Ads 4761346 and 4758015 were already identified as income-restricted in the [September 18 residual review](chelsea-bayesian-bathrooms-2026-09-18.md). The [source revision](chelsea-bayesian-source-revision-2026-09-18.md) explicitly retained low-price income-restricted offers as unresolved research cases while quarantining named nonresidential/location conflicts. The subsequent floor projections preserve that choice. No dedicated eligibility/product feature currently explains these two asks.

Both full descriptions say “Income Requirements Applicable”, prohibit guarantors, give household-income brackets, and require documents verifying household size, identity and income. The one-bedroom 4761346 reports minimum annual income $83,314 and a 1–2 person maximum range $83,314–$103,680. Studio 4758015 reports minimum $77,760 and maximum range $90,720–$103,680. Preserve the literal source ranges rather than silently repairing their awkward presentation.

Use a capture/ad-scoped eligibility claim and renter-feasibility rule, then test product treatment or a restricted-offer sensitivity cohort. Do not inflate their prices toward fitted medians, assign restrictions to every Port 10 unit, backdate 2026 wording into a permanent unit attribute, or interpret no matched wording as unrestricted. The [independent income-restriction screen](chelsea-income-restriction-research-2026-09-19.md) finds broader candidates with differing eligibility bands; it argues against fitting a universal discount from these two outliers.

## Newly actionable source issues before feature expansion

- **1260588**, rank 6: the entire own ad explicitly offers “Professional Loft Space avaialble for business use”. Prepare residential-scope quarantine, preserving the source ask.
- **937046**, rank 7: liquor rights, outdoor seating, cooking equipment, key money $300,000 and “Rent $15,500 plus taxes” describe a restaurant offer. The analytical ask is a supported commercial quote; the problem is residential scope.
- **2993341**, rank 14: full prose locates the apartment at 145th/Malcolm X, with Saint Nicholas Park/Jackie Robinson references, despite canonical 133 West 14th Street. **609730**, rank 12: prose places a loft across from Blue Note in Greenwich Village, despite canonical The Cass Gilbert. Prepare exact-ad unresolved-location quarantines consistent with the prior policy; do not invent corrected addresses.
- **2221592**, rank 11: explicit “Single Room Occupancy” and “Shared bathroom” warrant reported-composition uncertainty and SRO product-scope review. One reported full bath is not evidence of one private full bath.

For 2477915, 652674, 4979243 and 3813894, the old unresolved findings remain unresolved; repeating suspicious-price hypotheses adds no evidence. 4023400 has only an address description and 761202 has no description. 661080 is a separate feature lead: a described duplex penthouse with over 1,100 sq ft private terraces and bundled luxury finishes. Its residual does not identify a terrace coefficient independently.

## Evidence and next revision

Frozen input bundle: `data/model/chelsea-expanded-fit-residual-research-inputs-20260919`. Reviewed queue and exact 4953355 raw-listing/building witnesses: `data/model/chelsea-expanded-fit-residual-research-20260919`. Every proposed action retains rank, audit/unit/ad identity, source-row hash, own capture IDs, literal offsets and prior-review reference when found. The queue is research evidence, not an applied correction overlay.

Input selection is reproducible with `uv run --frozen --no-sync python -m docs.analysis.scripts.build_selected_residual_research_inputs --output <new-directory>`. The published input binds selection SHA `2fd7aa34bfa7d28897abad8fe5c757b6a6e6056bfb5e1fb84f483926ca73e124` and residual file SHA `5898a5920ddcae84ac90c424c0831a556987499f75341a44668d0e87c292cbb7`.

Execution checks: the input builder completed with exit 0 (session 29604); reviewed queue/raw-witness publication also completed with exit 0. A subsequent full bundle hash check passed and confirmed ranks 1–15, fifteen distinct units, six priority-0 cases, all historical price bases, and no applied source/model changes. An identical end-to-end replay of this new queue publication was not performed.

The next source revision should adjudicate the explicit commercial/location/SRO cases and the 4953355 conflict with existing reversible patch/scope machinery, refit, and review the newly exposed residual tail. Same-advertisement retrospective description evidence does not establish a physical or eligibility effective date at each historical ask. No model/source/UI changes were made by this review.
