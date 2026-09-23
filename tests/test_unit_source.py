import gzip

import pytest

from apartments.unit_source import SourceEvidence, extract, unit_page
from .test_review_service import service


def test_canonical_unit_url_extraction_is_explicit_and_bounded(tmp_path):
    path = tmp_path / "page.gz"
    with gzip.open(path, "wt") as stream:
        stream.write(
            '<html><head><link href="/building/a/4c" rel="canonical"></head><body>unitId=unrelated</body>'
        )
    assert extract(path, "https://streeteasy.com/rental/1") == (
        "https://streeteasy.com/building/a/4c",
        None,
    )
    with gzip.open(path, "wt") as stream:
        stream.write(
            '<head><link rel="canonical" href="/building/a/4c"><link rel="canonical" href="/building/a/5c"></head>'
        )
    assert extract(path, "https://streeteasy.com/rental/1")[0] is None
    assert unit_page("https://[invalid") is None
    assert unit_page("https://streeteasy.com/rental/1") is None
    assert unit_page("https://other.com/building/a/4c") is None
    assert unit_page("https://streeteasy.com@other.com/building/a/4c") is None
    assert unit_page("https://streeteasy.com/building/a/4c?unit=5c") is None
    assert (
        unit_page("http://www.streeteasy.com/building/a/4c/")
        == "https://streeteasy.com/building/a/4c"
    )


def evidence():
    source = SourceEvidence.__new__(SourceEvidence)
    source.digest = "fixture"
    source.error = None
    source.pages = {
        sid: {"canonical_url": "https://streeteasy.com/building/a/4c"} for sid in [1, 2]
    }
    source.latest = {1: "2", 2: "2"}
    source.history = {1: {"1", "2"}, 2: {"1", "2"}}
    return source


def test_shared_latest_allows_missing_canonical_and_incomplete_history():
    source = evidence()
    catalog = {
        lid: {
            "captures": [
                {"snapshot_id": int(lid), "building_slug": "a", "unit_label": "#4C"}
            ]
        }
        for lid in ["1", "2"]
    }
    members = {"https://streeteasy.com/building/a/4c": {"1", "2"}}
    history = {"1": {"1", "2"}, "2": {"1", "2"}}

    def check(**kwargs):
        return source.assess(
            ["1", "2"],
            catalog,
            members,
            kwargs.get("history", history),
            kwargs.get("corrected", set()),
            kwargs.get("reserved", set()),
        )

    assert check()["eligible"]
    source.history[2] = {"2"}
    assert check()["eligible"]
    assert any("history" in note.lower() for note in check()["notes"])
    source.history[2] = {"1", "2"}
    assert check(history={**history, "1": {"1", "2", "9"}})["eligible"]
    assert not check(corrected={1})["eligible"]
    assert not check(reserved={"1"})["eligible"]
    source.latest[1] = "3"
    assert not check()["eligible"]
    source.latest[1] = "2"
    source.pages[1]["canonical_url"] = None
    assert check()["eligible"]
    source.pages[1]["canonical_url"] = "https://streeteasy.com/building/a/4c"
    members["https://streeteasy.com/building/a/4c"].add("9")
    assert check()["eligible"]


def test_generic_canonical_page_cannot_automatically_establish_a_home():
    source = evidence()
    for row in source.pages.values():
        row["canonical_url"] = "https://streeteasy.com/building/a/studio"
    catalog = {
        lid: {
            "captures": [
                {"snapshot_id": int(lid), "building_slug": "a", "unit_label": "Studio"}
            ]
        }
        for lid in ["1", "2"]
    }
    result = source.assess(
        ["1", "2"],
        catalog,
        {"https://streeteasy.com/building/a/studio": {"1", "2"}},
        {"1": {"1", "2"}, "2": {"1", "2"}},
        set(),
        set(),
    )
    assert not result["eligible"] and any(
        "generic" in reason for reason in result["reasons"]
    )


def test_backfill_is_bound_to_the_exact_dataset_snapshots(service):
    import pyarrow as pa
    import pyarrow.parquet as pq
    from apartments.unit_source import VERSION, fingerprint, snapshot_rows

    root = service.root / "snapshots"
    root.mkdir()
    pq.write_table(
        pa.Table.from_pylist(
            [
                {"snapshot_id": 1, "body_hash": "a" * 64},
                {"snapshot_id": 2, "body_hash": "b" * 64},
            ]
        ),
        root / "part.parquet",
    )
    expected = snapshot_rows(service.root)
    rows = [
        {
            "snapshot_id": sid,
            "url": url,
            "body_hash": digest,
            "canonical_url": "https://streeteasy.com/building/a/4c",
            "error": None,
        }
        for sid, url, digest in expected
    ]
    metadata = {
        b"version": VERSION.encode(),
        b"dataset": service.dataset.encode(),
        b"snapshots": fingerprint(expected).encode(),
    }
    path = service.state / "unit-source-pages.parquet"
    table = pa.Table.from_pylist(rows).replace_schema_metadata(metadata)
    pq.write_table(table, path)
    assert len(SourceEvidence(service).pages) == 2
    pq.write_table(
        table.replace_schema_metadata({**metadata, b"dataset": b"wrong-dataset"}), path
    )
    with pytest.raises(ValueError, match="does not match"):
        SourceEvidence(service)
    rows[1]["body_hash"] = "c" * 64
    pq.write_table(pa.Table.from_pylist(rows).replace_schema_metadata(metadata), path)
    with pytest.raises(ValueError, match="does not match"):
        SourceEvidence(service)


def test_shared_latest_label_conflict_is_checked_across_the_entire_reference():
    source = evidence()
    source.latest[3] = "2"
    catalog = {
        lid: {
            "captures": [
                {
                    "snapshot_id": int(lid),
                    "building_slug": "a",
                    "unit_label": "4C" if lid != "3" else "4D",
                }
            ]
        }
        for lid in ["1", "2", "3"]
    }
    result = source.assess(["1", "2"], catalog, {}, {}, set(), set())
    assert not result["eligible"]
    assert result["latest_label_conflicts"][0]["latest_listing_id"] == "2"
    assert result["latest_label_conflicts"][0]["labels"] == [["a", "4C"], ["a", "4D"]]
