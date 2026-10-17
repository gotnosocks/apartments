"""When each ad now on the market went on it, by StreetEasy's own count.

The data pipeline's ads file gives each ad's `on_day`, the day of its first change to ACTIVE
(StreetEasy's `onMarketAt`), and StreetEasy's `days_on_market`. Both are about that one ad (its
listing id), not the apartment. An earlier ad of the same apartment is another listing id with
its own dates, so nothing here reaches back across ads. The same ad can still be marked rented
or taken off the market and then come back: the file's `break_status`, `break_day` and
`back_day` give the latest such break and the return, from the ad's own status changes.

The build dates a current row by its listing id when the ad's latest answer says ACTIVE and the
ad went on the market no later than the New York day of that answer. Other rows get no date.
"""

from __future__ import annotations

import sqlite3

import duckdb

SCHEMA = """
CREATE TABLE ad_dates(
  audit_id TEXT PRIMARY KEY REFERENCES listings(audit_id),
  listing_id TEXT NOT NULL, on_market_at TEXT NOT NULL, days_on_market INTEGER,
  as_of TEXT NOT NULL, break_status TEXT, break_at TEXT, back_at TEXT);
"""
ON_MARKET = """
SELECT listing_id, on_day, days_on_market, fetched::DATE AS as_of, break_status,
  break_day, back_day
FROM read_parquet($ads)
WHERE status = 'ACTIVE' AND on_day <= fetched::DATE
"""


def _day(value) -> str | None:
    return value.isoformat() if value is not None else None


def collect(files: dict | None, listings: list[dict]) -> list[dict]:
    """StreetEasy's on-market dates for the current rows of `listings`, from the ads file of
    the pipeline's `files` (`captures.pipeline_files`)."""
    current: dict[str, list[str]] = {}
    for r in listings:
        if r["is_current"] and r.get("listing_id"):
            current.setdefault(str(r["listing_id"]), []).append(r["audit_id"])
    if files is None or not current:
        return []
    con = duckdb.connect()
    try:
        con.execute("SET TimeZone = 'America/New_York'")
        found = con.execute(ON_MARKET, {"ads": files["ads"]}).fetchall()
    finally:
        con.close()
    out = []
    for listing_id, since, days, as_of, status, broke, back in found:
        for audit_id in current.get(listing_id, []):
            out.append(
                {
                    "audit_id": audit_id,
                    "listing_id": listing_id,
                    "on_market_at": since.isoformat(),
                    "days_on_market": days if days is not None and days >= 0 else None,
                    "as_of": as_of.isoformat(),
                    "break_status": status,
                    "break_at": _day(broke),
                    "back_at": _day(back),
                }
            )
    return out


def install(db, dates: list[dict], listings: list[dict]) -> dict:
    """Write the dates of the build's current rows; the counts go to the stats."""
    current = {r["audit_id"] for r in listings if r["is_current"]}
    rows = [d for d in dates if d["audit_id"] in current]
    db.executescript(SCHEMA)
    db.executemany(
        "INSERT INTO ad_dates VALUES "
        "(:audit_id, :listing_id, :on_market_at, :days_on_market, :as_of, "
        ":break_status, :break_at, :back_at)",
        rows,
    )
    return {"dated": len(rows), "current": len(current)}


def read(db, audit_id: str) -> dict | None:
    try:
        row = db.execute(
            "SELECT * FROM ad_dates WHERE audit_id = ?", (audit_id,)
        ).fetchone()
    except sqlite3.OperationalError:  # an older build has no ad_dates table
        return None
    return dict(row) if row is not None else None
