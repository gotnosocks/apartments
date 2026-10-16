"""Write the city fixture from the city archive on thelio.

The fixture holds a few files of the city archive, cut down to the blocks of the five fixture
buildings, along with a manifest in the archive's form. The script works in these steps:

1. It picks the files of `RELEASES` from the archive's manifest, and the latest copy of each
   NYC Open Data set.
2. It splits each member of a zip, or the gzipped CSV, into records. A record ends at a line
   break outside quotes.
3. It keeps the header, each record on one of `BLOCKS`, each record with more or fewer values
   than the header, and the last two records of the member. It finds a record's block from
   the record's BBL, or from its borough and block columns. The kept records keep their bytes,
   and a member keeps its line breaks and a final DOS end-of-file byte.
4. It writes each zip with its tables in the archive's order, leaving out the documents and
   folders, and each CSV gzipped with no name and a time of 0. It copies each file's manifest
   line with the new size and SHA-256.

    pipeline/.venv/bin/python pipeline/tests/make_city_fixture.py

The releases cover the forms the archive's files take: PAD's second copies of its tables in a
`win11` folder in 24c, old MapPLUTO tables ending in a DOS end-of-file byte in 09v1, rows with
only commas at the end of a table in 13v1, tables in a folder in 16v2, and a single table for
the city in 26v2.
"""

import argparse
import csv
import gzip
import hashlib
import io
import json
import re
import zipfile
from collections import deque
from collections.abc import Iterator
from itertools import islice
from pathlib import Path

ARCHIVE = Path("/data1/apartments/archive/city")
HERE = Path(__file__).resolve().parent
# The blocks of the five buildings of the fixture's export, as borough code and block.
BLOCKS = {(1, 1220), (1, 1238), (3, 1048), (3, 1266), (3, 2045)}
RELEASES = {"pad": ("24c", "26c"), "pluto": ("09v1", "13v1", "16v2", "26v2")}
OPEN_DATA = ("footprints", "landmarks", "dob_now_co", "dob_co")
BOROUGHS = {"MN": 1, "BX": 2, "BK": 3, "QN": 4, "SI": 5}


def records(stream) -> Iterator[bytes]:
    """Read a CSV's records from a binary stream, each with its line break. A record ends at a
    line break outside quotes."""
    record = b""
    for line in stream:
        record += line
        if record.count(b'"') % 2 == 0:
            yield record
            record = b""
    if record:
        yield record


def fields(record: bytes) -> list[str]:
    return next(csv.reader(io.StringIO(record.decode("latin-1"))), [])


def block(header: list[str], row: list[str]):
    """The row's borough code and block, or None."""
    values = dict(zip(header, (v.strip() for v in row)))
    for key in ("bbl", "base_bbl", "mappluto_bbl"):
        digits = values.get(key, "").split(".")[0]
        if re.fullmatch(r"[1-5]\d{9}", digits):
            return int(digits[0]), int(digits[1:6])
    borough = next(
        (
            values[k]
            for k in ("boro", "borough", "borocode", "boroughid")
            if values.get(k)
        ),
        "",
    )
    borough = BOROUGHS.get(borough.upper(), borough)
    try:
        return int(borough), int(values.get("block", ""))
    except ValueError:
        return None


def cut(stream) -> bytes:
    """Keep the header, the records on BLOCKS, the records with a wrong count of values and the
    last two records."""
    rows = records(stream)
    first = next(rows)
    header = [n.strip().lower() for n in fields(first)]
    kept, last = [first], deque(maxlen=2)
    for record in rows:
        if len(last) == 2:
            row = fields(last[0])
            if len(row) != len(header) or block(header, row) in BLOCKS:
                kept.append(last[0])
        last.append(record)
    return b"".join(kept + list(last))


def write_zip(source: Path, out: Path):
    with zipfile.ZipFile(source) as z, zipfile.ZipFile(out, "w") as w:
        for info in z.infolist():
            name = info.filename
            if not name.lower().endswith((".txt", ".csv")):
                continue
            with z.open(info) as stream:
                # PAD's street name table is fixed-width and holds no blocks. The city tables
                # leave it out, and the fixture keeps its first two lines.
                if re.fullmatch(r"snd.*\.txt", name, re.I):
                    data = b"".join(islice(stream, 2))
                else:
                    data = cut(stream)
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            w.writestr(entry, data)


def write_gzip(source: Path, out: Path):
    with gzip.open(source) as stream:
        data = cut(stream)
    with open(out, "wb") as f, gzip.GzipFile("", "wb", fileobj=f, mtime=0) as g:
        g.write(data)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--archive", type=Path, default=ARCHIVE)
    parser.add_argument("--out", type=Path, default=HERE / "fixture" / "city")
    args = parser.parse_args(argv)
    entries = [json.loads(line) for line in open(args.archive / "manifest.ndjson")]
    picked = [e for e in entries if e["release"] in RELEASES.get(e["source"], ())]
    for source in OPEN_DATA:
        picked.append(
            max(
                (e for e in entries if e["source"] == source),
                key=lambda e: e["release"],
            )
        )
    lines = []
    for entry in sorted(picked, key=lambda e: (e["source"], e["release"])):
        out = args.out / entry["path"]
        out.parent.mkdir(parents=True, exist_ok=True)
        source = args.archive / entry["path"]
        (write_zip if out.suffix == ".zip" else write_gzip)(source, out)
        data = out.read_bytes()
        lines.append(
            entry | {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        )
    with open(args.out / "manifest.ndjson", "w") as f:
        f.writelines(json.dumps(line, sort_keys=True) + "\n" for line in lines)


if __name__ == "__main__":
    main()
