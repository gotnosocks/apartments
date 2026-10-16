"""Write the test fixture from the full inputs on thelio.

The fixture holds the analysis rows of five buildings, the exported records of their ads and
the latest ask `rentfrontier.latest_ask` gave each of those rows. For the same rows,
`chain-rows.parquet` holds the values the chain's analysis datasets give them, read from the
datasets the latest-ask run names in its provenance. The script copies whole
buildings, so the building medians in the latest-ask checks come out as in the full run.
Between them, the five buildings carry each way of choosing an ask that the API run used, and
ad 2326634 at 1115 Union St, with 799 price changes.

    pipeline/.venv/bin/python pipeline/tests/make_fixture.py

The fixture's export mirrors the real one: a folder for each table and run, files named by their
first and last response IDs, and a manifest line for each file. Besides the ads, it holds the
answers for the buildings their records name. Each record keeps its bytes, so its SHA-256 still
equals `record_sha256`.
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
# The fields of the chain's analysis rows that the pipeline rebuilds, and the audit ID that
# joins them to the fixture's rows.
CHAIN_COLUMNS = {
    "audit_id": "VARCHAR",
    "source_listing_id": "VARCHAR",
    "price_at": "VARCHAR",
    "period": "VARCHAR",
    "unit_id": "VARCHAR",
    "canonical_unit_url": "VARCHAR",
    "building": "VARCHAR",
    "asking_rent": "DOUBLE",
    "bedrooms": "DOUBLE",
    "bathrooms": "DOUBLE",
    "reported_full_bathrooms": "BIGINT",
    "reported_half_bathrooms": "BIGINT",
    "square_feet": "DOUBLE",
    "listed_floor": "DOUBLE",
    "label_derived_floor": "DOUBLE",
    "floor_label_provenance": "JSON",
    "advertised_floor": "DOUBLE",
    "physical_floor": "DOUBLE",
    "floors_above_ground": "DOUBLE",
    "elevator": "BOOLEAN",
    "laundry_type": "VARCHAR",
    "doorman_type": "VARCHAR",
    "hvac_type": "VARCHAR",
    "pet_policy": "VARCHAR",
    "view_exposures": "JSON",
    "window_exposures": "JSON",
    "neighbourhood": "VARCHAR",
}
COPY = "(FORMAT parquet, COMPRESSION zstd)"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def listed(lines, table, export):
    """The export's files of `table`, as its manifest lists them."""
    return sorted(str(export / e["path"]) for e in lines if e["table"] == table)


def copy_runs(db, table, lines, export, out):
    """Write the picked answers of `table` as a file for each run, and return their manifest
    lines."""
    sources = {e["path"]: e for e in lines if e["table"] == table}
    manifest = []
    for (run,) in db.sql(f"SELECT DISTINCT run FROM {table} ORDER BY run").fetchall():
        first, last, rows, written = db.execute(
            f"SELECT min(response_id), max(response_id), count(*), list(DISTINCT filename) "
            f"FROM {table} WHERE run = ?",
            [run],
        ).fetchone()
        path = (
            Path(table) / f"run-{run:04d}" / f"responses-{first:07d}-{last:07d}.parquet"
        )
        (out / "export" / path).parent.mkdir(parents=True)
        key = "listing_id" if table == "ads" else "building_id"
        db.execute(
            f"""COPY (SELECT * EXCLUDE (filename) FROM {table} WHERE run = {run}
            ORDER BY response_id, {key}) TO '{out / "export" / path}' {COPY}"""
        )
        manifest.append(
            {
                "first": first,
                "last": last,
                "path": str(path),
                "rows": rows,
                "run": run,
                "sha256": sha256(out / "export" / path),
                "table": table,
                "written": max(
                    sources[str(Path(f).relative_to(export))]["written"]
                    for f in written
                ),
            }
        )
    return manifest


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
    parser.add_argument(
        "--provenance",
        default="/data1/apartments/external/latest-ask/20261015-13f5968-api/provenance.json",
    )
    parser.add_argument("--out", default=str(HERE / "fixture"))
    args = parser.parse_args()
    export, out = Path(args.export), Path(args.out)
    shutil.rmtree(out, ignore_errors=True)
    (out / "export").mkdir(parents=True)
    db = duckdb.connect(config={"TimeZone": "UTC", "memory_limit": "2GB"})

    db.execute(
        f"""COPY (SELECT * FROM read_parquet(?) WHERE building IN {BUILDINGS} ORDER BY ordinal)
        TO '{out / "rows.parquet"}' {COPY}""",
        [args.rows],
    )
    db.execute(f"CREATE VIEW rows AS SELECT * FROM '{out / 'rows.parquet'}'")
    db.execute(
        f"""COPY (SELECT r.ordinal, l.* FROM read_parquet(?) l JOIN rows r USING (audit_id)
        ORDER BY r.ordinal) TO '{out / "latest-ask.parquet"}' {COPY}""",
        [args.latest_ask],
    )

    datasets = json.loads(Path(args.provenance).read_text())["dataset"].split(",")
    db.execute(
        f"""COPY (SELECT r.ordinal, o.* REPLACE (
            o.price_at::TIMESTAMPTZ AS price_at, o.period::DATE AS period)
        FROM read_json(?, format = 'newline_delimited', columns = {CHAIN_COLUMNS}) o
        JOIN rows r USING (audit_id) ORDER BY r.ordinal)
        TO '{out / "chain-rows.parquet"}' {COPY}""",
        [[str(Path(d.strip()) / "observations.jsonl") for d in datasets]],
    )

    lines = [
        json.loads(line)
        for line in (export / "manifest.ndjson").read_text().splitlines()
    ]
    db.execute(
        """CREATE TABLE ads AS SELECT * FROM read_parquet(?, filename = true)
        WHERE listing_id::VARCHAR IN (SELECT source_listing_id FROM rows)""",
        [listed(lines, "ads", export)],
    )
    db.execute(
        """CREATE TABLE buildings AS SELECT * FROM read_parquet(?, filename = true)
        WHERE building_id IN (SELECT json_extract_string(record, '$.buildingId') FROM ads)""",
        [listed(lines, "buildings", export)],
    )
    manifest = [
        entry
        for table in ("ads", "buildings")
        for entry in copy_runs(db, table, lines, export, out)
    ]
    with open(out / "export" / "manifest.ndjson", "w") as f:
        f.writelines(json.dumps(e, sort_keys=True) + "\n" for e in manifest)

    counts = db.sql(
        "SELECT (SELECT count(*) FROM rows), (SELECT count(*) FROM ads), "
        "(SELECT count(*) FROM buildings), (SELECT count(*) FROM (SELECT record, "
        "record_sha256 FROM ads UNION ALL SELECT record, record_sha256 FROM buildings) "
        "WHERE sha256(record) <> record_sha256)"
    ).fetchone()
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(
        f"{counts[0]} rows, {counts[1]} ad answers, {counts[2]} building answers, "
        f"{counts[3]} hash mismatches, {size:,} bytes"
    )


if __name__ == "__main__":
    main()
