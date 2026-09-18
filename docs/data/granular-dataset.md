# Granular archive tables

The data preparation layer preserves captures and event mentions without
aggregating prices or attributes over time. It also derives source-declared unit
memberships from canonical URLs. An episode/listing ID is a source label that
links evidence. A model may later select an observation unit,
resolve physical identities, combine repeated evidence, or construct time windows.
Those choices do not replace these tables.

`models/modal_granular.py` converts the immutable completed Chelsea snapshot into
Parquet on the `chelsea-archive` Modal Volume. No StreetEasy requests, GPU, local
archive download, or legacy latest-unit import are involved. Four CPU workers at
most process 2,000 snapshots per shard, with bounded Parquet buffers. The quality
report uses DuckDB with a 1 GB memory limit and two threads.

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
available in `fetch_observations.fetched_at`. `parsed_at` records this new
interpretation. Source-created/updated dates and history event dates are source
assertions, not collection dates or guaranteed attribute-validity intervals.

A 2015 price reported on a page collected in 2026 is historical price evidence.
It does **not** establish that the page's 2026 bedroom count, square footage,
washer-dryer, or view applied in 2015. We retain the page's attributes and full
listing JSON alongside its history without making that backward join. Source unit
labels retain padding and punctuation; they are not silently merged into physical
apartments. Building membership is an observed attribute too.

Every run freezes the separate `corrections.jsonl` ledger and its hash. The raw
columns are never overwritten. The current ledger is empty, so raw and corrected
values coincide. Applying future time-bounded edits requires explicitly choosing
the attribute effective time; preparation never substitutes collection time.
Use `Overlay.apply` to create a separate corrected projection at that selected
time, retaining correction IDs and the raw observation. This keeps human assertions
separate from source evidence and avoids forcing a temporal model at this stage.

For retained captures, the complete source listing and nested feature/amenity/pricing
JSON remain in the Parquet tables. The normalized numeric columns are conveniences.
Parse failures remain explicit in either the listing observation or its exclusion
record, linked to the original body. Missing amenities do not mean
absence. Unknown source fields can be extracted later without re-scraping.

## Running and resuming

Use the project's existing virtual environment (install the `model` and `modal`
extras when setting up a new environment). Deploy with:

```sh
.venv/bin/modal deploy models/modal_granular.py
```

Start a durable background invocation:

```python
import modal
call = modal.Function.from_name('chelsea-granular-data', 'run_all').spawn(
    'chelsea-granular-20260916')
print(call.object_id)
```

Read status through the deployed `status` function. Re-running the same ID resumes
completed shards without reprocessing them. Only one invocation per run ID should
be active. A parser, source, or correction-ledger change requires a **new run ID**.
`plan.json` fixes source snapshot and ledger identity; per-shard checkpoints are
written after their Parquet files. `complete.json` is written only after all shards
and the quality report finish. Tables in an incomplete run are not publication-ready.

The final `quality-report.json` is small enough to download separately. Full tables
stay in `/archive/datasets/<run-id>/`. Counts describe saved, scoped StreetEasy
evidence, not a census of all Chelsea homes or realized signed leases.

Workers write distinct shard files and commit only closed files, then the coordinator
reloads before auditing. This follows [Modal’s concurrent-writer guidance](https://modal.com/docs/guide/volumes). Resumption checks Parquet footers and row counts
as well as checkpoint/parser identity. Eight bounded read threads per worker hide
cold-file latency; they do not issue network requests to StreetEasy.

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

The normal `parse_listing` / `process_shard` transform extracts three additional
fields for every listing capture, including when the listing object fails to
parse. Retained observations store all three columns; exclusions retain the declared
href and diagnostic reason:

- `canonical_href`: the single declared canonical href from the HTML head.
- `canonical_unit_url`: a normalized StreetEasy building/unit URL, or null when
  the canonical points to a rental listing, building alone, another host, or an
  unsupported path.
- `canonical_unit_error`: an explicit reason for missing/unsupported/conflicting
  evidence. Rental captures with this field set are excluded under the policy below.

Extraction uses the same bounded head parser as the older-dataset evidence
backfill. The helper is included in the transform implementation hash, so resuming
an old run with changed canonical extraction is rejected rather than mixing
interpretations. Start a new output dataset for the next normal transform; do not
rewrite an already completed dataset in place.

The review app reads these fields directly, without an additional backfill step
on newly transformed datasets. Canonical extraction records source evidence; it
preserves source observations and does not apply human review decisions. The
canonical-URL association step below derives unit memberships during finalization;
manually reviewed associations remain in the separate reversible identity ledger.


## Rental inclusion rule

The normal transform retains a rental capture in `listing_observations` only when
its HTML declares a usable canonical StreetEasy unit page (`canonical_unit_url`
is non-null). A rental-listing URL, building-only URL, foreign/unsupported URL,
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

Shard checkpoints and the quality report count exclusions. Coverage reconciles
retained observations plus intentional exclusions against input snapshots; genuinely
unprocessed snapshots still fail finalization. Overlaps or event/source-change
rows from excluded captures also fail integrity checks. Empty filtered shards
retain valid Parquet schemas and support normal resumption.

The rule is recorded as `listing_filter: rental-canonical-unit-v1` in `plan.json`
and included in the transform implementation hash. It requires a fresh output run;
existing completed datasets and review decisions are not rewritten. Applied to the
current reviewed rental corpus (excluding media-gallery captures), this policy
would exclude 8,094 of 96,783 captures and retain 88,689. Failed rental-page parses
without usable canonical evidence are also counted as exclusions.


## Media-gallery pages

The transform classifies recognized `/media_gallery` endpoints as `media_gallery`
before dispatching to any listing, building, or inventory parser. This handles
legacy snapshots whose original archive `kind` was `listing`, `building`, or null.
`snapshots.kind` remains the original value; the new `snapshots.page_type` records
the derived classification used for processing and coverage checks.

`media_gallery_observations` retains the snapshot ID, URL, collection/parse times,
listing ID/type when available, building ID, canonical evidence, property details,
media and signature-gallery JSON, and the complete selected gallery object. A
gallery does not need `propertyHistory` or a canonical unit link. It contributes
no rows to `listing_observations`, `listing_exclusions`, `event_mentions`, or
`source_changes`, even if its payload includes history or price-change fields.
No photos are downloaded; the embedded source media payload is preserved.

Missing, ambiguous, unresolved, or unreadable gallery payloads remain explicit
gallery parse errors. The report separates gallery counts/errors from listing
errors, reconciles gallery coverage, and rejects leakage into listing/history
tables. Missing gallery history is never a parsing error.

`plan.json` records `page_classification: media-gallery-v1`; the gallery parser
is included in the implementation hash. This change requires a new output run,
so completed datasets remain immutable. All eight gallery pages in the frozen
Chelsea archive (six sales and two rentals) have been checked against this parser.


## Canonical unit associations

Normal local and Modal finalization now run `canonical-url-v1`. Every retained
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
are not independent verification of a physical home. Review-app decisions are a
separate overlay and are not imported into the raw transform.

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

Both local and cloud runners call `apartments.granular_export.finish`, which builds
memberships before the quality report and completion marker. For a normal local run:

```sh
PYTHONPATH=src .venv/bin/python models/transform_local.py \
  --snapshot /path/to/archive.sqlite3 \
  --bodies /path/to/bodies \
  --corrections config/corrections.jsonl \
  --output /path/to/new-dataset
```

Use a new output directory: completed datasets remain immutable. The rule is
recorded in `plan.json` and `complete.json` and included in the implementation hash.
