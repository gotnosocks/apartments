"""Who listed each advertisement, from its own StreetEasy record: the lister's name
(`legacy.sourceGroupLabel`), whether the record carries a broker's licence, the
source type (PARTNER, FEED or OWNER), and two classifications that read no rent:

- `kind`: management (landlords and management companies), brokerage, owner (an
  OWNER listing) or other, from the lister's name (`BROKERAGE`, then
  `MANAGEMENT`; the patterns of the 2026-10-09 research review).
- `earlier` and `earlier_same`: how many of the building's captured rental
  listings were first listed before this one, and how many of those were by
  the same lister. Excluded listings count; listings with no ACTIVE rental
  event (no `listed_at`) count for none, and unnamed listers share one name. The lister is the building's own
  agent (`own_agent`) when it listed at least `AGENT_SHARE` of at least
  `AGENT_MIN_EARLIER` earlier listings: a management company or an exclusive
  leasing broker.

The lister name says little alone: about a fifth of the brokerages' names carry
no licence on the record (Citi Habitats, Halstead), and exclusive brokers act
for one landlord. Keyed by listing id, from the granular crawls (each listing's
last capture, as `rentfrontier.listing_extras`), listed from the earliest
ACTIVE rental event of the listing itself:

    python -m rentfrontier.lister
    python -m rentfrontier.lister --crawl page --crawl records --tag <name>

writes EXTERNAL_ROOT/lister/<date>-<commit><-name>/lister.parquet and
provenance.json. Refuses a dirty tree.

Each `--crawl` names a granular crawl's folder, `page` for the page crawls
(`CRAWLS`) or `records` for the API records of the newest clean build in the
data pipeline's catalog (`rentfrontier.api_records`). For the records file, I
check its SHA-256 and that of the ads file on the same catalog line, take each
listing's building from the ads file, and read the listed day from the rental
history in each of the listing's records, as the granular export's event
mentions give it. Each record counts as captured at its last fetch.
provenance.json lists both files under `sources`.
"""

from __future__ import annotations

import datetime as dt
import glob
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from rentfrontier import api_records
from rentfrontier.listing_extras import CRAWLS, EXTERNAL_ROOT

BROKERAGE = (
    r"Realty|Real Estate|Realtor|Sotheby|Elliman|Corcoran|Compass|Habitats|Halstead"
    r"|Bond New York|^CORE|Brown Harris|Town Residential|Mirador|City Wide"
    r"|Living New York|REAL New York|Bold New York|Oxford Property Group"
    r"|Quality Living|^MNS|^R New York|Nest Seekers|Keller Williams|Warburg|Spire"
    r"|Triplemint|Serhant|Coldwell|Fox Residential|Level Group|Smart City"
    r"|Manhattan Apartments|eXp|Brokerage|Leslie J. Garfield|Stribling|Engel"
    r"|Christie|Douglas|Platinum Properties|Kian|Exit|Siderow|Apartments"
)
MANAGEMENT = (
    r"Related|Equity Residential|StuyTown|Rose Associates|Rockrose|Brodsky"
    r"|Centennial|PRESTON|Metropolitan Property|Cornerstone|Stonehenge"
    r"|Clinton Management|^UDR|Beam Living|Glenwood|Lalezarian|Heller|Buchbinder"
    r"|Taichi|Moinian|Gotham|Durst|Fetner|Avalon|Greystar|Brookfield|Extell"
    r"|Dermot|Bozzuto|Silverstein|Two Trees|Jakobson|Pinnacle|Croman|Stellar"
    r"|Solil|Milford|Carlyle|Feil|Management|Mgmt|Properties|Property Services"
    r"|Residential|Rentals|Organization|Owner|Leasing"
)
AGENT_SHARE = 0.5
AGENT_MIN_EARLIER = 5


def record_lister(raw: str) -> dict:
    """The lister fields of one raw listing record (StreetEasy's listing JSON)."""
    d = json.loads(raw)
    legacy = d.get("legacy") or {}
    licence = legacy.get("license") or {}
    return {
        "lister": legacy.get("sourceGroupLabel"),
        "licensed": licence.get("licenseType") is not None,
        "source_type": (d.get("listingSource") or {}).get("sourceType"),
    }


def kind(lister: pd.Series, source_type: pd.Series) -> pd.Series:
    """management, brokerage, owner or other: brokerage names first."""
    name = lister.fillna("")
    return pd.Series(
        np.select(
            [
                source_type.eq("OWNER").to_numpy(),
                name.str.contains(BROKERAGE).to_numpy(),
                name.str.contains(MANAGEMENT).to_numpy(),
            ],
            ["owner", "brokerage", "management"],
            "other",
        ),
        index=lister.index,
    )


def earlier_counts(listings: pd.DataFrame) -> pd.DataFrame:
    """Per listing (columns building, lister, listed_at): the building's listings
    first listed on an earlier day, and those by the same lister."""
    d = listings.assign(lister=listings.lister.fillna(""))
    d = d.sort_values(["building", "listed_at", "listing_id"])
    day = d.listed_at.dt.floor("D")
    earlier = d.groupby("building").cumcount() - d.groupby(["building", day]).cumcount()
    same = (
        d.groupby(["building", "lister"]).cumcount()
        - d.groupby(["building", "lister", day]).cumcount()
    )
    return pd.DataFrame(
        {"earlier": earlier, "earlier_same": same}, index=d.index
    ).reindex(listings.index)


def own_agent(earlier: pd.Series, earlier_same: pd.Series) -> pd.Series:
    """own (the lister listed at least AGENT_SHARE of the building's earlier
    listings), outside, or few_earlier (under AGENT_MIN_EARLIER of them)."""
    earlier = earlier.astype(float)
    share = earlier_same.astype(float) / earlier.where(earlier > 0)
    return pd.Series(
        np.select(
            [
                (earlier < AGENT_MIN_EARLIER).to_numpy(),
                (share >= AGENT_SHARE).to_numpy(),
            ],
            ["few_earlier", "own"],
            "outside",
        ),
        index=earlier.index,
    )


def _first_listed(crawl: str) -> pd.Series:
    ev = pd.read_parquet(
        f"{crawl}/event_mentions",
        columns=[
            "listing_id",
            "event_listing_id",
            "event_category",
            "event_date",
            "status",
        ],
    )
    own = (
        ev.listing_id.eq(ev.event_listing_id)
        & ev.event_category.eq("rental")
        & ev.status.eq("ACTIVE")
    )
    return ev[own].groupby("listing_id").event_date.min()


def record_first_listed(raw: str, listing_id: str) -> str | None:
    """The earliest day of an ACTIVE event in the listing's own rental history
    in one raw record, with each episode and event the granular export's parser
    turns into an event mention."""
    history = json.loads(raw).get("propertyHistory")
    days = []
    for episode in history if isinstance(history, list) else []:
        if not isinstance(episode, dict):
            continue
        episode_id = episode.get("listingId") or episode.get("id")
        if (listing_id if episode_id is None else str(episode_id)) != listing_id:
            continue
        events = episode.get("rentalEventsOfInterest")
        for event in events if isinstance(events, list) else []:
            if (
                isinstance(event, dict)
                and event.get("status") == "ACTIVE"
                and event.get("date") is not None
            ):
                days.append(event["date"])
    return min(days, default=None)


def _from_records(records: dict, ads: dict) -> tuple[list[dict], pd.Series]:
    """Each record's lister fields with the building of its listing in the ads
    file, and each listing's earliest listed day over its records."""
    building = dict(
        zip(
            *pq.read_table(ads["path"], columns=["listing_id", "building"])
            .to_pydict()
            .values()
        )
    )
    rows, first = [], {}
    columns = ["listing_id", "listing_type", "collected_at", "raw_listing_json"]
    for r in api_records.captures(records, columns):
        if r["listing_type"] != "rental" or not r["raw_listing_json"]:
            continue
        rows.append(
            {
                "listing_id": r["listing_id"],
                "building": building.get(r["listing_id"]),
                "collected_at": r["collected_at"],
                **record_lister(r["raw_listing_json"]),
            }
        )
        day = record_first_listed(r["raw_listing_json"], r["listing_id"])
        if day is not None and (
            r["listing_id"] not in first or day < first[r["listing_id"]]
        ):
            first[r["listing_id"]] = day
    return rows, pd.Series(first, dtype=object)


def catalog_files() -> tuple[dict, dict]:
    """The records and ads files of the newest clean build in the pipeline's
    catalog, each checked."""
    records = api_records.records_file()
    return records, records["ads"]


def build(
    crawls: dict | None = None, records: dict | None = None, ads: dict | None = None
) -> pd.DataFrame:
    """Each listing's lister from its last capture in the crawls. A crawl
    `records` is the pipeline's records file, `records` and `ads` the checked
    records and ads files of one catalog line."""
    rows, firsts = [], []
    for crawl in (crawls or CRAWLS).values():
        if crawl == api_records.CRAWL:
            if records is None:
                records, ads = catalog_files()
            added, first = _from_records(records, ads)
            rows += added
            firsts.append(first)
            continue
        firsts.append(_first_listed(crawl))
        for path in sorted(
            glob.glob(f"{crawl}/listing_observations/**/*.parquet", recursive=True)
        ):
            for batch in pq.ParquetFile(path).iter_batches(
                batch_size=2000,
                columns=[
                    "listing_id",
                    "listing_type",
                    "building_slug",
                    "collected_at",
                    "raw_listing_json",
                ],
            ):
                for r in batch.to_pylist():
                    if r["listing_type"] == "rental" and r["raw_listing_json"]:
                        rows.append(
                            {
                                "listing_id": str(r["listing_id"]),
                                "building": r["building_slug"],
                                "collected_at": r["collected_at"],
                                **record_lister(r["raw_listing_json"]),
                            }
                        )
    out = pd.DataFrame(rows).sort_values(["collected_at", "listing_id"])
    out = out.drop_duplicates("listing_id", keep="last").reset_index(drop=True)
    first = pd.concat(firsts).groupby(level=0).min()
    out["listed_at"] = pd.to_datetime(
        out.listing_id.map(first), errors="coerce", utc=True
    )
    out["kind"] = kind(out.lister, out.source_type)
    dated = out.listed_at.notna() & out.building.notna()
    counts = earlier_counts(out[dated])
    out["earlier"] = counts.earlier.reindex(out.index).astype("Int64")
    out["earlier_same"] = counts.earlier_same.reindex(out.index).astype("Int64")
    return out.drop(columns="collected_at")


def _git(*args) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def parse(argv: list[str]) -> tuple[dict | None, str]:
    """The crawls and the directory tag a command line names."""
    crawls, tag = {}, ""
    while argv[:1] == ["--crawl"] and len(argv) > 1:
        if argv[1] == "page":
            crawls.update(CRAWLS)
        else:
            crawls[f"crawl-{len(crawls)}" if crawls else "crawl"] = argv[1]
        argv = argv[2:]
    if crawls and argv[:1] == ["--tag"] and len(argv) == 2:
        tag, argv = f"-{argv[1]}", []
    if argv:
        raise SystemExit(
            "usage: lister [--crawl <page | granular dir | records>]... [--tag <name>]"
        )
    return crawls or None, tag


def main(argv: list[str] | None = None):
    import sys

    crawls, tag = parse(sys.argv[1:] if argv is None else argv)
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("refusing a dirty tree")
    commit = _git("rev-parse", "HEAD")
    started = dt.datetime.now(dt.UTC)
    records, ads = (
        catalog_files()
        if api_records.CRAWL in (crawls or CRAWLS).values()
        else (None, None)
    )
    table = build(crawls, records, ads)
    out_dir = EXTERNAL_ROOT / "lister" / f"{started:%Y%m%d}-{commit[:7]}{tag}"
    out_dir.mkdir(parents=True, exist_ok=False)
    path = out_dir / "lister.parquet"
    table.to_parquet(path, index=False)
    sources = {}
    for name, crawl in (crawls or CRAWLS).items():
        if crawl == api_records.CRAWL:
            sources[name] = {"path": records["path"], "sha256": records["sha256"]}
            sources["ads_file"] = {"path": ads["path"], "sha256": ads["sha256"]}
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
                "built_at": started.isoformat(),
                "commit": commit,
                "listings": len(table),
                "dated": int(table.listed_at.notna().sum()),
                "kinds": table.kind.value_counts().to_dict(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "note": "each listing's last captured record; no rent read",
            },
            indent=2,
        )
    )
    print(f"wrote {path}: {len(table)} listings")


if __name__ == "__main__":
    main()
