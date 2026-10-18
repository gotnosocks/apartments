import fcntl
import hashlib
import json
import os
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from steps import records

FIXTURE = Path(__file__).resolve().parent / "fixture"
FILES = sorted(str(path) for path in (FIXTURE / "export" / "ads").glob("*/*.parquet"))


def connect():
    return duckdb.connect(config={"TimeZone": "UTC", "memory_limit": "1GB"})


def write(tmp_path, files):
    return records.write(
        connect().cursor(), files, tmp_path / "cache", tmp_path / "out", workers=1
    )


def answers_file(path, answers):
    """Write `answers`, (listing_id, fetched, response_id, outcome, record), as an export file
    of ads."""
    frame = pd.DataFrame(
        answers, columns=["listing_id", "fetched", "response_id", "outcome", "record"]
    )
    frame["record"] = [
        None if record is None else json.dumps(record, sort_keys=True)
        for record in frame.record
    ]
    frame["record_sha256"] = [
        None if text is None else hashlib.sha256(text.encode()).hexdigest()
        for text in frame.record
    ]
    db = connect()
    db.register("answers", frame)
    db.execute(
        f"""COPY (SELECT listing_id::BIGINT AS listing_id, fetched::TIMESTAMPTZ AS fetched,
        response_id::BIGINT AS response_id, 5 AS run, 'r' AS region, 1 AS generation, outcome,
        record_sha256, record FROM answers) TO '{path}' (FORMAT parquet)"""
    )
    return str(path)


def test_records_of_the_fixture(tmp_path):
    """Each record of the fixture export comes out serialized by `serialize`, with the time of
    its answer in seconds. `tests/test_pipeline_records.py` in the repository's own tests
    compares `serialize` with the granular export's parser. A second run reads nothing into the
    cache, writes the same bytes and deletes another version's cache folder."""
    line = write(tmp_path, FILES)
    path = tmp_path / "out" / line["path"]
    assert path.name == f"records-{line['sha256'][:16]}.parquet"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == line["sha256"]
    frame = pd.read_parquet(path)
    answers = (
        connect()
        .execute(
            f"""SELECT listing_id, epoch_us(fetched) AS fetched_us, response_id,
            record_sha256, record FROM read_parquet({records.sql_list(FILES)})
            WHERE outcome = 'record' ORDER BY listing_id"""
        )
        .df()
    )
    # Each listing of the fixture has one answer with a record.
    assert answers.listing_id.is_unique
    assert len(frame) == line["rows"] == line["read"] == len(answers) == 229
    assert frame.listing_id.is_monotonic_increasing
    assert set(frame.listing_type) == {"rental"}
    for row, answer in zip(
        frame.itertuples(index=False), answers.itertuples(index=False)
    ):
        assert (row.listing_id, row.response_id, row.record_sha256) == (
            answer.listing_id,
            answer.response_id,
            answer.record_sha256,
        )
        assert row.raw_listing_json == records.serialize(answer.record)
        assert row.collected_at == row.last_collected_at == answer.fetched_us / 1e6
    (current,) = (p for p in (tmp_path / "cache").iterdir() if p.is_dir())
    older = tmp_path / "cache" / ("0" * 64)
    older.mkdir()
    (older / "old.parquet").write_bytes(b"")
    again = write(tmp_path, FILES)
    assert again == line | {"read": 0}
    assert [p.name for p in (tmp_path / "out").iterdir()] == [path.name]
    assert sorted(p.name for p in (tmp_path / "cache").iterdir()) == [
        ".lock",
        current.name,
    ]


def test_a_noted_file_comes_back(tmp_path):
    """With the export's version, a second call returns the file it noted without reading the
    export: here its only export file is missing. A cut-off last line of the notes changes
    nothing. Another version, or a noted file with another modification time, makes the step
    write the file again."""
    cache, out = tmp_path / "cache", tmp_path / "out"
    first = records.write(
        connect().cursor(), FILES, cache, out, workers=1, version="v1"
    )
    assert first["reused"] is False
    path = out / first["path"]
    stamp = path.stat().st_mtime_ns
    missing = [str(tmp_path / "missing.parquet")]
    again = records.write(
        connect().cursor(), missing, cache, out, workers=1, version="v1"
    )
    assert again == first | {"read": 0, "reused": True}
    assert path.stat().st_mtime_ns == stamp
    # A line cut off by a stopped step counts for nothing.
    (notes,) = cache.glob(f"*/{records.NOTES}")
    with open(notes, "a") as f:
        f.write('{"version": "v1"')
    again = records.write(
        connect().cursor(), missing, cache, out, workers=1, version="v1"
    )
    assert again == first | {"read": 0, "reused": True}
    other = records.write(
        connect().cursor(), FILES, cache, out, workers=1, version="v2"
    )
    assert other == first | {"read": 0}
    os.utime(path, ns=(stamp, stamp + 1))
    changed = records.write(
        connect().cursor(), FILES, cache, out, workers=1, version="v1"
    )
    assert changed == first | {"read": 0}
    with pytest.raises(duckdb.IOException):
        records.write(connect().cursor(), missing, cache, out, workers=1, version="v3")


def test_integral_floats_become_integers(tmp_path):
    """Integral floats in prices and sizes come out as integers and other floats stay as they
    are, `__typename` keys go at any depth, and text keeps its non-ASCII characters."""
    record = {
        "__typename": "RentalListing",
        "id": "4000001",
        "description": "Café – sunny",
        "pricing": {
            "__typename": "Pricing",
            "price": 3050.0,
            "priceChanges": [
                {
                    "__typename": "PriceChange",
                    "changedAt": "2026-10-01",
                    "price": 3100.0,
                },
                {
                    "__typename": "PriceChange",
                    "changedAt": "2026-10-08",
                    "price": 3050.5,
                },
            ],
        },
        "propertyDetails": {"livingAreaSize": 750.0, "bathroomCount": 1.5},
    }
    files = [
        answers_file(
            tmp_path / "a.parquet",
            [(4000001, "2026-10-16 12:00:00+00", 1, "record", record)],
        )
    ]
    (text,) = pd.read_parquet(tmp_path / "out" / write(tmp_path, files)["path"])[
        "raw_listing_json"
    ]
    assert text == (
        '{"description":"Café – sunny","id":"4000001","pricing":{"price":3050,'
        '"priceChanges":[{"changedAt":"2026-10-01","price":3100},'
        '{"changedAt":"2026-10-08","price":3050.5}]},'
        '"propertyDetails":{"bathroomCount":1.5,"livingAreaSize":750}}'
    )


def test_fetch_times(tmp_path):
    """A record answered four times, twice at its first time, gives one row with its first and
    last answer's times and the lower ID of its two first answers. A changed record gives a
    second row, after the first, and an answer without a record gives none."""
    old = {"id": "4000002", "pricing": {"price": 3000.0}}
    new = {"id": "4000002", "pricing": {"price": 2900.0}}
    files = [
        answers_file(
            tmp_path / "a.parquet",
            [
                # DuckDB scans this answer first, and without the tie on IDs takes its ID.
                (4000002, "2026-10-15 01:00:00.000001+00", 8, "record", old),
                (4000002, "2026-10-15 01:00:00.000001+00", 7, "record", old),
                (4000002, "2026-10-15 02:00:00+00", 9, "record", old),
                (4000003, "2026-10-15 02:00:00+00", 9, "missing", None),
            ],
        ),
        answers_file(
            tmp_path / "b.parquet",
            [
                (4000002, "2026-10-16 03:00:00.5+00", 12, "record", old),
                (4000002, "2026-10-16 04:00:00+00", 14, "record", new),
            ],
        ),
    ]
    frame = pd.read_parquet(tmp_path / "out" / write(tmp_path, files)["path"])
    first = pd.Timestamp("2026-10-15 01:00:00.000001", tz="UTC")
    assert frame[
        ["listing_id", "collected_at", "last_collected_at", "response_id"]
    ].to_dict("records") == [
        {
            "listing_id": 4000002,
            "collected_at": (first.value // 1000) / 1e6,
            "last_collected_at": pd.Timestamp(
                "2026-10-16 03:00:00.5", tz="UTC"
            ).timestamp(),
            "response_id": 7,
        },
        {
            "listing_id": 4000002,
            "collected_at": pd.Timestamp("2026-10-16 04:00", tz="UTC").timestamp(),
            "last_collected_at": pd.Timestamp("2026-10-16 04:00", tz="UTC").timestamp(),
            "response_id": 14,
        },
    ]
    assert [
        json.loads(text)["pricing"]["price"] for text in frame.raw_listing_json
    ] == [
        3000,
        2900,
    ]


def test_a_record_twice_in_the_cache_stops(tmp_path):
    """A cache holding a record twice stops the step, and OUT keeps no file. So do another
    step holding the cache's lock and an export without records."""
    files = [
        answers_file(
            tmp_path / "a.parquet",
            [(4000004, "2026-10-16 12:00:00+00", 1, "record", {"id": "4000004"})],
        )
    ]
    line = write(tmp_path, files)
    (tmp_path / "out" / line["path"]).unlink()
    (cached,) = (tmp_path / "cache").glob("*/*.parquet")
    cached.with_name("copy.parquet").write_bytes(cached.read_bytes())
    with pytest.raises(ValueError, match="holds 1 records twice"):
        write(tmp_path, files)
    assert list((tmp_path / "out").iterdir()) == []
    cached.with_name("copy.parquet").unlink()
    with open(tmp_path / "cache" / ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with pytest.raises(RuntimeError, match="another records step holds"):
            write(tmp_path, files)
    assert list((tmp_path / "out").iterdir()) == []
    empty = [
        answers_file(
            tmp_path / "empty.parquet",
            [(4000005, "2026-10-16 12:00:00+00", 2, "missing", None)],
        )
    ]
    with pytest.raises(ValueError, match="the export holds no records"):
        write(tmp_path / "empty", empty)
    assert not (tmp_path / "empty" / "out").exists()
    with pytest.raises(ValueError, match="lists no ads files"):
        write(tmp_path / "none", [])
