"""Export the GraphQL collector's raw replies from the archive as Parquet files.

The collector keeps the body of every answer to an ad or building read, gzipped under
bodies/, but its graphql_search_ads and graphql_search_buildings tables hold only the
latest record of each ad and building. This exporter goes back to the stored bodies and
writes out every record of every read, so a pipeline can follow an ad across reads with
DuckDB or pyarrow and without the archive's SQLite schema. It opens the archive read-only
and writes four tables under export/ in the archive folder:

  - ads: a row for each listing ID in each read. When the reply holds a record for the
    ID, `outcome` is 'record' and `record` holds the record as JSON with sorted keys, the
    text the collector hashes for graphql_search_ads.record_sha256. When the reply's
    field answered without the ID, `outcome` is 'missing'. A field with no answer at all
    gets no rows, since the collector asked for its IDs again in a later request.
  - buildings: the same for building reads, with `building_id` as text.
  - requests: a row for each stored reply, with its Oxylabs job ID, the Oxylabs and
    StreetEasy status codes, and the bodies/ paths of the reply and of its query URL.
  - calls: a row for each POST the collector timed, failures included, keyed by the
    rowid of graphql_search_calls.

Each table gets a folder for each run, such as ads/run-0005/. For the ads, buildings and
requests tables, a file holds up to 250 replies in order of their graphql_search_responses
ID and goes by the first and last of them (responses-0006605-0006854.parquet). A calls
file holds up to 50,000 calls and goes by its first and last rowid (rows-....parquet).

The exporter writes each file under a .tmp name, syncs it and renames it into place, then
appends a line for it to export/manifest.ndjson with its rows and SHA-256. Finished files
stay as they are. The next export of a run starts above the highest ID in the file names
of the run's folder, so a reopened run gets new files for its new replies. On start the
exporter deletes leftover .tmp files and adds manifest lines for finished files missing
from the manifest, as after a crash between the rename and the append.

A database restored from a backup goes back to the backup's AUTOINCREMENT counter and
can give a new reply the ID of an exported one, and a VACUUM can renumber the rowids of
graphql_search_calls, a table with no INTEGER PRIMARY KEY. Resuming above the last
exported ID would then skip rows. So before resuming a run's table, the exporter compares
the archive's row at the last exported ID with the exported row, by run, kind and time,
and it stops with an error when they differ.
"""

import argparse
import fcntl
import gzip
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import urllib.parse
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from .graphql_search import ARCHIVE

RESPONSES_PER_FILE = 250
CALLS_PER_FILE = 50_000
# Rows go to the file in row groups of about this much text.
ROW_GROUP_BYTES = 32 << 20
FIELD = re.compile(r"(\w+): (rentalsByListingIds|buildingsByIds)\(ids: \[([\d ]*)\]\)")
FILE = re.compile(r"(?:responses|rows)-(\d+)-(\d+)\.parquet")

TIME = pa.timestamp("us", tz="UTC")
READ = [
    ("fetched", TIME),
    ("response_id", pa.int64()),
    ("run", pa.int32()),
    ("region", pa.string()),
    ("generation", pa.int32()),
    ("outcome", pa.string()),
    ("record_sha256", pa.string()),
    ("record", pa.string()),
]
SCHEMAS = {
    "ads": pa.schema([("listing_id", pa.int64()), *READ]),
    "buildings": pa.schema([("building_id", pa.string()), *READ]),
    "requests": pa.schema(
        [
            ("response_id", pa.int64()),
            ("run", pa.int32()),
            ("region", pa.string()),
            ("generation", pa.int32()),
            ("kind", pa.string()),
            ("fetched", TIME),
            ("response_sha256", pa.string()),
            ("response_path", pa.string()),
            ("query_sha256", pa.string()),
            ("query_path", pa.string()),
            ("entries", pa.int64()),
            ("bytes", pa.int64()),
            ("url_length", pa.int64()),
            ("oxylabs_job_id", pa.string()),
            ("api_status", pa.int32()),
            ("target_status", pa.int32()),
        ]
    ),
    "calls": pa.schema(
        [
            ("rowid", pa.int64()),
            ("run", pa.int32()),
            ("kind", pa.string()),
            ("started", TIME),
            ("seconds", pa.float64()),
            ("api_status", pa.int32()),
            ("target_status", pa.int32()),
            ("bytes", pa.int64()),
            ("url_length", pa.int64()),
            ("attempt", pa.int32()),
            ("error", pa.string()),
        ]
    ),
}
TABLES = tuple(SCHEMAS)


class ExportError(RuntimeError):
    """The archive disagrees with the files already exported, or with itself."""


def _sha256(data):
    return hashlib.sha256(data.encode() if isinstance(data, str) else data).hexdigest()


def _micros(seconds):
    return None if seconds is None else round(seconds * 1_000_000)


def _iso_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _fsync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def requested_ids(query_url):
    """The IDs in each aliased by-ID field of a query URL, by alias."""
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(query_url).query)["query"][0]
    return {alias: ids.split() for alias, _, ids in FIELD.findall(query)}


def read_rows(fields, body):
    """Rows of (ID, record JSON or None) for each answered field of a by-ID read.

    The collector's _split reads a reply the same way: a field with a list answers its
    IDs, and an ID with no record in the list is missing. The collector retries the IDs
    of a field without a list, so they get no rows here.
    """
    try:
        doc = json.loads(body)
    except ValueError:
        doc = None
    data = doc.get("data") if isinstance(doc, dict) else None
    data = data if isinstance(data, dict) else {}
    rows = []
    for alias, ids in fields.items():
        value = data.get(alias)
        if not isinstance(value, list):
            continue
        got = {
            str(r["id"]): r
            for r in value
            if isinstance(r, dict) and r.get("id") is not None
        }
        for i in ids:
            record = got.get(i)
            rows.append(
                (i, None if record is None else json.dumps(record, sort_keys=True))
            )
    return rows


class Writer:
    """A Parquet file of a table, written under .tmp and renamed into place on finish."""

    def __init__(self, export, table, folder, name):
        self.export, self.table = export, table
        self.path = folder / name
        self.tmp = folder / (name + ".tmp")
        self.writer = pq.ParquetWriter(self.tmp, SCHEMAS[table], compression="zstd")
        self.columns = {f.name: [] for f in SCHEMAS[table]}
        self.buffered = self.rows = 0

    def add(self, row):
        for name, values in self.columns.items():
            values.append(row[name])
        self.buffered += len(row.get("record") or "")
        self.rows += 1
        if self.buffered >= ROW_GROUP_BYTES:
            self.flush()

    def flush(self):
        if self.columns["run"]:
            self.writer.write_table(
                pa.Table.from_pydict(self.columns, schema=SCHEMAS[self.table])
            )
            self.columns = {name: [] for name in self.columns}
            self.buffered = 0

    def finish(self, run, first, last):
        self.flush()
        self.writer.close()
        with open(self.tmp, "rb") as f:
            os.fsync(f.fileno())
        os.rename(self.tmp, self.path)
        _fsync_dir(self.path.parent)
        self.export.note(self.table, run, first, last, self.path, self.rows)


class Export:
    """An export of the archive's runs into `out`, holding out/.lock while it lasts."""

    def __init__(self, data, out=None, *, per_file=RESPONSES_PER_FILE):
        self.data = Path(data)
        self.out = Path(out) if out else self.data / "export"
        self.per_file = per_file
        self.db = sqlite3.connect(
            f"file:{self.data / 'archive.sqlite3'}?mode=ro", uri=True, timeout=30
        )
        self.db.row_factory = sqlite3.Row
        self.manifest = self.out / "manifest.ndjson"

    def note(self, table, run, first, last, path, rows):
        line = {
            "table": table,
            "run": run,
            "first": first,
            "last": last,
            "path": str(path.relative_to(self.out)),
            "rows": rows,
            "sha256": _file_sha256(path),
            "written": _iso_now(),
        }
        with open(self.manifest, "a") as f:
            f.write(json.dumps(line, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
        self.report[table]["files"] += 1
        self.report[table]["rows"] += rows

    def folder(self, table, run):
        return self.out / table / f"run-{run:04d}"

    def finished(self, table, run):
        """The (first, last) IDs of the run's finished files of a table, in order."""
        folder = self.folder(table, run)
        if not folder.is_dir():
            return []
        spans = [FILE.fullmatch(p.name) for p in folder.iterdir()]
        return sorted((int(m[1]), int(m[2])) for m in spans if m)

    def repair(self):
        """Delete leftover .tmp files and add manifest lines for unlisted finished files."""
        lines = []
        if self.manifest.exists():
            lines = self.manifest.read_text().splitlines(keepends=True)
        if lines and not lines[-1].endswith("\n"):
            # A crash cut the last line short. Without it, the scan below lists its file again.
            lines.pop()
            tmp = self.manifest.with_name(self.manifest.name + ".tmp")
            with open(tmp, "w") as f:
                f.write("".join(lines))
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.manifest)
        listed = {json.loads(line)["path"] for line in lines if line.strip()}
        for table in TABLES:
            for path in sorted((self.out / table).glob("run-*/*")):
                if path.name.endswith(".tmp"):
                    path.unlink()
                    continue
                m = FILE.fullmatch(path.name)
                if not m or str(path.relative_to(self.out)) in listed:
                    continue
                run = int(path.parent.name.removeprefix("run-"))
                rows = pq.ParquetFile(path).metadata.num_rows
                self.note(table, run, int(m[1]), int(m[2]), path, rows)

    def run(self, runs=None):
        self.out.mkdir(parents=True, exist_ok=True)
        with open(self.out / ".lock", "a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ExportError(
                    f"another export holds {self.out / '.lock'}"
                ) from None
            self.report = {table: {"files": 0, "rows": 0} for table in TABLES}
            self.repair()
            known = {
                r["id"]: r
                for r in self.db.execute(
                    "SELECT id, region, generation FROM graphql_search_runs ORDER BY id"
                )
            }
            for run in runs or list(known):
                if run not in known:
                    raise ExportError(f"the archive has no run {run}")
                self.export_run(known[run])
        return self.report

    def export_run(self, run):
        for kind in ("ads", "buildings"):
            self.export_reads(run, kind)
        self.export_requests(run)
        self.export_calls(run)

    def _after(self, table, run_id):
        """The highest ID in the names of the run's files, checked against the archive."""
        spans = self.finished(table, run_id)
        if not spans:
            return 0
        first, last = spans[-1]
        if table == "calls":
            key, at, name = "rowid", "started", f"rows-{first:09d}-{last:09d}"
            row = self.db.execute(
                """SELECT run, 'calls' AS kind, started AS at FROM graphql_search_calls
                WHERE rowid=?""",
                (last,),
            ).fetchone()
        else:
            key, at, name = (
                "response_id",
                "fetched",
                f"responses-{first:07d}-{last:07d}",
            )
            row = self.db.execute(
                "SELECT run, kind, fetched AS at FROM graphql_search_responses WHERE id=?",
                (last,),
            ).fetchone()
        path = self.folder(table, run_id) / f"{name}.parquet"
        exported = pq.read_table(path, columns=[key, at])
        times = exported.filter(pc.equal(exported[key], last))[at].cast(pa.int64())
        kinds = {"calls": ("calls",), "requests": ("ads", "buildings")}.get(
            table, (table,)
        )
        if (
            row is None
            or row["run"] != run_id
            or row["kind"] not in kinds
            or any(t != _micros(row["at"]) for t in times.to_pylist())
        ):
            raise ExportError(
                f"the archive's row {last} of run {run_id} differs from the one in "
                f"{table}/{path.parent.name}/{path.name}; the archive's IDs moved"
            )
        return last

    def _responses(self, run, kinds, after):
        marks = ",".join("?" * len(kinds))
        ids = [
            r[0]
            for r in self.db.execute(
                f"""SELECT id FROM graphql_search_responses
                WHERE run=? AND kind IN ({marks}) AND id>? ORDER BY id""",
                (run["id"], *kinds, after),
            )
        ]
        return [ids[i : i + self.per_file] for i in range(0, len(ids), self.per_file)]

    def _response(self, response_id):
        return self.db.execute(
            """SELECT r.*, a.path AS response_path, q.path AS query_path,
            q.size AS url_length FROM graphql_search_responses r
            LEFT JOIN bodies a ON a.hash=r.sha256
            LEFT JOIN bodies q ON q.hash=r.query_sha256 WHERE r.id=?""",
            (response_id,),
        ).fetchone()

    def _body(self, path, response_id):
        if path is None:
            raise ExportError(f"response {response_id} has a body missing from bodies")
        return gzip.decompress((self.data / path).read_bytes())

    def export_reads(self, run, kind):
        folder = self.folder(kind, run["id"])
        folder.mkdir(parents=True, exist_ok=True)
        key = "listing_id" if kind == "ads" else "building_id"
        for chunk in self._responses(run, (kind,), self._after(kind, run["id"])):
            writer = Writer(
                self, kind, folder, f"responses-{chunk[0]:07d}-{chunk[-1]:07d}.parquet"
            )
            for response_id in chunk:
                r = self._response(response_id)
                fields = requested_ids(
                    self._body(r["query_path"], response_id).decode()
                )
                rows = read_rows(fields, self._body(r["response_path"], response_id))
                records = sum(record is not None for _, record in rows)
                if records != r["entries"]:
                    raise ExportError(
                        f"response {response_id} gives {records} records, and the "
                        f"archive counts {r['entries']}"
                    )
                for item, record in rows:
                    writer.add(
                        {
                            key: int(item) if kind == "ads" else item,
                            "fetched": _micros(r["fetched"]),
                            "response_id": response_id,
                            "run": run["id"],
                            "region": run["region"],
                            "generation": run["generation"],
                            "outcome": "missing" if record is None else "record",
                            "record_sha256": None
                            if record is None
                            else _sha256(record),
                            "record": record,
                        }
                    )
            writer.finish(run["id"], chunk[0], chunk[-1])

    def export_requests(self, run):
        folder = self.folder("requests", run["id"])
        folder.mkdir(parents=True, exist_ok=True)
        after = self._after("requests", run["id"])
        for chunk in self._responses(run, ("ads", "buildings"), after):
            writer = Writer(
                self,
                "requests",
                folder,
                f"responses-{chunk[0]:07d}-{chunk[-1]:07d}.parquet",
            )
            for response_id in chunk:
                r = self._response(response_id)
                capture = json.loads(r["capture"] or "{}")
                result = (capture.get("results") or [{}])[0]
                job = (capture.get("api_headers") or {}).get("x-oxylabs-job-id")
                writer.add(
                    {
                        "response_id": response_id,
                        "run": run["id"],
                        "region": run["region"],
                        "generation": run["generation"],
                        "kind": r["kind"],
                        "fetched": _micros(r["fetched"]),
                        "response_sha256": r["sha256"],
                        "response_path": r["response_path"],
                        "query_sha256": r["query_sha256"],
                        "query_path": r["query_path"],
                        "entries": r["entries"],
                        "bytes": r["bytes"],
                        "url_length": r["url_length"],
                        "oxylabs_job_id": None if job is None else str(job),
                        "api_status": capture.get("api_status"),
                        "target_status": result.get(
                            "status_code", result.get("status")
                        ),
                    }
                )
            writer.finish(run["id"], chunk[0], chunk[-1])

    def export_calls(self, run):
        folder = self.folder("calls", run["id"])
        folder.mkdir(parents=True, exist_ok=True)
        after = self._after("calls", run["id"])
        rows = self.db.execute(
            """SELECT rowid AS rowid, * FROM graphql_search_calls
            WHERE run=? AND rowid>? ORDER BY rowid""",
            (run["id"], after),
        ).fetchall()
        for start in range(0, len(rows), CALLS_PER_FILE):
            chunk = rows[start : start + CALLS_PER_FILE]
            first, last = chunk[0]["rowid"], chunk[-1]["rowid"]
            writer = Writer(
                self, "calls", folder, f"rows-{first:09d}-{last:09d}.parquet"
            )
            for c in chunk:
                writer.add(
                    {
                        **{k: c[k] for k in c.keys()},
                        "started": _micros(c["started"]),
                    }
                )
            writer.finish(run["id"], first, last)

    def close(self):
        self.db.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, help=f"archive folder (default {ARCHIVE})")
    parser.add_argument("--out", type=Path, help="export folder (default DATA/export)")
    parser.add_argument(
        "--run", type=int, action="append", help="a run to export (default every run)"
    )
    args = parser.parse_args(argv)
    export = Export(args.data or ARCHIVE, args.out)
    try:
        report = export.run(args.run)
    finally:
        export.close()
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
