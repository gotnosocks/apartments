import gzip
import hashlib
import json
import sqlite3

from apartments import granular_parse
from apartments.site import ad_dates
from apartments.site.web import create_app


def _archive(root, bodies):
    """A capture archive holding `bodies` (url -> bytes), gzipped by sha256."""
    base = root / "20261004" / "details" / "archive"
    base.mkdir(parents=True)
    db = sqlite3.connect(base / "archive.sqlite3")
    db.execute("CREATE TABLE bodies(hash TEXT, path TEXT)")
    db.execute("CREATE TABLE observations(url TEXT, body_hash TEXT)")
    shas = {}
    for url, body in bodies.items():
        sha = hashlib.sha256(body).hexdigest()
        path = f"bodies/{sha[:2]}/{sha}.gz"
        (base / path).parent.mkdir(parents=True, exist_ok=True)
        (base / path).write_bytes(gzip.compress(body))
        db.execute("INSERT INTO bodies VALUES (?, ?)", (sha, path))
        db.execute("INSERT INTO observations VALUES (?, ?)", (url, sha))
        shas[url] = sha
    db.commit()
    db.close()
    return shas


def _event(listing_id, date, status, index=0):
    return {
        "event_index": index,
        "event_listing_id": listing_id,
        "event_category": "rental",
        "event_date": date,
        "status": status,
    }


def test_last_break_is_the_ads_latest_return():
    events = [
        _event("7", "2026-08-10", "ACTIVE"),
        _event("7", "2026-08-14", "RENTED"),
        _event("7", "2026-08-17", "ACTIVE"),
        _event("7", "2026-08-25", "TEMPORARILY_OFF_MARKET"),
        _event("7", "2026-09-08", "ACTIVE"),
    ]
    assert ad_dates.last_break(events, "2026-08-10", "2026-10-05") == (
        "TEMPORARILY_OFF_MARKET",
        "2026-08-25",
        "2026-09-08",
    )
    assert ad_dates.last_break(events[:1], "2026-08-10", "2026-10-05") == (None,) * 3
    # Rented and back on the same day: the page lists the newer event first.
    same_day = [
        _event("7", "2026-10-05", "ACTIVE", 0),
        _event("7", "2026-10-05", "RENTED", 1),
        _event("7", "2026-08-10", "ACTIVE", 2),
    ]
    assert ad_dates.last_break(same_day, "2026-08-10", "2026-10-05") == (
        "RENTED",
        "2026-10-05",
        "2026-10-05",
    )
    # Off the market by the ad's own last event: no date at all.
    assert ad_dates.last_break(events[:2], "2026-08-10", "2026-10-05") is None


def test_collect_reads_this_ads_own_dates_only(tmp_path, monkeypatch):
    pages = {
        "https://streeteasy.com/rental/7": b"page seven",
        "https://streeteasy.com/rental/8": b"page eight",
    }
    shas = _archive(tmp_path / "archives", pages)
    ads = {
        b"page seven": {
            "id": 7,
            "onMarketAt": "2026-08-10T12:00:00Z",
            "daysOnMarket": 40,
        },
        # The page of another ad (an earlier listing of the same unit).
        b"page eight": {"id": 99, "onMarketAt": "2026-01-02T00:00:00Z"},
    }
    events = [
        _event("7", "2026-08-10", "ACTIVE"),
        _event("7", "2026-08-14", "RENTED"),
        _event("7", "2026-08-17", "ACTIVE"),
        # Another listing id on the same page never counts for ad 7.
        _event("6", "2026-09-01", "RENTED"),
    ]
    monkeypatch.setattr(
        granular_parse,
        "parse_listing",
        lambda body, url: ({"raw_listing_json": json.dumps(ads[body])}, events),
    )
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    rows = [
        {
            "audit_id": "a7",
            "source_listing_id": "7",
            "body_sha256": shas["https://streeteasy.com/rental/7"],
            "collected_at": "2026-10-05T03:00:00Z",
        },
        {
            "audit_id": "a8",
            "source_listing_id": "8",
            "body_sha256": shas["https://streeteasy.com/rental/8"],
            "collected_at": "2026-10-05T03:00:00Z",
        },
        {
            "audit_id": "a9",
            "source_listing_id": "9",
            "body_sha256": "0" * 64,
            "collected_at": "2026-10-05T03:00:00Z",
        },
    ]
    (dataset / "current-source-evidence.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows)
    )
    dates = ad_dates.collect(dataset, tmp_path / "archives")
    assert dates == [
        {
            "audit_id": "a7",
            "listing_id": "7",
            "on_market_at": "2026-08-10",
            "days_on_market": 40,
            "as_of": "2026-10-05",
            "break_status": "RENTED",
            "break_at": "2026-08-14",
            "back_at": "2026-08-17",
        }
    ]
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


def test_a_build_without_evidence_dates_nothing(site_root):
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
