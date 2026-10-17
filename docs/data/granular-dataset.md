# Granular archive tables

The granular datasets hold the page crawls' captures and every history entry each
page mentions, with no prices or attributes combined over time. They also hold the
unit memberships the pages declare in their canonical links. A listing ID there is
the source's label for linking evidence. Models choose an observation unit, resolve
physical apartments, combine repeated evidence and build time windows later, and
the tables stay as they are.

The granular folders under `/data1/apartments/archive/datasets/` hold the output
of past runs of a transform, and they stay as data. The transform read a frozen
archive snapshot into Parquet, on thelio (`models/transform_local.py`) or on
Modal (`models/modal_granular.py`), and `apartments.granular_export` finished
each run. The data pipeline now builds from the API export
([pipeline.md](pipeline.md)), so the transform's code is deleted, and git history
holds it. `rentfrontier.listing_extras.CRAWLS` lists the page crawls' folders,
and `listing_extras`, `lister`, `listing_outcomes`, `latest_ask` and `areas` read
them beside the pipeline's records file.

## Row meanings

| Table | One row represents |
| --- | --- |
| `fetch_observations` | An original request outcome, including errors, repeated bodies, and 304 responses |
| `snapshots` | An originally saved interpretation of a URL/body in a crawl generation |
| `listing_observations` | A retained listing interpretation of one snapshot, including parse failures on eligible pages |
| `listing_exclusions` | A rental capture excluded because it has no usable canonical unit page, with its source URL and reason |
| `media_gallery_observations` | A gallery capture with its media payload and listing metadata, without listing-history interpretation |
| `event_mentions` | One history entry at its original episode/event position in one snapshot |
| `building_observations` | A building interpretation of one snapshot, including failures |
| `inventory_observations` | An expanded inventory capture and its original completeness metadata |
| `inventory_rows` | One original inventory row, including HTML and closing records; record URL fields reflect the original extractor |
| `inventory_row_links` | One linked interpretation per original row, resolving listing/closing URLs from saved HTML and identifying placeholder rows |
| `source_changes` | One pricing-change or status-change source entry, with its original timestamp and JSON |
| `frontier` | An archived queue entry and its terminal/pending state |
| `url_aliases` | An explicitly recorded alias/redirect relationship |

`event_mentions` deliberately includes repeated events across snapshots and within
pages. Its occurrence key is `(snapshot_id, episode_index, event_category,
event_index)`. `event_key` hashes the source event, category, and history listing
ID; it supports later comparison without deleting observations. A source may
revise its history; unequal keys need not mean different real-world events.
Rental and sale listing IDs occupy separate namespaces.

Join interpretations to `snapshots` by `snapshot_id`, and snapshots to request
outcomes by **generation, URL, and body hash**. This is a one-to-many relationship;
joining without care can repeat history mentions. A 304 can reference an older
body with no new snapshot in its generation. Neither an error nor a 304 is a new
attribute version. Raw HTML remains addressable at
`/archive/bodies/<first-two-hash-characters>/<body_hash>.gz`.

## Time, attributes, and corrections

All numeric timestamps are UTC Unix seconds. `collected_at` comes from the raw
snapshot's `observed` clock; every original request clock remains independently
available in `fetch_observations.fetched_at`. `parsed_at` records when the
transform read the capture. Source-created/updated dates and history event dates are source
assertions, not collection dates or guaranteed attribute-validity intervals.

A 2015 price reported on a page collected in 2026 is historical price evidence.
It does **not** establish that the page's 2026 bedroom count, square footage,
washer-dryer, or view applied in 2015. We retain the page's attributes and full
listing JSON alongside its history without making that backward join. Source unit
labels retain padding and punctuation; they are not silently merged into physical
apartments. Building membership is an observed attribute too.

Each run froze the separate `corrections.jsonl` ledger and its hash, and left the
raw columns as captured. The ledger was empty, so raw and corrected values
coincide. A time-bounded correction needs an attribute effective time chosen for
it, since collection time is no stand-in. `apartments.corrections.Overlay.apply`
writes a separate corrected projection at that time, with the correction IDs and
the raw observation, so human assertions stay apart from source evidence.

For retained captures, the complete source listing and nested feature/amenity/pricing
JSON remain in the Parquet tables. The normalized numeric columns are conveniences.
Parse failures remain explicit in either the listing observation or its exclusion
record, linked to the original body. Missing amenities do not mean
absence. Unknown source fields can be extracted later without re-scraping.

## Legacy inventory metadata

Some early captures stored `links` rather than `records`, leaving the raw
`inventory_rows.listing_url` field empty. The companion `inventory_row_links`
table derives the links from the original HTML, preserving the original rows and
record URLs. Use its `listing_url` and `row_kind` for structured inventory joins.
The link interpretation has its own input and implementation hashes and processing
clock; it is a parser interpretation, not a human correction. Multiple candidate
links are retained explicitly. Empty-inventory message rows are placeholders, not
extra apartments.


## Canonical unit-page evidence

The transform read three fields from the HTML head of every listing capture,
including captures whose listing object failed to parse. Retained observations
store all three columns, and exclusions keep the declared href and the reason:

- `canonical_href`: the single declared canonical href from the HTML head.
- `canonical_unit_url`: a normalized StreetEasy building/unit URL, or null when
  the canonical points to a rental listing, building alone, another host, or an
  unsupported path.
- `canonical_unit_error`: an explicit reason for missing/unsupported/conflicting
  evidence. Rental captures with this field set are excluded under the policy below.

The fields record source evidence with no review decisions applied. At
finalization the transform derived unit memberships from them, as "Canonical unit
associations" below describes. Manually reviewed associations are kept in the
separate, reversible identity ledger.


## Rental inclusion rule

The transform kept a rental capture in `listing_observations` only when its
HTML declares a usable canonical StreetEasy unit page (`canonical_unit_url` is
non-null). A rental-listing URL, building-only URL, foreign/unsupported URL,
missing/conflicting canonical link, incomplete head, or unreadable body is excluded.
This is a page-identity rule, with no listing-date cutoff. Sale listing captures retain
their existing behavior. Media galleries are classified separately before this rule.

Excluded captures contribute no rows to `listing_observations`, `event_mentions`,
or `source_changes`. History mentioning an excluded listing can still occur on
another retained page; those occurrences are preserved. Every exclusion gets a
`listing_exclusions` row with `snapshot_id`, URL, listing ID/type when available,
collection time, canonical href/error, parse status/error, and the reason
`rental_missing_canonical_unit_page`. All original snapshot/fetch metadata and
archived HTML remain intact. This audit table is outside the review/model listing
inputs and does not create another manual-cleaning queue.

Each dataset made under the rule records `listing_filter: rental-canonical-unit-v1`
in its `plan.json`, and its quality report counts the exclusions. On the reviewed
rental corpus of the time, with media-gallery captures left out, the rule excludes
8,094 of 96,783 captures and keeps 88,689. Failed rental-page parses without a
usable canonical link count as exclusions too.


## Media-gallery pages

The transform classified recognized `/media_gallery` endpoints as `media_gallery`
before any listing, building or inventory parser read them, including legacy
snapshots whose archive `kind` was `listing`, `building` or null. `snapshots.kind`
keeps the archive's value, and `snapshots.page_type` holds the classification the
transform used.

`media_gallery_observations` retains the snapshot ID, URL, collection/parse times,
listing ID/type when available, building ID, canonical evidence, property details,
media and signature-gallery JSON, and the complete selected gallery object. A
gallery does not need `propertyHistory` or a canonical unit link. It contributes
no rows to `listing_observations`, `listing_exclusions`, `event_mentions`, or
`source_changes`, even if its payload includes history or price-change fields.
No photos are downloaded; the embedded source media payload is preserved.

Missing, ambiguous, unresolved or unreadable gallery payloads are recorded as
gallery parse errors, and a gallery without history is not an error. Each quality
report counts gallery captures and errors apart from listing errors.

Datasets with this classification record `page_classification: media-gallery-v1`
in `plan.json`. All eight gallery pages in the frozen Chelsea archive (six sales
and two rentals) were checked against the gallery parser.


## Canonical unit associations

The transform's finalization ran `canonical-url-v1`. Every retained
rental listing is assigned by its exact full canonical unit URL (building and
unit portions). Source display labels, latest-listing pointers, history contents,
and attributes do not need to agree. A listing with missing or conflicting URLs
across captures, and other listings sharing those affected URLs, remain unresolved
rather than bridging distinct unit pages. Singleton listings also receive unit IDs.

Outputs:

- `rental_units`: one row per canonical URL, with stable `unit_id`, URL, listing
  count, capture count, and rule version.
- `rental_unit_memberships`: one row per rental listing ID, its unit ID, canonical
  URL, capture count, and association status/reason.
- `rental_unit_observations`: one row per retained rental snapshot, linking that
  capture to its listing and unit. Null unit IDs explicitly mark unresolved rows.
- `canonical-units.json`: counts and hashes of source evidence and derived tables.

IDs use UUIDv5 of the normalized canonical URL, independent of listing IDs and
latest-listing pointers. They are stable across reruns and additional captures.
A changed canonical URL produces a different source identity; these associations
are not independent verification of a physical home. Review decisions are kept
in a separate overlay.

To access one unit's history without losing provenance:

```sql
SELECT u.unit_id, e.*
FROM rental_unit_observations u
JOIN event_mentions e USING (snapshot_id)
WHERE u.unit_id IS NOT NULL AND e.event_category = 'rental';
```

This attributes each history mention to the page that reported it. It does not
claim every historical advertisement has its own captured canonical page. Repeated
event mentions remain intact, as do changing attributes and prices. Consumers can
choose an event-deduplication policy separately.
