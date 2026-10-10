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
and counted in the JSON report. The copy uses `journal_mode=DELETE`, passes `integrity_check`
and is fsynced before the tool renames it into place and reports. The tool refuses a source whose
`crawler.lock` is held, and holds that lock for the whole copy: an immutable read of a database
still being written is silently wrong.

A compacted database is no longer self-contained: the stripped HTML exists only in `bodies/`.
Never prune `bodies/` (for Chelsea that is the shared `/data1/apartments/archive/bodies`, reached
through a symlink).

`tests/archive/test_compact.py` checks that the collection audit, the granular transform
(`listing_observations`, `event_mentions`, `snapshots`), `listing_identity.capture_evidence` and
`ArchiveStore` give the same answers on the copy. The other readers named in the review need no
change: `unit_history_pairs.py` reads `collection_memberships` or `scripts`, the alias tables
and model inputs read the parquet datasets, and current-listings captures never read crawl
databases.

Datasets do not pin the snapshot file: their `source_evidence_sha256` hashes the parsed rows,
and `granular_export`'s implementation hash covers parser code only. The tool does not write an
`archive.sqlite3.sha256`; whoever swaps a compacted copy in regenerates it with `sha256sum`.

## Measurements (Oct 8)

- **GV trial**: `snapshots/greenwich-village-20261001-final` went from 30.1 to 16.8 GB in about
  7 minutes. All 24,596 snapshot rows were stripped with verified bodies, and
  `collection_audit.audit` gave identical output on the original and on the copy. The trial copy
  was then deleted.
- **Duplicate crawl databases**: `cmp -l` of `crawls/chelsea-resume` against
  `snapshots/chelsea-backfill-20260912`, and of `crawls/west-village-low-rate-20260919` against
  `snapshots/west-village-backfill-20260930`, differs only in header bytes 19–20 (journal-mode
  flags) and 28 and 96 (change counter). The only reader of `crawls/chelsea-resume` is the disabled
  `apartments-archive.service` (raw archive browser on :8765).

- **Snapshots compacted** (Ben, typed Oct 8: "Compact the snapshots."), 01:56–04:16 ET, one at
  a time, smallest first. Before each swap the driver checked every other table row for row,
  every `snapshots` row for equality apart from `extracted`, and every changed `extracted` for
  JSON equality once the HTML is replaced by `content_sha256` = `body_hash`; it also compared the
  collection audit where the database has the rental-canonical tables (not the two Chelsea
  snapshots). The 161 unchanged Chelsea rows predate Oxylabs (`no_provider_capture`). File modes
  kept; `.sha256` regenerated. Driver and log: `/data1/apartments/tmp/se-compact/`.

  | snapshot | rows stripped | GB before | GB after |
  |---|---|---|---|
  | `west-village-backfill-20260921` | 4,136 of 4,136 | 4.8 | 2.7 |
  | `chelsea-20260908` | 6,080 of 6,241 | 7.4 | 4.3 |
  | `greenwich-village-20261001-final` | 24,596 of 24,596 | 30.1 | 16.8 |
  | `flatiron-gramercy-park-20261005-final` | 38,819 of 38,819 | 48.4 | 27.2 |
  | `west-village-backfill-20260930` | 44,785 of 44,785 | 55.1 | 30.8 |
  | `chelsea-backfill-20260912` | 124,808 of 124,969 | 158.9 | 89.1 |
  | total | | 304.7 | 170.9 |

  `snapshots/chelsea-20260908/complete.json` still records the pre-compaction byte count.

## Crawls write compact databases (Oct 10)

Ben, Oct 10: "Can we change the code, without changing functionality that we depend on, so that
either 1) the extra data is never created or 2) only the compressed version of the data is
created." Since then `crawler.py` stores `provider_capture` through `compact.without_page_copy`:
each `results[].content` that is the page body is replaced by `content_sha256` when the row is
written, the same rewrite `compact_database` makes afterwards (shared `compact.strip_results`).
A new crawl's database is therefore already compact, and its final snapshot is a plain copy;
running the compaction tool on it changes nothing. `crawler.py` is in the implementation hashes
of `rental_discovery` and `candidate_refresh` plans, so a run prepared before the change refuses
to resume (none was running) and a rebuilt plan gets a new hash. The three Oct 8 crawl databases (East Village,
NoMad, Stuyvesant Town/PCV) were deleted on Oct 10 (Ben: "delete them."); their compacted
snapshots and `bodies/` remain.

## Not done, and why

- **Compressing `extracted`** (zstd in SQLite, or a sidecar). Many readers parse the column
  directly with `json.loads` or SQL `json_extract`; a format change would touch all of them. A
  sample of 300 Stuyvesant Town rows (Oct 10) compresses 7.7× with zlib; `scripts` is 74% of it.
- **Dropping `scripts`**: in use (above).
- **Transparent compression**: `/data1` is ext4.
