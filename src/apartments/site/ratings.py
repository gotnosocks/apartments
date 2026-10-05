"""Ben's own ratings of listings: a score, tags and a note (docs/ratings.md).

Kept in their own SQLite file, outside the site builds, since a build replaces
`site/current`. One row per listing, plus every save appended to
`rating_events` so an edit never loses an earlier note. Reads of a file that
doesn't exist yet return nothing; only a save creates it.
"""

from __future__ import annotations

import datetime as dt
import ipaddress
import json
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_PATH = "/data1/apartments/ratings/ratings.sqlite"
SCORES = (1, 2, 3, 4, 5)
GOOD = (
    "light",
    "quiet",
    "layout",
    "kitchen",
    "closets",
    "outdoor space",
    "laundry",
    "views",
    "block",
    "building",
    "price",
)
BAD = (
    "dark",
    "noisy",
    "small",
    "awkward layout",
    "walk-up",
    "needs work",
    "no laundry",
    "avenue",
    "building",
    "price",
)
NOTE_MAX = 2000
TAG_MAX = 40
TAGS_MAX = 30
TAILNET = ipaddress.ip_network("100.64.0.0/10")

SCHEMA = """
CREATE TABLE IF NOT EXISTS ratings(
  audit_id TEXT PRIMARY KEY, unit_id TEXT NOT NULL, building_id TEXT NOT NULL,
  score INTEGER, tags TEXT NOT NULL, note TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, snapshot TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ratings_unit ON ratings(unit_id);
CREATE TABLE IF NOT EXISTS rating_events(
  id INTEGER PRIMARY KEY, audit_id TEXT NOT NULL, at TEXT NOT NULL,
  action TEXT NOT NULL, score INTEGER, tags TEXT, note TEXT);
"""


def tag_key(side: str, tag: str) -> str:
    """Tags are stored with their side, "+light" or "-building", since
    "building" and "price" can be either."""
    return ("+" if side == "good" else "-") + tag


def parse_form(form) -> tuple[int | None, list[str], str]:
    """The score, tags and note from a posted rating form; anything invalid
    is dropped rather than refused."""
    try:
        score = int(form.get("score") or 0)
    except ValueError:
        score = 0
    tags = [tag_key("good", t) for t in form.getlist("good") if t in GOOD]
    tags += [tag_key("bad", t) for t in form.getlist("bad") if t in BAD]
    for raw in (form.get("other") or "").split(","):
        tag = " ".join(raw.split()).lower().lstrip("+-")[:TAG_MAX]
        if tag and tag not in tags:
            tags.append(tag)
    note = (form.get("note") or "").strip().replace("\r\n", "\n")[:NOTE_MAX]
    return (score if score in SCORES else None), tags[:TAGS_MAX], note


def write_allowed(remote_addr: str | None, origin: str | None, hosts) -> bool:
    """A save only from the tailnet or this machine, posted by one of the
    site's own pages (its Origin, or Referer, names an allowed host)."""
    try:
        addr = ipaddress.ip_address(remote_addr or "")
    except ValueError:
        return False
    if not (addr.is_loopback or addr in TAILNET):
        return False
    host = urlsplit(origin or "").hostname
    return bool(host) and host.lower() in {h.strip("[]").lower() for h in hosts}


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _connect(self, create: bool = False) -> sqlite3.Connection | None:
        if not create and not self.path.is_file():
            return None
        if create:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.path, timeout=5)
        con.row_factory = sqlite3.Row
        if create:
            con.execute("PRAGMA journal_mode=WAL")
            con.executescript(SCHEMA)
        return con

    def _read(self, sql: str, params=()) -> list[dict]:
        con = self._connect()
        if con is None:
            return []
        try:
            return [_decode(r) for r in con.execute(sql, params)]
        except sqlite3.OperationalError:
            return []  # created but not yet written
        finally:
            con.close()

    def get(self, audit_id: str) -> dict | None:
        rows = self._read("SELECT * FROM ratings WHERE audit_id = ?", (audit_id,))
        return rows[0] if rows else None

    def for_unit(self, unit_id: str) -> dict[str, dict]:
        rows = self._read("SELECT * FROM ratings WHERE unit_id = ?", (unit_id,))
        return {r["audit_id"]: r for r in rows}

    def all(self) -> list[dict]:
        return self._read("SELECT * FROM ratings ORDER BY updated_at DESC")

    def scores(self) -> dict[str, int | None]:
        """Every rated listing's score, for the marks in listing tables."""
        return {
            r["audit_id"]: r["score"]
            for r in self._read(
                "SELECT audit_id, score, '[]' AS tags, '{}' AS snapshot FROM ratings"
            )
        }

    def save(self, audit_id, unit_id, building_id, score, tags, note, snapshot):
        now = _now()
        con = self._connect(create=True)
        try:
            with con:
                con.execute(
                    "INSERT INTO ratings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(audit_id) DO UPDATE SET score = excluded.score, "
                    "tags = excluded.tags, note = excluded.note, "
                    "updated_at = excluded.updated_at, snapshot = excluded.snapshot",
                    (
                        audit_id,
                        unit_id,
                        building_id,
                        score,
                        json.dumps(tags),
                        note,
                        now,
                        now,
                        json.dumps(snapshot),
                    ),
                )
                con.execute(
                    "INSERT INTO rating_events(audit_id, at, action, score, tags, note) "
                    "VALUES (?, ?, 'save', ?, ?, ?)",
                    (audit_id, now, score, json.dumps(tags), note),
                )
        finally:
            con.close()

    def clear(self, audit_id: str):
        con = self._connect(create=True)
        try:
            with con:
                con.execute("DELETE FROM ratings WHERE audit_id = ?", (audit_id,))
                con.execute(
                    "INSERT INTO rating_events(audit_id, at, action) VALUES (?, ?, 'clear')",
                    (audit_id, _now()),
                )
        finally:
            con.close()


def _decode(row: sqlite3.Row) -> dict:
    out = dict(row)
    if "tags" in out:
        out["tags"] = json.loads(out["tags"])
    if "snapshot" in out:
        out["snapshot"] = json.loads(out["snapshot"])
    return out


def tag_label(tag: str) -> tuple[str, str]:
    """("good" | "bad" | "own", the words) for a stored tag."""
    if tag[:1] == "+":
        return "good", tag[1:]
    if tag[:1] == "-":
        return "bad", tag[1:]
    return "own", tag
