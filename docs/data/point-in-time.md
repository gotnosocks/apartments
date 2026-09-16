# Collection-time and apartment attribute history

The raw archive is authoritative. `data/archive/archive.sqlite3` retains each
response (URL, fetch timestamp, status, headers, body hash, crawl generation).
Compressed bodies retain the complete saved document, including fields that the
current parser does not understand. Unchanged 200 responses and 304 revalidations
remain separate collection observations while sharing body storage. Errors are
observations, not proof that apartment attributes changed or disappeared.

The analysis database now has these append-only tables:

- `archive_observations`: a local mirror of **every** response, including building
  pages, sale pages, repeated/unchanged fetches, and errors. It includes the original
  collection time and a relative raw-body path. Copies of the same archive retain
  the same archive key across relocation.
- `attribute_versions`: each rental capture's complete normalized JSON, provenance,
  episode ID, commonly queried attributes, source-reported dates, and interpretation
  version. New captures and changed interpretations are appended, not overwritten.
- `event_capture_evidence`: links a price event to every retained capture
  interpretation that supports it, including that interpretation's original event JSON.
- `attribute_collection_evidence`: joins attribute versions to successful raw fetches
  of the same URL/body, including unchanged revalidations.

## Three different clocks

`collected_at` is when we collected the response. `source_created_at`,
`source_updated_at`, and `source_on_market_date` are assertions from the source
listing, retained separately. `recorded_at` is when this local interpretation or
observation mirror was recorded. `collection_time_basis` explains where the
collection timestamp came from. The complete original source values are retained
in JSON even if a date cannot be converted into a timestamp.

A listing created in 2015 and first scraped in 2026 is **not** something we knew in
2015. Nor does its creation date prove that its current page attributes were true
then. We deliberately do not manufacture effective-from/effective-to dates for
renovations, furnishing, room counts, or other changes.

Existing archive captures are backfilled using original response timestamps, which
may predate their local extraction. Historical import/processing times that were
not originally saved cannot be recovered: backfilled `recorded_at` is the migration
time. Legacy `listings.first_seen_at` and `last_seen_at` contain old ingestion-time
semantics; use the temporal evidence tables for collection-time questions. The
current `listings` row remains a convenience projection used by the unchanged model.

## Queries

Compare the attributes collected for a unit over time, separated by listing episode:

```sql
SELECT episode_id, collected_at, source_created_at, source_updated_at,
       bedrooms, bathrooms, square_feet, attributes_json, capture_id, version_id
FROM attribute_versions
WHERE source_listing_id = 'ten23-500-west-23rd-street-new_york/4c'
ORDER BY collected_at, episode_id, recorded_at;
```

Restrict evidence to pages collected before a cutoff. Add a `recorded_at` cutoff
when reproducing the interpretations actually present in the database at that time:

```sql
SELECT * FROM attribute_versions
WHERE collected_at <= TIMESTAMPTZ '2026-09-07 23:59:59+00'
  AND recorded_at <= TIMESTAMPTZ '2026-09-08 23:59:59+00';
```

Keep all episodes; the last page downloaded can be an older episode. This query
is a set of available evidence, not an assertion that a particular state was true
at every instant. Original responses can be re-parsed later with different schemas
without modifying the retained earlier interpretations.

## Migration and incremental updates

```sh
uv run apartments backfill-temporal
uv run apartments import-archive
```

The migration reads existing local captures and fetch records; it does not contact
StreetEasy or change the current analytical model. Repeating it adds no duplicate
versions. Each future imported rental capture records its attribute interpretation
and event evidence in the same transaction as the import. Every import also syncs
fetch evidence, even when the body is unchanged or no new rental snapshot is found.
A re-parser can call `retain_capture` with updated normalized JSON or a new parser
version to preserve its interpretation without destroying prior evidence.

The September 8, 2026 migration retained 1,582 attribute versions, 4,856 fetch
observations, and 65,246 event-to-capture evidence links. All migrated attribute
versions have original response collection timestamps. A repeat migration added
zero rows. The existing listings, captures, listing events, listing snapshots,
and furnishing periods were compared against the pre-migration backup and are
identical. No model fit or new scrape was run as part of this migration.


## Separate human corrections

Human attribute corrections now have a separate append-only overlay ledger and a
streaming raw-plus-corrected observation exporter. Corrections retain both when a
human entered the assertion and its explicitly chosen effective-time scope.
See [correction overlays](corrections.md) for targets, revisions, conflicts, strict
knowledge-time cutoffs, and the boundary with the legacy monthly fitter.
