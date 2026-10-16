"""The raw Parquet export of a GraphQL collection made against a fake API."""

import fcntl
import hashlib
import json
import urllib.parse

import pyarrow.parquet as pq
import pytest

from streeteasy_archive import graphql_export as ge
from streeteasy_archive import graphql_search as gs
from tests.archive.test_graphql_search import FakeAPI, make_api, make_collector


class DroppedField(FakeAPI):
    """The fake API, with the second field of the first ad read answered by null."""

    dropped = None

    def __call__(self, url, **kw):
        response = super().__call__(url, **kw)
        query = self.queries[-1]
        if self.dropped is None and "a1: rentalsByListingIds" in query:
            content = json.loads(response.payload["results"][0]["content"])
            self.dropped = [int(r["id"]) for r in content["data"]["a1"]]
            content["data"]["a1"] = None
            response.payload["results"][0]["content"] = json.dumps(content)
        return response


def collect(tmp_path, monkeypatch):
    monkeypatch.setattr(gs, "IDS_PER_FIELD", 2)
    base = make_api()
    api = DroppedField(base.ads, base.buildings, base.search)
    c = make_collector(tmp_path / "archive", api)
    c.collect()
    return c, api


def rows(out, table):
    return [
        row
        for path in sorted((out / table).glob("run-*/*.parquet"))
        for row in pq.read_table(path).to_pylist()
    ]


def manifest(out):
    return [
        json.loads(line)
        for line in (out / "manifest.ndjson").read_text().split("\n")
        if line
    ]


def files(out):
    return {
        str(p.relative_to(out)): p.read_bytes() for p in sorted(out.glob("*/run-*/*"))
    }


def archive_bytes(root):
    """The database, its WAL and the bodies. Readers mark the -shm index, so it is left out."""
    paths = [root / "archive.sqlite3", root / "archive.sqlite3-wal"]
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in paths + sorted(root.glob("bodies/*/*"))
    }


def test_export_writes_every_read_with_its_records(tmp_path, monkeypatch, capsys):
    c, api = collect(tmp_path, monkeypatch)
    archive = archive_bytes(tmp_path / "archive")
    assert ge.main(["--data", str(tmp_path / "archive")]) == 0
    assert archive_bytes(tmp_path / "archive") == archive
    report = json.loads(capsys.readouterr().out.splitlines()[-1])
    out = tmp_path / "archive" / "export"

    ads = rows(out, "ads")
    assert {r["run"] for r in ads} == {c.run} and {r["region"] for r in ads} == {"test"}
    by_read = {(r["listing_id"], r["response_id"]): r for r in ads}
    assert len(by_read) == len(ads)
    for r in ads:
        if r["outcome"] == "record":
            assert (
                r["record_sha256"] == hashlib.sha256(r["record"].encode()).hexdigest()
            )
            assert json.loads(r["record"]) == api.ads[str(r["listing_id"])]
        else:
            assert r["outcome"] == "missing" and r["record"] is None
    # The latest record of each ad in the collector's table is among the exported reads.
    for ad in c.db.execute(
        "SELECT * FROM graphql_search_ads WHERE response_id IS NOT NULL"
    ):
        row = by_read[ad["listing_id"], ad["response_id"]]
        assert row["record_sha256"] == ad["record_sha256"]
    assert {r["outcome"] for r in ads if r["listing_id"] == 1300003} == {"missing"}
    # The IDs of the null field come from the retries, and the first read has none of them.
    first = min(r["response_id"] for r in ads)
    assert api.dropped and all(
        r["response_id"] != first for r in ads if r["listing_id"] in api.dropped
    )
    assert {r["listing_id"] for r in ads if r["outcome"] == "record"} >= set(
        api.dropped
    )

    buildings = rows(out, "buildings")
    assert {r["building_id"] for r in buildings if r["outcome"] == "record"} == {
        "17503",
        "17504",
    }

    requests = rows(out, "requests")
    responses = c.db.execute(
        "SELECT * FROM graphql_search_responses ORDER BY id"
    ).fetchall()
    assert [r["response_id"] for r in requests] == [r["id"] for r in responses]
    for row, response in zip(requests, responses, strict=True):
        assert row["kind"] == response["kind"] and row["entries"] == response["entries"]
        assert row["api_status"] == 200 and row["target_status"] == 200
        url = c.store.get_body(response["query_sha256"])
        assert row["url_length"] == len(url)
        assert (tmp_path / "archive" / row["query_path"]).exists()
        assert (tmp_path / "archive" / row["response_path"]).exists()

    calls = rows(out, "calls")
    assert (
        len(calls)
        == c.db.execute("SELECT count(*) FROM graphql_search_calls").fetchone()[0]
    )
    assert {r["kind"] for r in calls} >= {"count", "slice", "ads", "buildings"}

    lines = manifest(out)
    assert sorted(line["path"] for line in lines) == sorted(files(out))
    for line in lines:
        data = (out / line["path"]).read_bytes()
        assert line["sha256"] == hashlib.sha256(data).hexdigest()
        assert line["rows"] == pq.ParquetFile(out / line["path"]).metadata.num_rows
    assert report["ads"] == {"files": 1, "rows": len(ads)}
    assert report["calls"] == {"files": 1, "rows": len(calls)}


def test_a_later_export_adds_files_above_the_finished_ones(tmp_path, monkeypatch):
    c, _ = collect(tmp_path, monkeypatch)
    export = ge.Export(tmp_path / "archive", per_file=2)
    export.run()
    out = export.out
    before = files(out)
    ad_responses = [
        r[0]
        for r in c.db.execute(
            "SELECT id FROM graphql_search_responses WHERE kind='ads' ORDER BY id"
        )
    ]
    folder = f"ads/run-{c.run:04d}"
    pairs = [ad_responses[i : i + 2] for i in range(0, len(ad_responses), 2)]
    assert [n for n in before if n.startswith(folder)] == [
        f"{folder}/responses-{p[0]:07d}-{p[-1]:07d}.parquet" for p in pairs
    ]
    assert export.run() == {table: {"files": 0, "rows": 0} for table in ge.TABLES}

    # The run goes on with a reply and a call.
    with c.store._tx():
        new = c.db.execute(
            """INSERT INTO graphql_search_responses(sha256,run,query_sha256,kind,entries,
            bytes,fetched,capture) SELECT sha256,run,query_sha256,kind,entries,bytes,
            fetched+60,capture FROM graphql_search_responses WHERE id=?""",
            (ad_responses[-1],),
        ).lastrowid
        call = c.db.execute(
            """INSERT INTO graphql_search_calls SELECT run,kind,started+60,seconds,
            api_status,target_status,bytes,url_length,attempt,error
            FROM graphql_search_calls ORDER BY rowid DESC LIMIT 1"""
        ).lastrowid
    report = ge.Export(tmp_path / "archive", per_file=2).run()
    after = files(out)
    assert {n: after[n] for n in before} == before
    assert sorted(set(after) - set(before)) == [
        f"ads/run-{c.run:04d}/responses-{new:07d}-{new:07d}.parquet",
        f"calls/run-{c.run:04d}/rows-{call:09d}-{call:09d}.parquet",
        f"requests/run-{c.run:04d}/responses-{new:07d}-{new:07d}.parquet",
    ]
    assert report["calls"] == {"files": 1, "rows": 1}
    assert len(manifest(out)) == len(after)


@pytest.mark.parametrize("cut", ["whole line", "half line"])
def test_an_export_after_a_crash_lists_the_unlisted_file(tmp_path, monkeypatch, cut):
    collect(tmp_path, monkeypatch)
    export = ge.Export(tmp_path / "archive")
    export.run()
    out = export.out
    lines = (out / "manifest.ndjson").read_text().splitlines(keepends=True)
    kept = "" if cut == "whole line" else lines[-1][: len(lines[-1]) // 2]
    (out / "manifest.ndjson").write_text("".join(lines[:-1]) + kept)
    stale = next(out.glob("ads/run-*")) / "responses-0000099-0000099.parquet.tmp"
    stale.write_bytes(b"partial")
    before = files(out)

    report = ge.Export(tmp_path / "archive").run()
    assert not stale.exists()
    assert files(out) == {n: b for n, b in before.items() if not n.endswith(".tmp")}
    assert manifest(out)[-1]["path"] == json.loads(lines[-1])["path"]
    assert len(manifest(out)) == len(lines)
    assert sum(t["files"] for t in report.values()) == 1


def test_moved_call_rowids_stop_the_export(tmp_path, monkeypatch):
    c, _ = collect(tmp_path, monkeypatch)
    ge.Export(tmp_path / "archive").run()
    with c.store._tx():
        c.db.execute(
            """UPDATE graphql_search_calls SET started=started+1
            WHERE rowid=(SELECT max(rowid) FROM graphql_search_calls)"""
        )
    with pytest.raises(ge.ExportError, match="IDs moved"):
        ge.Export(tmp_path / "archive").run()


@pytest.mark.parametrize("kind", ["ads", "buildings"])
def test_a_reused_response_id_stops_the_export(tmp_path, monkeypatch, kind):
    # A restored database can give a new reply the ID of the last exported one.
    c, _ = collect(tmp_path, monkeypatch)
    ge.Export(tmp_path / "archive").run()
    with c.store._tx():
        c.db.execute(
            """UPDATE graphql_search_responses SET fetched=fetched+1
            WHERE id=(SELECT max(id) FROM graphql_search_responses WHERE kind=?)""",
            (kind,),
        )
    with pytest.raises(ge.ExportError, match="IDs moved"):
        ge.Export(tmp_path / "archive").run()


def test_row_groups_follow_the_record_text(tmp_path, monkeypatch):
    collect(tmp_path, monkeypatch)
    monkeypatch.setattr(ge, "ROW_GROUP_BYTES", 1)
    export = ge.Export(tmp_path / "archive")
    export.run()
    (path,) = export.out.glob("ads/run-*/*.parquet")
    metadata = pq.ParquetFile(path).metadata
    records = sum(r["outcome"] == "record" for r in rows(export.out, "ads"))
    # Each record fills a row group, and the missing reads after the last one share one.
    assert records <= metadata.num_row_groups <= metadata.num_rows


def test_an_unknown_run_stops_the_export(tmp_path, monkeypatch):
    collect(tmp_path, monkeypatch)
    with pytest.raises(ge.ExportError, match="no run 99"):
        ge.Export(tmp_path / "archive").run([99])


def test_a_reply_disagreeing_with_its_count_stops_the_export(tmp_path, monkeypatch):
    c, _ = collect(tmp_path, monkeypatch)
    with c.store._tx():
        c.db.execute(
            """UPDATE graphql_search_responses SET entries=entries+1
            WHERE id=(SELECT min(id) FROM graphql_search_responses)"""
        )
    with pytest.raises(ge.ExportError, match="the archive counts"):
        ge.Export(tmp_path / "archive").run()


def test_a_held_lock_stops_a_second_export(tmp_path, monkeypatch):
    collect(tmp_path, monkeypatch)
    out = tmp_path / "archive" / "export"
    out.mkdir()
    with open(out / ".lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with pytest.raises(ge.ExportError, match="another export"):
            ge.Export(tmp_path / "archive").run()


def test_requested_ids_reads_each_by_id_field():
    query = (
        "query ArchiveRentals { a0: rentalsByListingIds(ids: [1 2]) { ...R } "
        "a1: rentalsByListingIds(ids: [3]) { ...R } } fragment R on RentalListing { id }"
    )
    url = gs.API_HOST + "?" + urllib.parse.urlencode({"query": query})
    assert ge.requested_ids(url) == {"a0": ["1", "2"], "a1": ["3"]}
