"""Feature filters, a features line in listing tables, and what the model read
for a listing whose ad leaves it out (playtest round 6, best 1-bed)."""

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


def _count(client, query):
    html = client.get("/listings?" + query).get_data(as_text=True)
    return int(
        re.search(r"<strong>([\d,]+)</strong> listing", html)[1].replace(",", "")
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
    html = client.get("/listings?laundry=in_unit").get_data(as_text=True)
    assert 'value="in_unit" selected' in html
    assert "laundry, doorman and outdoor filters leave out" in html


def test_elevator_yes_or_not_stated_keeps_unstated_listings(client, site_root):
    db = sqlite3.connect(site_root / "current" / "site.sqlite")
    db.execute("UPDATE listings SET elevator = 'yes'")
    db.commit()
    db.close()
    _set(site_root, "a1", elevator=None)
    every = _count(client, "")
    assert _count(client, "elevator=yes") == every - 1
    assert _count(client, "elevator=yes_or_unstated") == every
    html = client.get("/listings?elevator=yes").get_data(as_text=True)
    assert ">include listings that don't state an elevator</a>" in html


def test_listing_tables_show_floor_and_amenities(client, site_root):
    _set(site_root, "a1", floor=3, laundry="in_unit", elevator="yes")
    html = client.get("/listings").get_data(as_text=True)
    assert '<span class="feat">floor 3 · elevator · W/D in unit' in html


def test_a_floor_read_from_the_unit_number_says_so(client, site_root):
    inputs = {
        "log_floor": 1.3863,
        "looks onto a side street": 1.0,
        "outdoor:patio": 1.0,
    }
    _set(site_root, "a1", floor=None, inputs=json.dumps(inputs))
    html = " ".join(client.get("/listings/a1").get_data(as_text=True).split())
    assert (
        '4 <span class="muted">(not in the ad: read from the unit number)</span>'
        in html
    )
    assert "Looks onto</a></dt><dd>A side street" in html
    assert "<dt>Outdoor space</dt><dd>Patio" in html
    _set(site_root, "a1", inputs=json.dumps({"floor_unknown": 1.0}))
    html = " ".join(client.get("/listings/a1").get_data(as_text=True).split())
    assert (
        "<dt>Floor</dt><dd>not stated" in html
        and "Looks onto</a></dt><dd>not known" in html
    )


def test_the_capture_day_is_new_york_time(client, site_root):
    _set(site_root, "a1", is_current=1, collected_at="2026-10-05T02:05:20+00:00")
    html = client.get("/listings/a1").get_data(as_text=True)
    assert "Available now, captured 4 Oct 2026" in html
