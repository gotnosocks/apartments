"""Coded fields of each listing's own StreetEasy record that the analytical dataset
does not carry: private outdoor space types, room count, fireplace types, broker group,
source type and the listing's price changes (time and price of each, as JSON). Read from the granular crawls' listing observations (each listing's
last capture), keyed by listing id:

    python -m rentfrontier.listing_extras

writes EXTERNAL_ROOT/listing-extras/<date>-<commit>/listing-extras.parquet and
provenance.json. Refuses a dirty tree.
"""

from __future__ import annotations

import datetime as dt
import glob
import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

EXTERNAL_ROOT = Path("/data1/apartments/external")
CRAWLS = {
    "Chelsea": "/data1/apartments/archive/datasets/chelsea-granular-20260917-canonical-url-v1",
    "West Village": "/data1/apartments/archive/datasets/west-village-granular-20260930-canonical-url-v1",
    "Greenwich Village": "/data1/apartments/archive/datasets/greenwich-village-granular-20261005-canonical-url-v1",
    "Flatiron + Gramercy Park": "/data1/apartments/archive/datasets/flatiron-gramercy-park-granular-20261007-canonical-url-v1",
    "Stuyvesant Town/PCV": "/data1/apartments/archive/datasets/stuyvesant-town-pcv-granular-20261008-canonical-url-v1",
    "NoMad": "/data1/apartments/archive/datasets/nomad-granular-20261009-canonical-url-v1",
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


def build() -> pd.DataFrame:
    rows = []
    for neighbourhood, crawl in CRAWLS.items():
        for path in sorted(
            glob.glob(f"{crawl}/listing_observations/**/*.parquet", recursive=True)
        ):
            table = pq.read_table(
                path, columns=["listing_id", "collected_at", "raw_listing_json"]
            )
            for r in table.to_pylist():
                if r["raw_listing_json"]:
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


def main():
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("refusing a dirty tree")
    commit = _git("rev-parse", "HEAD")
    started = dt.datetime.now(dt.UTC)
    table = build()
    out_dir = EXTERNAL_ROOT / "listing-extras" / f"{started:%Y%m%d}-{commit[:7]}"
    out_dir.mkdir(parents=True, exist_ok=False)
    path = out_dir / "listing-extras.parquet"
    table.to_parquet(path, index=False)
    sources = {}
    for name, crawl in CRAWLS.items():
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
