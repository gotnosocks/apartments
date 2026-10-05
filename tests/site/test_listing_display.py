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
    assert "<dt>Note</dt>" in html and "An unusual combination for a studio" in html


def test_a_unit_whose_layout_jumps_says_so(client, site_root):
    db = sqlite3.connect(site_root / "current" / "site.sqlite")
    unit = db.execute("SELECT unit_id FROM listings WHERE audit_id = 'a1'").fetchone()[
        0
    ]
    first = db.execute(
        "SELECT id FROM listings WHERE unit_id = ? ORDER BY period, id LIMIT 1", (unit,)
    ).fetchone()[0]
    db.execute("UPDATE listings SET bedrooms = 4 WHERE id = ?", (first,))
    db.commit()
    db.close()
    html = client.get(f"/units/{unit}").get_data(as_text=True)
    assert "<strong>Layout changed</strong>" in html


def _unit_rows(db, audit_id):
    unit = db.execute(
        "SELECT unit_id FROM listings WHERE audit_id = ?", (audit_id,)
    ).fetchone()[0]
    return db.execute(
        "SELECT id, audit_id FROM listings WHERE unit_id = ? ORDER BY period, id",
        (unit,),
    ).fetchall()


def test_a_listing_says_when_its_advertisement_started_and_the_cut(client, site_root):
    db = sqlite3.connect(site_root / "current" / "site.sqlite")
    rows = _unit_rows(db, "a1")
    (first, _), (last, last_audit) = rows[0], rows[-1]
    db.execute(
        "UPDATE listings SET listing_id = 'ad-7' WHERE id IN (?, ?)", (first, last)
    )
    db.execute("UPDATE listings SET ask = 11000 WHERE id = ?", (first,))
    db.execute("UPDATE listings SET ask = 9995 WHERE id = ?", (last,))
    db.commit()
    db.close()
    html = " ".join(
        client.get(f"/listings/{last_audit}").get_data(as_text=True).split()
    )
    assert 'id="ad-start"' in html and "asking $11,000; this ask is 9% lower" in html
    first_html = client.get(f"/listings/{rows[0][1]}").get_data(as_text=True)
    assert 'id="ad-start"' not in first_html  # nothing earlier to compare


def test_a_listing_says_when_the_apartment_was_listed_with_other_bedrooms(
    client, site_root
):
    db = sqlite3.connect(site_root / "current" / "site.sqlite")
    rows = _unit_rows(db, "a1")
    db.execute("UPDATE listings SET bedrooms = 2 WHERE id = ?", (rows[0][0],))
    db.execute("UPDATE listings SET bedrooms = 1 WHERE id = ?", (rows[-1][0],))
    db.commit()
    db.close()
    html = " ".join(
        client.get(f"/listings/{rows[-1][1]}").get_data(as_text=True).split()
    )
    assert 'id="relabelled"' in html and "listed as 2 BR in" in html
