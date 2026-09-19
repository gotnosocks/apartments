# Fixed floor-source development panel, September 19, 2026

The panel freezes **26 distinct units** for repeated floor-feature research. It is deliberately selected for coverage rather than chosen from current advertisements or large residuals. Its IDs and seed are committed in `config/reviews/chelsea-floor-development-panel-20260919.json`.

The algorithm uses seed **20260919** and SHA-256 ordering. Among observations with a known model floor, it first selects one source observation per unit. It then takes two units from each floor-band × elevator-state cell, preferring two buildings where available. Bands are 1–2, 3–5, 6–9, 10–19, and 20+; elevator states are yes, no, and unknown. Prices and residuals play no role. Reversing the source row order reproduced the exact selected observations.

There are no eligible no-elevator observations assigned to the 10–19 or 20+ cells. The 20+/unknown cell has only two eligible units, both at Beatrice; both are included and this building repetition is explicit. The remaining populated cells each have two buildings. All 26 selected observations are historical advertisements in the fitted dataset; none is a held-out observation. All 26 happen to use label proxies under this declared selection method. This is a fixed development panel, not a representative population sample or an accuracy estimate.

Every distinct full captured description was read. Quotes in the review bundle are checked against the exact own-capture text and carry capture, body, raw-listing, and description hashes plus literal offsets. No observations, fitted inputs, or corrections were changed by this review.

## What the source review found

Three units have explicit unit-level floor prose agreeing with their labels: London Terrace Towers #4D (ad 4094446), 301 West 17 #6E (3921499), and 262 West 24 #6C (4114823). Their original `advertised_floor` is null. These are concrete cases for improving explicit-description extraction, although the new label proxy already gives the same numeric floor. They do not establish population accuracy.

At 156 West 15 #4A (3024360), the description says “Four (4) flights up in a walk-up building.” Label 4 therefore must not be interpreted as four floors above ground or silently converted to physical floor 4. At 208 Eighth Avenue #1A (3259307), the captured building count is 1 while the apartment is a “Short Walk Up”. Building floor counts are a compatibility filter, not ground truth about numbering or stair access.

London Terrace Gardens ads 3010982 and 3798517 have single-digit labels but no captured building count in their address-level building records. Their descriptions name the complex. Building/complex association and elevator evidence deserve review; concierge or doorman language alone does not prove an elevator. Two high-floor Beatrice advertisements also retain unknown elevator status even though another panel advertisement in that building has elevator=True. Source dates and evidence must be checked before resolving that inconsistency.

Two incidental price-basis leads emerged without selecting on price: ad 2700478 has historical target 3208 and explicitly calls its advertised amount net effective while quoting gross 3850; ad 2789377 has target 4530 and explicitly describes advertised rent as net effective for one free month. These need original own-advertisement price-path review before any quarantine or correction. This panel review did not establish that a later captured description describes the earlier target price.

Beatrice's text about apartments “starting on the 26th floor” describes the building range, not the selected units' individual floors 33, 48, or 52. Generic high-floor language, floor-to-ceiling windows, heated floors, and amenity floors were not treated as precise unit-floor measurements.

## Frozen panel

| Floor band / elevator | Advertisement | Building / captured label | Review finding |
|---|---:|---|---|
| 1-2 / yes | 3393536 | 125-west-16-street-new_york #2H | label only |
| 1-2 / yes | 1411908 | chelsea-green #2B | label only |
| 1-2 / no | 665337 | 338-west-17-street-new_york #2B | stairs compatible not physical mapping |
| 1-2 / no | 3259307 | 208-8-avenue-new_york #1A | count and access ambiguity |
| 1-2 / unknown | 1856232 | 319-west-22-street-new_york #1A | label only |
| 1-2 / unknown | 3642673 | 238-west-20-street-new_york #2A | label only |
| 3-5 / yes | 4094446 | london-terrace-towers #4D | literal floor agrees |
| 3-5 / yes | 2789377 | the-grove-250-west-19th-street-new_york #5K | label only with price basis lead |
| 3-5 / no | 3024360 | 156-west-15-street-new_york #4A | stairs label offset ambiguity |
| 3-5 / no | 3759993 | 452-west-23-street-new_york #3A | building count agrees only |
| 3-5 / unknown | 1235296 | 366-west-23-street-new_york #3W | label only |
| 3-5 / unknown | 4431461 | 228-8-avenue-new_york #4B | label only |
| 6-9 / yes | 2700478 | 507-west-chelsea #8G | label only with price basis lead |
| 6-9 / yes | 3100003 | citizen-condominium #8A | label only |
| 6-9 / no | 3921499 | 301-west-17-street-new_york #6E | literal floor agrees |
| 6-9 / no | 4114823 | 262-west-24-street-new_york #6C | literal floor agrees |
| 6-9 / unknown | 3010982 | 450-west-24-street-new_york #7C | label only missing building count |
| 6-9 / unknown | 3798517 | 445-west-23-street-new_york #9E | label only missing building count |
| 10-19 / yes | 3941179 | 777-6th-avenue #14E | building count agrees only |
| 10-19 / yes | 2019944 | the-grand-chelsea #15F | qualitative high floor only |
| 10-19 / unknown | 1778297 | 425-west-23-street-new_york #10E | label only |
| 10-19 / unknown | 3676084 | abington-house #11B | label only |
| 20+ / yes | 5058235 | ohm-312-11th-avenue-new_york #29D | qualitative high floor only |
| 20+ / yes | 4228899 | beatrice-105-west-29th-street-new_york #48I | building starting floor not unit floor |
| 20+ / unknown | 3721679 | beatrice-105-west-29th-street-new_york #33C | building starting floor not unit floor |
| 20+ / unknown | 2032521 | beatrice-105-west-29th-street-new_york #52H | building starting floor not unit floor |

## Reuse and provenance

Use the frozen audit IDs in the config for repeat checks. If source data changes, compare these same units and record the new source version; do not silently reroll the panel. A broader panel of unresolved labels would be a separate named cohort with a separate selection rule.

- Selection bundle: `data/model/chelsea-floor-development-panel-20260919`.
- Manual review: `data/model/chelsea-floor-development-panel-review-20260919`.
- Selection producer: `docs/analysis/scripts/build_floor_development_panel.py`.
- Manual-review publisher: `docs/analysis/scripts/review_floor_development_panel.py`.
