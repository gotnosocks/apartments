import copy
import hashlib
import importlib.util
import json
import os
import shutil
from pathlib import Path

import duckdb
import pandas as pd
import pytest

FIXTURE = Path(__file__).resolve().parent / "fixture"
BUILD = Path(__file__).resolve().parents[2] / "ops" / "pipeline" / "build.py"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# pytest imports test modules by path, so the helpers of test_pipeline.py load the same way.
helpers = load("pipeline_tests", Path(__file__).with_name("test_pipeline.py"))
copy_export, append_answers = helpers.copy_export, helpers.append_answers


@pytest.fixture
def build(monkeypatch, tmp_path):
    """`build.build` from ops/pipeline, with the environment it sets restored afterwards and an
    empty corrections ledger."""
    (tmp_path / "ledger").mkdir()
    monkeypatch.setenv("PIPELINE_EXPORT", "")
    monkeypatch.setenv("PIPELINE_STATE", "")
    monkeypatch.setenv("PIPELINE_LEDGER", str(tmp_path / "ledger"))
    monkeypatch.setenv("PIPELINE_MEMORY", "1GB")
    return load("build", BUILD).build


def test_build_writes_hashed_files_and_a_catalog_line(tmp_path, build):
    export = copy_export(tmp_path)
    first = build(export, tmp_path / "state", tmp_path / "out")
    frames = {}
    for stem, key, model in (
        ("rows", "rows", "analysis.rows"),
        ("ads", "ads_file", "analysis.ads"),
    ):
        path = tmp_path / "out" / first[key]["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == first[key]["sha256"]
        assert path.name == f"{stem}-{first[key]['sha256'][:16]}.parquet"
        frame = frames[stem] = pd.read_parquet(path)
        assert len(frame) == first[key]["rows"] == first["models"][model]["rows"]
        assert frame.listing_id.is_monotonic_increasing
    # The records file holds each of the fixture's 229 records once.
    path = tmp_path / "out" / first["records"]["path"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == first["records"]["sha256"]
    assert path.name == f"records-{first['records']['sha256'][:16]}.parquet"
    records = pd.read_parquet(path)
    assert len(records) == first["records"]["rows"] == first["records"]["read"] == 229
    assert (
        records.listing_id.is_monotonic_increasing and records.record_sha256.is_unique
    )
    assert frames["ads"].listing_id.is_unique
    assert set(frames["ads"].listing_id[frames["ads"].in_rows]) == set(
        frames["rows"].listing_id
    )
    assert first["ads"]["files"] == {
        str(path.relative_to(export)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (export / "ads").glob("*/*.parquet")
    }
    city = Path(os.environ["PIPELINE_CITY"])
    assert first["city"] == {
        "archive": str(city),
        "files": {
            str(path.relative_to(city)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in city.glob("*/*.*")
        },
    }
    assert all(model["seconds"] is not None for model in first["models"].values())
    # A second build from the same export rebuilds nothing and writes the same file.
    second = build(export, tmp_path / "state", tmp_path / "out")
    assert second["rows"] == first["rows"] and second["ads_file"] == first["ads_file"]
    assert second["records"] == first["records"] | {"read": 0, "reused": True}
    assert all(model["seconds"] is None for model in second["models"].values())
    assert sorted(path.name for path in (tmp_path / "out").iterdir()) == [
        first["ads_file"]["path"],
        "catalog.ndjson",
        first["records"]["path"],
        first["rows"]["path"],
    ]
    catalog = (tmp_path / "out" / "catalog.ndjson").read_text().splitlines()
    assert [json.loads(line) for line in catalog] == [first, second]


def tables(state, names):
    """Each model's row count and a hash over its rows in any order."""
    db = duckdb.connect(str(state / "pipeline.duckdb"), read_only=True)
    try:
        return {
            name: db.execute(
                f"""SELECT count(*), md5(coalesce(string_agg(h, ',' ORDER BY h), ''))
                FROM (SELECT md5(t::VARCHAR) AS h FROM {name} t)"""
            ).fetchone()
            for name in names
        }
    finally:
        db.close()


def back_on_market(record, listing_id, day, price):
    """A copy of `record` for ad `listing_id`, active again from `day` at `price`. The ad's
    entry in the unit history gets the event, and a missing entry is added first."""
    record = copy.deepcopy(record)
    stamp = f"{day}T10:00:00.000-04:00"
    record.update(id=str(listing_id), status="ACTIVE", offMarketAt=None)
    record["statusChanges"].append({"changedAt": stamp, "status": "ACTIVE"})
    record["pricing"]["price"] = price
    record["pricing"]["priceChanges"].append({"changedAt": stamp, "price": price})
    event = {
        "__typename": "RentalStatusChangeOfInterest",
        "date": day,
        "price": price,
        "status": "ACTIVE",
    }
    for entry in record["propertyHistory"]:
        if entry["listingId"] == str(listing_id):
            entry["rentalEventsOfInterest"].insert(0, event)
            entry["offMarketAt"] = None
            break
    else:
        record["propertyHistory"].insert(
            0,
            {
                "__typename": "RentalListingChangesOfInterest",
                "listingId": str(listing_id),
                "offMarketAt": None,
                "photos": [],
                "rentalEventsOfInterest": [event],
            },
        )
    return json.dumps(record, sort_keys=True)


def test_topup_build_equals_a_full_build(tmp_path, build):
    """Building runs 2 and 3, then adding run 4 and three answers of run 5, gives every model
    the table of a build of it all into an empty state, and the same rows, ads and records
    files. The top-up reads only the new answers' records. The run 5 answers put ad 4554594 of
    unit 12 of building 72793 back on the market at a new price, add an ad in unit 16, whose
    ads all came in run 2, and add an ad in a new unit of the building. A further build finds
    nothing to rebuild, and one without `STATE/merge.json` reads every answer again. Last, a
    run 4 file written again with another region makes ads.changes read every answer, and the
    build records that mode."""
    export = copy_export(tmp_path, keep=lambda line: line["run"] < 4)
    first = build(export, tmp_path / "state", tmp_path / "out")
    shutil.copy(FIXTURE / "export" / "manifest.ndjson", export / "manifest.ndjson")
    db = duckdb.connect()
    old = {
        listing_id: json.loads(record)
        for listing_id, record in db.execute(
            """SELECT listing_id, record FROM read_parquet(?)
            WHERE listing_id IN (4554594, 4984980)""",
            [str(FIXTURE / "export/ads/*/*.parquet")],
        ).fetchall()
    }
    db.close()
    unit = copy.deepcopy(old[4984980])
    unit.update(createdAt="2026-10-19T09:00:00.000-04:00", onMarketAt="2026-10-19")
    unit["statusChanges"], unit["pricing"]["priceChanges"] = [], []
    other = copy.deepcopy(unit)
    other.update(slug="16a", propertyHistory=[])
    added = [
        (4554594, back_on_market(old[4554594], 4554594, "2026-10-20", 4100)),
        (5900001, back_on_market(unit, 5900001, "2026-10-19", 3900)),
        (5900002, back_on_market(other, 5900002, "2026-10-19", 3700)),
    ]
    append_answers(export, helpers.answers("listing_id", added, 7001, "2026-10-21"))
    topup = build(export, tmp_path / "state", tmp_path / "out")
    full = build(export, tmp_path / "fresh", tmp_path / "out-fresh")
    assert not first["top_up"] and topup["top_up"] and not full["top_up"]
    assert topup["rows"] == full["rows"] and topup["ads_file"] == full["ads_file"]
    assert topup["records"] == full["records"] | {"read": 49 + len(added)}
    assert topup["ads"] == full["ads"] and topup["buildings"] == full["buildings"]
    # The top-up's change tables hold the answers of run 4 and run 5 and the ads they change,
    # and those of the build into an empty state hold every answer and ad.
    names = sorted(set(full["models"]) - {"ads.changes", "ads.touched"})
    merged, scratch = (
        tables(tmp_path / "state", names),
        tables(tmp_path / "fresh", names),
    )
    assert [name for name in names if merged[name] != scratch[name]] == []
    changes = tables(tmp_path / "state", ["ads.changes", "ads.touched"])
    everything = tables(tmp_path / "fresh", ["ads.changes", "ads.touched"])
    assert changes["ads.changes"][0] == 49 + len(added) < everything["ads.changes"][0]
    assert changes["ads.touched"][0] < everything["ads.touched"][0]
    # A build with no new answers reuses the mode and rebuilds nothing. With the record of the
    # merge code deleted, a build reads every answer again.
    again = build(export, tmp_path / "state", tmp_path / "out")
    assert again["top_up"] and all(
        m["seconds"] is None for m in again["models"].values()
    )
    (tmp_path / "state" / "merge.json").unlink()
    redone = build(export, tmp_path / "state", tmp_path / "out")
    assert not redone["top_up"] and redone["rows"] == full["rows"]
    assert redone["ads_file"] == full["ads_file"]
    every = sorted(full["models"])
    assert tables(tmp_path / "state", every) == tables(tmp_path / "fresh", every)
    # The build asks for a top-up, since raw.ads has a new file, but the previous answers of
    # run 4 no longer hold.
    lines = [json.loads(line) for line in open(export / "manifest.ndjson")]
    (line,) = [line for line in lines if line["table"] == "ads" and line["run"] == 4]
    path = export / line["path"]
    db = duckdb.connect()
    db.execute(
        f"""COPY (SELECT * REPLACE ('manhattan-59th-110th' AS region) FROM '{path}')
        TO '{path}.new' (FORMAT parquet)"""
    )
    db.close()
    Path(f"{path}.new").replace(path)
    line["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (export / "manifest.ndjson").write_text(
        "".join(json.dumps(line, sort_keys=True) + "\n" for line in lines)
    )
    moved = build(export, tmp_path / "state", tmp_path / "out")
    record = json.loads((tmp_path / "state" / "merge.json").read_text())
    assert not moved["top_up"] and record["incremental"] and not record["top_up"]
    db = duckdb.connect(str(tmp_path / "state" / "pipeline.duckdb"), read_only=True)
    regions = db.execute("SELECT DISTINCT unnest(regions) FROM ads.regions").fetchall()
    db.close()
    assert sorted(regions) == [
        ("brooklyn-prospect-park",),
        ("cases",),
        ("manhattan-59th-110th",),
    ]


def test_merge_code_change_rebuilds_the_merge_models(tmp_path, monkeypatch):
    """An edit to the materialization `merge` gives ads.changes new data, and so every model of
    kind `merge` a new fingerprint, and the plan rebuilds them."""
    project = tmp_path / "project"
    shutil.copytree(
        helpers.PROJECT,
        project,
        ignore=shutil.ignore_patterns(".venv", "tests", "logs", "__pycache__"),
    )
    (tmp_path / "src").symlink_to(helpers.PROJECT.parent / "src")

    def fingerprints():
        ctx = helpers.context(monkeypatch, tmp_path / "state", project=project)
        try:
            return {s.name: s.fingerprint for s in ctx.snapshots.values()}, {
                model.fqn
                for model in ctx.models.values()
                if model.kind.is_custom and model.kind.materialization == "merge"
            }
        finally:
            ctx.close()

    before, merges = fingerprints()
    code = project / "materializations" / "merge.py"
    code.write_text(code.read_text() + "\n# An edit.\n")
    after, _ = fingerprints()
    assert [n for n in before if before[n].data_hash != after[n].data_hash] == [
        '"pipeline"."ads"."changes"'
    ]
    assert len(merges) == 16 and merges <= {n for n in before if before[n] != after[n]}


def test_failed_audit_writes_nothing(tmp_path, build):
    """An export file repeating an answer fails the audit of ads.answers. The build stops, and
    OUT keeps only the first build's files and catalog line."""
    export = copy_export(tmp_path)
    first = build(export, tmp_path / "state", tmp_path / "out")
    before = {path.name: path.read_bytes() for path in (tmp_path / "out").iterdir()}
    repeated = (
        duckdb.connect(config={"TimeZone": "UTC"})
        .execute(
            "SELECT * FROM read_parquet(?) ORDER BY response_id LIMIT 1",
            [str(FIXTURE / "export/ads/run-0002/*.parquet")],
        )
        .df()
    )
    append_answers(export, repeated)
    with pytest.raises(SystemExit, match="build stopped"):
        build(export, tmp_path / "state", tmp_path / "out")
    assert sorted(before) == [
        first["ads_file"]["path"],
        "catalog.ndjson",
        first["records"]["path"],
        first["rows"]["path"],
    ]
    after = {path.name: path.read_bytes() for path in (tmp_path / "out").iterdir()}
    assert after == before


def test_failed_janitor_warns(tmp_path, build, monkeypatch, capsys):
    """The janitor raises after the build writes its files and catalog line. They stay in place,
    and the build returns its line with a warning on stderr."""
    import sqlmesh

    def fail(self, ignore_ttl):
        raise RuntimeError("planted")

    monkeypatch.setattr(sqlmesh.Context, "run_janitor", fail)
    line = build(copy_export(tmp_path), tmp_path / "state", tmp_path / "out")
    assert (tmp_path / "out" / line["rows"]["path"]).exists()
    assert (tmp_path / "out" / line["ads_file"]["path"]).exists()
    catalog = (tmp_path / "out" / "catalog.ndjson").read_text().splitlines()
    assert [json.loads(entry) for entry in catalog] == [line]
    assert "janitor failed: planted" in capsys.readouterr().err


def test_ledger_in_another_folder_rebuilds_nothing(tmp_path, build, monkeypatch):
    """The catalog line gives the ledger files by name. A build with the same files in another
    folder, as from another checkout, reuses every model, and a later edit there rebuilds the
    ledger models from that folder."""
    export = copy_export(tmp_path)
    names = {"": "2026-01-01-a.ndjson", "units": "2026-01-01-b.ndjson"}
    for folder in (tmp_path / "ledger", tmp_path / "elsewhere" / "ledger"):
        for sub, name in names.items():
            (folder / sub).mkdir(parents=True, exist_ok=True)
            (folder / sub / name).write_text("\n")
    digest = hashlib.sha256(b"\n").hexdigest()
    first = build(export, tmp_path / "state", tmp_path / "out")
    assert first["ledger"]["files"] == {names[""]: digest}
    assert first["ledger"]["units"]["files"] == {names["units"]: digest}
    monkeypatch.setenv("PIPELINE_LEDGER", str(tmp_path / "elsewhere" / "ledger"))
    second = build(export, tmp_path / "state", tmp_path / "out")
    assert second["ledger"] == first["ledger"]
    assert all(model["seconds"] is None for model in second["models"].values())
    for sub in names:
        (tmp_path / "elsewhere" / "ledger" / sub / names[sub]).write_text("\n\n")
    third = build(export, tmp_path / "state", tmp_path / "out")
    assert third["models"]["ledger.entries"]["seconds"] is not None
    assert third["models"]["ledger.unit_entries"]["seconds"] is not None
    assert third["rows"] == first["rows"]
