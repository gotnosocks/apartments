import csv
import fcntl
import gzip
import hashlib
import io
import json
import os
import time
import zipfile
from pathlib import Path

import duckdb
import pytest
from steps import city

FIXTURE = Path(__file__).parent / "fixture" / "city"


def add(archive: Path, source: str, release: str, path: str, members: dict[str, bytes]):
    """Write a zip of `members`, or a gzipped CSV for the member "", and list it."""
    out = archive / path
    out.parent.mkdir(parents=True, exist_ok=True)
    if "" in members:
        out.write_bytes(gzip.compress(members[""], mtime=0))
    else:
        with zipfile.ZipFile(out, "w") as z:
            for name, data in members.items():
                z.writestr(name, data)
    line = {
        "source": source,
        "release": release,
        "path": path,
        "published": "2026-01-02T03:04:05Z",
        "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
    }
    with open(archive / "manifest.ndjson", "a") as f:
        f.write(json.dumps(line) + "\n")


def read(paths: list[str]) -> str:
    return f"read_parquet({paths}, union_by_name = true)"


@pytest.fixture
def archive(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "manifest.ndjson").touch()
    return archive


def test_fixture_rows_match_csv(tmp_path):
    """Every row of every member the tables take, read by Python's csv module, is either a
    Parquet row with the same values or a refused row."""
    tables, files = city.unpack(FIXTURE, tmp_path / "cache")
    listed = city.listed(FIXTURE)
    assert files == {e["path"]: e["sha256"] for e in listed}
    db = duckdb.connect()
    for entry in listed:
        path = FIXTURE / entry["path"]
        for table, (source, takes) in city.TABLES.items():
            if source != entry["source"]:
                continue
            for member in filter(takes, city.members(path)):
                if member:
                    data = zipfile.ZipFile(path).read(member)
                else:
                    data = gzip.decompress(path.read_bytes())
                data = data.removesuffix(city.SUB)
                try:
                    text = data.decode("utf-8")
                except UnicodeDecodeError:
                    text = data.decode("latin-1")
                header, *records = csv.reader(io.StringIO(text, newline=""))
                expected = [r for r in records if len(r) == len(header)]
                refused = [r for r in records if r and len(r) != len(header)]
                names = [n.strip().lower() for n in header]
                got = db.execute(
                    f"""SELECT {", ".join(f'"{n}"' for n in names)}, record
                    FROM read_parquet({tables[table]}, union_by_name = true)
                    WHERE file = ? AND member = ? ORDER BY record""",
                    [entry["path"], member],
                ).fetchall()
                assert [r[-1] for r in got] == list(range(1, len(got) + 1))
                assert [[v or "" for v in r[:-1]] for r in got] == expected, (
                    path,
                    member,
                )
                lines = db.execute(
                    f"""SELECT DISTINCT line FROM read_parquet({tables["rejects"]})
                    WHERE file = ? AND member = ?""",
                    [entry["path"], member],
                ).fetchall()
                assert len(lines) == len(refused), (path, member)


def test_fixture_forms(tmp_path):
    tables, _ = city.unpack(FIXTURE, tmp_path / "cache")
    # PAD's zips from 24c hold each table twice, and the tables read the copy at the root.
    pad = duckdb.sql(
        f"SELECT DISTINCT release, member FROM {read(tables['pad_addresses'])}"
    )
    assert sorted(pad.fetchall()) == [("24c", "bobaadr.txt"), ("26c", "bobaadr.txt")]
    # Each MapPLUTO release keeps its lots on the five blocks.
    pluto = duckdb.sql(
        f"SELECT DISTINCT release FROM {read(tables['pluto'])} WHERE lot IS NOT NULL"
    )
    assert sorted(pluto.fetchall()) == [("09v1",), ("13v1",), ("16v2",), ("26v2",)]
    # The row of 13v1's Queens table with 80 values of 82 goes to the rejects.
    refused = duckdb.sql(
        f"SELECT DISTINCT release, member, error_type FROM {read(tables['rejects'])}"
    )
    assert ("13v1", "qn13v1.csv", "MISSING COLUMNS") in refused.fetchall()


def test_columns(archive, tmp_path):
    add(
        archive,
        "pluto",
        "09v1",
        "pluto/a.zip",
        {"MN.txt": b' Borough ,"Block"\nMN,1\nMN,2\x1a'},
    )
    tables, _ = city.unpack(archive, tmp_path / "cache")
    got = duckdb.sql(
        "SELECT * REPLACE (published = TIMESTAMPTZ '2026-01-02T03:04:05Z' AS published) "
        f"FROM {read(tables['pluto'])} ORDER BY record"
    )
    assert got.columns == [
        "borough",
        "block",
        "release",
        "published",
        "file",
        "member",
        "record",
        "encoding",
    ]
    assert got.fetchall() == [
        ("MN", "1", "09v1", True, "pluto/a.zip", "MN.txt", 1, "utf-8"),
        ("MN", "2", "09v1", True, "pluto/a.zip", "MN.txt", 2, "utf-8"),
    ]


def values(paths: list[str], columns: str) -> list[tuple]:
    return duckdb.sql(
        f"SELECT {columns} FROM {read(paths)} ORDER BY file, record"
    ).fetchall()


def test_latin_1(archive, tmp_path):
    add(
        archive,
        "landmarks",
        "2026-01-02",
        "landmarks/a.csv.gz",
        {"": b"name\nCaf\xe9\n"},
    )
    tables, _ = city.unpack(archive, tmp_path / "cache")
    assert values(tables["landmarks"], "name, encoding") == [("Café", "latin-1")]


def test_refused_rows(archive, tmp_path):
    add(
        archive,
        "dob_co",
        "2026-01-02",
        "dob_co/a.csv.gz",
        {"": b"a,b,c\n1,2,3\n4,5\n6,7,8\n"},
    )
    tables, _ = city.unpack(archive, tmp_path / "cache")
    assert values(tables["dob_co"], "a, record") == [("1", 1), ("6", 2)]
    refused = duckdb.sql(
        f"SELECT release, file, member, line, error_type, csv_line FROM {read(tables['rejects'])}"
    )
    assert refused.fetchall() == [
        ("2026-01-02", "dob_co/a.csv.gz", "", 3, "MISSING COLUMNS", "4,5")
    ]


def test_second_unpack_writes_nothing(archive, tmp_path, monkeypatch):
    add(archive, "landmarks", "2026-01-02", "landmarks/a.csv.gz", {"": b"a\n1\n"})
    first = city.unpack(archive, tmp_path / "cache")
    unpacked = []
    monkeypatch.setattr(
        city, "unpack_file", lambda *args: unpacked.append(args[1]["path"])
    )
    assert city.unpack(archive, tmp_path / "cache") == first
    assert unpacked == []
    # A new line unpacks only its file.
    add(archive, "landmarks", "2026-01-09", "landmarks/b.csv.gz", {"": b"a\n2\n"})
    city.unpack(archive, tmp_path / "cache")
    assert unpacked == ["landmarks/b.csv.gz"]


def test_new_code_gets_new_folders(archive, tmp_path, monkeypatch):
    add(archive, "landmarks", "2026-01-02", "landmarks/a.csv.gz", {"": b"a\n1\n"})
    first, _ = city.unpack(archive, tmp_path / "cache")
    monkeypatch.setattr(city, "CODE", "0" * 16)
    second, _ = city.unpack(archive, tmp_path / "cache")
    assert first["landmarks"] != second["landmarks"]
    assert values(first["landmarks"], "a") == values(second["landmarks"], "a")


def test_stopped_unpack(archive, tmp_path, monkeypatch):
    add(archive, "landmarks", "2026-01-02", "landmarks/a.csv.gz", {"": b"a\n1\n"})
    real = city.write_member

    def stop(*args):
        real(*args)
        raise KeyboardInterrupt

    monkeypatch.setattr(city, "write_member", stop)
    with pytest.raises(KeyboardInterrupt):
        city.unpack(archive, tmp_path / "cache")
    parts = list((tmp_path / "cache").glob("*/*.part"))
    assert len(parts) == 1
    monkeypatch.setattr(city, "write_member", real)
    tables, _ = city.unpack(archive, tmp_path / "cache")
    assert not parts[0].exists()
    assert values(tables["landmarks"], "a") == [("1",)]


def test_cut_line(archive, tmp_path):
    """A manifest line with no newline at its end belongs to a stopped fetch, and the unpack
    leaves its file alone."""
    add(archive, "landmarks", "2026-01-02", "landmarks/a.csv.gz", {"": b"a\n1\n"})
    add(archive, "landmarks", "2026-01-09", "landmarks/b.csv.gz", {"": b"a\n2\n"})
    manifest = archive / "manifest.ndjson"
    manifest.write_bytes(manifest.read_bytes().removesuffix(b"\n"))
    tables, files = city.unpack(archive, tmp_path / "cache")
    assert list(files) == ["landmarks/a.csv.gz"]
    assert values(tables["landmarks"], "a") == [("1",)]


def test_other_sources_left_out(archive, tmp_path):
    add(archive, "landmarks", "2026-01-02", "landmarks/a.csv.gz", {"": b"a\n1\n"})
    add(archive, "parks", "2026-01-02", "parks/a.csv.gz", {"": b"a\n1\n"})
    _, files = city.unpack(archive, tmp_path / "cache")
    assert list(files) == ["landmarks/a.csv.gz"]
    (code,) = (tmp_path / "cache").iterdir()
    assert len([p for p in code.iterdir() if p.is_dir()]) == 1


def test_sweep(archive, tmp_path):
    """An unpack deletes the folders of other code versions unused for a week, unless a load
    holds their lock."""
    add(archive, "landmarks", "2026-01-02", "landmarks/a.csv.gz", {"": b"a\n1\n"})
    cache = tmp_path / "cache"
    week_ago = time.time() - city.WEEK - 60
    for name in ("old", "recent", "held"):
        (cache / name / "folder").mkdir(parents=True)
        (cache / name / ".lock").touch()
        if name != "recent":
            os.utime(cache / name / ".lock", (week_ago, week_ago))
    with open(cache / "held" / ".lock") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        city.unpack(archive, cache)
    assert sorted(p.name for p in cache.iterdir()) == sorted(
        [city.CODE, "held", "recent"]
    )
