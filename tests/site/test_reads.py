import json
import sqlite3
from pathlib import Path

from apartments.site import reads
from apartments.site.web import create_app


def _app(site_root, research_file):
    app = create_app(site_root, research_data=research_file)
    app.config["TESTING"] = True
    return app.test_client()


def test_listing_page_logs_the_columns_it_reads(site_root, research_file, monkeypatch):
    monkeypatch.delenv("SITE_READS_LOG", raising=False)
    client = _app(site_root, research_file)
    assert client.get("/listings/a1").status_code == 200
    lines = [
        json.loads(x) for x in (site_root / "reads.jsonl").read_text().splitlines()
    ]
    page = next(x for x in lines if x["endpoint"] == "listing")
    assert page["status"] == 200
    assert "listings.contributions" in page["queried"]
    assert {"contributions", "inputs", "ask"} <= set(page["used"])


def _lines(site_root):
    return [json.loads(x) for x in (site_root / "reads.jsonl").read_text().splitlines()]


def test_the_streamed_csv_logs_its_query_and_keeps_its_body(
    site_root, research_file, monkeypatch
):
    monkeypatch.delenv("SITE_READS_LOG", raising=False)
    client = _app(site_root, research_file)
    response = client.get("/listings.csv")
    assert response.status_code == 200
    assert len(response.get_data(as_text=True).splitlines()) > 1
    line = next(x for x in _lines(site_root) if x["endpoint"] == "listings_csv")
    assert "listings.ask" in line["queried"]


def test_an_unwritable_log_leaves_the_page_working(
    site_root, research_file, monkeypatch, tmp_path
):
    monkeypatch.setenv("SITE_READS_LOG", str(tmp_path / "missing" / "reads.jsonl"))
    client = _app(site_root, research_file)
    assert client.get("/listings/a1").status_code == 200


def test_rows_read_by_position_or_whole_count_their_columns():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = reads.Row
    row = connection.execute("SELECT 1 AS a, 2 AS b, 3 AS c").fetchone()
    log = reads.ReadLog(Path("unused"))
    used, token = log.start()
    assert row[0] == 1 and row["b"] == 2
    assert used == {"a", "b"}
    assert dict(row) == {"a": 1, "b": 2, "c": 3}
    assert tuple(row) == (1, 2, 3) and row.keys() == ["a", "b", "c"]
    assert used == {"a", "b", "c"}
    reads._used.reset(token)
    assert row["a"] == 1 and used == {"a", "b", "c"}


def test_zero_leaves_no_log(site_root, research_file, monkeypatch):
    monkeypatch.setenv("SITE_READS_LOG", "0")
    client = _app(site_root, research_file)
    assert client.get("/listings/a1").status_code == 200
    assert not (site_root / "reads.jsonl").exists()
