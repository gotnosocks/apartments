"""Which way an apartment faces: the rear or a courtyard, the street, or both.

Data improvements labels each unit from all its listings
(`/data1/apartments/exposure/labels.parquet`): "own" when the apartment's own
listings show it (windows against the building's sides, an F/R label, ad text,
views), "line" when it has no evidence of its own but at least 75% of the
other apartments of its line (same building, same label letter or number)
agree. Leave-one-out, a line's label matches an apartment's own 89% of the
time. A current snapshot for display, not the model's input (the model reads
its as-of version, `rentfrontier.features.lineface_v1`).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

FILE = Path("/data1/apartments/exposure/labels.parquet")
SIDES = ("rear", "street", "both")
SOURCES = ("own", "line")

SCHEMA = """
CREATE TABLE exposure(unit_id TEXT PRIMARY KEY, exposure TEXT NOT NULL,
  source TEXT NOT NULL, street_kind TEXT, line_votes INTEGER, bedroom TEXT);
"""


def install(db: sqlite3.Connection, path: Path, labels, units: set[str]) -> dict:
    """Copy the labels (rows of the labels file) of this build's units into
    the build."""
    rows = [
        (
            r["unit_id"],
            r["exposure"],
            r["source"],
            r.get("street_kind") or None,
            r.get("line_votes"),
            r.get("bedroom") if r.get("bedroom") in ("rear", "street") else None,
        )
        for r in labels
        if r["unit_id"] in units
        and r.get("exposure") in SIDES
        and r.get("source") in SOURCES
    ]
    db.executescript(SCHEMA)
    db.executemany("INSERT INTO exposure VALUES (?,?,?,?,?,?)", rows)
    return {"installed": True, "file": str(path.resolve()), "units": len(rows)}


def describe(row) -> dict | None:
    """The words for a unit's label: "long" for the listing page, "short" for
    listing tables, "bedroom" when an ad says which way the bedroom faces."""
    if row is None:
        return None
    side, own = row["exposure"], row["source"] == "own"
    street = (
        f"the street ({row['street_kind']})" if row["street_kind"] else "the street"
    )
    where = {
        "rear": "the rear or a courtyard",
        "street": street,
        "both": f"both {street} and the rear",
    }[side]
    if own:
        long = f"Faces {where}"
    else:
        votes = row["line_votes"] or 0
        others = (
            f"{votes} other apartment{'' if votes == 1 else 's'}"
            if votes
            else "the other apartments"
        )
        verb = "does" if votes == 1 else "do"
        long = (
            f"Likely faces {where}: {others} in its line (same letter or number) {verb}"
        )
    short = {
        "rear": "rear-facing",
        "street": "street-facing",
        "both": "front and rear",
    }[side]
    bedroom = {"rear": "the rear or garden", "street": "the street"}.get(row["bedroom"])
    return {
        "side": side,
        "own": own,
        "long": long,
        "short": short if own else f"likely {short}",
        "bedroom": f"The ad says the bedroom faces {bedroom}" if bedroom else None,
    }
