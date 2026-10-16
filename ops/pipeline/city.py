"""Keep dated copies of the city's bulk records of lots and buildings.

    python3 ops/pipeline/city.py [--archive DIR] [--source NAME ...] [--verify]

The pipeline's identity and city-fact steps join each API building to these records as of each
ad's date. The script keeps each release of each source in ARCHIVE, /data1/apartments/archive/city
unless given, along with the release's date from its publisher. It works in these steps:

1. It takes an exclusive lock on ARCHIVE/.lock and exits when another run holds it. Then it
   cleans up after a stopped run: it deletes each `.part` file and cuts a last manifest line
   with no newline.
2. It asks each source for its files and skips a file when the manifest already lists it:
   - PAD, City Planning's Property Address Directory, comes as a zip for each quarter,
     `pad_YYQ.zip`. The script asks for each quarter from 23b, the oldest on the server, to the
     quarter after the current one. The server answers 404 for a quarter with no release. The
     script dates a release by the file's Last-Modified header.
   - MapPLUTO comes as a zip for each release. The script takes each release in
     `pluto_releases.csv`, with the date and the evidence for it from frontier's
     `PLUTO_RELEASES`. Then it asks for each later release name up to the current year and dates
     a new release by its Last-Modified header.
   - NYC Open Data serves building footprints, LPC's designated buildings and sites, and the DOB
     NOW and legacy DOB certificates of occupancy. For each of these the script reads the time
     of the last change to the dataset's rows, `rowsUpdatedAt`. When the manifest lists no copy
     from that time, it downloads all the rows as CSV. The CSV gives Socrata's `:id`,
     `:version`, `:created_at` and `:updated_at` for each row.
3. It downloads each file to a `.part` file beside its final path. It gzips each CSV with a
   fixed header time, so the same rows in the same order give the same bytes. It checks the
   download: a file with a Content-Length must have that many bytes, a zip must open, and a CSV
   must end with a newline. On a server error, a rate limit, a dropped connection or a short
   file, it waits and downloads the file again, up to five times. After a CSV download it reads
   `rowsUpdatedAt` again and drops the copy when the time moved, since the rows may then come
   from both sides of the change. Then it renames the file into place, flushes the folder to
   disk, appends a line for the file to ARCHIVE/manifest.ndjson and flushes the manifest. When
   a file fails, the script goes on to the next one and exits 1 at the end.

With `--verify` the script downloads nothing. It checks the size and SHA-256 of each listed file
and exits 1 when one differs. In both cases it prints a summary as JSON. A fetch's summary lists
the files fetched, absent, moved and failed, and gives the run's seconds and its peak memory.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import email.utils
import fcntl
import gzip
import hashlib
import http.client
import json
import os
import resource
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

DEFAULT_ARCHIVE = Path("/data1/apartments/archive/city")
DCP = "https://s-media.nyc.gov/agencies/dcp/assets/files/zip/data-tools/bytes"
OPEN_DATA = "https://data.cityofnewyork.us"
PLUTO_TABLE = Path(__file__).with_name("pluto_releases.csv")
# 23b is the oldest PAD release on City Planning's server, as quarter 1 of 2023 counting from 0.
PAD_FIRST = (2023, 1)
DATASETS = {
    "footprints": "5zhs-2jue",
    "landmarks": "ncre-qhxs",
    "dob_now_co": "pkdm-hqz6",
    "dob_co": "bs8b-p36w",
}
TRIES, WAIT = 5, 5.0


def stamp(moment: dt.datetime) -> str:
    return moment.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class Incomplete(Exception):
    """A download with fewer bytes than its Content-Length, or a file failing its check."""


def tries(action):
    """Call `action` up to TRIES times, with doubling waits between calls. Call it again after a
    server error, a rate limit, a dropped connection, a timeout or an incomplete download."""
    for attempt in range(TRIES):
        try:
            return action()
        except urllib.error.HTTPError as error:
            if (error.code < 500 and error.code != 429) or attempt == TRIES - 1:
                raise
        except (OSError, http.client.HTTPException, Incomplete):
            if attempt == TRIES - 1:
                raise
        time.sleep(WAIT * 2**attempt)


def request(url: str, timeout: float = 900):
    """Open the URL, or return None when the server answers 404."""
    headers = {"User-Agent": "Mozilla/5.0"}
    if url.startswith(OPEN_DATA) and (token := os.environ.get("NYC_OPEN_DATA_TOKEN")):
        headers["X-App-Token"] = token
    try:
        return urllib.request.urlopen(
            urllib.request.Request(url, headers=headers), timeout=timeout
        )
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def manifest(archive: Path) -> dict[str, dict]:
    """The manifest's lines by path. The script writes each line whole, with its newline."""
    path = archive / "manifest.ndjson"
    if not path.exists():
        return {}
    lines = {}
    for line in path.read_text().splitlines(keepends=True):
        if line.endswith("\n") and line.strip():
            entry = json.loads(line)
            lines[entry["path"]] = entry
    return lines


def pluto_table() -> list[dict]:
    with open(PLUTO_TABLE, newline="") as f:
        return list(csv.DictReader(f))


def rows_updated(dataset: str) -> dt.datetime:
    def read():
        response = request(f"{OPEN_DATA}/api/views/{dataset}.json", 60)
        if response is None:
            raise LookupError(f"Open Data has no dataset {dataset}")
        with response:
            return json.load(response)["rowsUpdatedAt"]

    return dt.datetime.fromtimestamp(tries(read), dt.UTC)


def offers(source: str, today: dt.date):
    """Yield a dict for each possible file of the source, with its manifest fields so far and
    its URL."""
    if source == "pad":
        start = PAD_FIRST[0] * 4 + PAD_FIRST[1]
        end = today.year * 4 + (today.month - 1) // 3 + 1
        for index in range(start, end + 1):
            year, quarter = divmod(index, 4)
            release = f"{year % 100:02d}{'abcd'[quarter]}"
            yield {
                "source": source,
                "release": release,
                "path": f"pad/pad_{release}.zip",
                "url": f"{DCP}/pad/pad_{release}.zip",
            }
    elif source == "pluto":
        table = pluto_table()
        for row in table:
            yield {
                "source": source,
                "release": row["release"],
                "path": f"pluto/{row['file']}",
                "url": f"{DCP}/pluto/{row['file']}",
                "published": row["published"] or None,
                "published_from": f"pluto_releases.csv: {row['evidence']}",
            }
        known = {row["release"] for row in table}
        for year in range(int(table[-1]["release"][:2]), today.year % 100 + 1):
            for version in range(1, 5):
                release = f"{year:02d}v{version}"
                if release not in known:
                    name = f"nyc_pluto_{release}_csv.zip"
                    yield {
                        "source": source,
                        "release": release,
                        "path": f"pluto/{name}",
                        "url": f"{DCP}/pluto/{name}",
                    }
    else:
        dataset = DATASETS[source]
        updated = rows_updated(dataset)
        yield {
            "source": source,
            "dataset": dataset,
            "release": stamp(updated),
            "path": f"{source}/{dataset}-{updated:%Y%m%dT%H%M%SZ}.csv.gz",
            "url": f"{OPEN_DATA}/api/v3/views/{dataset}/query.csv",
            "published": stamp(updated),
            "published_from": "rowsUpdatedAt",
        }


def download(url: str, part: Path, path: Path):
    """Download the URL into `part` and check the file. Return the response's headers, or None
    when the server answers 404. A file ending in `.gz` gets its bytes gzipped."""
    response = request(url)
    if response is None:
        return None
    gzipped = path.name.endswith(".gz")
    count, last = 0, b""
    with response, open(part, "wb") as raw:
        out = (
            gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=6, mtime=0)
            if gzipped
            else raw
        )
        while chunk := response.read(1 << 20):
            out.write(chunk)
            count, last = count + len(chunk), chunk
        if gzipped:
            out.close()
        raw.flush()
        os.fsync(raw.fileno())
    length = response.headers["Content-Length"]
    if length is not None and count != int(length):
        raise Incomplete(f"{url} gave {count} of {length} bytes")
    if gzipped and not last.endswith(b"\n"):
        raise Incomplete(f"{url} gave a CSV ending without a newline")
    if path.suffix == ".zip":
        try:
            zipfile.ZipFile(part).close()
        except zipfile.BadZipFile as error:
            raise Incomplete(f"{url} gave no zip: {error}") from error
    return response.headers


def fetch(archive: Path, entry: dict) -> str:
    """Download the entry's file and list it. Return "fetched", "absent" or "moved"."""
    path = archive / entry["path"]
    part = path.with_name(path.name + ".part")
    path.parent.mkdir(parents=True, exist_ok=True)

    def attempt():
        part.unlink(missing_ok=True)
        entry["retrieved"] = stamp(dt.datetime.now(dt.UTC))
        return download(entry["url"], part, path)

    try:
        headers = tries(attempt)
        if headers is None:
            return "absent"
        if "published" not in entry:
            modified = headers["Last-Modified"]
            if modified is None:
                entry.update(published=None, published_from="no Last-Modified header")
            else:
                published = email.utils.parsedate_to_datetime(modified)
                entry.update(published=stamp(published), published_from="Last-Modified")
        if (
            "dataset" in entry
            and stamp(rows_updated(entry["dataset"])) != entry["release"]
        ):
            return "moved"
        with open(part, "rb") as f:
            digest = hashlib.file_digest(f, "sha256").hexdigest()
        entry.update(bytes=part.stat().st_size, sha256=digest)
        os.replace(part, path)
    finally:
        part.unlink(missing_ok=True)
    # The renamed file goes to disk before its manifest line.
    folder = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(folder)
    finally:
        os.close(folder)
    with open(archive / "manifest.ndjson", "a") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return "fetched"


def run(archive: Path, sources, today: dt.date) -> tuple[dict, int]:
    started = time.monotonic()
    archive.mkdir(parents=True, exist_ok=True)
    lock = open(archive / ".lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return {"note": f"another run holds {archive / '.lock'}"}, 0
    for part in archive.rglob("*.part"):
        part.unlink()
    if (path := archive / "manifest.ndjson").exists():
        text = path.read_bytes()
        if not text.endswith(b"\n"):
            os.truncate(path, text.rfind(b"\n") + 1)
    listed = manifest(archive)
    summary = {"fetched": [], "absent": [], "moved": [], "failed": []}
    for source in sources:
        try:
            entries = list(offers(source, today))
        except Exception as error:
            summary["failed"].append({"source": source, "error": repr(error)})
            continue
        for entry in entries:
            if entry["path"] in listed:
                continue
            began = time.monotonic()
            try:
                outcome = fetch(archive, entry)
            except Exception as error:
                outcome = "failed"
                entry["error"] = repr(error)
            note = {"source": source, "release": entry["release"]}
            if outcome == "fetched":
                note.update(
                    bytes=entry["bytes"], seconds=round(time.monotonic() - began, 1)
                )
            elif outcome == "failed":
                note["error"] = entry["error"]
            summary[outcome].append(note)
    listed = manifest(archive)
    summary["listed"] = len(listed)
    summary["unlisted"] = sorted(
        str(p.relative_to(archive))
        for p in archive.glob("*/*")
        if p.is_file() and str(p.relative_to(archive)) not in listed
    )
    summary["seconds"] = round(time.monotonic() - started, 1)
    summary["peak_mib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
    return summary, 1 if summary["failed"] else 0


def verify(archive: Path) -> tuple[dict, int]:
    differ = []
    listed = manifest(archive)
    for path, entry in listed.items():
        file = archive / path
        if not file.is_file() or file.stat().st_size != entry["bytes"]:
            differ.append(path)
            continue
        with open(file, "rb") as f:
            if hashlib.file_digest(f, "sha256").hexdigest() != entry["sha256"]:
                differ.append(path)
    return {"listed": len(listed), "differ": differ}, 1 if differ else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument(
        "--source", action="append", choices=["pad", "pluto", *DATASETS]
    )
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    if args.verify:
        summary, status = verify(args.archive)
    else:
        sources = args.source or ["pad", "pluto", *DATASETS]
        summary, status = run(args.archive, sources, dt.date.today())
    print(json.dumps(summary))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
