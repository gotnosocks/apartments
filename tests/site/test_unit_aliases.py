"""A unit joined from differently written labels says so (Data improvements)."""

import sqlite3


def test_unit_page_names_its_other_labels(client, site_root):
    db = sqlite3.connect(site_root / "current" / "site.sqlite")
    unit = db.execute("SELECT unit_id FROM listings WHERE audit_id = 'a1'").fetchone()[
        0
    ]
    label = db.execute("SELECT label FROM units WHERE id = ?", (unit,)).fetchone()[0]
    db.execute(
        "UPDATE listings SET unit_label = '0' || ? WHERE audit_id = 'a1'", (label,)
    )
    db.commit()
    db.close()
    html = " ".join(client.get(f"/units/{unit}").get_data(as_text=True).split())
    assert f"also listed as 0{label}" in html
