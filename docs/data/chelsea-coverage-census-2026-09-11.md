# Chelsea coverage sanity check — September 11, 2026

The archive is in a plausible range for Chelsea excluding Hudson Yards: low thousands of building records and tens of thousands of residential units. Counts do not establish exhaustive geographic or physical-unit history coverage.

## Archive counts

A read-only Modal audit of the committed archive found 1,311 scope building roots and 1,311 captured canonical main-building pages. Every page yielded a primary building object, with 1,311 unique StreetEasy IDs. Source area IDs were Chelsea (979) and West Chelsea (332); none were Hudson Yards.

1,157 primary building records reported positive residential capacity; 154 had zero or missing capacity. Categories include 479 Rental buildings (19,029 units before complex adjustment), 210 Co-op buildings (7,498), 157 Condo buildings (5,542), plus mixed-use properties, smaller houses, commercial buildings, and other categories. Condos/co-ops can also have rental history; the Rental building category is not a census of renter-occupied housing.

The raw sum of residentialUnitCount is 34,103. London Terrace Gardens' complex 183468 repeats a 921-unit total on two addresses; London Terrace Towers' complex 194816 repeats 702 on three addresses. Removing only these obvious repeated complex totals gives 31,778 (and 18,108 in the Rental building category). This remains an approximate source-reported capacity, not verified unique apartments. Other complexes have distinct per-building capacities and must not automatically be collapsed to their maximum.

Captured inventories comprise 1,217 unavailable-rental pages with 25,535 rows and 592 unavailable-sales pages with 9,535 rows (sales include closing records). A separate audit accounted for all unavailable-rental detail links, including one redirect whose destination was already captured. Sierra illustrates why rows are not physical units: 393 unavailable-rental rows versus a reported residential capacity of 213.

The audited queue had 112,885 processed listing URLs and 9,070 pending listing URLs. These include historical episodes and URL aliases, not apartments; processed includes terminal errors. Counts are a committed-archive snapshot, not a continuously refreshed dashboard.

### Correction to previous status reports

The queue's kind=building totals (1,832 done / 1,488 pending at audit time) do not count unique buildings. Inspected pending examples include `?similar=1` and `?unit_type=rentals` variants of known roots. All 1,311 known main roots were already captured. Prior wording describing 1,488 buildings still missing was incorrect. Queue variants should be reviewed for avoidable provider spending before treating them as useful new-building discovery. This audit did not alter the active writer or queue.

## Public-data comparison

Source: [NYC DCP PLUTO](https://data.cityofnewyork.us/City-Government/Primary-Land-Use-Tax-Lot-Output-PLUTO-/64uk-42ks), downloaded via its public Socrata endpoint on September 11. Actual API rows report version 26v2 (the indexed web catalog was still describing 26v1).

PLUTO is one row per tax lot. `numbldgs` counts buildings on the lot; `unitsres` sums residential units across its buildings. A lot and a StreetEasy building record are not necessarily one-to-one. See the [DCP data dictionary](https://www.nyc.gov/assets/planning/download/pdf/data-maps/open-data/pluto_datadictionary.pdf).

Official census geography combines Chelsea and Hudson Yards; Community District 4 additionally contains Hell's Kitchen. Neither is an exact denominator for the requested scrape. Instead, use an explicitly approximate shared footprint: convex hull of archived building coordinates. The public dataset is independent within that footprint, but the footprint itself depends on observed StreetEasy buildings, so it cannot discover missing territory beyond the hull.

The API returned only 2,626 rows (about 460 KB) within the archived coordinate bounding box. A small local calculation clipped them to the hull. No large city dataset or archive database was downloaded.

| Measure | Shared footprint | Outward 25 m half-plane margin |
|---|---:|---:|
| Tax lots, all uses | 1,779 | 1,797 |
| Buildings, all uses | 1,962 | 1,981 |
| Lots with residential units | 1,333 | 1,335 |
| Buildings on those residential lots | 1,490 | 1,492 |
| Residential units | 36,761 | 36,812 |

A 50 m margin gives 37,751 units. Margin calculations are clipped by the downloaded bounding box. Buildings on residential lots can include nonresidential structures sharing a lot. This is a sensitivity check, not an official geographic census or exact coverage percentage.

## Interpretation

The 1,311 StreetEasy records and roughly 31,800 adjusted units of represented capacity are in the expected range compared with approximately 1,500 buildings on residential lots and 36,800 city-recorded units in the same general footprint. This supports substantial coverage, but is not evidence that 86% of physical units have histories. Public/affordable housing, properties never marketed on StreetEasy, source capacity errors, boundary differences, and unmatched complex identities can all explain differences.

The right next completeness check is an address/BBL/BIN reconciliation against city property records to identify absent buildings. Historical URLs, source labels, and inventory rows cannot substitute for that reconciliation.

## Evidence and reproduction

`models/modal_building_census.py` performs the read-only cloud audit. Small source exports and reproducibility parameters are in `data/exports/coverage-census-2026-09-11/`: archive-buildings.json, pluto-envelope.json, and comparison.json (exact polygon, query, source version, margin results). No Oxylabs calls were made for this audit.
