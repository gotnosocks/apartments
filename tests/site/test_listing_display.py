"""Listing details that need context (Data improvements, playtest round 1)."""

import sqlite3


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


def test_jargon_term_labels_get_plain_words(client, site_root):
    # Playtest round 4: "Building size and bath slopes", "HVAC" read as jargon.
    db = sqlite3.connect(site_root / "current" / "site.sqlite")
    db.execute(
        "INSERT INTO terms VALUES ((SELECT max(position) + 1 FROM terms), 'hvac', "
        "'HVAC', 'Heating and air conditioning.')"
    )
    db.commit()
    db.close()
    html = client.get("/research/glossary").get_data(as_text=True)
    assert ">Heating and cooling</dt>" in html and ">HVAC</dt>" not in html


def test_asks_and_estimates_moving_opposite_ways_are_explained(client, site_root):
    db = sqlite3.connect(site_root / "current" / "site.sqlite")
    rows = _unit_rows(db, "a1")
    (first, _), (last, _) = rows[0], rows[-1]
    unit = db.execute("SELECT unit_id FROM listings WHERE id = ?", (first,)).fetchone()[
        0
    ]
    db.execute(
        "UPDATE listings SET ask = 5000, estimate = 4400 WHERE unit_id = ?", (unit,)
    )
    db.execute("UPDATE listings SET ask = 4000, estimate = 4800 WHERE id = ?", (last,))
    db.commit()
    db.close()
    for url in (f"/units/{unit}",):
        html = " ".join(client.get(url).get_data(as_text=True).split())
        assert 'id="opposite-moves"' in html
        assert "each estimate leans toward the other listing's price" in html


def test_asks_and_estimates_moving_together_need_no_note(client, site_root):
    db = sqlite3.connect(site_root / "current" / "site.sqlite")
    rows = _unit_rows(db, "a1")
    db.execute("UPDATE listings SET ask = 4000, estimate = 4100")
    db.execute(
        "UPDATE listings SET ask = 5000, estimate = 4900 WHERE id = ?", (rows[-1][0],)
    )
    (unit,) = db.execute(
        "SELECT unit_id FROM listings WHERE id = ?", (rows[0][0],)
    ).fetchone()
    db.commit()
    db.close()
    html = client.get(f"/units/{unit}").get_data(as_text=True)
    assert 'id="opposite-moves"' not in html
