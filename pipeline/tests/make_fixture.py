"""Write the test fixture from the full inputs on thelio.

The fixture holds the analysis rows of five buildings, the exported records of their ads and
the latest ask `rentfrontier.latest_ask` gave each of those rows. The script copies whole
buildings, so the building medians in the latest-ask checks come out as in the full run.
Between them, the five buildings carry each way of choosing an ask that the API run used, and
ad 2326634 at 1115 Union St, with 799 price changes.

    pipeline/.venv/bin/python pipeline/tests/make_fixture.py

The fixture's export mirrors the real one: a folder for each run, files named by their first
and last response IDs, and a manifest line for each file. Each record keeps its bytes, so its
SHA-256 still equals `record_sha256`.
"""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import duckdb

BUILDINGS = (
    "1115-union-street-brooklyn",
    "129-west-89-street-new_york",
    "260-west-91-street-new_york",
    "270-15-street-brooklyn",
    "89-adelphi-street-brooklyn",
)
HERE = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--export", default="/data1/apartments/archive/crawls/api/export"
    )
    parser.add_argument(
        "--rows",
        default="/data1/apartments/pipeline/inputs/analysis-rows-20261015-13f5968-api.parquet",
    )
    parser.add_argument(
        "--latest-ask",
        default="/data1/apartments/external/latest-ask/20261015-13f5968-api/latest-ask.parquet",
    )
    parser.add_argument("--out", default=str(HERE / "fixture"))
    args = parser.parse_args()
    export, out = Path(args.export), Path(args.out)
    shutil.rmtree(out, ignore_errors=True)
    (out / "export").mkdir(parents=True)
    db = duckdb.connect(config={"TimeZone": "UTC", "memory_limit": "2GB"})
    copy = "(FORMAT parquet, COMPRESSION zstd)"

    db.execute(
        f"""COPY (SELECT * FROM read_parquet(?) WHERE building IN {BUILDINGS} ORDER BY ordinal)
        TO '{out / "rows.parquet"}' {copy}""",
        [args.rows],
    )
    db.execute(f"CREATE VIEW rows AS SELECT * FROM '{out / 'rows.parquet'}'")
    db.execute(
        f"""COPY (SELECT r.ordinal, l.* FROM read_parquet(?) l JOIN rows r USING (audit_id)
        ORDER BY r.ordinal) TO '{out / "latest-ask.parquet"}' {copy}""",
        [args.latest_ask],
    )

    lines = [
        json.loads(line)
        for line in (export / "manifest.ndjson").read_text().splitlines()
    ]
    lines = {e["path"]: e for e in lines if e["table"] == "ads"}
    db.execute(
        """CREATE TABLE picked AS SELECT * FROM read_parquet(?, filename = true)
        WHERE listing_id::VARCHAR IN (SELECT source_listing_id FROM rows)""",
        [[str(export / path) for path in sorted(lines)]],
    )
    manifest = []
    for (run,) in db.sql("SELECT DISTINCT run FROM picked ORDER BY run").fetchall():
        first, last, written = db.execute(
            "SELECT min(response_id), max(response_id), list(DISTINCT filename) FROM picked "
            "WHERE run = ?",
            [run],
        ).fetchone()
        path = (
            Path("ads") / f"run-{run:04d}" / f"responses-{first:07d}-{last:07d}.parquet"
        )
        (out / "export" / path).parent.mkdir(parents=True)
        db.execute(
            f"""COPY (SELECT * EXCLUDE (filename) FROM picked WHERE run = {run}
            ORDER BY response_id, listing_id) TO '{out / "export" / path}' {copy}"""
        )
        rows = db.execute(
            "SELECT count(*) FROM picked WHERE run = ?", [run]
        ).fetchone()[0]
        sources = [lines[str(Path(f).relative_to(export))] for f in written]
        manifest.append(
            {
                "first": first,
                "last": last,
                "path": str(path),
                "rows": rows,
                "run": run,
                "sha256": sha256(out / "export" / path),
                "table": "ads",
                "written": max(e["written"] for e in sources),
            }
        )
    with open(out / "export" / "manifest.ndjson", "w") as f:
        f.writelines(json.dumps(e, sort_keys=True) + "\n" for e in manifest)

    counts = db.sql(
        "SELECT (SELECT count(*) FROM rows), (SELECT count(*) FROM picked), "
        "(SELECT count(*) FROM picked WHERE sha256(record) <> record_sha256)"
    ).fetchone()
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(
        f"{counts[0]} rows, {counts[1]} records, {counts[2]} hash mismatches, {size:,} bytes"
    )


if __name__ == "__main__":
    main()
