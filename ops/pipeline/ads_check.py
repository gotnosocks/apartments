"""Check a build's ads file against the website's current captures and the ads' own histories.

    pipeline/.venv/bin/python ops/pipeline/ads_check.py [--ads FILE] [--export DIR]
        [--captures DIR] [--memory SIZE]

1. The script reads the ads file FILE, the newest ads-*.parquet under
   /data1/apartments/pipeline/datasets unless given, and prints its size, its count of rows and
   of distinct ads, and the ads by status, by whether they have a fit-ready row and by the
   other columns the website reads.
2. It reads each line of the website's API captures, DIR/api-*/details/snapshot/candidates.jsonl
   with DIR /data1/apartments/archive/current-listings unless given. It counts the captured
   ads missing from the file, the captured ads whose latest record in the file is the captured
   answer, and those with a later record in the file. A capture's `collected_at` is the fetch
   time of the answer it read, so the script matches it to the file's `fetched`. The two are
   written apart and round apart by up to a microsecond, so it takes times within a millisecond
   as one answer. For the ads of a shared answer it counts the ads whose status, ask, layout,
   size, building, unit page and flags differ between the capture and the file, and prints a
   few of each. The capture's values come from the old page-capture reading with its
   corrections, and the file's layout and flags are merged over all of an ad's records before
   any correction, so some differences are expected.
3. For each ad the file gives as ACTIVE, it reads the latest record from the export DIR,
   /data1/apartments/archive/crawls/api/export unless given, and runs the website's
   `ad_dates.last_break` over the ad's own events in the record's history, from the file's
   `on_day` to the New York day of the fetch. It counts the ads by whether that agrees with
   the file's `break_status`, `break_day` and `back_day`, and prints a few that differ. The
   history dates each change to the day, and `last_break` orders a day's changes by their
   places in the history.

It reads the export's files directly and leaves the build's database alone. DuckDB gets SIZE
of memory, 2GB unless given.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATASETS = Path("/data1/apartments/pipeline/datasets")
CAPTURES = Path("/data1/apartments/archive/current-listings")
EXPORT = Path("/data1/apartments/archive/crawls/api/export")
NEW_YORK = "America/New_York"
# Pairs of a capture field and a file column, compared on the ads whose latest record in the
# file is the captured answer.
COMPARED = [
    ("listing_status", "status"),
    ("rent", "page_price"),
    ("bedrooms", "bedrooms"),
    ("bathrooms", "bathrooms"),
    ("square_feet", "square_feet"),
    ("building_id", "building"),
    ("canonical_unit_url", "page"),
    ("furnished", "furnished"),
    ("short_term", "short_term"),
    ("elevator", "elevator"),
    ("doorman_type", "doorman_type"),
    ("laundry_type", "laundry_type"),
]


def newest(pattern: str) -> Path:
    files = sorted(DATASETS.glob(pattern), key=lambda p: p.stat().st_mtime)
    if not files:
        sys.exit(f"no {pattern} under {DATASETS}")
    return files[-1]


def show(db, title: str, sql: str) -> None:
    print(title)
    text = db.sql(sql).fetchdf().to_string(index=False)
    print("    " + text.replace("\n", "\n    "))


def captured(root: Path) -> list[dict]:
    """The compared fields of each line of the API captures under `root`, with the capture's
    folder and the fetch time of the answer it read."""
    out = []
    for path in sorted(root.glob("api-*/details/snapshot/candidates.jsonl")):
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            c = json.loads(line)
            row = {"capture": path.parents[2].name}
            row["listing_id"] = str(c["source_listing_id"])
            row["collected"] = c.get("collected_at")
            for field, _ in COMPARED:
                value = c.get(field)
                row[field] = None if value is None else str(value)
            out.append(row)
    return out


def last_break():
    spec = importlib.util.spec_from_file_location(
        "ad_dates", REPO / "src" / "apartments" / "site" / "ad_dates.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.last_break


def own_events(record: dict, listing_id: str) -> list[dict]:
    """The ad's own events in the record's history, as the website's page parser lists them."""
    events = []
    for episode in record.get("propertyHistory") or []:
        if not isinstance(episode, dict):
            continue
        ad = episode.get("listingId") or episode.get("id")
        if str(ad) != listing_id:
            continue
        for index, event in enumerate(episode.get("rentalEventsOfInterest") or []):
            if isinstance(event, dict):
                events.append(
                    {
                        "event_index": index,
                        "event_date": event.get("date"),
                        "status": event.get("status"),
                    }
                )
    return events


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ads", type=Path)
    parser.add_argument("--export", type=Path, default=EXPORT)
    parser.add_argument("--captures", type=Path, default=CAPTURES)
    parser.add_argument("--memory", default="2GB")
    args = parser.parse_args()
    import duckdb
    import pandas as pd

    ads = args.ads or newest("ads-*.parquet")
    print(f"ads: {ads} ({ads.stat().st_size / 2**20:.0f} MiB)")
    spill = tempfile.mkdtemp(prefix="ads-check-")
    db = duckdb.connect()
    db.execute(f"SET memory_limit = '{args.memory}'")
    db.execute(f"SET temp_directory = '{spill}'")
    db.execute("SET threads = 3")
    db.execute("SET TimeZone = 'UTC'")
    db.execute(f"CREATE VIEW ads AS SELECT * FROM read_parquet('{ads}')")
    show(
        db,
        "rows and ads:",
        "SELECT count(*) AS rows, count(DISTINCT listing_id) AS ads FROM ads",
    )
    show(
        db,
        "ads by status and fit-ready row:",
        """
        SELECT status, in_rows, count(*) AS ads,
            count(*) FILTER (WHERE last_change = 'ACTIVE' AND break_status IS NOT NULL)
                AS back_after_break,
            count(*) FILTER (WHERE len(floor_plans) > 0) AS with_floor_plans,
            count(*) FILTER (WHERE page IS NOT NULL) AS with_page,
            count(*) FILTER (WHERE len(ledger_entries) > 0) AS with_ledger_entries
        FROM ads GROUP BY ALL ORDER BY ads DESC
    """,
    )

    db.register("capture_lines", pd.DataFrame(captured(args.captures)))
    db.execute(
        """CREATE VIEW capture AS SELECT * REPLACE (collected::TIMESTAMPTZ AS collected)
        FROM capture_lines"""
    )
    shared = "abs(epoch_us(a.fetched) - epoch_us(c.collected)) < 1000"
    show(
        db,
        "captured ads by capture:",
        f"""
        SELECT c.capture, count(*) AS lines, count(DISTINCT c.listing_id) AS ads,
            count(DISTINCT c.listing_id) FILTER (WHERE a.listing_id IS NULL) AS not_in_file,
            count(DISTINCT c.listing_id) FILTER (WHERE {shared}) AS same_answer,
            count(DISTINCT c.listing_id)
                FILTER (WHERE epoch_us(a.fetched) - epoch_us(c.collected) >= 1000)
                AS later_answer
        FROM capture c LEFT JOIN ads a USING (listing_id)
        GROUP BY ALL ORDER BY ALL
    """,
    )
    # A capture writes numbers as Python prints them and the file's as DuckDB casts them, so
    # the numbers compare as numbers and the rest as text.
    for field, column in COMPARED:
        numeric = field in ("rent", "bedrooms", "bathrooms", "square_feet")
        left = f"try_cast(c.{field} AS DOUBLE)" if numeric else f"lower(c.{field})"
        right = f"a.{column}::DOUBLE" if numeric else f"lower(a.{column}::VARCHAR)"
        show(
            db,
            f"{field} against {column}, on the ads of a shared answer:",
            f"""
            WITH pairs AS (
                SELECT DISTINCT c.listing_id, {left} AS captured, {right} AS file
                FROM capture c JOIN ads a USING (listing_id)
                WHERE {shared}
            )
            SELECT count(*) AS ads,
                count(*) FILTER (WHERE captured IS NOT DISTINCT FROM file) AS same,
                count(*) FILTER (WHERE captured IS NULL AND file IS NOT NULL)
                    AS only_file,
                count(*) FILTER (WHERE captured IS NOT NULL AND file IS NULL)
                    AS only_capture,
                count(*) FILTER (WHERE captured <> file) AS differ,
                list(listing_id || ': ' || captured || ' / ' || file ORDER BY listing_id)
                    FILTER (WHERE captured <> file)[1:3] AS examples
            FROM pairs
        """,
        )

    files = [
        str(args.export / json.loads(line)["path"])
        for line in (args.export / "manifest.ndjson").read_text().splitlines()
        if line.endswith("}") and json.loads(line)["table"] == "ads"
    ]
    records = db.sql(
        f"""
        SELECT a.listing_id, a.on_day::VARCHAR AS since,
            (r.fetched AT TIME ZONE '{NEW_YORK}')::DATE::VARCHAR AS as_of,
            a.break_status, a.break_day::VARCHAR AS break_day, a.back_day::VARCHAR AS back_day,
            a.last_change, r.record
        FROM ads a
        JOIN read_parquet({sorted(set(files))}) r
            ON r.response_id = a.response_id AND r.listing_id = a.listing_id::BIGINT
        WHERE a.status = 'ACTIVE'
    """
    ).fetchall()
    gap = last_break()
    counts: dict[str, int] = {}
    examples: dict[str, list] = {}
    for listing_id, since, as_of, status, day, back, last, text in records:
        found = gap(own_events(json.loads(text), listing_id), since, as_of)
        file = (status, day, back) if last == "ACTIVE" else None
        if found == file:
            kind = "same, back after a break" if file and file[0] else "same"
        elif found is None:
            kind = "history ends off the market"
        elif file is None:
            kind = f"history back on the market, file's last change {last}"
        else:
            kind = "different break"
        counts[kind] = counts.get(kind, 0) + 1
        examples.setdefault(kind, []).append((listing_id, found, file))
    print(f"ACTIVE ads against the history's last break ({len(records)} ads):")
    for kind, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"    {kind}: {n}")
        if not kind.startswith("same"):
            for listing_id, found, file in examples[kind][:3]:
                print(f"        {listing_id}: history {found}, file {file}")
    print(f"checked at {dt.datetime.now(dt.UTC):%Y-%m-%dT%H:%MZ}")
    db.close()
    shutil.rmtree(spill)


if __name__ == "__main__":
    main()
