"""Feature filters and a features line in a building's listing table (playtest round 6,
best 1-bed)."""

import json
import re
import sqlite3


def _set(site_root, audit_id, **values):
    db = sqlite3.connect(site_root / "current" / "site.sqlite")
    sets = ", ".join(f"{k} = ?" for k in values)
    db.execute(
        f"UPDATE listings SET {sets} WHERE audit_id = ?", (*values.values(), audit_id)
    )
    db.commit()
    db.close()


GROVE = "the-grove-250-west-19th-street-new_york"


def _count(client, query):
    html = client.get(f"/buildings/{GROVE}?" + query).get_data(as_text=True)
    return int(
        re.search(r'class="results-links">([\d,]+) listing', html)[1].replace(",", "")
    )


def test_laundry_doorman_and_outdoor_filters(client, site_root):
    db = sqlite3.connect(site_root / "current" / "site.sqlite")
    db.execute("UPDATE listings SET laundry = NULL, doorman = NULL")
    db.commit()
    db.close()
    inputs = json.dumps({"outdoor:balcony": 1.0})
    _set(site_root, "a1", laundry="in_unit", doorman="unspecified", inputs=inputs)
    assert _count(client, "laundry=in_unit") == 1
    assert _count(client, "laundry=any") == 1
    assert _count(client, "doorman=any") == 1
    assert _count(client, "doorman=full_time") == 0
    assert _count(client, "outdoor=yes") == 1


def test_elevator_yes_or_not_stated_keeps_unstated_listings(client, site_root):
    db = sqlite3.connect(site_root / "current" / "site.sqlite")
    db.execute("UPDATE listings SET elevator = 'yes'")
    db.commit()
    db.close()
    _set(site_root, "a1", elevator=None)
    every = _count(client, "")
    assert _count(client, "elevator=yes") == every - 1
    assert _count(client, "elevator=yes_or_unstated") == every


def test_listing_tables_show_floor_and_amenities(client, site_root):
    _set(site_root, "a1", floor=3, laundry="in_unit", elevator="yes")
    html = client.get(f"/buildings/{GROVE}").get_data(as_text=True)
    assert '<span class="feat">floor 3 · elevator · W/D in unit' in html
