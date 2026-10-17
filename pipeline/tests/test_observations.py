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
    pipeline's latest asks and the pet policies of `PET_FEE_ADS`."""
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
        if (
            row["source_listing_id"] in helpers.PET_FEE_ADS
            and row["pet_policy"] is None
        ):
            row["pet_policy"] = "allowed_restrictions_unknown"
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
    theirs = data.load(chain, cache_root=tmp_path / "cache")
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
    # A rows file the catalog lists brings its own ads file.
    assert converter.pick_build(catalog, rows, None) == build_files
    # A rows file without `latest_ask` holds only the first asks.
    old = converter.pick_build(catalog, first, ads)
    assert old["catalog"] is None
    with pytest.raises(SystemExit, match="has no latest_ask column"):
        converter.write(tmp_path / "old", old, None, served, audit)
    assert not (tmp_path / "old").exists()
