"""Where a listing's ask is likely to fall (the predictive interval), when the
bundle has it; the range for the typical rent otherwise."""

import sqlite3

from apartments.site import build

BUILDING = "/buildings/the-grove-250-west-19th-street-new_york"


def with_predictive(site_root):
    db = sqlite3.connect(site_root / "current" / "site.sqlite")
    db.execute(
        "UPDATE listings SET pred_lower_80 = estimate * 0.85, pred_upper_80 = estimate * 1.15,"
        " pred_lower_95 = estimate * 0.75, pred_upper_95 = estimate * 1.25"
    )
    db.commit()
    db.close()


def test_lists_leave_the_range_out_without_the_flag(client, site_root):
    with_predictive(site_root)
    listings = " ".join(client.get(BUILDING).get_data(as_text=True).split())
    assert "Likely ask range</th>" not in listings
    assert "Typical rent, 95% range" not in listings


def test_lists_carry_the_range_with_the_flag(client, site_root, monkeypatch):
    with_predictive(site_root)
    monkeypatch.setenv("SITE_LIST_RANGES", "1")
    listings = client.get(BUILDING).get_data(as_text=True)
    assert (
        "Likely ask range</th>" in listings
        and "Typical rent, 95% range" not in listings
    )


def test_the_build_reads_the_bundle_fields():
    row = {"estimate_pred_lower_80": 100.0, "estimate_pred_upper_80": float("nan")}
    assert build._real(row.get("estimate_pred_lower_80")) == 100.0
    assert build._real(row.get("estimate_pred_upper_80")) is None
    assert build._real(row.get("estimate_pred_lower_95")) is None
    assert build.SCHEMA_VERSION == 5
