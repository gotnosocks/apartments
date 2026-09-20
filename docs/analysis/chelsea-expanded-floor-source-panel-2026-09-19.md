# Expanded floor data: deterministic source panel

Reviewed all **20 advertisements, 19 units and 36 attached captures** in the
fixed panel. No contrary numbered unit-floor claim was found. Three own-ad
passages agree explicitly with their label-derived floor; silence in the other
advertisements does **not** independently confirm the numbering rule. Every
advertisement's attached captures have identical description hashes, so repeated
captures are not independent corroboration.

## Selection and review scope

From the 6,085 newly inferred observations, include every row with floor above
52. For each of the four named inference rules, rank buildings by descending
newly inferred observation count, breaking ties by building ID. Take the first
three buildings (all if fewer); within each, sort observations by inferred floor,
integer advertisement ID, then audit ID and select zero-based index `(n-1)//2`.
Union by audit ID and sort by building, floor, advertisement ID and audit ID.
This produces ten high-floor rows plus ten format/building representatives.
It is a deterministic development review panel, not a random accuracy sample.

The preparation script verifies the complete reversible source lineage and the
bound description archive with `load_evidence`. I read every selected full own-ad
description, checked all attached capture/label identities, and distinguished
unit-floor language from building amenities, access descriptions and photography
qualifications. The immutable panel retains complete descriptions, source-row
hashes, raw/body hashes and capture IDs. No scraping, source correction, model
input change or main-model promotion was performed by this review.

## Case findings

| Advertisement | Building | Label → proxy | Own-description finding |
|---|---|---|---|
| 2355966 | 134 W15 | `3RW` → 3 | “two floors up”; access description, not a contrary numbered-floor claim. |
| 2112469 | 21 Chelsea | `702` → 7 | Building marketing only; no numbered unit-floor claim. |
| 4729493 | 241 W15 | `3RW` → 3 | “3rd floor of a walkup building”; agrees with label. |
| 4732309 | 3Eleven | `5304` → 53 | “HIGH FLOOR”; no exact unit-floor number. |
| 4922908 | 3Eleven | `5302` → 53 | “HIGH FLOOR CORNER”; no exact unit-floor number. |
| 4972564 | 3Eleven | `5302` → 53 | “HIGH FLOOR CORNER”; no exact unit-floor number. |
| 5034450 | 3Eleven | `5301` → 53 | River views; no exact unit-floor number. |
| 5047403 | 3Eleven | `5307` → 53 | “53RD FLOOR!” in the opening headline; agrees with label. |
| 4829507 | 3Eleven | `5405` → 54 | “HIGH FLOOR”; no exact unit-floor number. |
| 4872104 | 3Eleven | `5401` → 54 | “HIGH FLOOR”; no exact unit-floor number. |
| 4618468 | 3Eleven | `5701` → 57 | “HIGH FLOOR”; no exact unit-floor number. |
| 4766836 | 3Eleven | `5702` → 57 | “HIGH FLOOR”; no exact unit-floor number. |
| 4802012 | 3Eleven | `5708` → 57 | “HIGH FLOOR”; no exact unit-floor number. |
| 4713746 | 416 W25 | `2RE` → 2 | One-sentence bedroom description; no floor claim. |
| 942756 | HL23 | `11THFLOOR` → 11 | “this 11th floor”; agrees with ordinal label. |
| 4685806 | Ruby Chelsea | `N14B` → 14 | Building marketing only; no unit-floor claim. |
| 5058537 | Caledonia | `811` → 8 | Northern exposure/city views; no unit-floor claim. |
| 3964727 | Carteret | `817` → 8 | No unit-floor claim; building described as 17-story versus captured count 18. |
| 4913210 | Tate | `N6G` → 6 | North-facing apartment; no unit-floor claim. Explicit lease assignment. |
| 3381574 | Thomas Eddy | `S5J` → 5 | Only “Draft rental description”; no corroborating prose. |

All ten observations above floor 52 are **nine units in one building, 3Eleven**:
five observations at 53, two at 54, three at 57. Its captured building count is
62. The recurring **42nd-floor sky deck** is a shared amenity, not a competing
floor assignment for these units. All ten ads qualify their images as
representative; this prevents treating photographs as unit-specific evidence.
Only advertisement 5047403 supplies an exact matching high-floor prose claim.
The remaining high-floor values retain their label-proxy status. These ten rows
extend the spline boundary to 57; they do not provide broad cross-building
support for that upper tail.

Two ancillary findings warrant separate tracking. Carteret's prose count of 17
and structured count of 18 show why the building-count guard is a compatibility
filter rather than a physical-height mapping; floor 8 passes both counts. Tate
4913210 explicitly offers a lease assignment, which may warrant the separate
rental-scope review. Neither supports changing its unit floor. For 3Eleven
4972564, the $8,739 net/$10,195 gross distinction is already respected by this
observation's $10,195 target; no price replacement is suggested here. Historical
target timing still follows the existing own-ad event policy.

The three explicit agreements are opportunities to improve future own-description
extraction coverage (53rd-floor headline, “3rd floor of a walkup building”,
“this 11th floor”). That improvement is outside this frozen fit. The current
label projection already recovers their matching values.

A follow-up replay passed each complete bound description, without added
structured attributes, to `attribute-evidence-v6`. All three returned
`advertised_floor=null` with no floor evidence. These are therefore confirmed
gaps in the current description matcher, not just missing values in an older
analytical snapshot. No extractor change was made during the running fit.

## Exact source bindings and reproduction

- Expanded source manifest: `d244ca6710e080e18059f1b3279a373e187ea38fb4219c51deff7e49f4604717`.
- Expanded observations: `5f7adaccfda5abd9855f1f62d4761b8bdfccdbe913add21494b4ab6757db4d92`.
- Description archive manifest: `79308dfdbefd7fe8a03630bdd048fa742d0f7cd3335b82f25da0575a9d9b7e08`.
- Panel manifest: `90a36b6f0bbde3a7cb3e0b2a2e327fb89fd00132adab420476e64feabff6f0bd`.
- Panel records: `4968ae1322b08a144f3dc20a75e6c0469f72e507f83976837c8aac55c32dc283`.
- Ordered panel audit IDs: `0fb8d2a93e220d6c4ddc5131dbc503730d02091acce81bc7782b3cf377177826`.

Panel artifact: `data/model/chelsea-expanded-floor-source-panel-20260919`.
Source: `data/model/chelsea-expanded-label-floor-analysis-20260919`.
Descriptions: `data/model/chelsea-refreshed-bayesian-descriptions-20260918`.

```bash
UV_CACHE_DIR=/tmp/apartments-uv-cache uv run --frozen --no-sync python \
  -m docs.analysis.scripts.prepare_expanded_floor_source_panel
```

The script reproduces the evidence panel and verifies an identical existing
publication. The qualitative findings above are the manual review of that
bound panel, not an automated entailment test.
