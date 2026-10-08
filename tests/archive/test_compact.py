import hashlib
import json
import sqlite3

import pyarrow.parquet as pq
import pytest

from apartments.granular_export import prepare, process_shard
from streeteasy_archive.collection_audit import audit
from streeteasy_archive.collection_policy import setup
from streeteasy_archive.compact import compact_database, main
from streeteasy_archive.extract import extract
from streeteasy_archive.listing_identity import capture_evidence
from streeteasy_archive.store import ArchiveStore

UNIT = "https://streeteasy.com/building/example/4c"
URL = "https://streeteasy.com/rental/123"
OTHER = "https://streeteasy.com/rental/456"


def page(listing_id):
    listing = {
        "id": listing_id,
        "propertyDetails": {"address": {"displayUnit": "4C"}, "bedroomCount": 1},
        "propertyHistory": [
            {
                "listingId": listing_id,
                "rentalEventsOfInterest": [{"date": "2020-01-01", "price": 3000}],
            }
        ],
    }
    return (
        '<head><link rel="canonical" href="'
        + UNIT
        + '"></head><body><script type="application/json">'
        + json.dumps({"listing": listing})
        + "</script></body>"
    ).encode()


def provider(raw, content=None):
    """The envelope the Oxylabs downloader puts in response.meta['archive_provider']."""
    return {
        "provider": "oxylabs",
        "target_url": URL,
        "results": [
            {
                "content": raw.decode() if content is None else content,
                "status_code": 200,
                "_response": {"headers": {"Content-Type": "text/html"}},
            }
        ],
    }


def crawl(root):
    """A crawl as the Oxylabs runtime records it: provider HTML inside extracted."""
    s = ArchiveStore(root)
    g = s.new_generation()
    setup(s, g)
    raw = page("123")
    data = extract(raw, URL, "text/html")
    data["provider_capture"] = provider(raw)
    s.record(g, URL, 200, {}, raw, "text/html", data)
    other = page("456")
    data = extract(other, OTHER, "text/html")
    # A provider body that is not the stored body is kept as it is.
    data["provider_capture"] = provider(other, content="<html>different</html>")
    s.record(g, OTHER, 200, {}, other, "text/html", data)
    s.record_gap(g, URL, 503, {}, "blocked", body=b"blocked")
    with s._tx():
        s.db.execute(
            "INSERT INTO collection_memberships VALUES(?,?,?,?,?,?)",
            (g, "rental:123:detail", UNIT, UNIT, "proof", 0),
        )
        for url in (URL, OTHER):
            s.db.execute(
                "INSERT OR IGNORE INTO scope_urls VALUES(?,?,'test')", (g, url)
            )
            s.db.execute(
                "INSERT OR REPLACE INTO frontier(generation,url,kind,state)"
                " VALUES(?,?,'listing','done')",
                (g, url),
            )
    s.close()


def compacted(tmp_path, **kw):
    source = tmp_path / "crawl"
    crawl(source)
    out = tmp_path / "compact"
    out.mkdir()
    report = compact_database(
        source / "archive.sqlite3", out / "archive.sqlite3", source, **kw
    )
    (out / "bodies").symlink_to(source / "bodies")
    return source, out, report


def rows(path, sql):
    db = sqlite3.connect(path)
    try:
        return db.execute(sql).fetchall()
    finally:
        db.close()


def test_strips_only_provider_html_that_matches_a_stored_body(tmp_path):
    source, out, report = compacted(tmp_path)
    assert report["snapshots"] == {"stripped": 1, "content_differs_from_body": 1}
    assert report["json_bytes_removed"] > len(page("123")) // 2
    before = dict(
        rows(source / "archive.sqlite3", "SELECT id, extracted FROM snapshots")
    )
    after = dict(rows(out / "archive.sqlite3", "SELECT id, extracted FROM snapshots"))
    assert before.keys() == after.keys()
    changed = [i for i in before if before[i] != after[i]]
    assert len(changed) == 1
    old, new = json.loads(before[changed[0]]), json.loads(after[changed[0]])
    result = old["provider_capture"]["results"][0]
    digest = hashlib.sha256(result.pop("content").encode()).hexdigest()
    result["content_sha256"] = digest
    assert new == old
    body = rows(
        source / "archive.sqlite3",
        f"SELECT body_hash FROM snapshots WHERE id={changed[0]}",
    )[0][0]
    assert digest == body


def test_every_other_table_and_the_schema_are_copied_exactly(tmp_path):
    source, out, _ = compacted(tmp_path)
    a, b = source / "archive.sqlite3", out / "archive.sqlite3"
    schema = "SELECT type, name, sql FROM sqlite_master ORDER BY name"
    assert rows(a, schema) == rows(b, schema)
    for (name,) in rows(a, "SELECT name FROM sqlite_master WHERE type='table'"):
        cols = (
            "*" if name != "snapshots" else "id, generation, url, body_hash, observed"
        )
        sql = f'SELECT rowid, {cols} FROM "{name}" ORDER BY rowid'
        assert rows(a, sql) == rows(b, sql), name
    assert rows(b, "PRAGMA journal_mode") == [("delete",)]


def test_readers_give_the_same_answers_on_the_compacted_copy(tmp_path):
    source, out, _ = compacted(tmp_path)
    assert audit(out) == audit(source)
    for root in (source, out):
        (root / "edits.jsonl").write_text("")
    exports = []
    for root in (source, out):
        target = tmp_path / ("export-" + root.name)
        plan = prepare(root / "archive.sqlite3", target, root / "edits.jsonl", 1)
        for part in range(plan["shards"]):
            process_shard(root / "archive.sqlite3", target, part, root / "bodies")
        exports.append(
            {
                # parsed_at is the wall clock of the parse, so it always differs.
                name: [
                    {k: v for k, v in r.items() if k != "parsed_at"}
                    for r in pq.read_table(target / name).to_pylist()
                ]
                for name in ("listing_observations", "event_mentions", "snapshots")
            }
        )
    assert exports[0] == exports[1]
    assert exports[0]["listing_observations"]
    sql = "SELECT url, extracted FROM snapshots ORDER BY id"
    for (url, a), (_, b) in zip(
        rows(source / "archive.sqlite3", sql), rows(out / "archive.sqlite3", sql)
    ):
        assert capture_evidence(json.loads(a), url) == capture_evidence(
            json.loads(b), url
        )
    # The HTML stays readable from the body file, and a re-crawl can open the copy.
    store = ArchiveStore(out)
    first = rows(out / "archive.sqlite3", "SELECT body_hash FROM snapshots ORDER BY id")
    assert store.get_body(first[0][0]) == page("123")
    store.close()


def test_missing_or_corrupt_body_keeps_the_provider_html(tmp_path):
    source = tmp_path / "crawl"
    crawl(source)
    for path in (source / "bodies").rglob("*.gz"):
        path.write_bytes(b"not gzip of the page")
    report = compact_database(
        source / "archive.sqlite3", tmp_path / "x.sqlite3", source
    )
    assert report["snapshots"]["body_unavailable"] == 1
    report = compact_database(
        source / "archive.sqlite3", tmp_path / "y.sqlite3", source, verify_bodies=False
    )
    assert report["snapshots"]["stripped"] == 1
    for path in (source / "bodies").rglob("*.gz"):
        path.unlink()
    report = compact_database(
        source / "archive.sqlite3", tmp_path / "z.sqlite3", source
    )
    assert report["snapshots"] == {
        "body_unavailable": 1,
        "content_differs_from_body": 1,
    }


def test_refuses_existing_destination_and_leaves_source_unchanged(tmp_path, capsys):
    source = tmp_path / "crawl"
    crawl(source)
    db = source / "archive.sqlite3"
    before = db.read_bytes()
    with pytest.raises(ValueError):
        compact_database(db, db, source)
    main([str(db), str(tmp_path / "out.sqlite3"), "--crawl-dir", str(source)])
    out = capsys.readouterr().out
    assert json.loads(out[out.index("{") :])["snapshots"]["stripped"] == 1
    assert db.read_bytes() == before


def test_refuses_while_a_crawler_holds_the_lock(tmp_path):
    import fcntl

    source = tmp_path / "crawl"
    crawl(source)
    with (source / "crawler.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match="crawler holds"):
            compact_database(source / "archive.sqlite3", tmp_path / "x.sqlite3", source)
    assert not (tmp_path / "x.sqlite3").exists()
    assert not (tmp_path / "x.sqlite3.partial").exists()


def test_planner_statistics_are_copied(tmp_path):
    source = tmp_path / "crawl"
    crawl(source)
    db = sqlite3.connect(source / "archive.sqlite3")
    db.execute("ANALYZE")
    db.commit()
    db.close()
    compact_database(source / "archive.sqlite3", tmp_path / "x.sqlite3", source)
    sql = "SELECT * FROM sqlite_stat1 ORDER BY tbl, idx"
    assert rows(tmp_path / "x.sqlite3", sql) == rows(source / "archive.sqlite3", sql)
