# Archive storage

Review of the crawl and scrape storage on `/data1`, Oct 8 2026 (Ben: "Review the current crawl /
scrape design and make it more storage efficient without breaking existing functionality").

## Where the bytes are

A crawl keeps each page twice:

- **The body**: gzip, content-addressed, in the crawl's `bodies/<hh>/<sha256>.gz` (11 GB for all
  neighbourhoods).
- **The database** `archive.sqlite3`: the `snapshots` table is 99.5% of each database. Its
  `extracted` JSON averages about 1.2 MB a row.

Average KB per snapshot row, by key of `extracted` (sampled by rowid):

| key | GV | FGP | Chelsea backfill | WV backfill |
|---|---|---|---|---|
| `provider_capture` | 530 | 539 | 548 | 517 |
| `scripts` | 472 | 481 | 500 | 461 |
| `images`, `anchors`, `data_attributes`, `links`, `text`, `tables` | ~200 | | | |

`provider_capture` is the Oxylabs envelope (`oxylabs.py` puts it in
`response.meta['archive_provider']`; `crawler.py` copies it into `extracted`). In it,
`results[].content` is the whole page HTML: 533 of its 530–548 KB. That HTML hashes to the row's
`body_hash` (24 of 24 sampled GV rows), so it is a second, uncompressed copy of the body file.
No reader uses it: the only reference is the writer in `crawler.py`, and
`capture.capture_metadata` already drops `content` from observations for this reason. It is
about 44% of every crawl and snapshot database.

`scripts` is also derived from the HTML, but scope, listing identity, the modal archive readers
and the building census read it, so it stays.

Sizes on Oct 8 (GiB):

| database | GiB |
|---|---|
| `snapshots/chelsea-backfill-20260912` | 148.0 |
| `crawls/chelsea-resume` (crawl DB, same byte size as the Chelsea snapshot) | 148.0 |
| `crawls/west-village-low-rate-20260919` (crawl DB, same byte size as the WV snapshot) | 51.3 |
| `snapshots/west-village-backfill-20260930` | 51.3 |
| `snapshots/flatiron-gramercy-park-20261005-final` | 45.1 |
| `snapshots/greenwich-village-20261001-final` | 28.0 |
| `snapshots/chelsea-20260908` | 6.9 |
| `snapshots/west-village-backfill-20260921` | 4.5 |

## Compaction tool

`python -m streeteasy_archive.compact SOURCE DEST --crawl-dir CRAWL` writes a new database. The
source is opened immutable and never changed. The copy keeps every table, row id, index and
`sqlite_sequence`, and rewrites only `snapshots.extracted`: in `provider_capture.results[]`,
`content` is replaced by `content_sha256` (= `body_hash`). A row is stripped only when its
content hashes to `body_hash` and the body file under `CRAWL/bodies/` exists and decompresses to
that hash (`--no-verify-bodies` skips the decompression). Every other row is copied unchanged
and counted in the JSON report. The copy uses `journal_mode=DELETE` and passes
`integrity_check`.

`tests/archive/test_compact.py` checks that the collection audit, the granular transform
(`listing_observations`, `event_mentions`, `snapshots`), `listing_identity.capture_evidence` and
`ArchiveStore` give the same answers on the copy. The other readers named in the review need no
change: `unit_history_pairs.py` reads `collection_memberships` or `scripts`, the alias tables
and model inputs read the parquet datasets, and current-listings captures never read crawl
databases.

Datasets do not pin the snapshot file: their `source_evidence_sha256` hashes the parsed rows,
and `granular_export`'s implementation hash covers parser code only. A compacted snapshot gets a
new `archive.sqlite3.sha256`.

## Not done, and why

- **Editing the crawler** so new crawls never store the copy. `crawler.py`, `capture.py`,
  `oxylabs.py` and `store.py` are hash-locked (`ruff.toml`; `rental_discovery.py` checks them
  against frozen implementations). For the next crawl, compact its final snapshot with this tool
  instead of a plain copy.
- **Compressing `extracted`** (zstd in SQLite, or a sidecar). Many readers parse the column
  directly with `json.loads` or SQL `json_extract`; a format change would touch all of them.
- **Dropping `scripts`**: in use (above).
- **Transparent compression**: `/data1` is ext4.
