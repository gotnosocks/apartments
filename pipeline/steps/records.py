"""Write the records file: each distinct API record of an ad, as the granular export gave it.

    python pipeline/steps/records.py --export DIR --cache DIR --out DIR

`ops/pipeline/build.py` calls `write` after its plan, with the database's own connection, and
puts the file beside the rows and ads files. Run as a script, the module opens a DuckDB
connection of its own, writes the file into OUT and records nothing in a catalog.

The page parser's output gave the frontier builders each record as `raw_listing_json`, with
`collected_at`, `snapshot_id` and `listing_type` beside it. To give the builders the same input
from the export, the step works like this:

1. It locks `CACHE/.lock`, and stops when another records step holds that lock. With the lock
   held, any `.part` file in the cache comes from a step that stopped, and the step deletes it.
2. It reads each record missing from the cache with `serialize`, in worker processes, and keeps
   the results in Parquet files in the cache folder, under a folder named by the SHA-256 of this
   file. A top-up then reads only its new records, and a change to this file starts a new
   folder. Each cache file holds 20,000 records or a few thousand more, sorted by listing, in
   row groups of 2,048.
3. It groups the export's answers with a record by listing and by `record_sha256`, in a
   temporary table. Each group becomes a row of the file, with the times of its first and last
   answer and the export's `response_id` of the first one. Two answers at the same microsecond
   go by the lower `response_id`, so two builds pick the same one.
4. It takes the listings in ranges of 100,000 IDs. For each range it joins the range's groups
   to their records, which DuckDB finds by the row groups' listing IDs without reading the
   whole cache, sorts them by listing and then by first answer, and appends them to the file.
   On Oct 16 DuckDB ran out of a 1 GB limit sorting run 2's 238,532 records in one query, and a
   range holds about 60,000.
5. It writes the file under a `.part` name, hashes it and renames it to
   `records-<first 16 hex digits of the SHA-256>.parquet`. When that file is already there with
   the same SHA-256, it keeps the old one.
6. It deletes the cache folders that other versions of this file left, about 3 GB each on the
   Oct 16 export, and then releases the lock.

When `ops/pipeline/build.py` gives the export's version, the step reads its notes in the cache
folder, `written.ndjson`, right after taking the lock. If they give a file under that version for
the same OUT, and the file still has its noted size and modification time, the step returns the
noted line and skips steps 2 to 5, along with step 1's removal of `.part` files, which runs at
the start of step 2. Otherwise it goes on as above and notes the file it writes.
On the Oct 17 export, writing and hashing the 3.4 GB file took about 90 s of each build.

The step stops with an error on an export without records, rather than writing an empty file.

The file has a row for each distinct record of each listing:

- `listing_id`: the ad's listing ID.
- `collected_at`: the time of the first answer with this record, in seconds since the epoch.
  The granular export gave a record the time of the archive snapshot of its body, and the
  collector writes a snapshot on the first answer with a new body at a page's URL. The export
  keeps times in microseconds, so the value can differ from the archive's by less than one.
- `last_collected_at`: the time of the last answer with the record.
- `response_id`: the export's ID of the first answer, the lower one when two answers share the
  first microsecond. The export has no archive snapshot IDs,
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
import fcntl
import hashlib
import json
import multiprocessing
import os
import re
import shutil
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
# The cache folder's notes of the files the step wrote, a line each.
NOTES = "written.ndjson"
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
    # `write` holds the cache's lock, so a `.part` file here comes from a step that stopped.
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


def write(
    cursor,
    files,
    cache: Path,
    out: Path,
    workers: int | None = None,
    version: str | None = None,
) -> dict:
    """Write the records file of the export files `files` into `out`, and return its name,
    SHA-256 and row count, with the count of records the step read into the cache and whether
    it reused an earlier file.

    `ops/pipeline/build.py` passes `version`, its SHA-256 over the export's list of ads files.
    After writing a file, the step notes it under that version in the cache folder. A later
    call with the same version and the same code looks up the note, and when the noted file is
    still in `out` with its noted size and modification time, the call returns the noted line
    without reading the export."""
    workers = workers or int(os.environ.get("PIPELINE_WORKERS", "4"))
    if not files:
        raise ValueError("the export lists no ads files")
    folder = cache / file_sha256(Path(__file__))
    folder.mkdir(parents=True, exist_ok=True)
    with open(cache / ".lock", "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(
                f"another records step holds {cache / '.lock'}"
            ) from None
        line = written(folder, version, out) if version else None
        if line is None:
            line = write_locked(cursor, files, folder, out, workers) | {"reused": False}
            if version:
                note(folder, version, out, line)
        for other in cache.iterdir():
            if (
                other != folder
                and other.is_dir()
                and re.fullmatch("[0-9a-f]{64}", other.name)
            ):
                shutil.rmtree(other)
    return line


def written(folder: Path, version: str, out: Path) -> dict | None:
    """The line of the latest file noted under `version` for `out`, when that file keeps its
    noted size and modification time, or None."""
    notes = folder / NOTES
    if not notes.exists():
        return None
    for text in reversed(notes.read_text().splitlines()):
        # A step stopped while appending leaves a cut-off line.
        try:
            entry = json.loads(text)
        except json.JSONDecodeError:
            continue
        if entry["version"] != version or entry["out"] != str(out.resolve()):
            continue
        try:
            stat = (out / entry["path"]).stat()
        except FileNotFoundError:
            return None
        if (stat.st_size, stat.st_mtime_ns) != (entry["bytes"], entry["mtime_ns"]):
            return None
        return {key: entry[key] for key in ("path", "sha256", "rows")} | {
            "read": 0,
            "reused": True,
        }
    return None


def note(folder: Path, version: str, out: Path, line: dict) -> None:
    """Append the file of `line` to the notes of `folder`, under `version`, with its size and
    modification time."""
    stat = (out / line["path"]).stat()
    entry = {
        "version": version,
        "out": str(out.resolve()),
        "path": line["path"],
        "sha256": line["sha256"],
        "rows": line["rows"],
        "bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }
    path = folder / NOTES
    # After a cut-off line, the entry starts a line of its own.
    start = "\n" if path.exists() and not path.read_text().endswith("\n") else ""
    with open(path, "a") as f:
        f.write(start + json.dumps(entry, sort_keys=True) + "\n")


def write_locked(cursor, files, folder: Path, out: Path, workers: int) -> dict:
    answers = f"read_parquet({sql_list(files)})"
    cursor.execute(f"SET threads = {THREADS}")
    try:
        added = fill_cache(cursor, answers, folder, workers)
        if not any(folder.glob("*.parquet")):
            raise ValueError("the export holds no records")
        cursor.execute(
            f"""CREATE OR REPLACE TEMP TABLE record_groups AS
            SELECT listing_id, record_sha256,
                epoch_us(min(fetched)) / 1e6 AS collected_at,
                epoch_us(max(fetched)) / 1e6 AS last_collected_at,
                arg_min(response_id, (fetched, response_id)) AS response_id
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
    if not groups:
        raise ValueError("the export holds no records")
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
