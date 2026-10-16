"""Unpack the city archive into Parquet files for the city models.

`ops/pipeline/city.py` keeps the city's bulk records of lots and buildings in
`/data1/apartments/archive/city` and lists each file in the archive's `manifest.ndjson`.
DuckDB can't read a member of a zip, so `config.py` calls `unpack` as the project loads, and the
city models read the Parquet files `unpack` writes. For each listed file, `unpack` works in
these steps:

1. It picks a folder for the file: `<code>/<entry>` under the cache, where `<code>` is the
   first 16 hex digits of the SHA-256 of this module's file and DuckDB's version, and `<entry>`
   the same for the file's manifest line. When the folder exists, it goes on to the next file.
2. It copies each member it reads out of a zip, or the gzipped CSV itself, to a scratch file.
   An old MapPLUTO table ends in a DOS end-of-file byte, and the copy leaves that byte out. As
   it copies, it checks the bytes as UTF-8, and it takes Latin-1 for a member with bytes UTF-8
   can't decode.
3. DuckDB reads the copy as CSV, with every value as text. Each column name goes to lower
   case. A row with too few or too many values goes to the folder's `rejects.parquet`, with
   DuckDB's line number for it, DuckDB's reason and the row's text, and the read goes on.
4. It writes each table member to a Parquet file, with these columns after the member's own:
   - `release` and `published`, from the manifest line;
   - `file`, the path of the archive's file, and `member`, the member of the zip;
   - `record`, the row's place among the rows DuckDB kept from the member, from 1;
   - `encoding`, the one DuckDB read the copy with.
5. It flushes the scratch folder to disk and renames it to the file's folder.

Each folder holds the rows of one listed file, read by one version of this code. When the
module or DuckDB changes, or the manifest gains a line, `unpack` writes new folders and leaves
the existing ones as they are. It holds a lock on the code's folder while it works, so two loads
never unpack the same file at once, and it marks the lock file's time when it finishes. Then it
deletes the folder of each other version of the code whose lock file is more than a week old,
when no load holds that lock. A file holding no member for one of its source's tables stops the
unpack with an error.

`TABLES` gives the members each table takes. `unpack` returns each table's Parquet files,
sorted, with the rejected rows under `rejects`, along with each listed file of a source the
tables read and its SHA-256. For a table with no file in the archive, it returns an empty file
with only the added columns.
"""

from __future__ import annotations

import codecs
import fcntl
import gzip
import hashlib
import json
import os
import shutil
import time
import zipfile
from pathlib import Path

import duckdb

# Each table, with the source it reads and the members it takes from each file. A zip of PAD
# holds a second copy of each table in a `win11` folder from 24c to 25c, and the table takes the
# copy at the zip's root. A file of rows from NYC Open Data is its own member, with the name "".
TABLES = {
    "pad_addresses": ("pad", lambda name: name == "bobaadr.txt"),
    "pad_lots": ("pad", lambda name: name == "bobabbl.txt"),
    "pluto": ("pluto", lambda name: name.lower().endswith((".txt", ".csv"))),
    "footprints": ("footprints", lambda name: name == ""),
    "landmarks": ("landmarks", lambda name: name == ""),
    "dob_now_co": ("dob_now_co", lambda name: name == ""),
    "dob_co": ("dob_co", lambda name: name == ""),
}
# A new DuckDB may read a CSV differently, so its version goes into the hash with the code.
CODE = hashlib.sha256(
    Path(__file__).read_bytes() + duckdb.__version__.encode()
).hexdigest()[:16]
# A DOS end-of-file byte.
SUB = b"\x1a"
WEEK = 7 * 24 * 3600
# The columns each table adds to a member's own, and the columns of the refused rows.
ADDED = "release VARCHAR, published TIMESTAMPTZ, file VARCHAR, member VARCHAR, record BIGINT, encoding VARCHAR"
REJECTS = (
    "release VARCHAR, published TIMESTAMPTZ, file VARCHAR, member VARCHAR, line UBIGINT, "
    "column_name VARCHAR, error_type VARCHAR, error_message VARCHAR, csv_line VARCHAR"
)


def listed(archive: Path) -> list[dict]:
    """The archive's manifest lines, each with its text under `line`. A line with no newline at
    the end is one a stopped fetch cut off, and the fetch's next run drops it."""
    entries = []
    for line in (archive / "manifest.ndjson").read_text().splitlines(keepends=True):
        if line.endswith("\n") and line.strip():
            entries.append(json.loads(line) | {"line": line.rstrip("\n")})
    return entries


def members(path: Path) -> list[str]:
    if path.suffix != ".zip":
        return [""]
    with zipfile.ZipFile(path) as z:
        return sorted(i.filename for i in z.infolist() if not i.is_dir())


def copy_member(path: Path, member: str, out: Path) -> str:
    """Copy the member of the archive's file at `path` to `out`, leaving out a final DOS
    end-of-file byte. Return the copy's encoding: UTF-8 when all its bytes decode as UTF-8, and
    Latin-1 otherwise."""
    if member:
        source = zipfile.ZipFile(path).open(member)
    else:
        source = gzip.open(path)
    decoder = codecs.getincrementaldecoder("utf-8")()
    encoding = "utf-8"
    with source, open(out, "wb") as f:
        while chunk := source.read(1 << 20):
            f.write(chunk)
            try:
                decoder.decode(chunk)
            except UnicodeDecodeError:
                encoding = "latin-1"
    with open(out, "rb+") as f:
        if f.seek(0, os.SEEK_END) and f.seek(-1, os.SEEK_END) and f.read(1) == SUB:
            f.truncate(f.tell() - 1)
    try:
        decoder.decode(b"", final=True)
    except UnicodeDecodeError:
        encoding = "latin-1"
    return encoding


def read_csv(path: Path, encoding: str) -> str:
    return (
        f"read_csv('{path}', header = true, all_varchar = true, delim = ',', quote = '\"', "
        f"escape = '\"', strict_mode = true, encoding = '{encoding}', store_rejects = true)"
    )


def write_member(db, copy: Path, encoding: str, entry: dict, member: str, out: Path):
    """Write the CSV `copy` of a member to the Parquet file `out`, and add the rows DuckDB
    refuses to the `rejects` table."""
    names = [
        row[0]
        for row in db.sql(
            f"DESCRIBE SELECT * FROM {read_csv(copy, encoding)}"
        ).fetchall()
    ]
    columns = ", ".join(
        '"{}" AS "{}"'.format(
            n.replace('"', '""'), n.strip().lower().replace('"', '""')
        )
        for n in names
    )
    values = [entry["release"], entry["published"], entry["path"], member]
    db.execute(
        f"""COPY (
            SELECT {columns}, ? AS release, ?::TIMESTAMPTZ AS published, ? AS file,
                ? AS member, ordinality AS record, ? AS encoding
            FROM {read_csv(copy, encoding)} WITH ORDINALITY
        ) TO '{out}' (FORMAT parquet, COMPRESSION zstd)""",
        [*values, encoding],
    )
    db.execute(
        """INSERT INTO rejects
        SELECT ?, ?::TIMESTAMPTZ, ?, ?, line, column_name, error_type::VARCHAR, error_message,
            csv_line
        FROM reject_errors
        ORDER BY line, column_idx""",
        values,
    )
    db.execute("DROP TABLE reject_errors; DROP TABLE reject_scans")


def unpack_file(archive: Path, entry: dict, folder: Path):
    path = archive / entry["path"]
    part = folder.with_name(f"{folder.name}.part")
    shutil.rmtree(part, ignore_errors=True)
    part.mkdir(parents=True)
    # With preserve_insertion_order, DuckDB writes the rows in the member's order. A sort on
    # `record` gives the same file and doubles the memory for MapPLUTO's table of the whole city.
    # A date with no time in `published` reads as midnight UTC, whatever the process's zone.
    db = duckdb.connect(
        config={
            "memory_limit": "1GB",
            "threads": 4,
            "preserve_insertion_order": True,
            "TimeZone": "UTC",
        }
    )
    db.execute(f"CREATE TEMP TABLE rejects ({REJECTS})")
    names = members(path)
    for table, (source, takes) in TABLES.items():
        if entry["source"] != source:
            continue
        taken = [m for m in names if takes(m)]
        if not taken:
            raise ValueError(f"{entry['path']} holds no member for {table}")
        for i, member in enumerate(taken):
            copy = part / "member.csv"
            encoding = copy_member(path, member, copy)
            write_member(
                db, copy, encoding, entry, member, part / f"{table}-{i}.parquet"
            )
            copy.unlink()
    db.execute(
        f"COPY rejects TO '{part / 'rejects.parquet'}' (FORMAT parquet, COMPRESSION zstd)"
    )
    db.close()
    # DuckDB doesn't flush its files to disk, and a folder in place counts as unpacked, so the
    # step flushes the files and the folder before the rename, and the code's folder after it.
    for file in part.iterdir():
        fsync(file)
    fsync(part)
    os.replace(part, folder)
    fsync(folder.parent)


def fsync(path: Path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def unpack(archive: Path, cache: Path) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Unpack each listed file missing from the cache. Return each table's Parquet files and
    each listed file of the archive with its SHA-256."""
    code = cache / CODE
    tables = {table: [] for table in [*TABLES, "rejects"]}
    files = {}
    with lock_code(code):
        for entry in listed(archive):
            if entry["source"] not in {source for source, _ in TABLES.values()}:
                continue
            folder = code / hashlib.sha256(entry["line"].encode()).hexdigest()[:16]
            if not folder.is_dir():
                unpack_file(archive, entry, folder)
            files[entry["path"]] = entry["sha256"]
            for table in TABLES:
                tables[table] += [str(p) for p in folder.glob(f"{table}-*.parquet")]
            tables["rejects"].append(str(folder / "rejects.parquet"))
        # A table with no file in the archive reads an empty file with only the added columns.
        for table, paths in tables.items():
            if not paths:
                paths.append(str(empty(code, table)))
        os.utime(code / ".lock")
    sweep(cache)
    return {table: sorted(paths) for table, paths in tables.items()}, files


def lock_code(code: Path):
    """Create the code's folder and lock it. A sweep can move the folder away while a load waits
    for its lock, and then the load starts again with a new folder."""
    while True:
        code.mkdir(parents=True, exist_ok=True)
        lock = open(code / ".lock", "a")
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            if os.stat(code / ".lock").st_ino == os.fstat(lock.fileno()).st_ino:
                return lock
        except FileNotFoundError:
            pass
        lock.close()


def empty(code: Path, table: str) -> Path:
    path = code / f"empty-{table}.parquet"
    if not path.exists():
        db = duckdb.connect()
        db.execute(f"CREATE TABLE empty ({REJECTS if table == 'rejects' else ADDED})")
        db.execute(f"COPY empty TO '{path}.part' (FORMAT parquet)")
        db.close()
        os.replace(f"{path}.part", path)
    return path


def sweep(cache: Path):
    """Delete the folders of other versions of this code that no load has used for a week. With
    the lock held, the sweep renames a folder to `<code>.old` and then deletes it, so a load
    never finds a folder partway deleted. It also deletes an `.old` folder a stopped sweep
    left."""
    # Another load's sweep may delete an `.old` folder at the same time.
    for code in sorted(cache.iterdir()):
        if code.suffix == ".old":
            shutil.rmtree(code, ignore_errors=True)
            continue
        if code.name == CODE or not (code / ".lock").is_file():
            continue
        old = code.with_name(f"{code.name}.old")
        with open(code / ".lock") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                continue
            if time.time() - os.fstat(lock.fileno()).st_mtime <= WEEK:
                continue
            shutil.rmtree(old, ignore_errors=True)
            os.rename(code, old)
        shutil.rmtree(old, ignore_errors=True)
