"""Write the records file: each distinct API record of an ad, as the granular export gave it.

    python pipeline/steps/records.py --export DIR --cache DIR --out DIR

`ops/pipeline/build.py` calls `write` after its plan, with the database's own connection, and
puts the file beside the rows and ads files. Run as a script, the module opens a DuckDB
connection of its own, writes the file into OUT and records nothing in a catalog.

The page parser's output gave the frontier builders each record as `raw_listing_json`, with
`collected_at`, `snapshot_id` and `listing_type` beside it. To give the builders the same input
from the export, the step works like this:

1. It groups the export's answers with a record by listing and by `record_sha256`, in a
   temporary table. Each group becomes a row of the file, with the times of its first and last
   answer and the export's `response_id` of the first one.
2. It reads each record missing from the cache with `serialize`, in worker processes, and keeps
   the results in Parquet files in the cache folder, under a folder named by the SHA-256 of this
   file. A top-up then reads only its new records, and a change to this file starts a new
   folder. Each cache file holds up to 20,000 records sorted by listing, in row groups of 2,048.
3. It takes the listings in ranges of 100,000 IDs. For each range it joins the range's groups
   to their records, which DuckDB finds by the row groups' listing IDs without reading the
   whole cache, sorts them by listing and then by first answer, and appends them to the file.
   On Oct 16 DuckDB ran out of a 1 GB limit sorting run 2's 238,532 records in one query, and a
   range holds about 60,000.
4. It writes the file under a `.part` name, hashes it and renames it to
   `records-<first 16 hex digits of the SHA-256>.parquet`. When that file is already there with
   the same SHA-256, it keeps the old one.

The file has a row for each distinct record of each listing:

- `listing_id`: the ad's listing ID.
- `collected_at`: the time of the first answer with this record, in seconds since the epoch.
  The granular export gave a record the time of the archive snapshot of its body, and the
  collector writes a snapshot on the first answer with a new body at a page's URL. The export
  keeps times in microseconds, so the value can differ from the archive's by less than one.
- `last_collected_at`: the time of the last answer with the record.
- `response_id`: the export's ID of the first answer. The export has no archive snapshot IDs,
  and the frontier builders used them only to order two snapshots with the same time.
- `listing_type`: 'rental' on every row, as the granular export gave every API record.
- `record_sha256`: the export's SHA-256 of the record.
- `raw_listing_json`: the record with `__typename` keys dropped and integral floats written as
  integers, as `apartments.graphql_listing.normalize` reads it, serialized as the granular
  export serialized it, with sorted keys, no spaces and non-ASCII characters left as they are.

`PIPELINE_WORKERS` sets the number of worker processes, 4 unless set.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing
import os
import sys
import time
import uuid
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

# The step sends records to the workers in batches of BATCH and writes a cache file every FLUSH
# records, so a step cut short keeps most of its work.
BATCH = 500
FLUSH = 20_000
CACHE_ROW_GROUP = 2_048
# The listing IDs of a range of the final sort.
RANGE = 100_000
# A record runs to about 4 KB, so a row group of 16,384 rows holds about 64 MB of JSON, which a
# reader takes in at once.
ROW_GROUP = 16_384
# DuckDB reads ahead of the workers on each thread, and on Oct 16 twelve threads took run 2's
# records past 3 GB.
THREADS = 4
CACHE = pa.schema(
    [
        ("listing_id", pa.int64()),
        ("record_sha256", pa.string()),
        ("raw_listing_json", pa.string()),
    ]
)
SORT = [
    ("listing_id", "ascending"),
    ("collected_at", "ascending"),
    ("record_sha256", "ascending"),
]


def normalize(value):
    """The record as `apartments.graphql_listing.normalize` gives it: no `__typename`, integral
    floats as ints."""
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items() if k != "__typename"}
    if isinstance(value, list):
        return [normalize(v) for v in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def serialize(record: str) -> str:
    """The export's record text as the granular export's `raw_listing_json`."""
    return json.dumps(
        normalize(json.loads(record)),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def serialize_batch(rows):
    return [
        (listing_id, sha256, serialize(record)) for listing_id, sha256, record in rows
    ]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_cache(folder: Path, rows):
    table = pa.Table.from_arrays(
        [pa.array(column, field.type) for column, field in zip(zip(*rows), CACHE)],
        schema=CACHE,
    ).sort_by([("listing_id", "ascending"), ("record_sha256", "ascending")])
    name = f"{uuid.uuid4().hex}.parquet"
    part = folder / f"{name}.part"
    pq.write_table(table, part, compression="zstd", row_group_size=CACHE_ROW_GROUP)
    # The data goes to disk before the rename, so a crash leaves either no file or a whole one.
    with open(part, "rb") as file:
        os.fsync(file.fileno())
    os.replace(part, folder / name)


def sql_list(paths) -> str:
    return "[" + ", ".join("'" + str(p).replace("'", "''") + "'" for p in paths) + "]"


def fill_cache(cursor, answers: str, folder: Path, workers: int) -> int:
    """Read each record missing from the cache folder into it, and return their count."""
    # One process at a time writes the cache, so a `.part` file here comes from a step that
    # stopped.
    for part in folder.glob("*.part"):
        part.unlink()
    cached = (
        f"read_parquet('{folder}/*.parquet')" if any(folder.glob("*.parquet")) else None
    )
    # The first answer for each record missing from the cache. The semi join keeps the picks in
    # its hash table and streams the records past it.
    missing = f"""
        WITH picks AS (
            SELECT record_sha256, min(response_id) AS response_id
            FROM {answers} WHERE outcome = 'record'
            {f"AND record_sha256 NOT IN (SELECT record_sha256 FROM {cached})" if cached else ""}
            GROUP BY record_sha256
        )
        SELECT a.listing_id, a.record_sha256, a.record
        FROM {answers} a SEMI JOIN picks p
            ON a.record_sha256 = p.record_sha256 AND a.response_id = p.response_id
        WHERE a.outcome = 'record'
    """
    reader = cursor.execute(missing).to_arrow_reader(BATCH)
    count, pending, rows = 0, [], []
    with ProcessPoolExecutor(
        workers, mp_context=multiprocessing.get_context("spawn")
    ) as pool:
        for batch in reader:
            triples = list(
                zip(
                    batch.column("listing_id").to_pylist(),
                    batch.column("record_sha256").to_pylist(),
                    batch.column("record").to_pylist(),
                )
            )
            pending.append(pool.submit(serialize_batch, triples))
            # At most two batches per worker wait, to bound memory.
            while len(pending) > 2 * workers:
                rows.extend(pending.pop(0).result())
            if len(rows) >= FLUSH:
                write_cache(folder, rows)
                count += len(rows)
                rows = []
        for future in pending:
            rows.extend(future.result())
    if rows:
        write_cache(folder, rows)
        count += len(rows)
    return count


def write(cursor, files, cache: Path, out: Path, workers: int | None = None) -> dict:
    """Write the records file of the export files `files` into `out`, and return its name,
    SHA-256 and row count, with the count of records the step read into the cache."""
    workers = workers or int(os.environ.get("PIPELINE_WORKERS", "4"))
    folder = cache / file_sha256(Path(__file__))
    folder.mkdir(parents=True, exist_ok=True)
    answers = f"read_parquet({sql_list(files)})"
    cursor.execute(f"SET threads = {THREADS}")
    try:
        added = fill_cache(cursor, answers, folder, workers)
        cursor.execute(
            f"""CREATE OR REPLACE TEMP TABLE record_groups AS
            SELECT listing_id, record_sha256,
                epoch_us(min(fetched)) / 1e6 AS collected_at,
                epoch_us(max(fetched)) / 1e6 AS last_collected_at,
                arg_min(response_id, fetched) AS response_id
            FROM {answers} WHERE outcome = 'record'
            GROUP BY listing_id, record_sha256"""
        )
        try:
            line = write_file(cursor, f"read_parquet('{folder}/*.parquet')", out)
        finally:
            cursor.execute("DROP TABLE IF EXISTS record_groups")
    finally:
        cursor.execute("RESET threads")
    return line | {"read": added}


def write_file(cursor, cached: str, out: Path) -> dict:
    (doubled,) = cursor.execute(
        f"SELECT count(*) - count(DISTINCT record_sha256) FROM {cached}"
    ).fetchone()
    if doubled:
        raise ValueError(f"the cache holds {doubled} records twice")
    groups, low, high = cursor.execute(
        "SELECT count(*), min(listing_id), max(listing_id) FROM record_groups"
    ).fetchone()
    out.mkdir(parents=True, exist_ok=True)
    part = out / f"records-{os.getpid()}.parquet.part"
    rows, writer = 0, None
    try:
        for start in range(low - low % RANGE, high + 1, RANGE):
            table = cursor.execute(
                f"""SELECT g.listing_id, g.collected_at, g.last_collected_at, g.response_id,
                    'rental' AS listing_type, g.record_sha256, c.raw_listing_json
                FROM record_groups g JOIN {cached} c USING (record_sha256)
                WHERE g.listing_id >= {start} AND g.listing_id < {start + RANGE}
                    AND c.listing_id >= {start} AND c.listing_id < {start + RANGE}"""
            ).to_arrow_table()
            if not table.num_rows:
                continue
            table = table.sort_by(SORT)
            if writer is None:
                writer = pq.ParquetWriter(
                    part,
                    table.schema,
                    compression="zstd",
                    use_dictionary=["listing_type"],
                )
            writer.write_table(table, row_group_size=ROW_GROUP)
            rows += table.num_rows
        if writer is not None:
            writer.close()
            writer = None
        if rows != groups:
            raise ValueError(f"the cache lacks {groups - rows} of {groups} records")
        digest = file_sha256(part)
    except BaseException:
        if writer is not None:
            writer.close()
        part.unlink(missing_ok=True)
        raise
    target = out / f"records-{digest[:16]}.parquet"
    if target.exists() and file_sha256(target) == digest:
        part.unlink()
    else:
        part.rename(target)
    return {"path": target.name, "sha256": digest, "rows": rows}


def export_files(export: Path) -> list[str]:
    """The export's listed ads files, as `config.exported` lists them."""
    paths = set()
    for line in (export / "manifest.ndjson").read_text().splitlines(keepends=True):
        if not line.endswith("\n") or not line.strip():
            continue
        entry = json.loads(line)
        if entry["table"] == "ads":
            paths.add(entry["path"])
    return [str(export / path) for path in sorted(paths)]


def main(argv=None) -> int:
    import duckdb

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    started = time.time()
    db = duckdb.connect(
        config={
            "TimeZone": "UTC",
            "memory_limit": os.environ.get("PIPELINE_MEMORY", "5GB"),
            "preserve_insertion_order": False,
            "temp_directory": str(args.cache / "spill"),
        }
    )
    line = write(db.cursor(), export_files(args.export), args.cache, args.out)
    db.close()
    print(json.dumps(line | {"seconds": round(time.time() - started, 1)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
