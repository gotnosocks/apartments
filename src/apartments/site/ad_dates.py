"""When each advertisement now on the market went on it, by StreetEasy's own count.

A current row's dataset evidence names the page it was read from (`body_sha256`).
The page is kept, content-addressed, in a current-listings capture archive, and
its listing object carries StreetEasy's `onMarketAt` and `daysOnMarket`. Both
are about that one advertisement (its listing id), not the apartment. An earlier
ad of the same apartment is another listing id with its own dates, so nothing
here reaches back across ads. The same ad can still be marked rented or taken
off the market and then come back: the latest such break and the return are
kept from the ad's own status events. A row whose page is not found, does not
parse, or belongs to another listing id simply gets no date.
"""

from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import itertools
import json
import sqlite3
from pathlib import Path

ARCHIVES = Path("/data1/apartments/archive/current-listings")
SCHEMA = """
CREATE TABLE ad_dates(
  audit_id TEXT PRIMARY KEY REFERENCES listings(audit_id),
  listing_id TEXT NOT NULL, on_market_at TEXT NOT NULL, days_on_market INTEGER,
  as_of TEXT NOT NULL, break_status TEXT, break_at TEXT, back_at TEXT);
"""


def last_break(events: list[dict], since: str, as_of: str):
    """The ad's latest break (status, date) and the day it came back on the
    market, from its own dated status events; (None, None, None) if it has been
    on the market without a break since `since`."""
    # StreetEasy lists events newest first, so on a shared day the higher
    # event_index is the earlier one.
    keyed = []
    for e in events:
        d = _date(e.get("event_date"))
        if e.get("status") and d and since <= d <= as_of:
            keyed.append((d, -int(e.get("event_index") or 0), e["status"]))
    dated = [(d, s) for d, _, s in sorted(keyed)]
    found = (None, None, None)
    for (d0, s0), (d1, s1) in itertools.pairwise(dated):
        if s0 != "ACTIVE" and s1 == "ACTIVE":
            found = (s0, d0, d1)
    if dated and dated[-1][1] != "ACTIVE":
        return None  # the ad's own events say it is off the market now
    return found


def _date(value) -> str | None:
    try:
        return dt.date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        return None


class _Bodies:
    """Page bodies by sha256 across the capture archives under `root`."""

    def __init__(self, root: Path):
        self.archives = [
            (p.parent, sqlite3.connect(f"file:{p}?mode=ro", uri=True))
            for p in sorted(root.glob("*/*/archive/archive.sqlite3"))
        ]

    def get(self, sha: str) -> tuple[bytes, str] | None:
        for base, db in self.archives:
            hit = db.execute(
                "SELECT b.path, o.url FROM bodies b JOIN observations o "
                "ON o.body_hash = b.hash WHERE b.hash = ? LIMIT 1",
                (sha,),
            ).fetchone()
            if hit is None:
                continue
            try:
                raw = (base / hit[0]).read_bytes()
                body = gzip.decompress(raw) if hit[0].endswith(".gz") else raw
            except (OSError, gzip.BadGzipFile, EOFError):
                continue
            if hashlib.sha256(body).hexdigest() == sha:
                return body, hit[1]
        return None

    def close(self):
        for _, db in self.archives:
            db.close()


def collect(dataset: Path, root: Path = ARCHIVES) -> list[dict]:
    """StreetEasy's on-market date for each current row of `dataset` whose page
    is in an archive under `root`."""
    evidence = dataset / "current-source-evidence.jsonl"
    if not evidence.is_file() or not root.is_dir():
        return []
    from apartments.granular_parse import parse_listing

    bodies = _Bodies(root)
    out = []
    try:
        for line in evidence.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            found = bodies.get(r.get("body_sha256") or "")
            if found is None:
                continue
            try:
                listing, events = parse_listing(*found)
                ad = json.loads(listing.get("raw_listing_json") or "null") or {}
            except (ValueError, KeyError, TypeError):
                continue
            listing_id = str(r.get("source_listing_id") or "")
            # Only this advertisement's own listing object counts.
            if not listing_id or str(ad.get("id")) != listing_id:
                continue
            since, as_of = _date(ad.get("onMarketAt")), _date(r.get("collected_at"))
            if since is None or as_of is None or since > as_of:
                continue
            days = ad.get("daysOnMarket")
            own = [
                e
                for e in events
                if e.get("event_listing_id") == listing_id
                and e.get("event_category") == "rental"
            ]
            gap = last_break(own, since, as_of)
            if gap is None:
                continue
            out.append(
                {
                    "audit_id": r["audit_id"],
                    "listing_id": listing_id,
                    "on_market_at": since,
                    "days_on_market": days
                    if isinstance(days, int) and days >= 0
                    else None,
                    "as_of": as_of,
                    "break_status": gap[0],
                    "break_at": gap[1],
                    "back_at": gap[2],
                }
            )
    finally:
        bodies.close()
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
