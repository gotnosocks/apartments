from streeteasy_archive.store import ArchiveStore
from streeteasy_archive.web import create_app


def fixture_archive(tmp_path):
    store = ArchiveStore(tmp_path)
    generation = store.new_generation()
    url = "https://streeteasy.com/building/example/4a"
    store.enqueue(
        generation,
        [
            {"url": url, "kind": "listing"},
            {"url": "https://streeteasy.com/sale/999", "kind": "listing"},
        ],
    )
    body = b'<title>Apartment 4A</title><script>alert("unsafe")</script>'
    store.record(
        generation,
        url,
        200,
        {"ETag": "v1"},
        body,
        "text/html",
        {
            "title": "Apartment 4A",
            "extraction_version": 1,
            "scripts": [{"text": 'alert("unsafe")'}],
        },
    )
    return store, generation, url, body


def test_browser_counts_only_captured_details_and_filters(tmp_path):
    store, gen, url, body = fixture_archive(tmp_path)
    client = create_app(tmp_path).test_client()
    assert client.get("/").status_code == 200
    summary = client.get("/api/summary").json
    assert summary["captured"]["listing"] == 1
    assert summary["queue"]["pending"] == 1
    pages = client.get("/api/pages?kind=listing&state=captured").json
    assert pages["total"] == 1
    assert pages["items"][0]["url"] == url
    assert (
        client.get("/api/pages?state=pending").json["items"][0]["url"].endswith("999")
    )
    assert client.get("/api/pages?q=%27%20OR%201%3D1--").json["total"] == 0
    assert client.get("/api/pages?page=nonsense").status_code == 400
    assert client.get("/api/summary?generation=999").status_code == 404


def test_browser_live_history_source_and_read_only(tmp_path):
    store, gen, url, body = fixture_archive(tmp_path)
    app = create_app(tmp_path)
    client = app.test_client()
    page = client.get("/api/page", query_string={"url": url}).json
    obs = page["history"][0]["id"]
    assert (
        client.get(f"/api/observations/{obs}/extraction").json["title"]
        == "Apartment 4A"
    )
    raw = client.get(f"/api/observations/{obs}/raw")
    assert "<script>" in raw.json["text"]
    assert raw.mimetype == "application/json"
    download = client.get(f"/api/observations/{obs}/raw?download=1")
    assert download.data == body
    assert download.headers["Content-Disposition"].startswith("attachment;")
    assert download.headers["X-Content-Type-Options"] == "nosniff"
    store.record(gen, url, 200, {"ETag": "v2"}, b"changed", "text/plain")
    assert (
        client.get("/api/page", query_string={"url": url}).json["observation_count"]
        == 2
    )
    assert client.get("/api/summary").json["responses"] == 2
    assert client.post("/api/pages").status_code == 405
    assert client.get("/", headers={"Host": "untrusted.test"}).status_code == 400
    assert "script-src 'self'" in client.get("/").headers["Content-Security-Policy"]
    assert store.db.execute("SELECT count(*) FROM observations").fetchone()[0] == 2


def test_empty_archive_shell_and_missing_body(tmp_path):
    store = ArchiveStore(tmp_path)
    client = create_app(tmp_path).test_client()
    assert client.get("/api/summary").json["generation"] is None
    assert client.get("/api/pages").json["total"] == 0
    assert client.get("/api/observations/999/raw").status_code == 404


def test_summary_omits_resolved_errors_but_history_preserves_them(tmp_path):
    store, gen, url, body = fixture_archive(tmp_path)
    store.record_gap(gen, url, 404, {}, "HTTP 404 coverage gap", body=b"missing")
    client = create_app(tmp_path).test_client()
    assert len(client.get("/api/summary").json["errors"]) == 1
    store.record(gen, url, 200, {}, body, "text/html", {"title": "Recovered"})
    assert client.get("/api/summary").json["errors"] == []
    assert any(
        row["status"] == 404
        for row in client.get("/api/page", query_string={"url": url}).json["history"]
    )
    excluded = "https://streeteasy.com/building/example/d"
    store.enqueue(gen, [{"url": excluded, "kind": "excluded"}])
    store.record_gap(gen, excluded, 404, {}, "old split URL artifact", body=b"missing")
    assert client.get("/api/summary").json["errors"] == []


def test_explicit_tailnet_hosts_remain_read_only(tmp_path, monkeypatch):
    import pytest

    hostname = "thelio.example.ts.net"
    origin = f"http://{hostname}:8765"
    monkeypatch.delenv("ARCHIVE_ALLOWED_HOSTS", raising=False)
    assert (
        create_app(tmp_path).test_client().get("/", base_url=origin).status_code == 400
    )
    monkeypatch.setenv("ARCHIVE_ALLOWED_HOSTS", hostname)
    client = create_app(tmp_path).test_client()
    assert client.get("/", base_url=origin).status_code == 200
    assert (
        client.get("/", base_url="http://other.example.ts.net:8765").status_code == 400
    )
    assert client.post("/api/pages", base_url=origin).status_code == 405
    with pytest.raises(ValueError, match="exact hostnames"):
        create_app(tmp_path, allowed_hosts=[".ts.net"])
