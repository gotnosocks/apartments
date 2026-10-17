"""Coded fields of each listing's own StreetEasy record that the analytical dataset
does not carry: private outdoor space types, room count, fireplace types, broker group,
source type and the listing's price changes (time and price of each, as JSON). Read from the granular crawls' rental listing observations (each listing's
last capture), keyed by listing id. A sale listing can carry a rental's id, so
the builder skips sale observations:

    python -m rentfrontier.listing_extras
    python -m rentfrontier.listing_extras --crawl <granular dir> --tag <name>
    python -m rentfrontier.listing_extras --crawl <granular dir> --tag <name> --base <file>
    python -m rentfrontier.listing_extras --crawl records --tag <name> --base <file>

writes EXTERNAL_ROOT/listing-extras/<date>-<commit>[-<tag>]/listing-extras.parquet
and provenance.json, from the crawls in CRAWLS or from the one crawl named.
With --base, I keep that file's rows and add the crawl's rows for the listings
it lacks, as an extended cohort's added rows need. Refuses a dirty tree.

`--crawl records` reads the API records of the newest clean build in the data
pipeline's catalog in place of a granular crawl, after checking the file's
SHA-256 (`rentfrontier.api_records`). Each record counts as captured at its
last fetch, and provenance.json lists the file's name and SHA-256 under
`sources`.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd

from rentfrontier import api_records

EXTERNAL_ROOT = Path("/data1/apartments/external")
CRAWLS = {
    "Chelsea": "/data1/apartments/archive/datasets/chelsea-granular-20260917-canonical-url-v1",
    "West Village": "/data1/apartments/archive/datasets/west-village-granular-20260930-canonical-url-v1",
    "Greenwich Village": "/data1/apartments/archive/datasets/greenwich-village-granular-20261005-canonical-url-v1",
    "Flatiron + Gramercy Park": "/data1/apartments/archive/datasets/flatiron-gramercy-park-granular-20261007-canonical-url-v1",
    "Stuyvesant Town/PCV": "/data1/apartments/archive/datasets/stuyvesant-town-pcv-granular-20261008-canonical-url-v1",
    "NoMad": "/data1/apartments/archive/datasets/nomad-granular-20261009-canonical-url-v1",
    "East Village": "/data1/apartments/archive/datasets/east-village-granular-20261010-canonical-url-v1",
    "Midtown West": "/data1/apartments/archive/datasets/midtown-west-granular-20261014-canonical-url-v1",
}


def record_extras(raw: str) -> dict:
    """The fields of one raw listing record (StreetEasy's listing JSON)."""
    d = json.loads(raw)
    details = d.get("propertyDetails") or {}
    feats = details.get("features") or {}
    legacy = d.get("legacy") or {}
    return {
        "outdoor_types": "|".join(sorted(feats.get("privateOutdoorSpaceTypes") or [])),
        "fireplace_types": "|".join(sorted(feats.get("fireplaceTypes") or [])),
        "room_count": details.get("roomCount"),
        "broker_group": legacy.get("sourceGroupLabel"),
        "source_type": (d.get("listingSource") or {}).get("sourceType"),
        "price_changes": json.dumps(
            [
                [c.get("changedAt"), c.get("price")]
                for c in (d.get("pricing") or {}).get("priceChanges") or []
            ]
        ),
    }


def build(crawls: dict | None = None, records: dict | None = None) -> pd.DataFrame:
    """Each listing's fields from its last capture in the crawls. A crawl
    `records` is the pipeline's records file, `records` once checked."""
    rows = []
    columns = ["listing_id", "listing_type", "collected_at", "raw_listing_json"]
    for neighbourhood, crawl in (crawls or CRAWLS).items():
        for r in api_records.observations(crawl, columns, records):
            if r["listing_type"] == "rental" and r["raw_listing_json"]:
                rows.append(
                    {
                        "listing_id": str(r["listing_id"]),
                        "collected_at": r["collected_at"],
                        "neighbourhood": neighbourhood,
                        **record_extras(r["raw_listing_json"]),
                    }
                )
    out = pd.DataFrame(rows).sort_values(["collected_at", "listing_id"])
    return out.drop_duplicates("listing_id", keep="last").reset_index(drop=True)


def _git(*args) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def main(argv: list[str] | None = None):
    import sys

    argv = sys.argv[1:] if argv is None else argv
    crawls, tag, base = None, "", None
    if argv[4:5] == ["--base"] and len(argv) == 6:
        base, argv = Path(argv[5]), argv[:4]
    if argv[:1] == ["--crawl"] and argv[2:3] == ["--tag"] and len(argv) == 4:
        crawls, tag = {"crawl": argv[1]}, f"-{argv[3]}"
    elif argv:
        raise SystemExit(
            "usage: listing_extras"
            " [--crawl <granular dir | records> --tag <name> [--base <file>]]"
        )
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("refusing a dirty tree")
    commit = _git("rev-parse", "HEAD")
    started = dt.datetime.now(dt.UTC)
    records = (
        api_records.records_file()
        if api_records.CRAWL in (crawls or CRAWLS).values()
        else None
    )
    table = build(crawls, records)
    if base is not None:
        # The base file's listings keep their rows; the crawl adds the rest.
        kept = pd.read_parquet(base)
        added = table[~table.listing_id.isin(set(kept.listing_id))]
        table = pd.concat([kept, added], ignore_index=True)
    out_dir = EXTERNAL_ROOT / "listing-extras" / f"{started:%Y%m%d}-{commit[:7]}{tag}"
    out_dir.mkdir(parents=True, exist_ok=False)
    path = out_dir / "listing-extras.parquet"
    table.to_parquet(path, index=False)
    sources = {}
    for name, crawl in (crawls or CRAWLS).items():
        if crawl == api_records.CRAWL:
            sources[name] = {"path": records["path"], "sha256": records["sha256"]}
            continue
        complete = Path(crawl) / "complete.json"
        sources[name] = {
            "path": crawl,
            "complete_sha256": hashlib.sha256(complete.read_bytes()).hexdigest()
            if complete.exists()
            else None,
        }
    (out_dir / "provenance.json").write_text(
        json.dumps(
            {
                "sources": sources,
                "base": {
                    "path": str(base),
                    "sha256": hashlib.sha256(base.read_bytes()).hexdigest(),
                }
                if base
                else None,
                "built_at": started.isoformat(),
                "commit": commit,
                "listings": len(table),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "note": "each listing's last captured record (as the description evidence is)",
            },
            indent=2,
        )
    )
    print(f"wrote {path}: {len(table)} listings")


if __name__ == "__main__":
    main()
