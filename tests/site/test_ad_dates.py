import datetime as dt
import sqlite3

from apartments.site import ad_dates
from apartments.site.web import create_app


def _ad(listing_id, **kw):
    a = {
        "listing_id": listing_id,
        "status": "ACTIVE",
        "fetched": dt.datetime(2026, 10, 5, 15, tzinfo=dt.UTC),
        "on_day": dt.date(2026, 8, 10),
        "days_on_market": 40,
    }
    return {**a, **kw}


def test_collect_dates_the_current_ads_on_the_market(pipeline):
    files = pipeline.write(
        [
            _ad(
                "7",
                break_status="RENTED",
                break_day=dt.date(2026, 8, 14),
                back_day=dt.date(2026, 8, 17),
            ),
            _ad("8", status="RENTED"),
            # On the market after the answer: a date from another listing of the unit.
            _ad("9", on_day=dt.date(2026, 10, 6)),
            # Fetched on the evening of Oct 5 in New York.
            _ad(
                "10",
                fetched=dt.datetime(2026, 10, 6, 2, tzinfo=dt.UTC),
                days_on_market=-3,
            ),
            _ad("11"),
        ]
    )
    listings = [
        {"audit_id": a, "listing_id": a[1:], "is_current": 1}
        for a in ("a7", "a8", "a9", "a10")
    ]
    listings += [
        {"audit_id": "k7", "listing_id": "7", "is_current": 1},
        {"audit_id": "a11", "listing_id": "11", "is_current": 0},
        {"audit_id": "a12", "listing_id": None, "is_current": 1},
    ]
    assert ad_dates.collect(None, listings) == []
    dates = sorted(ad_dates.collect(files, listings), key=lambda d: d["audit_id"])
    seven = {
        "listing_id": "7",
        "on_market_at": "2026-08-10",
        "days_on_market": 40,
        "as_of": "2026-10-05",
        "break_status": "RENTED",
        "break_at": "2026-08-14",
        "back_at": "2026-08-17",
    }
    assert dates == [
        {
            "audit_id": "a10",
            "listing_id": "10",
            "on_market_at": "2026-08-10",
            "days_on_market": None,
            "as_of": "2026-10-05",
            "break_status": None,
            "break_at": None,
            "back_at": None,
        },
        {"audit_id": "a7", **seven},
        {"audit_id": "k7", **seven},
    ]
    dates = [d for d in dates if d["audit_id"] == "a7"]
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE listings(audit_id TEXT PRIMARY KEY)")
    listings = [
        {"audit_id": "a7", "is_current": 1},
        {"audit_id": "a8", "is_current": 1},
    ]
    assert ad_dates.install(db, dates, listings) == {"dated": 1, "current": 2}
    assert ad_dates.read(db, "a7")["back_at"] == "2026-08-17"
    assert ad_dates.read(db, "a8") is None
    assert ad_dates.read(sqlite3.connect(":memory:"), "a7") is None


def _current(site_root):
    db = sqlite3.connect(site_root / "current" / "site.sqlite")
    audit, listing = db.execute(
        "SELECT audit_id, listing_id FROM listings WHERE is_current "
        "AND listing_id IS NOT NULL LIMIT 1"
    ).fetchone()
    return db, audit, listing


def _page(site_root, audit):
    client = create_app(site_root, allowed_hosts=["localhost"]).test_client()
    return client.get(f"/listings/{audit}", headers={"Host": "localhost"}).get_data(
        as_text=True
    )


def _date_row(db, audit, listing, **extra):
    db.execute(
        "INSERT INTO ad_dates VALUES (?, ?, '2026-08-10', 40, '2026-10-05', ?, ?, ?)",
        (audit, listing, extra.get("status"), extra.get("at"), extra.get("back")),
    )
    db.commit()


def test_a_build_without_a_pipeline_build_dates_nothing(site_root):
    db, audit, _ = _current(site_root)
    assert db.execute("SELECT count(*) FROM ad_dates").fetchone() == (0,)
    assert 'id="on-market"' not in _page(site_root, audit)


def test_the_listing_page_says_when_this_ad_went_on_the_market(site_root):
    db, audit, listing = _current(site_root)
    _date_row(db, audit, listing)
    html = _page(site_root, audit)
    assert "This ad has been on StreetEasy since <strong>Aug 10, 2026</strong>" in html
    assert "56 days before it was captured on Oct 5, 2026" in html
    assert "The dates are for this ad only" in html


def test_a_relisted_ad_says_when_it_came_back(site_root):
    db, audit, listing = _current(site_root)
    _date_row(db, audit, listing, status="RENTED", at="2026-08-14", back="2026-08-17")
    html = " ".join(_page(site_root, audit).split())
    assert "This ad first went on StreetEasy on Aug 10, 2026." in html
    assert "StreetEasy marked it rented on Aug 14, 2026" in html
    assert "back on the market since <strong>Aug 17, 2026</strong>, 49 days" in html


def test_another_ads_date_is_not_shown(site_root):
    db, audit, listing = _current(site_root)
    _date_row(db, audit, f"{listing}-other")
    assert 'id="on-market"' not in _page(site_root, audit)
