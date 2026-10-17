import json
import sqlite3

import duckdb
import pytest

from apartments.site import build, captures, detail


@pytest.fixture
def detail_root(tmp_path, bundle, monkeypatch):
    monkeypatch.setenv("SITE_DETAIL_ON_REQUEST", "1")
    root = tmp_path / "site-detail"
    build.build(bundle, root, scope="Chelsea")
    return root


@pytest.fixture
def detail_client(detail_root, research_file):
    from apartments.site.web import create_app

    app = create_app(
        detail_root,
        allowed_hosts=["thelio.example.ts.net"],
        research_data=research_file,
    )
    app.config["TESTING"] = True
    return app.test_client()


def _parts(root):
    db = sqlite3.connect(root / "current" / "site.sqlite")
    try:
        return {
            a: c
            for a, c in db.execute(
                "SELECT audit_id, contributions FROM listings WHERE method != ?",
                (captures.METHOD,),
            )
        }
    finally:
        db.close()


def test_detail_build_leaves_parts_out_of_the_table(detail_root):
    stored = _parts(detail_root)
    assert stored and all(c is None for c in stored.values())
    path = detail_root / "current" / detail.FILE
    ids = [
        a
        for (a,) in duckdb.sql(
            f"SELECT audit_id FROM read_parquet('{path}')"
        ).fetchall()
    ]
    assert ids == sorted(stored)
    meta = json.loads(
        sqlite3.connect(detail_root / "current" / "site.sqlite")
        .execute("SELECT value FROM meta WHERE key = 'stats'")
        .fetchone()[0]
    )
    assert meta["detail"]["rows"] == len(stored)


def test_parts_on_request_match_the_stored_parts(site_root, detail_root):
    stored = _parts(site_root)
    sha = json.loads((detail_root / "current" / "build.json").read_text())[
        "summary_sha256"
    ]
    build_dir = (detail_root / "current").resolve()
    for audit_id, contributions in stored.items():
        assert detail.lookup(build_dir, sha, audit_id) == json.loads(contributions)
    assert detail.lookup(build_dir, sha, "no-such-row") is None


def test_listing_pages_render_alike(client, detail_client, site_root):
    for audit_id in list(_parts(site_root))[:5]:
        a = client.get(f"/listings/{audit_id}")
        b = detail_client.get(f"/listings/{audit_id}")
        assert a.status_code == b.status_code == 200
        assert a.get_data(as_text=True) == b.get_data(as_text=True)


def test_story_renders_from_detail(detail_client):
    assert detail_client.get("/research/story").status_code == 200
