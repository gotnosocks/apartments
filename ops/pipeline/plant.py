"""Plant known errors in a copy of the scraper's export, build both copies and count the errors
that reach the fit-ready rows.

    pipeline/.venv/bin/python ops/pipeline/plant.py --work DIR [--export DIR] [--per-kind N]
        [--seed TEXT] [--kinds KIND,...]

The script works in these steps:

1. It builds EXPORT, the sample `ops/pipeline/sample.py` writes unless given, into WORK/clean
   with `ops/pipeline/build.py`. On a later run with the same WORK, the build finds its state
   in place and rebuilds only what a change to the export or the code calls for.
2. From the clean ads file it takes the ads with a fit-ready row, no ledger entry, a page price,
   a latest ask and a bedroom count from 0 to 4. It orders them by the MD5 hash of the seed
   and the ad's ID, `plant` unless given, and deals N ads, 50 unless given, to each kind of
   error in KINDS in turn, so each ad gets at most one error.
3. It writes WORK/planted/export, a copy of EXPORT with the errors in it, and
   WORK/planted/key.json, which lists each planted ad with its kind and the value the error
   gives it. Each error comes in as it could from StreetEasy:
   - In a later answer. For the kinds ending in `_latest` and for `future_active`, a new
     answer an hour after the ad's latest one carries a copy of that answer's record with the
     error: a price change to 10 times or a tenth of the page price, another bedroom count, or
     an ACTIVE event in the ad's own history 30 days after the fetch. The price change comes
     while the ad was on the market, halfway from its last price change to its off-market day.
     For an ad still on the market, the change comes halfway to a minute before the fetch.
     When the last change came on or after the off-market day, the change comes a minute
     after it, and `ads.kept_changes` drops it as a late placeholder.
     These answers go in a run of their own, one past the export's last.
   - In every record. For the kinds ending in `_all`, every record of the ad gives its prices
     times 10 or 100, or another bedroom count. Every other ad's history gives the ad's events
     with the same prices.
   It recomputes `record_sha256` for each record it changes, rewrites each ads file with its
   answers in the same order and copies the buildings files. The manifest lists each file with
   its new SHA-256.
4. It builds WORK/planted/export into WORK/planted the same way.
5. It compares the two builds ad by ad, reading the ask from the ads file's `latest_ask` and
   the bedrooms from the rows file. For each kind it counts the planted ads the planted build
   drops, by the reasons the ads file gives, and the ads it keeps with their clean value, with
   the planted value or with another value. It counts the kept ads with the ads file's
   `ask_check`, which the check lists for review, and the other ads it keeps with the planted
   value as missed. For the ask errors it counts the kept ads by the step of
   `analysis.latest_ask` giving the ask, its `how`, read from the planted build's state. It also counts the ads without an error whose row changes
   between the builds, as a planted ad's error can move its building's median ask. It prints
   the counts and writes them to WORK/report.json.

Another bedroom count means one more, or 3 for 4 bedrooms. A value counts as the planted or the
clean value within half a percent. Each build runs with `PIPELINE_MEMORY` and
`PIPELINE_WORKERS` from the environment, or 1500MB and 2 workers, and the city cache of
`config.py`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
SAMPLE = Path("/data1/apartments/pipeline/sample/export")
NEW_YORK = ZoneInfo("America/New_York")
FACTORS = {
    "ask_x10_latest": 10,
    "ask_div10_latest": 0.1,
    "ask_x10_all": 10,
    "ask_x100_all": 100,
}
KINDS = (
    "ask_x10_latest",
    "ask_div10_latest",
    "beds_flip_latest",
    "future_active",
    "ask_x10_all",
    "ask_x100_all",
    "beds_flip_all",
)
# Quoted runs of digits, as ads' IDs appear in a record's text.
QUOTED = re.compile(r'"(\d+)"')


def build(export: Path, folder: Path) -> dict:
    """Build `export` into `folder` with build.py, and return the build's catalog line."""
    env = dict(
        os.environ,
        PYTHONPATH=os.pathsep.join([str(REPO / "pipeline"), str(REPO / "src")]),
        PIPELINE_MEMORY=os.environ.get("PIPELINE_MEMORY", "1500MB"),
        PIPELINE_WORKERS=os.environ.get("PIPELINE_WORKERS", "2"),
    )
    command = [sys.executable, str(REPO / "ops" / "pipeline" / "build.py")]
    command += ["--export", str(export), "--state", str(folder / "state")]
    command += ["--out", str(folder / "out")]
    started = time.monotonic()
    done = subprocess.run(command, env=env, capture_output=True, text=True)
    if done.returncode:
        lines = (done.stdout + done.stderr).splitlines()
        sys.exit(f"the build of {export} failed:\n" + "\n".join(lines[-30:]))
    print(f"built {export} in {time.monotonic() - started:.0f} s", flush=True)
    catalog = (folder / "out" / "catalog.ndjson").read_text().splitlines()
    return json.loads(catalog[-1])


def flip(bedrooms: int) -> int:
    return bedrooms + 1 if bedrooms < 4 else 3


def episodes(record: dict, listing_id: int) -> list[dict]:
    """The parts of the record's history for ad `listing_id`."""
    return [
        e
        for e in record.get("propertyHistory") or []
        if isinstance(e, dict)
        and str(e.get("listingId") or e.get("id")) == str(listing_id)
    ]


def scale(record: dict, listing_id: int, factor: float, own: bool) -> None:
    """Multiply the prices of ad `listing_id` in `record` by `factor`: its events in the
    history, and when `own`, the record's pricing."""

    def times(value):
        return value if value is None else round(value * factor)

    for episode in episodes(record, listing_id):
        for event in episode.get("rentalEventsOfInterest") or []:
            if isinstance(event, dict) and "price" in event:
                event["price"] = times(event["price"])
    if own and isinstance(record.get("pricing"), dict):
        pricing = record["pricing"]
        for key in ("price", "rentedPrice"):
            if key in pricing:
                pricing[key] = times(pricing[key])
        for change in pricing.get("priceChanges") or []:
            change["price"] = times(change.get("price"))


def plant_every(
    listing_id: int, text: str | None, planted: dict[int, str]
) -> str | None:
    """`text` with the errors of the `_all` kinds in `planted`, for the ads it gives."""
    if text is None:
        return None
    ads = {int(i) for i in QUOTED.findall(text)} | {listing_id}
    ads &= planted.keys()
    if not ads:
        return text
    record = json.loads(text)
    for ad in sorted(ads):
        kind = planted[ad]
        own = ad == listing_id
        if kind in FACTORS:
            scale(record, ad, FACTORS[kind], own)
        elif own:
            details = record.get("propertyDetails")
            if isinstance(details, dict) and details.get("bedroomCount") is not None:
                details["bedroomCount"] = flip(details["bedroomCount"])
    return json.dumps(record)


def instant(text: str) -> dt.datetime:
    """The instant a record's date or time gives, a date counting from New York's midnight."""
    value = dt.datetime.fromisoformat(text)
    return value if value.tzinfo else value.replace(tzinfo=NEW_YORK)


def change_time(record: dict, fetched: dt.datetime) -> dt.datetime:
    """The time of a planted price change: halfway from the ad's last price change, or its
    first day, to its off-market day, or to a minute before `fetched` for an ACTIVE ad or one
    without that day. When the last change came on or after the off-market day, the planted
    change comes a minute after it, as a late change."""
    pricing = record.get("pricing") or {}
    times = [
        instant(change["changedAt"])
        for change in pricing.get("priceChanges") or []
        if change.get("changedAt")
    ]
    first = record.get("onMarketAt") or record.get("createdAt")
    if first:
        times.append(instant(first))
    start = max(times, default=fetched - dt.timedelta(days=1))
    end = fetched - dt.timedelta(minutes=1)
    if record.get("status") != "ACTIVE" and record.get("offMarketAt"):
        end = instant(record["offMarketAt"])
    if end <= start:
        return start + dt.timedelta(minutes=1)
    return start + (end - start) / 2


def plant_later(record: dict, listing_id: int, kind: str, fetched: dt.datetime):
    """Put the error of `kind` in `record`, the copy of the ad's latest record for an answer
    fetched at `fetched`, and return the value the error gives the ad."""
    local = fetched.astimezone(NEW_YORK)
    pricing = record.setdefault("pricing", {})
    if kind in FACTORS:
        value = round(pricing["price"] * FACTORS[kind])
        pricing["price"] = value
        at = change_time(record, fetched).astimezone(NEW_YORK)
        stamp = at.isoformat(timespec="milliseconds")
        changes = pricing.get("priceChanges") or []
        pricing["priceChanges"] = changes + [{"changedAt": stamp, "price": value}]
        return value
    if kind == "beds_flip_latest":
        details = record.get("propertyDetails") or {}
        record["propertyDetails"] = details
        value = flip(int(details.get("bedroomCount") or 0))
        details["bedroomCount"] = value
        return value
    event = {
        "__typename": "RentalStatusChangeOfInterest",
        "date": (local.date() + dt.timedelta(days=30)).isoformat(),
        "price": pricing.get("price"),
        "status": "ACTIVE",
    }
    own = episodes(record, listing_id)
    if own:
        own[0]["rentalEventsOfInterest"] = [event] + (
            own[0].get("rentalEventsOfInterest") or []
        )
    else:
        history = record.get("propertyHistory") or []
        part = {"listingId": str(listing_id), "rentalEventsOfInterest": [event]}
        record["propertyHistory"] = [part] + history
    return None


def manifest(export: Path) -> list[dict]:
    """The manifest's lines, each path once, leaving out a cut-off last line as `config.py`
    does."""
    lines = {}
    for text in (export / "manifest.ndjson").read_text().splitlines(keepends=True):
        if not text.endswith("\n") or not text.strip():
            continue
        line = json.loads(text)
        if lines.setdefault(line["path"], line)["sha256"] != line["sha256"]:
            sys.exit(f"the manifest gives {line['path']} two hashes")
    return list(lines.values())


def file_line(export: Path, line: dict) -> dict:
    data = (export / line["path"]).read_bytes()
    return dict(line, sha256=hashlib.sha256(data).hexdigest())


def write_planted(
    db, source: Path, out: Path, picks: dict[int, str], clean_ads: str
) -> dict:
    """Write the planted copy of `source` to `out`, and return the key."""
    from duckdb import sqltypes as t

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    every = {ad: kind for ad, kind in picks.items() if kind.endswith("_all")}
    db.create_function(
        "plant_every",
        lambda ad, text: plant_every(ad, text, every),
        [t.BIGINT, t.VARCHAR],
        t.VARCHAR,
        null_handling="special",
    )
    lines = []
    for line in manifest(source):
        path = out / line["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        if line["table"] != "ads":
            shutil.copyfile(source / line["path"], path)
        else:
            db.execute(
                f"""COPY (
                    SELECT * EXCLUDE (planted) REPLACE (
                        CASE WHEN planted IS DISTINCT FROM record
                        THEN sha256(planted) ELSE record_sha256 END AS record_sha256,
                        planted AS record)
                    FROM (SELECT *, plant_every(listing_id, record) AS planted
                        FROM read_parquet('{source / line["path"]}'))
                ) TO '{path}' (FORMAT parquet)"""
            )
        lines.append(file_line(out, line))

    files = [str(out / line["path"]) for line in lines if line["table"] == "ads"]
    later = sorted(ad for ad, kind in picks.items() if not kind.endswith("_all"))
    key = {}
    if later:
        lines.append(write_later(db, out, files, later, picks, clean_ads, key))
    with open(out / "manifest.ndjson", "w") as f:
        for line in lines:
            f.write(json.dumps(line, sort_keys=True) + "\n")
    return key


def write_later(
    db, out: Path, files: list[str], later: list[int], picks, clean_ads: str, key: dict
) -> dict:
    """Write the later answers of the ads in `later` to a new run of `out`, add each ad's kind
    and value to `key`, and return the file's manifest line."""
    import pandas as pd

    latest = db.sql(
        f"""SELECT r.* FROM read_parquet({files}) r
        JOIN (SELECT listing_id::BIGINT AS listing_id, response_id
            FROM read_parquet('{clean_ads}')) a USING (listing_id, response_id)
        WHERE r.listing_id IN ({", ".join(map(str, later))})
        ORDER BY r.listing_id"""
    ).fetchdf()
    top = db.sql(
        f"SELECT max(response_id), max(run) FROM read_parquet({files})"
    ).fetchone()
    first, run = int(top[0]) + 1, int(top[1]) + 1
    records = []
    for i, answer in enumerate(latest.itertuples(index=False)):
        record = json.loads(answer.record)
        fetched = answer.fetched.to_pydatetime() + dt.timedelta(hours=1)
        kind = picks[answer.listing_id]
        value = plant_later(record, answer.listing_id, kind, fetched)
        key[str(answer.listing_id)] = {"kind": kind, "value": value}
        text = json.dumps(record)
        records.append(
            answer._replace(
                fetched=fetched,
                response_id=first + i,
                run=run,
                record=text,
                record_sha256=hashlib.sha256(text.encode()).hexdigest(),
            )
        )
    frame = pd.DataFrame(records, columns=latest.columns)
    db.register("later", frame)
    name = f"responses-{first:07d}-{first + len(frame) - 1:07d}.parquet"
    line = {
        "first": first,
        "last": first + len(frame) - 1,
        "path": f"ads/run-{run:04d}/{name}",
        "rows": len(frame),
        "run": run,
        "table": "ads",
        "written": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (out / line["path"]).parent.mkdir(parents=True)
    db.execute(
        f"CREATE TEMP TABLE typed AS SELECT * FROM read_parquet('{files[0]}') LIMIT 0"
    )
    db.execute("INSERT INTO typed SELECT * FROM later")
    db.execute(f"COPY typed TO '{out / line['path']}' (FORMAT parquet)")
    return file_line(out, line)


def outcome(kind: str, row) -> str:
    if not row.in_rows:
        return "dropped"
    if kind == "future_active":
        return "kept"
    field = "bedrooms" if kind.startswith("beds") else "latest_ask"
    got, clean, value = getattr(row, field), getattr(row, f"clean_{field}"), row.value

    def near(a, b):
        return a is not None and b is not None and abs(a - b) <= 0.005 * abs(b)

    if near(got, value):
        return "kept, planted value"
    if near(got, clean):
        return "kept, clean value"
    return "kept, other value"


def run(
    export: Path,
    work: Path,
    per_kind: int = 50,
    seed: str = "plant",
    kinds: tuple[str, ...] = KINDS,
    build=build,
) -> dict:
    """Plant the errors of `kinds` in a copy of `export`, build both copies into `work` with
    `build` and return the report."""
    import duckdb
    import pandas as pd

    if export.resolve().is_relative_to(work.resolve()):
        raise ValueError(f"the export {export} lies inside the work folder {work}")
    db = duckdb.connect(config={"TimeZone": "UTC", "memory_limit": "1GB", "threads": 2})
    clean = build(export, work / "clean")
    clean_ads = str(work / "clean" / "out" / clean["ads_file"]["path"])
    clean_rows = str(work / "clean" / "out" / clean["rows"]["path"])
    quoted = seed.replace("'", "''")
    eligible = db.sql(
        f"""SELECT listing_id::BIGINT FROM read_parquet('{clean_ads}')
        WHERE in_rows AND len(ledger_entries) = 0 AND page_price IS NOT NULL
            AND latest_ask IS NOT NULL AND bedrooms IN (0, 1, 2, 3, 4)
        ORDER BY md5('{quoted}' || listing_id), listing_id
        LIMIT {per_kind * len(kinds)}"""
    ).fetchall()
    picks = {ad: kinds[i % len(kinds)] for i, (ad,) in enumerate(eligible)}
    if not picks:
        raise ValueError(f"no ad of the clean build of {export} can take an error")
    planted_export = work / "planted" / "export"
    key = write_planted(db, export, planted_export, picks, clean_ads)
    values = db.sql(
        f"""SELECT a.listing_id, a.latest_ask, r.bedrooms
        FROM read_parquet('{clean_ads}') a LEFT JOIN read_parquet('{clean_rows}') r
            USING (listing_id)
        WHERE a.listing_id IN ({", ".join(f"'{ad}'" for ad in picks)})"""
    ).fetchall()
    for listing_id, ask, bedrooms in values:
        kind = picks[int(listing_id)]
        if kind.endswith("_all"):
            value = ask * FACTORS[kind] if kind in FACTORS else flip(int(bedrooms))
            key[listing_id] = {"kind": kind, "value": value}
    (work / "planted" / "key.json").write_text(
        json.dumps(key, indent=1, sort_keys=True)
    )
    planted = build(planted_export, work / "planted")
    planted_ads = str(work / "planted" / "out" / planted["ads_file"]["path"])
    planted_rows = str(work / "planted" / "out" / planted["rows"]["path"])
    # The step of `analysis.latest_ask` giving each planted ad's ask, read from the build's
    # state once the build has closed it.
    state = work / "planted" / "state" / "pipeline.duckdb"
    with duckdb.connect(str(state), read_only=True) as planted_state:
        steps = dict(
            planted_state.execute(
                "SELECT listing_id, how FROM analysis.latest_ask "
                "WHERE listing_id IN (SELECT unnest($ads))",
                {"ads": sorted(key)},
            ).fetchall()
        )

    rows = [
        {"listing_id": ad, "kind": v["kind"], "value": v["value"]}
        for ad, v in key.items()
    ]
    db.register("key", pd.DataFrame(rows))
    side = """SELECT a.listing_id, a.in_rows, a.latest_ask, r.bedrooms, a.exclusion_reasons,
        a.identity_reasons, a.ask_check IS NOT NULL AS ask_checked, a.fate
        FROM read_parquet('{ads}') a LEFT JOIN read_parquet('{rows}') r USING (listing_id)"""
    db.execute(f"CREATE TEMP VIEW c AS {side.format(ads=clean_ads, rows=clean_rows)}")
    db.execute(
        f"CREATE TEMP VIEW p AS {side.format(ads=planted_ads, rows=planted_rows)}"
    )
    compared = db.sql(
        """SELECT k.kind, k.listing_id, k.value::DOUBLE AS value,
            c.latest_ask AS clean_latest_ask, c.bedrooms AS clean_bedrooms,
            p.in_rows, p.latest_ask, p.bedrooms,
            list_concat(p.exclusion_reasons, p.identity_reasons) AS reasons, p.fate,
            p.ask_checked
        FROM key k JOIN c USING (listing_id) JOIN p USING (listing_id)
        ORDER BY k.kind, k.listing_id"""
    ).fetchdf()
    compared = compared.astype(object).where(compared.notna(), None)
    report = {"export": str(export), "seed": seed, "kinds": {}}
    for row in compared.itertuples(index=False):
        counts = report["kinds"].setdefault(row.kind, {"planted": 0, "outcomes": {}})
        counts["planted"] += 1
        result = outcome(row.kind, row)
        if result == "dropped":
            reasons = [] if row.reasons is None else list(row.reasons)
            reasons = reasons or [row.fate or "no row"]
            result = "dropped: " + ", ".join(sorted(reasons))
        counts["outcomes"][result] = counts["outcomes"].get(result, 0) + 1
        if row.in_rows and row.kind.startswith("ask"):
            step = steps.get(row.listing_id) or "none"
            counts.setdefault("steps", {})
            counts["steps"][step] = counts["steps"].get(step, 0) + 1
        if row.in_rows and row.ask_checked:
            counts["flagged"] = counts.get("flagged", 0) + 1
        elif result.startswith("kept, planted") or result == "kept":
            counts.setdefault("missed", []).append(row.listing_id)
    others = db.sql(
        """SELECT c.listing_id, c.in_rows AS clean_in_rows, p.in_rows,
            c.latest_ask AS clean_ask, p.latest_ask, c.bedrooms AS clean_beds, p.bedrooms
        FROM c JOIN p USING (listing_id)
        WHERE listing_id NOT IN (SELECT listing_id FROM key)
            AND (c.in_rows IS DISTINCT FROM p.in_rows
                OR c.latest_ask IS DISTINCT FROM p.latest_ask
                OR c.bedrooms IS DISTINCT FROM p.bedrooms)
        ORDER BY listing_id"""
    ).fetchall()
    report["other_ads_changed"] = len(others)
    report["other_examples"] = [list(map(str, row)) for row in others[:10]]
    (work / "report.json").write_text(json.dumps(report, indent=1))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--export", type=Path, default=SAMPLE)
    parser.add_argument("--per-kind", type=int, default=50)
    parser.add_argument("--seed", default="plant")
    parser.add_argument("--kinds", default=",".join(KINDS))
    args = parser.parse_args()
    kinds = tuple(args.kinds.split(","))
    if set(kinds) - set(KINDS):
        sys.exit(f"unknown kinds: {sorted(set(kinds) - set(KINDS))}")
    report = run(args.export, args.work, args.per_kind, args.seed, kinds)
    for kind, counts in report["kinds"].items():
        print(f"{kind}: {counts['planted']} planted")
        for result, n in sorted(counts["outcomes"].items(), key=lambda kv: -kv[1]):
            print(f"    {n:4d}  {result}")
        for step, n in sorted(counts.get("steps", {}).items(), key=lambda kv: -kv[1]):
            print(f"    {n:4d}  kept ads with the ask of step: {step}")
        if counts.get("flagged"):
            print(
                f"    {counts['flagged']:4d}  kept ads the ask check lists for review"
            )
    print(f"ads without an error whose row changed: {report['other_ads_changed']}")


if __name__ == "__main__":
    main()
