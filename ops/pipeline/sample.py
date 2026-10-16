"""Write a sample of the scraper's export: every answer for the ads of a share of the buildings.

    pipeline/.venv/bin/python ops/pipeline/sample.py [--export DIR] [--out DIR] [--share S]

`ops/pipeline/diff.py --export OUT/export` builds the sample on both sides of a diff, with the
full export's range of cases at a small fraction of its size. The script works in these steps:

1. It reads the export's manifest and picks each building whose ID has an MD5 hash in the
   first S of the hashes' range, 0.01 unless given. DuckDB's `md5_number` reads the hash as a
   little-endian number. It takes the IDs from the buildings' own
   answers and from the ads' records, so a building with no answer of its own can be picked.
   The same IDs fall in the sample on every run, so a later export adds only the new answers
   of the same buildings.
2. It picks each ad with a record naming a picked building, and takes every answer for those
   ads, with or without a record. It takes every answer for the picked buildings and for any
   other building a picked ad's record names.
3. It writes the answers of each table as a file for each run, under OUT/export, laid out as
   the export is, with a manifest line for each file, as `pipeline/tests/make_fixture.py`
   writes the fixture. It replaces OUT/export as a whole.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import time
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parents[2]
DEFAULT_EXPORT = Path("/data1/apartments/archive/crawls/api/export")
DEFAULT_OUT = Path("/data1/apartments/pipeline/sample")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fixture = load("make_fixture", REPO / "pipeline" / "tests" / "make_fixture.py")


def manifest(export: Path) -> list[dict]:
    lines = (export / "manifest.ndjson").read_text().splitlines(keepends=True)
    # The exporter writes each line whole and drops a cut-off last line on its next start.
    return [json.loads(line) for line in lines if line.endswith("\n") and line.strip()]


def sample(export: Path, out: Path, share: float) -> dict:
    started = time.monotonic()
    lines = manifest(export)
    ads = fixture.listed(lines, "ads", export)
    buildings = fixture.listed(lines, "buildings", export)
    work = out / "export.new"
    shutil.rmtree(work, ignore_errors=True)
    db = duckdb.connect(config={"TimeZone": "UTC", "memory_limit": "2GB", "threads": 4})
    db.execute(
        """CREATE TABLE named AS
        SELECT DISTINCT listing_id, json_extract_string(record, '$.buildingId') AS building_id
        FROM read_parquet(?) WHERE record IS NOT NULL""",
        [ads],
    )
    db.execute(
        """CREATE TABLE picked AS
        SELECT building_id FROM (
            SELECT building_id FROM named
            UNION SELECT building_id FROM read_parquet(?)
        )
        WHERE building_id IS NOT NULL AND md5_number(building_id) / 2::DOUBLE ** 128 < ?""",
        [buildings, share],
    )
    db.execute(
        """CREATE TABLE picked_ads AS
        SELECT DISTINCT listing_id FROM named WHERE building_id IN (SELECT * FROM picked)"""
    )
    db.execute(
        """CREATE TABLE ads AS SELECT * FROM read_parquet(?, filename = true)
        WHERE listing_id IN (SELECT * FROM picked_ads)""",
        [ads],
    )
    db.execute(
        """CREATE TABLE buildings AS SELECT * FROM read_parquet(?, filename = true)
        WHERE building_id IN (SELECT * FROM picked)
            OR building_id IN (
                SELECT building_id FROM named WHERE listing_id IN (SELECT * FROM picked_ads)
            )""",
        [buildings],
    )
    (work / "export").mkdir(parents=True)
    entries = [
        entry
        for table in ("ads", "buildings")
        for entry in fixture.copy_runs(db, table, lines, export, work)
    ]
    with open(work / "export" / "manifest.ndjson", "w") as f:
        f.writelines(json.dumps(e, sort_keys=True) + "\n" for e in entries)
    out.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(out / "export", ignore_errors=True)
    (work / "export").rename(out / "export")
    work.rmdir()
    counts = db.sql(
        "SELECT (SELECT count(*) FROM picked), (SELECT count(*) FROM picked_ads), "
        "(SELECT count(*) FROM ads), (SELECT count(*) FROM buildings), "
        "(SELECT count(DISTINCT listing_id) FROM named)"
    ).fetchone()
    return {
        "buildings_picked": counts[0],
        "ads": counts[1],
        "ad_answers": counts[2],
        "building_answers": counts[3],
        "ads_in_export": counts[4],
        "bytes": sum(
            p.stat().st_size for p in (out / "export").rglob("*") if p.is_file()
        ),
        "seconds": round(time.monotonic() - started, 1),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--export", type=Path, default=DEFAULT_EXPORT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--share", type=float, default=0.01)
    args = parser.parse_args(argv)
    print(json.dumps(sample(args.export, args.out, args.share)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
