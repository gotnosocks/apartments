"""Observed listings of the pipeline's regions outside the served fit, with no estimates.

The pipeline collects Hoboken and Jersey City (region `nj-jersey-city-hoboken`) as well as New
York, and no fit covers them yet. The build reads their rows from the pipeline's newest build
(`captures.pipeline_files`) into the `observed` table, apart from the listings tables, so the
NYC pages and their estimates stay as they were. Each row gives what the ad states and the ask
the dataset keeps (the latest ask, net of any concession). The ads file adds the ad's status:
the build counts a listing as on the market when its latest answer says ACTIVE and came within
`captures.CURRENT_DAYS` of the build.

A reading of the NJ ads the screen flagged (`READS`, one verdict per ad, read in full by Sonnet
readers) found room shares, shops and offices, and a vacation rental among them. The build
leaves those out (`HIDDEN` verdicts) and counts them by verdict for the page.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import duckdb

from . import captures

REGIONS = {"nj-jersey-city-hoboken": "Hoboken and Jersey City"}
READS = (
    Path(__file__).resolve().parents[3]
    / "config"
    / "reviews"
    / "nj-ad-reads-20261019.jsonl"
)
# The verdicts the build leaves out, each with its words for one ad and for several.
HIDDEN = {
    "ROOM_SHARE": ("room share", "room shares"),
    "COMMERCIAL": ("shop or office", "shops or offices"),
    "SHORT_STAY": ("short stay", "short stays"),
}

QUERY = """
SELECT r.listing_id, r.unit_id, r.page AS unit_url, r.building, r.neighbourhood,
  r.price_at::VARCHAR AS price_at, strftime(r.period, '%Y-%m-01') AS period,
  r.latest_ask AS ask, r.latest_gross AS gross_ask, r.bedrooms, r.bathrooms,
  r.square_feet, coalesce(r.physical_floor, r.advertised_floor) AS floor,
  r.elevator, r.laundry_type AS laundry, r.doorman_type AS doorman,
  r.pet_policy AS pets, r.months_free, r.lease_term,
  a.status, a.fetched::TIMESTAMP AS fetched
FROM read_parquet($rows) r LEFT JOIN read_parquet($ads) a USING (listing_id)
WHERE list_has_any(r.regions, $regions)
ORDER BY r.listing_id
"""


def hidden(path: Path | None = None) -> dict[str, str]:
    """The verdict of each read listing the build leaves out, by listing id, from `path`
    (READS by default)."""
    path = path or READS
    if not path.is_file():
        return {}
    reads = (json.loads(line) for line in path.read_text().splitlines() if line)
    return {r["listing_id"]: r["verdict"] for r in reads if r["verdict"] in HIDDEN}


def rows(
    files: dict | None, at: dt.datetime | None = None, reads: Path | None = None
) -> tuple[list[dict], dict]:
    """The site's observed rows of REGIONS from the pipeline files, and a status for build.json."""
    if files is None:
        return [], {"rows": 0, "reason": "no pipeline build to read listings from"}
    at = at or captures.now()
    con = duckdb.connect()
    try:
        con.execute("SET TimeZone = 'UTC'")
        columns = {
            name
            for name, *_ in con.execute(
                "DESCRIBE SELECT * FROM read_parquet(?)", [files["rows"]]
            ).fetchall()
        }
        if "regions" not in columns:
            return [], {"rows": 0, "reason": "the rows file has no regions column"}
        cursor = con.execute(
            QUERY,
            {"rows": files["rows"], "ads": files["ads"], "regions": list(REGIONS)},
        )
        names = [d[0] for d in cursor.description]
        found = [dict(zip(names, values)) for values in cursor.fetchall()]
    finally:
        con.close()
    from .build import building_names, unit_label

    left_out = hidden(reads)
    start = at - dt.timedelta(days=captures.CURRENT_DAYS)
    out, dropped = [], {}
    for r in found:
        verdict = left_out.get(r["listing_id"])
        if verdict:
            dropped[verdict] = dropped.get(verdict, 0) + 1
            continue
        if r["ask"] is None:
            continue
        fetched = r.pop("fetched")
        fetched = fetched.replace(tzinfo=dt.UTC) if fetched else None
        status = r.pop("status")
        r["is_current"] = int(
            status == "ACTIVE" and fetched is not None and start <= fetched <= at
        )
        r["seen_at"] = fetched.isoformat() if fetched else None
        r["building_name"] = building_names(r["building"] or "", None)[1]
        r["unit_label"] = unit_label(r["unit_url"])
        r["listing_url"] = (
            f"https://streeteasy.com/rental/{r['listing_id']}"
            if r["listing_id"].isdigit()
            else None
        )
        r["elevator"] = {True: "yes", False: "no"}.get(r["elevator"])
        r["concession"] = captures.concession(r)
        r["floor"] = None if r["floor"] is None else int(r["floor"])
        for key in ("months_free", "lease_term", "gross_ask"):
            r.pop(key)
        out.append(r)
    return out, {
        "rows": len(out),
        "current": sum(r["is_current"] for r in out),
        "regions": list(REGIONS),
        "left_out": dict(sorted(dropped.items())),
        "reads": str(reads or READS),
    }
