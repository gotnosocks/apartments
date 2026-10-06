"""Unit-id pairs that a StreetEasy unit page's own rental history joins.

A unit page lists the ads of its apartment's past rentals. When an ad the
canonical-url-v1 transform filed under unit A appears in unit B's page history,
A and B are one apartment written two ways. West Village and Greenwich Village
crawls record these memberships (`collection_memberships`); the Chelsea crawl
predates that table, so its saved unit pages are parsed here with the
crawler's own rule (`streeteasy_archive.collection_policy.annotate`).

Writes one JSON line per unordered pair (first evidence only) and a provenance
file beside it. Needs the repo's `src` on PYTHONPATH (apartments, parsel).

    PYTHONPATH=src python frontier/scripts/unit_history_pairs.py OUT.jsonl
"""

import gzip
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ARCHIVE = Path("/data1/apartments/archive")
PARTS = {
    "Chelsea": (
        "datasets/chelsea-granular-20260917-canonical-url-v1",
        "snapshots/chelsea-backfill-20260912/archive.sqlite3",
    ),
    "West Village": (
        "datasets/west-village-granular-20260930-canonical-url-v1",
        "snapshots/west-village-backfill-20260930/archive.sqlite3",
    ),
    "Greenwich Village": (
        "datasets/greenwich-village-granular-20261005-canonical-url-v1",
        "snapshots/greenwich-village-20261001-final/archive.sqlite3",
    ),
}


def recorded_memberships(db):
    """(listing_id, unit page url) from the crawl's collection_memberships."""
    for key, url in db.execute(
        "SELECT listing_key, unit_url FROM collection_memberships"
    ):
        match = re.fullmatch(r"rental:(\d+):detail", key or "")
        if match and url:
            yield match[1], url


def parsed_memberships(db, urls):
    """The same pairs, parsed from the latest saved body of each unit page
    (the crawler records every fetch; the latest page lists the most history)."""
    from apartments.granular_parse import parse_listing

    latest = {}
    for url, digest, fetched in db.execute(
        "SELECT url, body_hash, fetched FROM observations WHERE status = 200"
        " AND body_hash IS NOT NULL AND url LIKE 'https://streeteasy.com/building/%'"
    ):
        if url in urls and fetched > latest.get(url, ("", -1.0))[1]:
            latest[url] = (digest, fetched)
    for url, (digest, _) in latest.items():
        body = gzip.decompress(
            (ARCHIVE / "bodies" / digest[:2] / f"{digest}.gz").read_bytes()
        )
        row, events = parse_listing(body, url)
        rental = [e for e in events if e["event_category"] == "rental"]
        # collection_policy.annotate's eligibility, for a unit page (url == its unit).
        if not (
            row.get("canonical_unit_url") == url
            and not row.get("canonical_unit_error")
            and row.get("listing_id")
            and row.get("listing_type") == "rental"
            and rental
            and row.get("parse_status") == "ok"
        ):
            continue
        ids = {
            str(e["event_listing_id"])
            for e in rental
            if str(e.get("event_listing_id", "")).isdigit()
        }
        ids.add(str(row["listing_id"]))
        yield from ((i, url) for i in ids)


def pairs(neighbourhood, dataset, snapshot):
    units = pd.read_parquet(
        dataset / "rental_units/derived.parquet",
        columns=["unit_id", "canonical_unit_url"],
    )
    members = pd.read_parquet(
        dataset / "rental_unit_memberships/derived.parquet",
        columns=["listing_id", "unit_id", "status"],
    )
    members = members[members.status.eq("associated")]
    db = sqlite3.connect(snapshot.resolve().as_uri() + "?mode=ro", uri=True)
    tables = {
        r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    if "collection_memberships" in tables:
        found = recorded_memberships(db)
    else:
        found = parsed_memberships(db, set(units.canonical_unit_url))
    evidence = pd.DataFrame(
        list(found), columns=["listing_id", "unit_url"]
    ).drop_duplicates()
    db.close()
    evidence["page_unit"] = evidence.unit_url.map(
        dict(zip(units.canonical_unit_url, units.unit_id))
    )
    e = evidence.merge(members[["listing_id", "unit_id"]], on="listing_id")
    e = e[e.page_unit.notna() & (e.page_unit != e.unit_id)]
    e["a"] = e[["unit_id", "page_unit"]].min(axis=1)
    e["b"] = e[["unit_id", "page_unit"]].max(axis=1)
    e = e.sort_values(["a", "b", "listing_id"]).drop_duplicates(["a", "b"])
    return [
        {
            "unit_id": a,
            "other_unit_id": b,
            "listing_id": lid,
            "unit_url": url,
            "neighbourhood": neighbourhood,
        }
        for a, b, lid, url in zip(e.a, e.b, e.listing_id, e.unit_url)
    ]


def main(out):
    out = Path(out)
    rows, parts = [], []
    for name, (dataset, snapshot) in PARTS.items():
        found = pairs(name, ARCHIVE / dataset, ARCHIVE / snapshot)
        rows += found
        parts.append(
            {
                "neighbourhood": name,
                "dataset": str(ARCHIVE / dataset),
                "snapshot": str(ARCHIVE / snapshot),
                "pairs": len(found),
            }
        )
    out.write_text("".join(json.dumps(r) + "\n" for r in rows))
    provenance = {
        "made_by": "frontier/scripts/unit_history_pairs.py",
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "parts": parts,
        "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
    }
    out.with_suffix(".provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n"
    )


if __name__ == "__main__":
    main(sys.argv[1])
