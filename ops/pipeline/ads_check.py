"""Check a build's ads file against the ads' own histories.

    pipeline/.venv/bin/python ops/pipeline/ads_check.py [--ads FILE] [--export DIR]
        [--memory SIZE]

1. The script reads the ads file FILE, the newest ads-*.parquet under
   /data1/apartments/pipeline/datasets unless given, and prints its size, its count of rows and
   of distinct ads, and the ads by status, by whether they have a fit-ready row and by the
   other columns the website reads.
2. For each ad the file gives as ACTIVE, it reads the latest record from the export DIR,
   /data1/apartments/archive/crawls/api/export unless given, and runs `last_break` over the
   ad's own events in the record's history, from the file's `on_day` to the New York day of
   the fetch. `last_break` is the website's reading of an ad's history from before #945, when
   the site read the histories itself. The script counts the ads by whether its result agrees
   with the file's `break_status`, `break_day` and `back_day`, and prints a few that differ.
   The history dates each change to the day, and `last_break` orders a day's changes by their
   places in the history. It counts ACTIVE ads without an `on_day` apart, since `last_break`
   needs one.

It reads the export's files directly and leaves the build's database alone. DuckDB gets SIZE
of memory, 2GB unless given, and spills to a scratch folder under TMPDIR, which the script
removes at the end.
"""

from __future__ import annotations

import argparse
import datetime as dt
import itertools
import json
import shutil
import sys
import tempfile
from pathlib import Path

DATASETS = Path("/data1/apartments/pipeline/datasets")
EXPORT = Path("/data1/apartments/archive/crawls/api/export")
NEW_YORK = "America/New_York"


def newest(pattern: str) -> Path:
    files = sorted(DATASETS.glob(pattern), key=lambda p: p.stat().st_mtime)
    if not files:
        sys.exit(f"no {pattern} under {DATASETS}")
    return files[-1]


def show(db, title: str, sql: str) -> None:
    print(title)
    text = db.sql(sql).fetchdf().to_string(index=False)
    print("    " + text.replace("\n", "\n    "))


def last_break(events: list[dict], since: str, as_of: str):
    """The ad's latest break (status, date) and the day it came back on the market, from its
    own dated status events; (None, None, None) if it has been on the market without a break
    since `since`, and None if its events end off the market."""
    # StreetEasy lists events newest first, so on a shared day the higher event_index is the
    # earlier one.
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
        return None
    return found


def _date(value) -> str | None:
    try:
        return dt.date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        return None


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
    parser.add_argument("--memory", default="2GB")
    args = parser.parse_args()
    import duckdb

    ads = args.ads or newest("ads-*.parquet")
    print(f"ads: {ads} ({ads.stat().st_size / 2**20:.0f} MiB)")
    scratch = Path(tempfile.mkdtemp(prefix="ads-check-"))
    db = None
    try:
        db = duckdb.connect()
        db.execute(f"SET memory_limit = '{args.memory}'")
        db.execute(f"SET temp_directory = '{scratch / 'spill'}'")
        db.execute("SET threads = 3")
        db.execute("SET TimeZone = 'UTC'")
        check(db, args, ads)
    finally:
        if db is not None:
            db.close()
        shutil.rmtree(scratch)


def check(db, args, ads: Path) -> None:
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
    counts: dict[str, int] = {}
    examples: dict[str, list] = {}
    for listing_id, since, as_of, status, day, back, last, text in records:
        if since is None:
            counts["no on_day"] = counts.get("no on_day", 0) + 1
            examples.setdefault("no on_day", []).append((listing_id, None, None))
            continue
        found = last_break(own_events(json.loads(text), listing_id), since, as_of)
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


if __name__ == "__main__":
    main()
