import importlib.util
import json
from pathlib import Path

import duckdb
import pandas as pd
import pytest

FIXTURE = Path(__file__).resolve().parent / "fixture"
OBSERVATIONS = (
    Path(__file__).resolve().parents[2] / "ops" / "pipeline" / "observations.py"
)
FIRST_ASK = "historical_initial_own_advertisement_ask"
# The chain's alias table and history pairs cover the Manhattan neighbourhoods they were built
# for. The pipeline builds both for every building, so it also joins two Park Slope units to the
# units of their floor-word spellings: "4th-floor" to "4" and "2nd-floor" to "2".
PARK_SLOPE = {
    "unit:363741c4-1330-5f41-9e22-655ec9ae977d": "unit:357c333f-2e72-5a1f-9463-93a054593fe2",
    "unit:5d0a7af9-8129-512c-8db7-9bdd4de0b3c7": "unit:05f12b29-34c5-5493-876c-55d1c039e589",
}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# pytest imports test modules by path, so the build fixture of test_build.py loads the same way.
tests = load("build_tests", Path(__file__).with_name("test_build.py"))
helpers, build = tests.helpers, tests.build


def chain_records() -> list[dict]:
    """The fixture's chain rows as the chain writes them to observations.jsonl, with the
    pipeline's latest asks and the fills of `ELEVATOR_FILLS` and `PET_FILLS`."""
    db = duckdb.connect(config={"TimeZone": "UTC"})
    result = db.execute(
        f"""SELECT c.* REPLACE (
            strftime(c.price_at, '%Y-%m-%dT%H:%M:%S+00:00') AS price_at,
            strftime(c.period, '%Y-%m-%d') AS period,
            l.latest_ask AS asking_rent,
            c.floor_label_provenance::VARCHAR AS floor_label_provenance,
            c.view_exposures::VARCHAR AS view_exposures,
            c.window_exposures::VARCHAR AS window_exposures)
        FROM '{FIXTURE / "chain-rows.parquet"}' c
        JOIN '{FIXTURE / "latest-ask.parquet"}' l ON l.listing_id = c.source_listing_id
        ORDER BY c.source_listing_id"""
    )
    names = [column[0] for column in result.description]
    records = []
    for row in (dict(zip(names, values)) for values in result.fetchall()):
        for key in ("floor_label_provenance", "view_exposures", "window_exposures"):
            row[key] = json.loads(row[key])
        # The fixture's Parquet file holds the floors as doubles, and the chain writes a
        # floor read from the unit label as an int.
        if row["label_derived_floor"] is not None:
            row["label_derived_floor"] = int(row["label_derived_floor"])
        if row["floor_label_provenance"]["status"] == "label_proxy":
            row["listed_floor"] = int(row["listed_floor"])
        for key, fills in (
            ("elevator", helpers.ELEVATOR_FILLS),
            ("pet_policy", helpers.PET_FILLS),
        ):
            if row[key] is None:
                row[key] = fills.get(row["source_listing_id"])
        row["analysis_price_basis"] = FIRST_ASK
        row["description_interpreted_at"] = None
        records.append(row)
    return records


def write_dataset(folder: Path, records: list[dict]) -> Path:
    folder.mkdir(parents=True)
    with open(folder / "observations.jsonl", "w") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True) + "\n")
    return folder


@pytest.fixture
def converter(monkeypatch):
    monkeypatch.setenv("PIPELINE_MEMORY", "1GB")
    return load("observations", OBSERVATIONS)


def test_observations_load_as_the_chains(tmp_path, build, converter):
    """The dataset folder written from the fixture build's rows file loads with
    `rentfrontier.data.load` to the chain's rows, with the rows file's latest asks."""
    catalog = tmp_path / "out"
    line = build(helpers.copy_export(tmp_path), tmp_path / "state", catalog)
    original, ads = catalog / line["rows"]["path"], catalog / line["ads_file"]["path"]
    expected = chain_records()
    assert len(expected) == 229
    # The build's rows file with a made-up latest ask for an ad, as a ledger set of the ask
    # gives it, and an ad whose API record has no views or windows. Then the rows file of a
    # build from before the `latest_ask` column.
    changed, bare = expected[2]["source_listing_id"], expected[3]["source_listing_id"]
    expected[2]["asking_rent"] = 1234.0
    expected[3]["view_exposures"] = expected[3]["window_exposures"] = None
    rows, first = catalog / "rows-ask-set.parquet", catalog / "rows-first-asks.parquet"
    duckdb.execute(
        f"""COPY (SELECT * REPLACE (
                CASE WHEN listing_id = '{changed}' THEN 1234.0 ELSE latest_ask END AS latest_ask,
                CASE WHEN listing_id = '{bare}' THEN NULL ELSE view_exposures END
                    AS view_exposures,
                CASE WHEN listing_id = '{bare}' THEN NULL ELSE window_exposures END
                    AS window_exposures) FROM '{original}')
        TO '{rows}' (FORMAT parquet)"""
    )
    duckdb.execute(
        f"""COPY (SELECT * EXCLUDE (latest_ask) FROM '{original}')
        TO '{first}' (FORMAT parquet)"""
    )
    # The catalog's newest line from a clean checkout, followed by a line from a checkout with
    # changes and a line still being written.
    clean = {
        **line,
        "code": {**line["code"], "clean": True},
        "rows": {**line["rows"], "path": rows.name, "sha256": converter.sha256(rows)},
    }
    dirty = {**line, "code": {**line["code"], "clean": False}, "rows": {"sha256": "0"}}
    (catalog / "catalog.ndjson").write_text(
        json.dumps(clean) + "\n" + json.dumps(dirty) + "\n" + json.dumps(dirty)[:20]
    )
    # An ad left out of the chain's audit IDs, and an ad the served dataset gives another.
    new_ad, other_id = (
        expected[0]["source_listing_id"],
        expected[1]["source_listing_id"],
    )
    for record in expected:
        if record["source_listing_id"] == new_ad:
            record["audit_id"] = f"api:{new_ad}"
    keys = [
        {k: r[k] for k in ("source_listing_id", "audit_id", "analysis_price_basis")}
        for r in expected
        if r["source_listing_id"] != new_ad
    ]
    # A row the chain prices at the ad's current page, under an ID of its own.
    keys.append(
        {
            "source_listing_id": other_id,
            "audit_id": "capture:refresh:0:1",
            "analysis_price_basis": "current_capture_gross_ask",
        }
    )
    audit = write_dataset(tmp_path / "audit", keys)
    hoods = sorted({r["neighbourhood"] for r in expected})
    served = [
        {
            "source_listing_id": r["source_listing_id"],
            "audit_id": "served"
            if r["source_listing_id"] == other_id
            else r["audit_id"],
            "analysis_price_basis": FIRST_ASK,
            "neighbourhood": r["neighbourhood"],
        }
        for r in expected
        if r["source_listing_id"] != new_ad
    ]
    served = write_dataset(tmp_path / "served", served)

    out = tmp_path / "dataset"
    build_files = converter.pick_build(catalog, None, None)
    assert build_files["rows"]["path"] == str(rows.resolve())
    assert build_files["catalog"]["code"] == clean["code"]
    manifest = converter.write(out, build_files, None, served, audit)
    assert sorted(path.name for path in out.iterdir()) == [
        "manifest.json",
        "observations.jsonl",
    ]
    assert not list(tmp_path.glob(".dataset.tmp-*"))
    assert json.loads((out / "manifest.json").read_text()) == manifest
    assert manifest["rows"] == 229
    assert list(manifest["neighbourhoods"]) == hoods
    assert manifest["audit_ids"]["from_chain"] == 228
    assert manifest["audit_ids"]["api"] == 1
    assert manifest["served"]["audit_id_differs"] == [
        {
            "source_listing_id": other_id,
            "served": "served",
            "audit_ids": next(
                r["audit_id"] for r in expected if r["source_listing_id"] == other_id
            ),
        }
    ]
    assert manifest["files"]["observations.jsonl"] == converter.sha256(
        out / "observations.jsonl"
    )
    assert manifest["rows_file"]["path"].endswith(".parquet")

    data = converter.frontier_data()
    chain = write_dataset(tmp_path / "chain", expected)
    ours = data.load(out, cache_root=tmp_path / "cache")
    theirs = data.DATA_RULES["unit-labels-v17"](
        data.load(chain, cache_root=tmp_path / "cache")
    )
    theirs["unit_id"] = theirs.unit_id.replace(PARK_SLOPE)
    theirs = data.DATA_RULES["unit-splits-v4"](theirs)
    pd.testing.assert_frame_equal(ours, theirs, check_like=True)
    # The fields a fit's frame leaves out.
    lines = [json.loads(line) for line in (out / "observations.jsonl").open()]
    assert [r["source_listing_id"] for r in lines] == [
        r["source_listing_id"] for r in expected
    ]
    for key in (
        "floor_label_provenance",
        "advertised_floor",
        "physical_floor",
        "floors_above_ground",
    ):
        assert [r[key] for r in lines] == [r[key] for r in expected], key
    assert all(sorted(r) == sorted(expected[0]) for r in lines)
    # The chain writes a floor read from the unit label as an int.
    for r in lines:
        assert r["label_derived_floor"] is None or type(r["label_derived_floor"]) is int
        if r["floor_label_provenance"]["status"] == "label_proxy":
            assert type(r["listed_floor"]) is int

    with pytest.raises(SystemExit, match="exists"):
        converter.write(out, build_files, None, served, audit)
    # The first neighbourhood's rows written under the second's name.
    old_hood, new_hood = hoods[0], hoods[1]
    renamed = tmp_path / "renamed"
    moved = converter.write(
        renamed, build_files, None, served, audit, {old_hood: new_hood}
    )
    assert moved["renamed"] == {
        old_hood: {"to": new_hood, "rows": manifest["neighbourhoods"][old_hood]}
    }
    assert moved["neighbourhoods"] == {
        h: n + (manifest["neighbourhoods"][old_hood] if h == new_hood else 0)
        for h, n in manifest["neighbourhoods"].items()
        if h != old_hood
    }
    assert [
        json.loads(line)["neighbourhood"]
        for line in (renamed / "observations.jsonl").open()
    ] == [
        new_hood if r["neighbourhood"] == old_hood else r["neighbourhood"]
        for r in lines
    ]
    # A rename adds its old name to the neighbourhoods asked for, and a rename moving no rows
    # stops the script.
    only = converter.write(
        tmp_path / "only", build_files, [new_hood], served, audit, {old_hood: new_hood}
    )
    assert only["neighbourhoods"] == {new_hood: moved["neighbourhoods"][new_hood]}
    with pytest.raises(SystemExit, match="moved no rows of Nowhere"):
        converter.write(
            tmp_path / "none", build_files, None, served, audit, {"Nowhere": new_hood}
        )
    assert not (tmp_path / "none").exists()
    # A rows file the catalog lists brings its own ads file.
    assert converter.pick_build(catalog, rows, None) == build_files
    # A rows file without `latest_ask` holds only the first asks.
    old = converter.pick_build(catalog, first, ads)
    assert old["catalog"] is None
    with pytest.raises(SystemExit, match="has no latest_ask column"):
        converter.write(tmp_path / "old", old, None, served, audit)
    assert not (tmp_path / "old").exists()


def test_port_diff(tmp_path, monkeypatch):
    """`port_diff.py` gives BEFORE the rules' fills, then counts the rows apart by field and by
    whether DATASET holds them."""
    port_diff = load("port_diff", OBSERVATIONS.with_name("port_diff.py"))
    data = port_diff.frontier()
    after = chain_records()
    before = [dict(r) for r in after[1:]]
    # A rule fills the first elevator BEFORE lacks, and BEFORE lacks a pet policy as well.
    filled = next(r for r in before if r["elevator"] is True)
    filled["elevator"] = None
    lacking = next(r for r in before if r["pet_policy"] is not None)
    lacking["pet_policy"] = None

    def fill(frame):
        frame = frame.copy()
        frame.loc[frame.audit_id == filled["audit_id"], "elevator"] = "yes"
        return frame

    monkeypatch.setitem(data.DATA_RULES, "fill-test", fill)
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    result = port_diff.compare(
        write_dataset(tmp_path / "before", before),
        write_dataset(tmp_path / "after", after),
        ["fill-test"],
        write_dataset(tmp_path / "within", [lacking]),
        0.0025,
    )
    assert result["matched"] == len(before)
    assert result["before_alone"] == {"rows": 0, "within": 0, "outside": 0}
    assert result["after_alone"] == {"rows": 1, "within": 0, "outside": 1}
    assert result["changed"] == {
        "rows": 2,
        "within": 1,
        "outside": 1,
        "share": 2 / len(after),
        "negligible": False,
    }
    pets = data.load(tmp_path / "after", cache_root=tmp_path / "cache").set_index(
        "audit_id"
    )["pets"][lacking["audit_id"]]
    assert result["fields"] == {
        "pets": {
            "rows": 1,
            "within": 1,
            "outside": 0,
            "pairs": [{"before": "unknown", "after": pets, "rows": 1, "within": 1}],
            "examples": [lacking["audit_id"]],
        }
    }


def test_port_diff_after_rules(tmp_path, monkeypatch):
    """With `after_rules`, `port_diff.py` runs those rules on AFTER too, and a row they bring
    into line with BEFORE counts as unchanged."""
    port_diff = load("port_diff", OBSERVATIONS.with_name("port_diff.py"))
    data = port_diff.frontier()
    after = chain_records()
    before = [dict(r) for r in after]
    lacking = next(r for r in before if r["pet_policy"] is not None)
    lacking["pet_policy"] = None

    def clear(frame):
        frame = frame.copy()
        frame.loc[frame.audit_id == lacking["audit_id"], "pets"] = "unknown"
        return frame

    monkeypatch.setitem(data.DATA_RULES, "clear-test", clear)
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    folders = (
        write_dataset(tmp_path / "before", before),
        write_dataset(tmp_path / "after", after),
    )
    alone = port_diff.compare(*folders, [], None, 0.0025)
    assert alone["changed"]["rows"] == 1
    assert list(alone["fields"]) == ["pets"]
    after = port_diff.compare(*folders, [], None, 0.0025, ["clear-test"])
    assert after["changed"]["rows"] == 0
    both = port_diff.compare(*folders, ["clear-test"], None, 0.0025, ["clear-test"])
    assert both["after"]["rules"] == ["clear-test"]
    assert both["changed"] == {"rows": 0, "share": 0.0, "negligible": True}
    assert both["fields"] == {}


def test_port_diff_load_in_chunks(tmp_path):
    """`port_diff.load` writes the loader's cache a few rows at a time, and the loader reads the
    same frame back as it builds in one go."""
    port_diff = load("port_diff", OBSERVATIONS.with_name("port_diff.py"))
    data = port_diff.frontier()
    records = chain_records()
    assert len(records) > 3
    folder = write_dataset(tmp_path / "rows", records)
    pd.testing.assert_frame_equal(
        port_diff.load(data, folder, tmp_path / "chunks", chunk=3),
        data.load(folder, cache_root=tmp_path / "whole"),
    )
