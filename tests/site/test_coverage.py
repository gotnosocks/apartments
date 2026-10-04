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
