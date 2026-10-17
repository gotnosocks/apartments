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
    provenance = json.loads((out / "provenance.json").read_text())
    assert (provenance["rows"], provenance["rows_with_description"]) == (4, 2)

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
    """The records file gives each row its listing's record fetched last, as the
    granular crawl does, and the build leaves out listings no row names."""
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
    assert descriptions.record_descriptions(records, {"1", "2", "3"}).to_dict() == {
        "1": "Sunny one bedroom",
        "2": None,
        "3": "Perry",
    }
    out = descriptions.build(None, cohort, "api", "abcdef0123", records=records)
    evidence = [
        json.loads(x) for x in (out / "evidence.jsonl").read_text().splitlines()
    ]
    assert [(e["audit_id"], e["description"]) for e in evidence] == [
        ("a", "Sunny one bedroom"),
        ("c", "Perry"),
    ]
    provenance = json.loads((out / "provenance.json").read_text())
    assert provenance["records"]["sha256"] == line["records"]["sha256"]
    assert provenance["granular"] is None


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
