"""Which neighbourhoods "Available now" covers, and when they were captured."""

import json
import sqlite3


def test_available_now_says_what_was_captured(client):
    html = client.get("/listings?status=current").get_data(as_text=True)
    assert "seen on the market in the latest capture" in html
    assert "no current capture yet" not in html  # every neighbourhood has one
    assert "seen on the market" not in client.get("/listings").get_data(as_text=True)


def test_a_neighbourhood_without_a_current_capture_is_named(client, site_root):
    db = sqlite3.connect(site_root / "current" / "site.sqlite")
    db.execute(
        "UPDATE listings SET neighbourhood = 'West Village'"
        " WHERE id = (SELECT MIN(id) FROM listings WHERE is_current = 0)"
    )
    stats = json.loads(
        db.execute("SELECT value FROM meta WHERE key = 'stats'").fetchone()[0]
    )
    stats["neighbourhoods"] = {"Chelsea": 3, "West Village": 1}
    db.execute("UPDATE meta SET value = ? WHERE key = 'stats'", (json.dumps(stats),))
    db.commit()
    db.close()
    html = client.get("/listings?status=current").get_data(as_text=True)
    assert "<strong>West Village has no current capture yet</strong>" in html
    estimates = client.get("/estimates").get_data(as_text=True)
    assert "West Village has no current capture yet" in estimates


def test_capture_day_is_new_york_time(client):
    html = client.get("/listings?status=current").get_data(as_text=True)
    assert "captured 2026-" not in html  # a day in words, not an ISO date


def test_an_old_capture_says_listings_may_have_rented(client, site_root):
    db = sqlite3.connect(site_root / "current" / "site.sqlite")
    db.execute(
        "UPDATE listings SET collected_at = '2020-01-01T00:00:00+00:00' WHERE is_current = 1"
    )
    db.commit()
    db.close()
    html = " ".join(
        client.get("/listings?status=current").get_data(as_text=True).split()
    )
    assert "listings may have rented since" in html and "days old" in html
    estimates = " ".join(client.get("/estimates").get_data(as_text=True).split())
    assert "may have rented since" in estimates


def test_a_fresh_capture_has_no_staleness_note(client, site_root):
    import datetime as dt

    now = dt.datetime.now(dt.UTC).isoformat()
    db = sqlite3.connect(site_root / "current" / "site.sqlite")
    db.execute("UPDATE listings SET collected_at = ? WHERE is_current = 1", (now,))
    db.commit()
    db.close()
    html = client.get("/listings?status=current").get_data(as_text=True)
    assert "may have rented since" not in html
