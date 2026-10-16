import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import duckdb
import pytest

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


def low(building_id):
    """Whether a share of 0.5 picks the building, by Python's own reading of the hash."""
    return int.from_bytes(hashlib.md5(building_id.encode()).digest(), "little") < 2**127


def write_run(db, export, table, rows):
    """Write the rows of the table `rows` as a new run of the export's `table`."""
    run, first, last, count = db.sql(
        f"SELECT max(run), min(response_id), max(response_id), count(*) FROM {rows}"
    ).fetchone()
    path = Path(table) / f"run-{run:04d}" / f"responses-{first:07d}-{last:07d}.parquet"
    (export / path).parent.mkdir(parents=True)
    db.execute(f"COPY {rows} TO '{export / path}' (FORMAT parquet)")
    line = {
        "first": first,
        "last": last,
        "path": str(path),
        "rows": count,
        "run": run,
        "sha256": hashlib.sha256((export / path).read_bytes()).hexdigest(),
        "table": table,
        "written": "2026-10-23T12:00:00Z",
    }
    with open(export / "manifest.ndjson", "a") as f:
        f.write(json.dumps(line, sort_keys=True) + "\n")


def planted(tmp_path):
    """Copy the fixture export and add a run with the cases the fixture lacks:
    1. a later record of a picked ad, giving a building outside the picked ones;
    2. a `missing` answer of an ad outside the sample, and one of an ad with no record at all;
    3. an answer of a picked building that no ad gives.
    Return the copy and the planted building IDs."""
    export = tmp_path / "export"
    shutil.copytree(FIXTURE / "export", export)
    db = duckdb.connect(config={"TimeZone": "UTC"})
    answers(db, "ads", export, "ads")
    answers(db, "buildings", export, "buildings")
    gives = db.sql(
        "SELECT listing_id, list(DISTINCT json_extract_string(record, '$.buildingId')) "
        "FROM ads WHERE record IS NOT NULL GROUP BY listing_id ORDER BY listing_id"
    ).fetchall()
    inside = next(ad for ad, ids in gives if all(map(low, ids)))
    outside = next(ad for ad, ids in gives if not any(map(low, ids)))
    known = {b for _, ids in gives for b in ids}
    fresh = [str(n) for n in range(900000, 900100) if str(n) not in known]
    given, alone = (
        next(b for b in fresh if not low(b)),
        next(b for b in fresh if low(b)),
    )
    run, response, listing = db.sql(
        "SELECT max(run) + 1, (SELECT max(response_id) FROM (FROM ads UNION ALL BY NAME "
        "FROM buildings)), max(listing_id) FROM ads"
    ).fetchone()
    db.execute(
        f"""CREATE TABLE new_ads AS
        SELECT * REPLACE ({run} AS run, {response} + 1 AS response_id,
            fetched + INTERVAL 7 DAY AS fetched,
            json_merge_patch(record, json_object('buildingId', '{given}'))::VARCHAR AS record)
        FROM ads WHERE listing_id = {inside} ORDER BY response_id DESC LIMIT 1"""
    )
    db.execute("UPDATE new_ads SET record_sha256 = sha256(record)")
    db.execute(
        f"""INSERT INTO new_ads
        SELECT a.* REPLACE ({run} AS run, {response} + n AS response_id, 'missing' AS outcome,
            NULL AS record_sha256, NULL AS record, l AS listing_id)
        FROM (SELECT * FROM ads WHERE listing_id = {outside} ORDER BY response_id LIMIT 1) a,
            (VALUES (2, {outside}), (3, {listing} + 1)) v(n, l)"""
    )
    db.execute(
        f"""CREATE TABLE new_buildings AS
        SELECT a.* REPLACE ({run} AS run, {response} + n AS response_id, b AS building_id)
        FROM (SELECT * FROM buildings ORDER BY response_id LIMIT 1) a,
            (VALUES (4, '{given}'), (5, '{alone}')) v(n, b)"""
    )
    write_run(db, export, "ads", "new_ads")
    write_run(db, export, "buildings", "new_buildings")
    return export, given, alone, outside, listing + 1


def test_sample_takes_whole_buildings(tmp_path):
    export, given, alone, outside, recordless = planted(tmp_path)
    out = tmp_path / "out" / "export"
    counts = sample.sample(export, tmp_path / "out", 0.5)
    db = duckdb.connect()
    answers(db, "full_ads", export, "ads")
    answers(db, "full_buildings", export, "buildings")
    answers(db, "ads", out, "ads")
    answers(db, "buildings", out, "buildings")
    gives, recordless_ads = {}, set()
    for listing_id, building_id in db.sql(
        "SELECT listing_id, json_extract_string(record, '$.buildingId') FROM full_ads"
    ).fetchall():
        if building_id is None:
            recordless_ads.add(listing_id)
        else:
            gives.setdefault(listing_id, set()).add(building_id)
    ids = set().union(*gives.values()) | {
        b for (b,) in db.sql("SELECT building_id FROM full_buildings").fetchall()
    }
    picked = {b for b in ids if low(b)}
    assert 0 < len(picked) < len(ids)
    picked_ads = {ad for ad, b in gives.items() if b & picked} | recordless_ads
    taken = picked | set().union(*(gives.get(ad, set()) for ad in picked_ads))
    assert {outside, recordless} <= picked_ads and alone in picked
    assert given in taken and given not in picked
    expected = db.execute(
        "SELECT * FROM full_ads WHERE list_contains(?, listing_id) "
        "ORDER BY response_id, listing_id",
        [sorted(picked_ads)],
    ).fetchall()
    assert (
        db.sql("SELECT * FROM ads ORDER BY response_id, listing_id").fetchall()
        == expected
    )
    assert (
        db.sql("SELECT * FROM buildings ORDER BY response_id").fetchall()
        == db.execute(
            "SELECT * FROM full_buildings WHERE list_contains(?, building_id) "
            "ORDER BY response_id",
            [sorted(taken)],
        ).fetchall()
    )
    assert counts["buildings_picked"] == len(picked)
    assert counts["ads"] == len(picked_ads)
    assert counts["ad_answers"] == len(expected)
    # The records keep their bytes, and each manifest line gives its file's SHA-256.
    assert not db.sql(
        "SELECT * FROM ads WHERE sha256(record) <> record_sha256"
    ).fetchall()
    for entry in sample.manifest(out):
        digest = hashlib.sha256((out / entry["path"]).read_bytes()).hexdigest()
        assert entry["sha256"] == digest


def test_sample_refuses_an_output_over_the_export(tmp_path):
    export = tmp_path / "export" / "export"
    shutil.copytree(FIXTURE / "export", export)
    # The sample would replace the export, go inside it, or replace a folder holding it.
    for out in (export.parent, export, tmp_path):
        with pytest.raises(ValueError, match="overlaps the export"):
            sample.sample(export, out, 0.5)
    assert (export / "manifest.ndjson").is_file()


def test_manifest_reads_a_repeated_line_once(tmp_path):
    export = tmp_path / "export"
    shutil.copytree(FIXTURE / "export", export)
    lines = (export / "manifest.ndjson").read_text().splitlines(keepends=True)
    (export / "manifest.ndjson").write_text("".join(lines + lines[:1]))
    assert sample.manifest(export) == [json.loads(line) for line in lines]
    changed = dict(json.loads(lines[0]), sha256="0" * 64)
    (export / "manifest.ndjson").write_text("".join(lines) + json.dumps(changed) + "\n")
    with pytest.raises(ValueError, match="two hashes"):
        sample.manifest(export)


def test_sample_writes_the_same_bytes_again(tmp_path):
    export, out = FIXTURE / "export", tmp_path / "out"
    sample.sample(export, out, 0.5)
    first = (out / "export" / "manifest.ndjson").read_text()
    sample.sample(export, out, 0.5)
    assert (out / "export" / "manifest.ndjson").read_text() == first
    assert sorted(p.name for p in out.iterdir()) == ["export"]
