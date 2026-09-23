import gzip
import json
import sqlite3
import pyarrow.parquet as pq
from apartments.granular_export import prepare, process_shard


def create_repeated_listing_export(tmp_path):
    db = tmp_path / "archive.sqlite3"
    c = sqlite3.connect(db)
    c.executescript("""CREATE TABLE snapshots(id INTEGER,generation INTEGER,url TEXT,body_hash TEXT,observed REAL,extraction_version INTEGER,extracted TEXT);
 CREATE TABLE scope_urls(generation INTEGER,url TEXT);
 CREATE TABLE frontier(generation INTEGER,url TEXT,kind TEXT,state TEXT,attempts INTEGER);
 CREATE TABLE observations(id INTEGER,generation INTEGER,url TEXT,fetched REAL,status INTEGER,content_type TEXT,headers TEXT,body_hash TEXT,not_modified INTEGER,error TEXT);
 CREATE TABLE url_aliases(generation INTEGER,url TEXT,target_url TEXT,reason TEXT,created REAL);""")
    url = "https://streeteasy.com/rental/123"
    c.execute("INSERT INTO scope_urls VALUES(1,?)", (url,))
    c.execute("INSERT INTO frontier VALUES(1,?,'listing','done',1)", (url,))
    listing = {
        "id": 123,
        "propertyDetails": {"address": {"displayUnit": "04C"}, "bedroomCount": 1},
        "propertyHistory": [
            {
                "listingId": 123,
                "rentalEventsOfInterest": [
                    {"date": "2020-01-01", "price": 3000},
                    {"date": "2020-01-01", "price": 3000},
                ],
            }
        ],
    }
    listing["pricing"] = {
        "priceChanges": [{"changedAt": "2020-01-01T12:34:56Z", "price": 3000}]
    }
    listing["statusChanges"] = [
        {"changedAt": "2020-01-02T01:00:00Z", "status": "RENTED"}
    ]
    body = (
        '<html><head><link rel="canonical" href="https://streeteasy.com/building/demo/04c"></head><body><script type="application/json">'
        + json.dumps({"listing": listing})
        + "</script>"
    ).encode()
    for i, h in enumerate(["aa111", "bb222"], 1):
        dest = tmp_path / "bodies" / h[:2]
        dest.mkdir(parents=True)
        (dest / f"{h}.gz").write_bytes(gzip.compress(body))
        c.execute(
            "INSERT INTO snapshots VALUES(?,1,?,?,?,5,?)", (i, url, h, 1000 + i, "{}")
        )
    for i, (status, h) in enumerate(
        [(200, "aa111"), (304, "aa111"), (200, "bb222"), (403, None)], 1
    ):
        c.execute(
            "INSERT INTO observations VALUES(?,1,?,?,?, ?,?,?,?,?)",
            (
                i,
                url,
                1000 + i,
                status,
                "text/html",
                "{}",
                h,
                status == 304,
                "blocked" if status == 403 else None,
            ),
        )
    c.commit()
    c.close()
    ledger = tmp_path / "edits.jsonl"
    ledger.write_text("")
    root = tmp_path / "out"
    plan = prepare(db, root, ledger, chunk_size=1)
    assert plan["metadata_counts"]["fetch_observations"] == 4
    for part in range(plan["shards"]):
        first = process_shard(db, root, part, tmp_path / "bodies")
        assert process_shard(db, root, part, tmp_path / "bodies") == first
    return db, root, ledger, plan


def test_preserves_fetches_snapshots_and_repeated_events(tmp_path):
    db, root, ledger, plan = create_repeated_listing_export(tmp_path)
    observations = pq.read_table(root / "listing_observations").to_pylist()
    assert len(observations) == 2
    assert all(
        r["canonical_unit_url"] == "https://streeteasy.com/building/demo/04c"
        for r in observations
    )
    assert all(
        r["canonical_href"] == "https://streeteasy.com/building/demo/04c"
        and r["canonical_unit_error"] is None
        for r in observations
    )
    from apartments.review_service import ReviewService
    from apartments.unit_source import SourceEvidence

    (root / "complete.json").write_text("{}")
    service = ReviewService(root, tmp_path / "review-state")
    evidence = SourceEvidence(service)
    assert len(evidence.pages) == 2 and evidence.error is None
    assert (
        evidence.pages[1]["canonical_url"] == "https://streeteasy.com/building/demo/04c"
    )
    assert not (service.state / "unit-source-pages.parquet").exists()
    service.close()
    events = pq.read_table(root / "event_mentions").to_pylist()
    assert len(events) == 4
    changes = pq.read_table(root / "source_changes").to_pylist()
    assert len(changes) == 4
    assert {r["source_path"] for r in changes} == {
        "pricing.priceChanges",
        "statusChanges",
    }
    assert all(r["source_timestamp"] for r in changes)
    assert {r["event_index"] for r in events} == {0, 1}
    assert {r["snapshot_id"] for r in events} == {1, 2}
    assert len(set(r["event_key"] for r in events)) == 1
    assert prepare(db, root, ledger, chunk_size=1) == plan

    # A checkpoint alone cannot conceal a missing Parquet part.
    (root / "event_mentions" / "part-00000.parquet").unlink()
    process_shard(db, root, 0, tmp_path / "bodies")
    assert pq.read_table(root / "event_mentions").num_rows == 4


def test_transform_filters_non_unit_rentals_and_reconciles_exclusions(tmp_path):
    import pytest
    from apartments.granular_quality import audit_dataset
    from apartments.granular_report import render_report

    db = tmp_path / "archive.sqlite3"
    c = sqlite3.connect(db)
    c.executescript("""CREATE TABLE snapshots(id INTEGER,generation INTEGER,url TEXT,body_hash TEXT,observed REAL,extraction_version INTEGER,extracted TEXT);
 CREATE TABLE scope_urls(generation INTEGER,url TEXT);
 CREATE TABLE frontier(generation INTEGER,url TEXT,kind TEXT,state TEXT,attempts INTEGER);
 CREATE TABLE observations(id INTEGER,generation INTEGER,url TEXT,fetched REAL,status INTEGER,content_type TEXT,headers TEXT,body_hash TEXT,not_modified INTEGER,error TEXT);
 CREATE TABLE url_aliases(generation INTEGER,url TEXT,target_url TEXT,reason TEXT,created REAL);""")
    # A retained old listing; recent unsupported links; missing, conflicting and
    # incomplete heads; a sale; and a valid canonical page with a parse failure.
    heads = {
        1: '<link rel="canonical" href="/building/demo/1a">',
        2: '<link rel="canonical" href="/rental/2">',
        3: "",
        4: '<link rel="canonical" href="/building/demo">',
        5: '<link rel="canonical" href="https://other.example/building/demo/1a">',
        6: '<link rel="canonical" href="/building/demo/1a"><link rel="canonical" href="/building/demo/2a">',
        7: '<link rel="canonical" href="/building/demo/1a">',
        8: '<link rel="canonical" href="/sale/8">',
        9: '<link rel="canonical" href="/building/demo/9a">',
        10: '<link rel="canonical" href="/building/demo/10a">',
    }
    for sid, head in heads.items():
        kind = "sale" if sid == 8 else "rental"
        url = f"https://streeteasy.com/{kind}/{sid}"
        h = f"{sid:064x}"
        listing = {
            "id": sid,
            "createdAt": "2006-01-01" if sid == 1 else "2026-01-01",
            "propertyDetails": {},
            "pricing": {
                "price": 3000,
                "priceChanges": [{"changedAt": "2026-01-01", "price": 3000}],
            },
            "statusChanges": [{"changedAt": "2026-01-02", "status": "RENTED"}],
            "propertyHistory": [
                {
                    "listingId": sid,
                    "rentalEventsOfInterest": [{"date": "2026-01-01", "price": 3000}],
                }
            ],
        }
        if sid == 1:
            listing["propertyHistory"].append(
                {
                    "listingId": 2,
                    "rentalEventsOfInterest": [{"date": "2026-01-01", "price": 3000}],
                }
            )
        if sid == 9:
            listing = {}  # Canonical unit exists even though the listing failed to parse.
        if sid == 10:
            listing["propertyDetails"] = [
                "malformed"
            ]  # Unexpected parser exception also retains canonical evidence.
        body = (
            "<html><head>"
            + head
            + ("" if sid == 7 else "</head><body>")
            + '<script type="application/json">'
            + json.dumps({"listing": listing})
            + "</script>"
        ).encode()
        dest = tmp_path / "bodies" / h[:2]
        dest.mkdir(parents=True, exist_ok=True)
        (dest / f"{h}.gz").write_bytes(gzip.compress(body))
        c.execute("INSERT INTO scope_urls VALUES(1,?)", (url,))
        c.execute("INSERT INTO frontier VALUES(1,?,'listing','done',1)", (url,))
        c.execute(
            "INSERT INTO snapshots VALUES(?,1,?,?,?,5,?)",
            (sid, url, h, 1000 + sid, "{}"),
        )
    c.commit()
    c.close()
    ledger = tmp_path / "edits.jsonl"
    ledger.write_text("")
    root = tmp_path / "out"
    plan = prepare(db, root, ledger, chunk_size=20)
    assert plan["listing_filter"] == "rental-canonical-unit-v1"
    result = process_shard(db, root, 0, tmp_path / "bodies")
    assert process_shard(db, root, 0, tmp_path / "bodies") == result
    kept = pq.read_table(root / "listing_observations").to_pylist()
    assert {r["snapshot_id"] for r in kept} == {1, 8, 9, 10}
    assert all(r["canonical_unit_url"] for r in kept if r["listing_type"] == "rental")
    exclusions = pq.read_table(root / "listing_exclusions").to_pylist()
    assert {r["snapshot_id"] for r in exclusions} == set(range(2, 8))
    assert all(
        r["reason"] == "rental_missing_canonical_unit_page"
        and r["canonical_unit_error"]
        for r in exclusions
    )
    assert result["counts"]["listing_exclusions"] == 6
    events = pq.read_table(root / "event_mentions").to_pylist()
    assert {r["snapshot_id"] for r in events} == {1, 8}
    assert any(r["snapshot_id"] == 1 and r["event_listing_id"] == "2" for r in events)
    assert {
        r["snapshot_id"] for r in pq.read_table(root / "source_changes").to_pylist()
    } == {1, 8}
    assert pq.read_table(root / "snapshots").num_rows == 10
    report = audit_dataset(root)
    assert report["coverage"]["listing"] == {
        "expected_snapshots": 10,
        "observed_snapshots": 4,
        "intentionally_excluded": 6,
        "expected_unobserved": 0,
    }
    assert not any(report["referential_checks"].values())
    assert report["listing_exclusions"]["by_reason"] == {
        "rental_missing_canonical_unit_page": 6
    }
    assert "Intentional listing exclusions" in render_report(report)
    assert "Unexplained missing" in render_report(report)
    # A missing exclusion part cannot be hidden by the checkpoint.
    (root / "listing_exclusions" / "part-00000.parquet").unlink()
    assert (
        process_shard(db, root, 0, tmp_path / "bodies")["counts"]["listing_exclusions"]
        == 6
    )
    # Existing runs cannot resume under a new filtering rule.
    old_plan = {k: v for k, v in plan.items() if k != "listing_filter"}
    (root / "plan.json").write_text(json.dumps(old_plan))
    with pytest.raises(ValueError, match="listing_filter.*new output ID"):
        prepare(db, root, ledger, chunk_size=20)

    # A shard containing only excluded captures still writes valid empty data tables.
    excluded_root = tmp_path / "excluded-only"
    prepare(db, excluded_root, ledger, chunk_size=1)
    only = process_shard(db, excluded_root, 1, tmp_path / "bodies")
    assert (
        only["counts"]["listing_observations"]
        == only["counts"]["event_mentions"]
        == only["counts"]["source_changes"]
        == 0
    )
    assert pq.read_table(excluded_root / "listing_exclusions").num_rows == 1
    partial_report = audit_dataset(excluded_root)
    assert partial_report["coverage"]["listing"] == {
        "expected_snapshots": 10,
        "observed_snapshots": 0,
        "intentionally_excluded": 1,
        "expected_unobserved": 9,
    }


def test_galleries_are_separate_even_with_legacy_kind_and_history_payload(
    tmp_path, monkeypatch
):
    from apartments import granular_parse
    from apartments.granular_quality import audit_dataset
    from apartments.granular_report import render_report
    from .test_granular_media import gallery, gallery_body

    db = tmp_path / "archive.sqlite3"
    c = sqlite3.connect(db)
    c.executescript("""CREATE TABLE snapshots(id INTEGER,generation INTEGER,url TEXT,body_hash TEXT,observed REAL,extraction_version INTEGER,extracted TEXT);
 CREATE TABLE scope_urls(generation INTEGER,url TEXT);
 CREATE TABLE frontier(generation INTEGER,url TEXT,kind TEXT,state TEXT,attempts INTEGER);
 CREATE TABLE observations(id INTEGER,generation INTEGER,url TEXT,fetched REAL,status INTEGER,content_type TEXT,headers TEXT,body_hash TEXT,not_modified INTEGER,error TEXT);
 CREATE TABLE url_aliases(generation INTEGER,url TEXT,target_url TEXT,reason TEXT,created REAL);""")
    originals = {1: "listing", 2: "building", 3: None, 4: "media_gallery"}
    for sid, kind in originals.items():
        listing = gallery(sid)
        listing["propertyHistory"] = [
            {
                "listingId": sid,
                "saleEventsOfInterest": [{"date": "2026-01-01", "price": 900000}],
            }
        ]
        listing["pricing"] = {
            "priceChanges": [{"changedAt": "2026-01-01", "price": 900000}]
        }
        listing["statusChanges"] = [{"changedAt": "2026-01-01", "status": "ACTIVE"}]
        url = f"https://streeteasy.com/{'rental' if sid == 2 else 'sale'}/{sid}" + (
            "/media_gallery" if sid > 1 else ""
        )
        h = f"{sid:064x}"
        if sid != 4:
            path = tmp_path / "bodies" / h[:2] / (h + ".gz")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(gzip.compress(gallery_body(listing)))
        c.execute("INSERT INTO scope_urls VALUES(1,?)", (url,))
        c.execute("INSERT INTO frontier VALUES(1,?,?,'done',1)", (url, kind))
        c.execute(
            "INSERT INTO snapshots VALUES(?,1,?,?,?,5,?)",
            (sid, url, h, 1000 + sid, "{}"),
        )
    c.commit()
    c.close()
    ledger = tmp_path / "edits.jsonl"
    ledger.write_text("")
    root = tmp_path / "out"
    plan = prepare(db, root, ledger)
    assert plan["page_classification"] == "media-gallery-v1"
    snapshots = pq.read_table(root / "snapshots").to_pylist()
    assert {r["snapshot_id"]: r["kind"] for r in snapshots} == originals
    assert [r["page_type"] for r in snapshots] == [
        "listing",
        "media_gallery",
        "media_gallery",
        "media_gallery",
    ]
    parsed = []
    original = granular_parse.parse_listing

    def tracking_parser(body, url):
        parsed.append(url)
        return original(body, url)

    monkeypatch.setattr(granular_parse, "parse_listing", tracking_parser)
    result = process_shard(db, root, 0, tmp_path / "bodies")
    assert parsed == ["https://streeteasy.com/sale/1"]
    assert pq.read_table(root / "listing_observations").num_rows == 1
    assert pq.read_table(root / "listing_exclusions").num_rows == 0
    for table in ("event_mentions", "source_changes"):
        assert {r["snapshot_id"] for r in pq.read_table(root / table).to_pylist()} == {
            1
        }
    media = pq.read_table(root / "media_gallery_observations").to_pylist()
    assert [r["parse_status"] for r in media] == ["ok", "ok", "error"]
    assert all(json.loads(r["media_json"])["photos"] for r in media[:2])
    assert (
        result["errors"][0]["snapshot_id"] == 4
        and result["errors"][0]["page_type"] == "media_gallery"
    )
    report = audit_dataset(root)
    assert report["coverage"]["listing"]["expected_snapshots"] == 1
    assert report["coverage"]["media_gallery"] == {
        "expected_snapshots": 3,
        "observed_snapshots": 3,
        "expected_unobserved": 0,
    }
    assert report["parse_failures"]["listing_observations"]["error_rows"] == 0
    assert report["media_gallery_observations"]["error_rows"] == 1
    assert not any(report["referential_checks"].values())
    assert "Gallery parse errors | 1" in render_report(report)
    assert process_shard(db, root, 0, tmp_path / "bodies") == result
