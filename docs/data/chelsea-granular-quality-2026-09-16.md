# Chelsea granular data quality report — September 16, 2026

The full scoped archive has been converted into eleven Parquet tables on Modal.
Every expected listing, building, and inventory snapshot is represented, and all
snapshot-link checks pass. The eight partial listing parses are old gallery pages;
all 121,110 saved detail-page observations produced attributes and history.

The saved building observations contain **1,311 distinct building slugs**. Listing
observations cover 1,307 building slugs and **25,570 rental building/unit-label
pairs** (plus 8,344 sale pairs, which can overlap the rental set). These are source
labels, not a resolved census of physical apartments. There are 91,885 distinct
listing identities after distinguishing rental and sale ID namespaces.

For rental observations, square footage is missing in **66.3%**, feature metadata
in **26.9%**, and amenity metadata in **6.3%**. Unit labels are missing in 1,282
rental observations (1.3%) and 1,287 sale observations (5.3%). Bedrooms, bathrooms,
and room counts are present except on the eight gallery captures. Presence does
not establish accuracy: 6 rental observations have flagged bedroom counts, 305
have flagged bathroom counts, and 37 have flagged room counts. Flags identify
nonpositive bathroom/room counts, negative bedroom counts, or counts above 20;
they are review prompts, not deletion rules.

**5,464 typed building/unit-label groups have conflicting bedroom, bathroom, or
size values.** Those observations remain separate. Among rental groups, 2,233
have differing bedroom counts, 837 differing bathroom counts, and 1,830 differing
square footage; categories overlap. Differences can reflect source errors,
identity ambiguity, or actual changes. No effective dates or corrections were
invented.

All 2,938,566 history mentions have parseable dates. Of these, 1,274 have
nonpositive prices (1,142 rental and 132 sale mentions), retained for explicit
model-stage treatment. The 457,276 distinct event keys are comparison statistics;
all repeated evidence remains in the tables.

The inventory audit found one harmless placeholder: Sierra's unavailable-sales
page says “No info for unavailable units.” Thus **35,071 saved HTML rows contain
35,070 listing/closing records and one message**. A separate link interpretation
recovered 2,574 URLs missing from legacy structured extraction metadata, using the
saved HTML. It retains 33,904 listing links and 1,166 closing links, with no
unresolved rows, source-row loss, or conflicting non-null original URLs. Three
rows have multiple candidate links; the original recorded link disambiguates them,
and all candidates remain preserved. The original inventory rows are unchanged.

The archive retains **966 HTTP 404 outcomes**. Converting all saved data does not
recover unavailable source pages or establish complete Chelsea census coverage.

The correction ledger is empty for this run. Human edits remain a separate,
versioned overlay. Listing episodes are links, not aggregation units; temporal
alignment, physical-unit resolution, event selection, and any averaging remain
model-stage decisions.

Data location: `chelsea-archive:/datasets/chelsea-granular-20260916/`.
Only these small reports were downloaded; the full archive and tables remain on
Modal. No re-scraping or GPU work was performed.

Workflow and row definitions: [granular dataset](granular-dataset.md).
Follow-up evidence: [bounded diagnostic results](chelsea-granular-followup-2026-09-16.json).

This report describes captured source evidence. It does not establish a complete census, signed leases, or verified physical units.

## Provenance

| Field | Value |
| --- | --- |
| Report root | /archive/datasets/chelsea-granular-20260916 |
| Source snapshot | /archive/snapshots/chelsea-backfill-20260912/archive.sqlite3 |
| Run version | granular-v1 |

Correction ledger: active=True, visible records=not reported.

## Captured tables

| Table | Rows |
| --- | --- |
| listing_observations | 121118 |
| event_mentions | 2938566 |
| snapshots | 124966 |
| fetch_observations | 127184 |
| building_observations | 1832 |
| inventory_rows | 35071 |
| inventory_observations | 1809 |
| source_changes | 788809 |
| frontier | 127455 |
| url_aliases | 2011 |
| inventory_row_links | 35071 |

## Listing observations

| Listing type | Observed captures | Share of captures |
| --- | --- | --- |
| rental | 96785 | 79.9% |
| sale | 24333 | 20.1% |

Distinct typed listing identities: **91885** (listing type and listing ID are separate namespaces).

Distinct source `(building_slug, unit_label)` pairs: rental **25570**, sale **8344**, unknown **0**. These are source labels, not verified physical units.

### Model-variable missingness and JSON state

| Type | Field | Missing/count state | % missing where available |
| --- | --- | --- | --- |
| rental | bedrooms | 2 | 0.0% |
| rental | bathrooms | 2 | 0.0% |
| rental | square_feet | 64122 | 66.3% |
| rental | room_count | 2 | 0.0% |
| rental | features_json | missing 26069 (26.9%); nonempty 70716 (73.1%) |  |
| rental | amenities_json | missing 6083 (6.3%); nonempty 90702 (93.7%) |  |
| rental | pricing_json | empty 2 (0.0%); nonempty 96783 (100.0%) |  |
| sale | bedrooms | 6 | 0.0% |
| sale | bathrooms | 6 | 0.0% |
| sale | square_feet | 6612 | 27.2% |
| sale | room_count | 6 | 0.0% |
| sale | features_json | missing 5482 (22.5%); nonempty 18851 (77.5%) |  |
| sale | amenities_json | missing 678 (2.8%); nonempty 23655 (97.2%) |  |
| sale | pricing_json | empty 6 (0.0%); nonempty 24327 (100.0%) |  |
| unknown | bedrooms | 0 | not reported |
| unknown | bathrooms | 0 | not reported |
| unknown | square_feet | 0 | not reported |
| unknown | room_count | 0 | not reported |
| unknown | features_json | not reported |  |
| unknown | amenities_json | not reported |  |
| unknown | pricing_json | not reported |  |

### Numeric quality flags

Invalid values are quality flags retained in the source observations; they are not deleted.

| Field | Non-null | Invalid/range flags |
| --- | --- | --- |
| bedrooms | 121110 | 17 |
| bathrooms | 121110 | 492 |
| square_feet | 50384 | 0 |
| room_count | 121110 | 96 |
| collected_at | 121118 | 0 |
| parsed_at | 121118 | 0 |

## History events

| Measure | Value |
| --- | --- |
| Event rows | 2938566 |
| Positive prices | 2937292 |
| Parseable dates | 2938566 |
| Date range | 2004–2026 |
| Distinct semantic event keys | 457276 |
| Duplicate evidence rows | 2481290 |
| Events with change ≤1% | 615597 |

Repeated event rows are retained evidence; duplicate keys do not imply rows were discarded.

### Event categories and density

| Category/measure | Value |
| --- | --- |
| Category: rental | 2551136 |
| Category: sale | 387430 |
| Density | {'min': 1, 'max': 1546, 'p50': 13.0, 'p95': 76.0} |

## Disagreements and parse failures

| Diagnostic | Count |
| --- | --- |
| Listing identity attribute disagreement groups | 0 |
| Source-pair attribute disagreement groups | 5464 |
| Listing parse error rows | 8 |
| Building parse error rows | 0 |

Attribute disagreements are retained for review and are not automatically corrected or treated as proven temporal changes. Missing amenities do not mean absence, and nonempty JSON can still contain an empty item list.

## Coverage and linkage checks

| Kind | Expected snapshots | Observed snapshots | Expected without observation |
| --- | --- | --- | --- |
| listing | 121118 | 121118 | 0 |
| building | 1832 | 1832 | 0 |
| inventory | 1809 | 1809 | 0 |

| Referential check | Rows missing referenced snapshot |
| --- | --- |
| listing_observations_missing_snapshot | 0 |
| building_observations_missing_snapshot | 0 |
| inventory_rows_missing_snapshot | 0 |
| inventory_observations_missing_snapshot | 0 |
| event_mentions_missing_snapshot | 0 |
| source_changes_missing_snapshot | 0 |

Fetch status counts: 200=124980, 308=33, 403=3, 404=966, null=1202.

Inventory reconciliation: observations=1809, count_sum=35070, row_count_sum=35071, mismatch_rows=1.

Inventory row-count mismatches by snapshot: **0**.

## Inventory link interpretation

| Measure | Count |
| --- | --- |
| rows | 35071 |
| distinct_occurrences | 35071 |
| missing_source_rows | 0 |
| unlinked_source_rows | 0 |
| recovered_legacy_links | 2574 |

| Row kind | Count |
| --- | --- |
| placeholder | 1 |
| listing | 33904 |
| closing | 1166 |

This companion table derives links from saved row HTML while preserving original extraction metadata. Placeholder messages do not represent extra units.

## Source changes

| Measure | Value |
| --- | --- |
| Rows | 788809 |
| By source path | pricing.priceChanges=375738, statusChanges=413071 |
| Date parsing | parseable=788809, unparseable=0 |
| Snapshots represented | 121110 |

## Interpretation limits and next data-quality actions

- Attributes describe the capture in which they were observed; do not back-join the latest attributes onto historical events.
- Keep source-label disagreements visible and review them; do not auto-correct or silently merge labels into physical units.
- Choose listing identity, event deduplication, and model time windows explicitly before training.
- Quantify missingness by variable and listing type, investigate parse failures, and reconcile snapshot linkage before modeling.
- Treat any future aggregation as a modeling decision; this report does not assert physical-unit completeness or signed-lease outcomes.
