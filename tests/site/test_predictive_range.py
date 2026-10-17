"""Where a listing's ask is likely to fall (the predictive interval), when the
bundle has it; the range for the typical rent otherwise."""

import sqlite3

from apartments.site import build


def with_predictive(site_root):
    db = sqlite3.connect(site_root / "current" / "site.sqlite")
    db.execute(
        "UPDATE listings SET pred_lower_80 = estimate * 0.85, pred_upper_80 = estimate * 1.15,"
        " pred_lower_95 = estimate * 0.75, pred_upper_95 = estimate * 1.25"
    )
    db.commit()
    db.close()


def test_listing_page_shows_the_likely_ask_range(client, site_root):
    with_predictive(site_root)
    html = " ".join(client.get("/listings/a1").get_data(as_text=True).split())
    assert "asks for this apartment likely fall in" in html and "(80%;" in html
    assert "That middle 80% is the likely ask range above" in html
    listings = " ".join(client.get("/listings").get_data(as_text=True).split())
    assert "Likely ask range</th>" not in listings
    assert "Typical rent, 95% range" not in listings
    assert "Each listing's own page shows its range" in listings


def test_lists_carry_the_range_with_the_flag(client, site_root, monkeypatch):
    with_predictive(site_root)
    monkeypatch.setenv("SITE_LIST_RANGES", "1")
    listings = client.get("/listings").get_data(as_text=True)
    assert (
        "Likely ask range</th>" in listings
        and "Typical rent, 95% range" not in listings
    )


def test_without_it_the_typical_rent_range_stays(client):
    html = " ".join(client.get("/listings/a1").get_data(as_text=True).split())
    assert (
        "95% sure the typical rent itself is" in html and "likely fall in" not in html
    )


def test_the_build_reads_the_bundle_fields():
    row = {"estimate_pred_lower_80": 100.0, "estimate_pred_upper_80": float("nan")}
    assert build._real(row.get("estimate_pred_lower_80")) == 100.0
    assert build._real(row.get("estimate_pred_upper_80")) is None
    assert build._real(row.get("estimate_pred_lower_95")) is None
    assert build.SCHEMA_VERSION == 4


def test_csv_carries_the_likely_ask_range_with_the_flag(client, site_root, monkeypatch):
    import csv
    import io

    with_predictive(site_root)

    def rows():
        text = client.get("/listings.csv").get_data(as_text=True)
        return list(csv.DictReader(io.StringIO(text)))

    assert rows() and "pred_lower_80" not in rows()[0]
    monkeypatch.setenv("SITE_LIST_RANGES", "1")
    assert float(rows()[0]["pred_lower_80"]) > 0
