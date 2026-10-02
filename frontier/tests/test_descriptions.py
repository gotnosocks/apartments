"""Advertisement descriptions: the granular-crawl evidence file and sources."""

import json

import pandas as pd
import pytest
from rentfrontier import data, descriptions


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


def test_sets_built_on_a_multi_source_set_read_the_same_sources():
    from rentfrontier import features

    def bases(name):
        while True:
            fn = features.FEATURE_SETS[name]
            name = getattr(fn, "keywords", {}).get("base")
            if name is None:
                return
            yield name

    for name in features.FEATURE_SETS:
        for base in bases(name):
            if base in features.DESCRIPTION_SOURCES:
                assert features.description_files(name) == (
                    features.description_files(base)
                ), name
