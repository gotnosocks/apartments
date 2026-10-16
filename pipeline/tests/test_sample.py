import hashlib
import importlib.util
from pathlib import Path

import duckdb

FIXTURE = Path(__file__).resolve().parent / "fixture"
SAMPLE = Path(__file__).resolve().parents[2] / "ops" / "pipeline" / "sample.py"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sample = load("pipeline_sample", SAMPLE)


def answers(db, name, export, table):
    files = [
        str(export / e["path"]) for e in sample.manifest(export) if e["table"] == table
    ]
    db.execute(f"CREATE TABLE {name} AS SELECT * FROM read_parquet(?)", [files])


def test_sample_takes_whole_buildings(tmp_path):
    export, out = FIXTURE / "export", tmp_path / "out" / "export"
    counts = sample.sample(export, tmp_path / "out", 0.5)
    db = duckdb.connect()
    answers(db, "full_ads", export, "ads")
    answers(db, "full_buildings", export, "buildings")
    answers(db, "ads", out, "ads")
    answers(db, "buildings", out, "buildings")
    db.execute(
        "CREATE TABLE named AS SELECT DISTINCT listing_id, "
        "json_extract_string(record, '$.buildingId') AS building_id FROM full_ads "
        "WHERE record IS NOT NULL"
    )
    ids = [b for (b,) in db.sql("SELECT DISTINCT building_id FROM named").fetchall()]
    picked = [
        b
        for b in ids
        if int.from_bytes(hashlib.md5(b.encode()).digest(), "little") < 2**127
    ]
    assert 0 < len(picked) < len(ids)
    expected = db.execute(
        "SELECT * FROM full_ads WHERE listing_id IN (SELECT listing_id FROM named "
        "WHERE list_contains(?, building_id)) ORDER BY response_id, listing_id",
        [picked],
    ).fetchall()
    assert (
        db.sql("SELECT * FROM ads ORDER BY response_id, listing_id").fetchall()
        == expected
    )
    assert (
        db.sql("SELECT * FROM buildings ORDER BY response_id").fetchall()
        == db.execute(
            "SELECT * FROM full_buildings WHERE list_contains(?, building_id) ORDER BY response_id",
            [picked],
        ).fetchall()
    )
    assert counts["buildings_picked"] == len(picked)
    assert counts["ad_answers"] == len(expected)
    # The records keep their bytes, and each manifest line gives its file's SHA-256.
    assert not db.sql(
        "SELECT * FROM ads WHERE sha256(record) <> record_sha256"
    ).fetchall()
    for entry in sample.manifest(out):
        digest = hashlib.sha256((out / entry["path"]).read_bytes()).hexdigest()
        assert entry["sha256"] == digest


def test_sample_writes_the_same_bytes_again(tmp_path):
    export, out = FIXTURE / "export", tmp_path / "out"
    sample.sample(export, out, 0.5)
    first = (out / "export" / "manifest.ndjson").read_text()
    sample.sample(export, out, 0.5)
    assert (out / "export" / "manifest.ndjson").read_text() == first
    assert sorted(p.name for p in out.iterdir()) == ["export"]
