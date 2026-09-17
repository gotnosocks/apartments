# Granular archive tables

The data preparation layer does **not** aggregate to a listing episode, physical
unit, calendar month, or any other modeling interval. An episode/listing ID is a
source label that links evidence. A model may later select an observation unit,
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
| `listing_observations` | A listing interpretation of one snapshot, including failures |
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

The complete source listing and nested feature/amenity/pricing JSON remain in the
Parquet tables. The normalized numeric columns are conveniences, and parse failures
remain explicit rows linked to the original body. Missing amenities do not mean
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
columns for every listing capture, including when the listing object fails to
parse:

- `canonical_href`: the single declared canonical href from the HTML head.
- `canonical_unit_url`: a normalized StreetEasy building/unit URL, or null when
  the canonical points to a rental listing, building alone, another host, or an
  unsupported path.
- `canonical_unit_error`: an explicit reason for missing/unsupported/conflicting
  evidence. Missing evidence does not itself invalidate the listing's other data.

Extraction uses the same bounded head parser as the older-dataset evidence
backfill. The helper is included in the transform implementation hash, so resuming
an old run with changed canonical extraction is rejected rather than mixing
interpretations. Start a new output dataset for the next normal transform; do not
rewrite an already completed dataset in place.

The review app reads these fields directly, without an additional backfill step
on newly transformed datasets. Canonical extraction records source evidence; it
never silently merges listings or applies human review decisions. Durable unit
associations remain in the separate reversible identity ledger.
