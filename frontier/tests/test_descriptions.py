"""Advertisement descriptions: the granular-crawl evidence file and sources."""

import json

import pandas as pd
import pytest
from rentfrontier import api_records, data, descriptions


def _granular(root):
    (root / "listing_observations").mkdir(parents=True)
    pd.DataFrame(
        {
            "listing_id": ["1", "1", "2", "3"],
            "collected_at": [1.0, 2.0, 1.0, 1.0],
            "snapshot_id": [1, 2, 3, 4],
            "raw_listing_json": [
                json.dumps({"description": "Old ad"}),
                json.dumps({"description": "Sunny one bedroom"}),
                json.dumps({"description": None}),
                json.dumps({"description": "Studio on Perry"}),
            ],
        }
    ).to_parquet(root / "listing_observations" / "part-00000.parquet")
    (root / "complete.json").write_text("{}")


def test_build_writes_each_rows_own_ad_as_last_captured(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "OUTPUT_ROOT", tmp_path / "out")
    _granular(tmp_path / "granular")
    cohort = tmp_path / "cohort"
    cohort.mkdir()
    rows = [("a", "1"), ("b", "2"), ("c", "3"), ("d", "9")]
    (cohort / "observations.jsonl").write_text(
        "".join(
            json.dumps({"audit_id": a, "source_listing_id": s}) + "\n" for a, s in rows
        )
    )
    out = descriptions.build(tmp_path / "granular", cohort, "wv", "abcdef0123")
    assert out.name.startswith("wv-") and out.name.endswith("-abcdef0")
    evidence = [
        json.loads(x) for x in (out / "evidence.jsonl").read_text().splitlines()
    ]
    assert {(e["audit_id"], e["description"]) for e in evidence} == {
        ("a", "Sunny one bedroom"),
        ("c", "Studio on Perry"),
    }
    assert {e["description_record"] for e in evidence} == {"latest"}
    provenance = json.loads((out / "provenance.json").read_text())
    assert (provenance["rows"], provenance["rows_with_description"]) == (4, 2)
    assert "last captured record" in provenance["rule"]

    frame = pd.DataFrame({"audit_id": ["a", "x"], "source_listing_id": ["1", "7"]})
    other = tmp_path / "other.jsonl"
    other.write_text(
        json.dumps({"audit_id": "x", "source_listing_id": "7", "description": "Loft"})
        + "\n"
    )
    token = descriptions.SOURCES.set((other, out / "evidence.jsonl"))
    try:
        assert descriptions.attach(frame).tolist() == ["sunny one bedroom", "loft"]
    finally:
        descriptions.SOURCES.reset(token)
    token = descriptions.SOURCES.set((out / "evidence.jsonl", out / "evidence.jsonl"))
    try:
        with pytest.raises(ValueError, match="overlap"):
            descriptions.attach(frame)
    finally:
        descriptions.SOURCES.reset(token)


def test_build_skips_another_datasets_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "OUTPUT_ROOT", tmp_path / "out")
    _granular(tmp_path / "granular")
    for name, rows in (("base", [("a", "1")]), ("extended", [("a", "1"), ("c", "3")])):
        (tmp_path / name).mkdir()
        (tmp_path / name / "observations.jsonl").write_text(
            "".join(
                json.dumps({"audit_id": a, "source_listing_id": s}) + "\n"
                for a, s in rows
            )
        )
    out = descriptions.build(
        tmp_path / "granular",
        tmp_path / "extended",
        "added",
        "abcdef0123",
        skip=tmp_path / "base",
    )
    evidence = [
        json.loads(x) for x in (out / "evidence.jsonl").read_text().splitlines()
    ]
    assert [e["audit_id"] for e in evidence] == ["c"]
    provenance = json.loads((out / "provenance.json").read_text())
    assert provenance["skipped_dataset"] == str(tmp_path / "base")


def test_only_listed_feature_sets_read_west_villages_ads(monkeypatch):
    from rentfrontier import features, run

    monkeypatch.setattr(run.data, "sha256", lambda path: "sha")
    assert set(run.feature_sources("nb-facing-v2")) >= {
        "descriptions",
        "descriptions_wv",
    }
    assert "descriptions_wv" not in run.feature_sources("nb-facing-v1")
    seen = {}

    def record(frame, train):
        seen["sources"] = descriptions.SOURCES.get()

    monkeypatch.setitem(features.FEATURE_SETS, "nb-facing-v2", record)
    features.build("nb-facing-v2", pd.DataFrame(), [])
    assert seen["sources"] == (descriptions.SOURCE, descriptions.WV_SOURCE)
    assert descriptions.SOURCES.get() == (descriptions.SOURCE,)


def test_build_reads_each_rows_ad_from_the_records_file(
    tmp_path, monkeypatch, records_catalog
):
    """With no ACTIVE record among them, the records file gives each row its
    listing's record fetched last, as the granular crawl does, and the build
    leaves out listings no row names."""
    monkeypatch.setattr(data, "OUTPUT_ROOT", tmp_path / "out")
    line = records_catalog(
        [
            {
                "listing_id": 1,
                "collected_at": 1.0,
                "last_collected_at": 5.0,
                "record": {"description": "Sunny one bedroom"},
            },
            {"listing_id": 1, "collected_at": 2.0, "record": {"description": "Old ad"}},
            {"listing_id": 2, "collected_at": 1.0, "record": {"description": None}},
            {"listing_id": 3, "collected_at": 1.0, "record": {"description": "Perry"}},
            {"listing_id": 4, "collected_at": 1.0, "record": {"description": "Other"}},
        ]
    )
    cohort = tmp_path / "cohort"
    cohort.mkdir()
    rows = [("a", "1"), ("b", "2"), ("c", "3"), ("d", "9")]
    (cohort / "observations.jsonl").write_text(
        "".join(
            json.dumps({"audit_id": a, "source_listing_id": s}) + "\n" for a, s in rows
        )
    )
    records = api_records.records_file()
    table = descriptions.record_descriptions(records, {"1", "2", "3"})
    assert table.description.to_dict() == {
        "1": "Sunny one bedroom",
        "2": None,
        "3": "Perry",
    }
    assert set(table.record) == {"latest"}
    out = descriptions.build(None, cohort, "api", "abcdef0123", records=records)
    evidence = [
        json.loads(x) for x in (out / "evidence.jsonl").read_text().splitlines()
    ]
    assert [
        (e["audit_id"], e["description"], e["description_record"]) for e in evidence
    ] == [("a", "Sunny one bedroom", "latest"), ("c", "Perry", "latest")]
    provenance = json.loads((out / "provenance.json").read_text())
    assert provenance["records"]["sha256"] == line["records"]["sha256"]
    assert provenance["granular"] is None
    assert provenance["rows_by_description_record"] == {"latest": 2}


def test_records_give_each_row_its_last_active_ad(
    tmp_path, monkeypatch, records_catalog
):
    """A listing with an ACTIVE record takes the text of its ACTIVE record fetched
    last, even where a closed record fetched later cut, changed or added text. A
    listing with none takes its record fetched last. Each evidence line names the
    record it read."""
    monkeypatch.setattr(data, "OUTPUT_ROOT", tmp_path / "out")

    def ad(listing, at, status, text):
        return {
            "listing_id": listing,
            "collected_at": at,
            "record": {"description": text, "status": status},
        }

    records_catalog(
        [
            ad(1, 1.0, "ACTIVE", "Sunny one bedroom"),
            ad(1, 5.0, "RENTED", "."),
            ad(2, 1.0, "ACTIVE", "First text"),
            ad(2, 3.0, "ACTIVE", "Second text"),
            ad(2, 4.0, "DELISTED", None),
            ad(3, 1.0, "DRAFT", "Draft"),
            ad(3, 2.0, "IN_CONTRACT", "In contract"),
            ad(4, 1.0, "ACTIVE", None),
            ad(4, 2.0, "DELISTED", "Added after"),
        ]
    )
    cohort = tmp_path / "cohort"
    cohort.mkdir()
    (cohort / "observations.jsonl").write_text(
        "".join(
            json.dumps({"audit_id": a, "source_listing_id": a}) + "\n"
            for a in ("1", "2", "3", "4")
        )
    )
    records = api_records.records_file()
    table = descriptions.record_descriptions(records, {"1", "2", "3", "4"})
    assert table.to_dict("index") == {
        "1": {"description": "Sunny one bedroom", "record": "last_active"},
        "2": {"description": "Second text", "record": "last_active"},
        "3": {"description": "In contract", "record": "latest"},
        "4": {"description": None, "record": "last_active"},
    }
    out = descriptions.build(None, cohort, "api", "abcdef0123", records=records)
    evidence = [
        json.loads(x) for x in (out / "evidence.jsonl").read_text().splitlines()
    ]
    assert [
        (e["audit_id"], e["description"], e["description_record"]) for e in evidence
    ] == [
        ("1", "Sunny one bedroom", "last_active"),
        ("2", "Second text", "last_active"),
        ("3", "In contract", "latest"),
    ]
    provenance = json.loads((out / "provenance.json").read_text())
    assert provenance["rows_by_description_record"] == {"last_active": 2, "latest": 1}
    assert "ACTIVE record fetched last" in provenance["rule"]


def test_main_takes_a_granular_crawl_or_the_records_file(monkeypatch, records_catalog):
    from rentfrontier import run

    line = records_catalog(
        [{"listing_id": 1, "collected_at": 1.0, "record": {"description": "x"}}]
    )
    seen = []
    monkeypatch.setattr(run, "git", lambda *a: "" if a[0] == "status" else "abc")
    monkeypatch.setattr(descriptions, "build", lambda *a: seen.append(a) or "out")
    descriptions.main(["--records", "--dataset", "/d", "--name", "n"])
    assert seen[-1][0] is None and seen[-1][5]["sha256"] == line["records"]["sha256"]
    descriptions.main(["--granular", "/g", "--dataset", "/d", "--name", "n"])
    assert str(seen[-1][0]) == "/g" and seen[-1][5] is None
    with pytest.raises(SystemExit):
        descriptions.main(
            ["--records", "--granular", "/g", "--dataset", "/d", "--name", "n"]
        )
