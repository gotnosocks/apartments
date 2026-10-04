"""Listing details that need context (Data improvements, playtest round 1)."""

import sqlite3


def test_views_are_marked_as_listed_by_the_broker(client, site_root):
    db = sqlite3.connect(site_root / "current" / "site.sqlite")
    db.execute(
        "UPDATE listings SET views = ? WHERE audit_id = 'a1'", ('["city", "park"]',)
    )
    db.commit()
    db.close()
    html = client.get("/listings/a1").get_data(as_text=True)
    assert "(as listed by the broker)" in html


def test_a_large_studio_is_flagged(client, site_root):
    db = sqlite3.connect(site_root / "current" / "site.sqlite")
    db.execute(
        "UPDATE listings SET bedrooms = 0, square_feet = 1173 WHERE audit_id = 'a1'"
    )
    db.commit()
    db.close()
    html = client.get("/listings/a1").get_data(as_text=True)
    assert "An unusual combination for a studio" in html


def test_a_unit_whose_layout_jumps_says_so(client, site_root):
    db = sqlite3.connect(site_root / "current" / "site.sqlite")
    unit = db.execute("SELECT unit_id FROM listings WHERE audit_id = 'a1'").fetchone()[
        0
    ]
    first = db.execute(
        "SELECT MIN(id) FROM listings WHERE unit_id = ?", (unit,)
    ).fetchone()[0]
    db.execute("UPDATE listings SET bedrooms = 4 WHERE id = ?", (first,))
    db.commit()
    db.close()
    html = client.get(f"/units/{unit}").get_data(as_text=True)
    assert "<strong>Layout changed</strong>" in html
