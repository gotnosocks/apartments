# Source review of spline versus increment floor movements

The review found useful feature-extraction and cohort leads, but no new contradiction requiring a floor-label correction among these cases. The largest changes in fitted rent are small relative to several remaining residuals. Large unit-offset changes at Beatrice are principally evidence of how the model reallocates contributions, not evidence that those units suddenly became mispriced.

## Scope and evidence

Read all 34 case records and all distinct complete descriptions in the frozen [review inputs](../../data/model/chelsea-spline-floor-movement-review-inputs-20260919/cases.jsonl), covering 51 own-advertisement captures. Verified bundle hashes, description hashes, and advertisement/audit identity bindings. The bundle manifest SHA256 is `2b3d70a7df7ede7c8127c59a3d2b73f3f6b52c84e7751f116078071d73e5fdd0`; its plan binds source, comparison and evidence manifests. This was an offline review of archived text and structured attributes, not a new scrape or photographic/floorplan inspection.

The set contains the 25 largest distinct-unit **changes in fitted dollar rent**, plus examples of the five largest unit-offset and five largest common-reference building-effect changes; one example overlaps. It is neither the largest absolute-residual set nor a representative sample or holdout. There are 33 historical initial asks and one refreshed current ask. Both models fit the same observations and labels; changing the floor representation and prior can also redistribute nonfloor and group contributions.

All 33 numeric floor proxies agree with their literal captured unit labels and remain within the archived building floor-count guard. Chelsea Modern `PH9/10A` remains unknown: its duplex description does not justify collapsing two levels into one physical floor. Chelsea Stratus 35E additionally says “35th floor” in prose. Nothing here independently verifies physical height or a building's skipped numbering.

## Findings worth pursuing

1. **Historical furnishing status is incompletely represented.** Vesta 17 / 201 West 17th Street **6B, ad 4141846**, explicitly offers the apartment furnished only for a one- or two-year lease. Its fitted row has `furnished=null`, and the text also explicitly identifies an in-unit Whirlpool washer/dryer while `laundry_type=null`. Walker Tower **18D, ad 2021775**, explicitly describes a furnished rental while `furnished=null`. These are concrete own-advertisement review leads for the historical cohort's furnishing treatment. Verify and record the intended price/attribute-time interpretation before any correction or quarantine; do not modify the completed matched floor comparison. Chelsea Mercantile **17N, ad 2521833**, offers either furnished or unfurnished: the text does **not** establish which basis applies to its $19,500 ask.

2. **A bathroom conflict escaped the structured-count flag.** Chelsea Modern **PH9/10A, ad 2728974**, describes five bedrooms and **5.5 baths**, while the observation contains five full and zero half baths (`bathrooms=5`). Its `consistent_explicit_count` statuses describe the structured evidence, not agreement with this prose. Record as a conflict requiring adjudication, not an automatic extra half-bath. Its $9,685 positive residual is much larger than the +$103 fitted movement. A duplex, two master suites, 1,300+ square feet of private terraces, fireplace and extensive renovation are additional omitted-feature candidates.

3. **Private outdoor space, ceiling height, renovation and en-suite layout recur in the luxury residuals.** Mercantile 17N has a gut renovation, 10.5-foot ceilings, corner layout and explicit river/skyline views; its largest fitted movement is −$376 (−2.55%), leaving a +$5,107 residual. Soori High Line **10C, ad 3973940**, has a duplex layout, 1,036 square feet of private terraces and its own rooftop pool, leaving +$7,538. Walker Tower 18C, 200 West 16th 17D, 161 West 16th 17A, Chelsea Stratus 35A/35E and 132 Ninth Avenue 2R all advertise private outdoor space. A Juliet balcony, shared roof deck and substantial private terrace must remain distinct. These observations motivate source-bound extraction, not a causal premium inferred from these selected cases.

4. **Some existing feature families still miss literal text.** Mercantile 17N has null view/exposure fields despite explicit south/west, Hudson River and downtown-skyline claims. Walker Tower 17A's southeast-facing prose is absent from its window directions; 18C's river-view claim is absent from its water-view field. Vesta 17 6B misses explicit in-unit laundry. The Andrea 6B says south-facing while its south exposure is null. Distinguish direct unit claims from generic building marketing, and distinguish a laundry/utility room from an explicit installed washer/dryer. Similar prose at 551 West 21st 17A and 100 Eleventh 16C merits targeted extractor checks.

5. **Recurring charges and service availability need their own time-aware representation.** Beatrice's newer ads specify a mandatory $135 monthly amenity charge; some add utility fees/estimates. 606W30 includes an HVAC charge without an amount, and The Grove 17C quotes a $55 per-person monthly amenity fee. These are not established errors in the advertised-rent target. Keep base ask and separately evidenced recurring charges distinct for apartment-search cost comparisons. Fitzroy 6E's description says some building amenities are still to be completed; One High Line 31B anticipates future hotel services. Avoid treating a promised service as already available at the historical price date.

## Group shifts versus residuals

The five largest unit-offset movements are Beatrice **52B, 52I, 52A, 52C and 52E**. Median log unit effects move upward by **0.0392–0.0418**, but the corresponding example fitted rents move downward only **$22–$55**. The labels consistently say floor 52; the building archive says 53 floors, and generic building prose says residences start at 26. This supports keeping the label proxy, while highlighting concentrated upper-floor support and offset compensation. The descriptions do not establish unique unit-level views, renovations or laundry changes. Generic “24-hour concierge” should also not be silently converted into a particular doorman category.

The five largest common-reference building-effect movements are only **0.0042–0.0050 in absolute log effect**, with descriptively overlapping intervals. Their example fitted changes are +$8 at 132 Ninth 2R, −$1 at 233 Ninth 3R, −$7 at The Andrea 6B, −$8 at Fitzroy 6E, and +$114 at 606W30 39G. These examples can flag source issues but cannot adjudicate a whole building. Fitzroy's large *level* of building effect is a separate question from its small *change* between these models.

## Case-by-case disposition

Dollar change is spline fitted rent minus increment fitted rent. Residual is advertised ask minus spline fitted rent. Rounded dollars are descriptive posterior-fit summaries, not uncertainty intervals for between-fit differences. `M` is a top-25 distinct-unit fitted movement, `U` a unit-offset example, and `B` a building-effect example.

| Ad / apartment | Selection | Δ fit | Residual | Source finding / disposition |
|---|---|---:|---:|---|
| 2521833 — Mercantile 17N | M1 | −$376 | +$5,107 | Renovated corner loft, 10.5-ft ceilings and explicit views; view/direction gaps. Furnished **or** unfurnished basis unresolved. |
| 1262316 — Walker Tower 18C | M2 | −$293 | +$4,736 | 285-sq-ft terrace, fireplace, en-suite bedrooms; water-view extraction lead. No label conflict. |
| 4031437 — 551 West 21st 14A | M3 | +$271 | +$1,035 | Never-lived-in, private elevator, 11-ft ceilings, four en-suite bedrooms; source dimensions consistent. |
| 1328434 — Walker Tower 17A | M4 | −$263 | −$1,740 | Southeast direction missing; en-suite bedrooms and laundry/utility room; short/long term offered, no established short-term ask. |
| 2021775 — Walker Tower 18D | M5 | −$246 | −$2,828 | **Furnished** duplex, 400-sq-ft terrace; furnishing field unresolved. Label alone describes only one level. |
| 1544055 — 161 West 16th 17A | M6 | −$213 | +$2,088 | 75-ft wraparound terrace, 10-ft ceilings, explicit skyline; square footage and exposures missing. |
| 4117017 — Chelsea Stratus 35A | M7 | −$180 | −$2,656 | Balcony, corner layout, en-suite bedrooms; encoded directions/area present. Negative residual is not explained merely by luxury text. |
| 5142924 — 200 West 16th 17D | M8 | −$172 | +$1,216 | 700+ sq ft private outdoor space; area and named three directions missing. No label conflict. |
| 2714657 — Beatrice 52G | M9 | −$166 | +$442 | Generic building marketing; consistent label 52; no unit-specific anomaly established. |
| 3881023 — 200 West 16th 18D | M10 | −$158 | +$2,415 | Renovation and broad water/city views; virtually staged photos do **not** establish furnished tenancy. |
| 4772630 — The Grove 17C | M11 | −$157 | +$1,216 | Fee-only description; $55/person/month amenity charge, sparse unit attributes. No inferred physical-floor or luxury correction. |
| 3097232 — 551 West 21st 17A | M12 | −$152 | +$5,015 | Highest ceilings in building, private elevator, en-suite bedrooms, river views; view/direction extraction leads. |
| 3942081 — 551 West 21st 17B | M13 | −$150 | +$6,754 | Library, private elevator, 11-ft ceilings and en-suite bedrooms; missing luxury/layout features plausible. |
| 3973940 — Soori High Line 10C | M14 | −$131 | +$7,538 | Duplex penthouse, extensive terraces and private rooftop pool. Keep label distinct from multi-level geometry. |
| 1610425 — 161 West 16th 17D | M15 | −$130 | +$2,609 | Renovated oversized one-bedroom, fireplace, fitted home office; interior area unknown. |
| 4141846 — Vesta 17 6B | M16 | −$122 | +$3,419 | **Furnished only** and explicit in-unit washer/dryer missing from fields; high-priority evidence review. |
| 5012447 — 606W30 39G | M17, B5 | +$114 | +$7 | Generic amenities and fees, no new unit-specific explanation needed; no floor conflict. |
| 5148603 — 606W30 40C | M18 | +$113 | −$137 | Only refreshed-current case; generic amenities/fees and label 40 consistent. |
| 1762546 — Beatrice 52H | M19 | −$112 | +$1,138 | Generic tower marketing; no direct unit-specific view or physical-floor verification. |
| 864121 — Porter House 6W | M20 | −$111 | +$4,084 | Renovated loft, 10-ft ceilings, high-end finishes, corner layout; source dimensions agree. |
| 1474972 — Citizen 12C | M21 | +$109 | −$4,858 | Text supports three bedrooms/three baths; low $6,995 historical ask remains unexplained. Inspect own price history/identity before calling a bargain or correcting counts. |
| 1231611 — Chelsea Stratus 35E | M22 | −$109 | +$978 | Prose explicitly confirms floor 35; balcony and private storage, city-view extraction gap. |
| 2728974 — Chelsea Modern PH9/10A | M23 | +$103 | +$9,685 | Unknown compound floor retained; **5.5-bath prose versus 5-full/0-half** conflict; extensive private outdoor space. |
| 4601585 — One High Line 31B | M24 | −$103 | +$4,481 | Newly finished unit, en-suite bedrooms, future hotel services; no label contradiction. |
| 2856701 — 100 Eleventh 16C | M25 | +$103 | −$1,223 | Four-exposure and Hudson River prose incompletely represented; source area/counts agree. |
| 4798052 — Beatrice 52B | U1 | −$22 | −$532 | Floor-effect/unit-offset reallocation; $135 amenity charge separately evidenced. |
| 4934050 — Beatrice 52I | U2 | −$23 | +$213 | Same reallocation; recurring amenity/utility charges do not redefine base rent. |
| 4952256 — Beatrice 52A | U3 | −$36 | −$91 | Same reallocation; no unique unit feature established by generic prose. |
| 4279606 — Beatrice 52C | U4 | −$40 | −$620 | Same reallocation; historical generic building description. |
| 4872879 — Beatrice 52E | U5 | −$55 | −$679 | Same reallocation; $135 amenity charge separately evidenced. |
| 3966327 — 132 Ninth 2R | B1 | +$8 | +$103 | Private deck, upstairs/downstairs bathrooms, high ceilings; likely multi-level layout, not an exact physical-floor mapping. |
| 1241913 — 233 Ninth 3R | B2 | −$1 | −$56 | Prose says two flights up, compatible with label 3; no-elevator status is not proved by that phrase alone. |
| 5128094 — The Andrea 6B | B3 | −$7 | +$158 | Explicit south-facing, Juliet balcony, daily concierge; distinguish balcony type and concierge from full-time doorman. |
| 3813020 — Fitzroy 6E | B4 | −$8 | +$1,982 | Two beds plus office, private elevator, 11-ft ceilings, two en-suites; promised amenities require time-aware treatment. |

## Follow-through and limits

Propose an evidence-bound historical furnishing review for ads **4141846 and 2021775**, a bathroom-conflict review for **2728974**, and extractor regression examples for the explicit laundry and direction/view omissions above. No new correction, quarantine, source mutation or feature refit was applied in this review. Repeated advertisements, unknown area, chronology and ask-price basis remain potential explanations; text from an archived capture is not independent proof that a physical attribute existed on the original historical price date.

The top-25 dollar movements range from about $103 to $376, and the largest proportional fitted movement in that selected set is 2.55%. Several residuals remain thousands of dollars. Neither a smaller residual nor a descriptive luxury-feature match establishes the correct floor representation, a causal amenity value, or a mispriced apartment. The evidence supports continued extraction and source review while retaining the completed models as a clean matched comparison.
