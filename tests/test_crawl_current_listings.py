import gzip
import hashlib
import json
import sqlite3

from apartments import crawl_current_listings as ccl


def test_rows_are_dated_by_page_capture_and_failures_kept(tmp_path, monkeypatch):
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    (dataset / "complete.json").write_text("{}")
    crawl = tmp_path / "crawl"
    (crawl / "bodies").mkdir(parents=True)
    (crawl / "bodies" / "a").write_bytes(gzip.compress(b"<html>unit a</html>"))
    (crawl / "bodies" / "b").write_bytes(b"<html>unit b</html>")
    ha = hashlib.sha256(b"<html>unit a</html>").hexdigest()
    hb = hashlib.sha256(b"<html>unit b</html>").hexdigest()
    snapshot = tmp_path / "archive.sqlite3"
    db = sqlite3.connect(snapshot)
    db.execute(
        "create table bodies(hash text primary key, path text, size int, created real)"
    )
    db.executemany(
        "insert into bodies values (?, ?, 0, 0)",
        [(ha, "bodies/a"), (hb, "bodies/b"), ("0" * 64, "bodies/b")],
    )
    db.commit()
    db.close()
    unit = "https://streeteasy.com/building/example/1a"
    ads = [
        ("101", unit, unit, 1, ha, 1791440623.0),
        ("102", unit.replace("1a", "2b"), None, 2, hb, 1791440700.0),
        # A saved body that no longer matches its hash is a failure, not a row.
        ("103", unit, unit, 3, "0" * 64, 1791440800.0),
    ]
    monkeypatch.setattr(ccl, "active_ads", lambda d: ads)
    seen = {}

    def interpret(target, observation, body, plan_hash, *, interpreted_at):
        seen[target["source_listing_id"]] = (body, interpreted_at)
        if observation["error"]:
            return {**target, "status": "failed", "reason": observation["error"]}
        candidate = {
            "source_listing_id": target["source_listing_id"],
            "collected_at": interpreted_at,
            "known_at": interpreted_at,
        }
        return {"status": "parsed", "candidate": candidate}

    monkeypatch.setattr(ccl.refresh, "interpret", interpret)
    report = ccl.build(dataset, snapshot, crawl, tmp_path / "out")
    assert (
        seen["101"][0] == b"<html>unit a</html>"
        and seen["102"][0] == b"<html>unit b</html>"
    )
    # Dated by the page's capture time, never by when the conversion ran.
    assert seen["101"][1].startswith("2026-10-08T06:23:43")
    out = tmp_path / "out" / "details" / "snapshot"
    rows = [
        json.loads(line) for line in (out / "candidates.jsonl").read_text().splitlines()
    ]
    assert [r["source_listing_id"] for r in rows] == ["101"]
    assert rows[0]["crawl_provenance"]["snapshot_id"] == 1
    failures = [
        json.loads(line) for line in (out / "failures.jsonl").read_text().splitlines()
    ]
    assert failures == [
        {"source_listing_id": "102", "url": ads[1][1], "reason": "no canonical unit"},
        {
            "source_listing_id": "103",
            "url": unit,
            "reason": "saved body missing or hash mismatch",
        },
    ]
    assert report["candidates"] == 1 and report["failures"] == 2
    assert (out / "complete.json").exists()
