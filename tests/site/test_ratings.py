"""Ratings of listings: a score, tags and a note, kept apart from the builds
(docs/ratings.md)."""

import csv
import io
import json
import sqlite3

from apartments.site import ratings

ORIGIN = {"Origin": "http://localhost"}


def _rate(client, **form):
    data = {"audit_id": "a1", **form}
    return client.post("/ratings", data=data, headers=ORIGIN)


def test_a_rating_is_saved_shown_and_exported(client, ratings_db):
    assert not ratings_db.exists()
    html = client.get("/listings/a1").get_data(as_text=True)
    assert 'id="rating"' in html and 'action="/ratings"' in html
    assert not ratings_db.exists()  # reading never creates the file
    r = _rate(
        client,
        score="4",
        good=["light", "quiet"],
        bad=["walk-up", "not a tag"],
        other="Near the park, +roof",
        note="Nice <b>kitchen</b>",
    )
    assert r.status_code == 303 and r.headers["Location"].endswith(
        "/listings/a1#rating"
    )
    saved = ratings.Store(ratings_db).get("a1")
    assert saved["score"] == 4
    assert saved["tags"] == ["+light", "+quiet", "-walk-up", "near the park", "roof"]
    assert saved["snapshot"]["ask"] > 0 and saved["snapshot"]["build"]
    html = client.get("/listings/a1").get_data(as_text=True)
    assert (
        'aria-label="4 out of 5"' in html and "Nice &lt;b&gt;kitchen&lt;/b&gt;" in html
    )
    assert '<span class="rtag bad">− walk-up</span>' in html
    # Rated listings are marked in listing tables.
    assert 'title="Your rating">★4</span>' in client.get("/listings").get_data(
        as_text=True
    )
    page = client.get("/ratings").get_data(as_text=True)
    assert "<strong>1</strong> rating" in page and "Nice &lt;b&gt;kitchen" in page
    page = client.get("/ratings?tag=-dark").get_data(as_text=True)
    assert "No ratings match." in page
    rows = list(
        csv.DictReader(io.StringIO(client.get("/ratings.csv").get_data(as_text=True)))
    )
    assert rows[0]["audit_id"] == "a1" and rows[0]["score"] == "4" and rows[0]["ask"]
    data = json.loads(client.get("/ratings.json").get_data(as_text=True))
    assert data[0]["tags"][0] == "+light" and "snapshot" in data[0]


def test_an_edit_keeps_the_history_and_clear_removes_it(client, ratings_db):
    _rate(client, score="2", note="first")
    html = client.get("/listings/a1?edit=1").get_data(as_text=True)
    assert 'value="2" checked' in html and ">first</textarea>" in html
    _rate(client, score="", note="second")
    assert ratings.Store(ratings_db).get("a1")["score"] is None
    _rate(client, action="clear")
    assert ratings.Store(ratings_db).get("a1") is None
    events = (
        sqlite3.connect(ratings_db)
        .execute("SELECT action, note FROM rating_events ORDER BY id")
        .fetchall()
    )
    assert events == [("save", "first"), ("save", "second"), ("clear", None)]


def test_saves_need_the_sites_own_origin_and_a_tailnet_address(client, ratings_db):
    r = client.post("/ratings", data={"audit_id": "a1", "score": "5"})
    assert r.status_code == 403
    r = client.post(
        "/ratings",
        data={"audit_id": "a1", "score": "5"},
        headers={"Origin": "https://evil.example"},
    )
    assert r.status_code == 403
    r = client.post(
        "/ratings",
        data={"audit_id": "a1", "score": "5"},
        headers=ORIGIN,
        environ_base={"REMOTE_ADDR": "203.0.113.9"},
    )
    assert r.status_code == 403
    r = client.post(
        "/ratings",
        data={"audit_id": "a1", "score": "5"},
        headers={"Origin": "http://thelio.example.ts.net"},
        environ_base={"REMOTE_ADDR": "100.80.84.126"},
    )
    assert r.status_code == 303
    assert _rate(client, audit_id="nope").status_code == 404


def test_no_ratings_yet(client):
    page = client.get("/ratings").get_data(as_text=True)
    assert "No ratings yet." in page
    assert client.get("/ratings.csv").get_data(as_text=True).strip() == "audit_id"
    assert json.loads(client.get("/ratings.json").get_data(as_text=True)) == []
