"""Write a sample of the scraper's export: every answer for the ads of a share of the buildings.

    pipeline/.venv/bin/python ops/pipeline/sample.py [--export DIR] [--out DIR] [--share S]

`ops/pipeline/diff.py --sample` builds the sample on both sides of a diff, at a small fraction of
the full export's size. The script works in these steps:

1. It reads the export's manifest and picks a building when the MD5 hash of its ID falls in the
   first S of the hashes' range, 0.01 unless given. DuckDB's `md5_number` reads the hash as a
   little-endian number. The IDs come from the buildings' own answers and from the ads'
   records, so a building with no answer of its own can be picked. The same IDs fall in the
   sample on every run. On a later export, the script takes those buildings' new answers and
   picks each new building by the same hash test.
2. It picks an ad when one of its records gives a picked building. It also picks every ad with
   a `missing` answer, which carries no record. It keeps all of them, since the export holds
   only a few and the build has to handle them. It takes every answer of the picked ads, with or without a record, and every
   answer of the picked buildings. When a picked ad's record gives a building outside the
   picked ones, it takes that building's answers too.
3. It writes each table's answers into a new folder, in a file for each run. The files and the
   manifest follow the export's layout, the same way `pipeline/tests/make_fixture.py` writes
   the fixture. Then it moves the old OUT/export aside, renames the new folder into its place
   and deletes the old one.
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
    """The export's manifest lines, one for each listed file."""
    entries = {}
    for line in (export / "manifest.ndjson").read_text().splitlines(keepends=True):
        # The exporter writes each line whole and drops a cut-off last line on its next start.
        if not line.endswith("\n") or not line.strip():
            continue
        entry = json.loads(line)
        if entries.setdefault(entry["path"], entry)["sha256"] != entry["sha256"]:
            raise ValueError(f"manifest gives {entry['path']} two hashes")
    return list(entries.values())


def sample(export: Path, out: Path, share: float) -> dict:
    started = time.monotonic()
    target, source = (out / "export").resolve(), export.resolve()
    if target.is_relative_to(source) or source.is_relative_to(target):
        raise ValueError(f"{out / 'export'} overlaps the export {export}")
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
        SELECT listing_id FROM named WHERE building_id IN (SELECT * FROM picked)
        UNION SELECT listing_id FROM read_parquet(?) WHERE record IS NULL""",
        [ads],
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
    # The old sample moves aside just before the new one moves in, so OUT/export holds a whole
    # sample at almost every moment.
    old = out / "export.old"
    shutil.rmtree(old, ignore_errors=True)
    if (out / "export").exists():
        (out / "export").rename(old)
    (work / "export").rename(out / "export")
    work.rmdir()
    shutil.rmtree(old, ignore_errors=True)
    counts = db.execute(
        "SELECT (SELECT count(*) FROM picked), (SELECT count(*) FROM picked_ads), "
        "(SELECT count(*) FROM ads), (SELECT count(*) FROM buildings), "
        "(SELECT count(DISTINCT listing_id) FROM read_parquet(?))",
        [ads],
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
