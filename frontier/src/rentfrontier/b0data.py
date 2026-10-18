"""Write the B0 baseline's input from a pipeline build.

    python -m rentfrontier.b0data OUT --state STATE [--catalog DIR] [--rows FILE]

The script picks the newest build in DIR's `catalog.ndjson` (/data1/apartments/pipeline/datasets
unless given), or the build whose rows file is FILE, and checks each file's SHA-256 against the
catalog line. It then reads the build's rows, ads and records files, and the pipeline state at
STATE for each ad's kept price changes, and writes `OUT/rows.parquet` with a row for every row
of the rows file:

- `listing_id`, `audit_id` (the listing ID as text), `building`, `unit_id` (the row's
  `split_unit`, as `ops/pipeline/observations.py` gives it), `neighbourhood`, `price_at`.
- `latest_ask`, the row's net-effective latest ask, and `bedrooms`, `full_baths`, `half_baths`.
- `latest_day`, the day of the latest ask. `analysis.latest_ask` records how it chose the ask
  (`how`), and the script dates each choice:
    - `latest` and `latest, nearer building`: the day of the ad's last kept change on or after
      the row's day, as `analysis.latest_change` picks the change. When the ad has none,
      `analysis.latest_change` takes the change in effect on the row's day, and the script
      dates it by the row's day (`row, change before`).
    - `earlier change, nearer building`: the day of the ad's last kept change on or after the
      row's day at the chosen price.
    - `page price` and `page price, digit`: the day the ad's latest record was last collected.
    - `first, nearer building` and `own ask, captured before the row`: the row's own day.
  A choice the script cannot date takes the row's day, and `latest_day_how` says which case
  dated each row.
- `furnished` and `short_term` from the ads file, and three flags from the ad's description in
  its latest record, with the patterns of `features.DESCRIPTION_FLAGS`: `shared_space`,
  `income_restricted` and `rent_stabilized`. A row whose record has no description longer than
  20 characters gets false for the three text flags, and `description_known` false.

`OUT/manifest.json` records the build's files and their SHA-256, the state file, the row count
and how many rows each dating case and flag covers.

I take days in UTC, as the pipeline's sessions do.

DuckDB locks the state file even read-only, so I run the script between builds, holding the
same locks a build holds:

    ops/job gpu -x -- systemd-run --user --scope -q -p MemoryMax=6G -p MemorySwapMax=0 -- \\
        env TMPDIR=/data1/apartments/tmp/pipeline/tmp PYTHONPATH=frontier/src \\
        /data1/apartments/venvs/pipeline/bin/python -m rentfrontier.b0data OUT \\
        --state /data1/apartments/pipeline/state/pipeline.duckdb
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

CATALOG = Path("/data1/apartments/pipeline/datasets")
# The patterns of `features.DESCRIPTION_FLAGS`, copied so the script runs in the pipeline's
# venv, which has DuckDB and lacks the frontier's scientific stack. A test checks the copy.
TEXT_FLAGS = {
    "shared_space": r"shared (?:bath|kitchen)|\bsro\b|roommate",
    "income_restricted": r"income restrict|affordable housing|housing lottery|\bami\b",
    "rent_stabilized": r"rent[- ]stabiliz",
}
MIN_DESCRIPTION = 20
# The catalog key of each file (the line's `ads` key lists the ad responses read).
KINDS = {"rows": "rows", "ads": "ads_file", "records": "records"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def pick_build(catalog: Path, rows: Path | None = None) -> dict:
    """The catalog line of the newest build, or of the build whose rows file is `rows`."""
    lines = [
        json.loads(line)
        for line in (catalog / "catalog.ndjson").read_text().splitlines()
        if line.strip()
    ]
    if rows is not None:
        digest = sha256(rows)
        lines = [line for line in lines if line["rows"]["sha256"] == digest]
        if not lines:
            raise SystemExit(f"no catalog line lists {rows}")
    line = lines[-1]
    for kind in KINDS:
        path = catalog / line[KINDS[kind]]["path"]
        if sha256(path) != line[KINDS[kind]]["sha256"]:
            raise SystemExit(f"{path} does not match its catalog line")
    return line


def text_flag_sql() -> str:
    parts = []
    for name, pattern in TEXT_FLAGS.items():
        pattern = pattern.replace("'", "''")
        parts.append(
            f"coalesce(known AND regexp_matches(text, '{pattern}'), false) AS {name}"
        )
    return ",\n        ".join(parts)


def record_flags(records: Path) -> str:
    """Each record's text flags, one pass over the records without keeping their text."""
    return f"""
CREATE TEMP TABLE recf AS
SELECT listing_id, greatest(collected_at, coalesce(last_collected_at, collected_at)) AS collected_at,
    coalesce(length(text) > {MIN_DESCRIPTION}, false) AS known,
    {text_flag_sql()}
FROM (
    SELECT listing_id, collected_at, last_collected_at,
        lower(json_extract_string(raw_listing_json, '$.description')) AS text
    FROM read_parquet('{records}')
)
"""


def query(rows: Path, ads: Path) -> str:
    return f"""
WITH r AS (
    SELECT listing_id, building, split_unit AS unit_id, neighbourhood, price_at,
        strftime(price_at, '%Y-%m-%d') AS day, latest_ask, bedrooms, full_baths, half_baths
    FROM read_parquet('{rows}')
),
la AS (SELECT listing_id, how, first_ask, latest_ask AS chosen FROM pipeline.analysis.latest_ask),
lc AS (SELECT listing_id, near_first FROM pipeline.analysis.latest_change),
k AS (
    SELECT r.listing_id,
        arg_max(k.day, k.n) FILTER (WHERE k.day >= r.day) AS live_day,
        arg_max(k.day, k.n) FILTER (WHERE k.day >= r.day AND k.price = lc.near_first) AS near_day
    FROM r JOIN pipeline.ads.kept_changes k USING (listing_id) LEFT JOIN lc USING (listing_id)
    GROUP BY r.listing_id
),
rec AS (
    SELECT listing_id, max(collected_at) AS collected_at,
        arg_max(known, collected_at) AS known,
        {", ".join(f"arg_max({f}, collected_at) AS {f}" for f in TEXT_FLAGS)}
    FROM recf GROUP BY listing_id
),
dated AS (
    SELECT r.*, la.how,
        CASE
            WHEN la.how IN ('latest', 'latest, nearer building') AND k.live_day IS NOT NULL
                THEN 'change'
            WHEN la.how = 'earlier change, nearer building' AND k.near_day IS NOT NULL
                THEN 'earlier change'
            WHEN la.how IN ('page price', 'page price, digit') AND rec.collected_at IS NOT NULL
                THEN 'record'
            WHEN la.how IN ('latest', 'latest, nearer building') THEN 'row, change before'
            WHEN la.how IN ('first, nearer building', 'own ask, captured before the row')
                THEN 'row'
            ELSE 'row, undated'
        END AS latest_day_how,
        k.live_day, k.near_day,
        strftime(to_timestamp(rec.collected_at), '%Y-%m-%d') AS record_day,
        coalesce(rec.known, false) AS known, {", ".join(f"coalesce(rec.{f}, false) AS {f}" for f in TEXT_FLAGS)}
    FROM r LEFT JOIN la USING (listing_id) LEFT JOIN k USING (listing_id)
        LEFT JOIN rec USING (listing_id)
)
SELECT d.listing_id, CAST(d.listing_id AS VARCHAR) AS audit_id, d.building, d.unit_id,
    d.neighbourhood, d.price_at, d.latest_ask, d.bedrooms, d.full_baths, d.half_baths,
    CAST(CASE d.latest_day_how
        WHEN 'change' THEN d.live_day
        WHEN 'earlier change' THEN d.near_day
        WHEN 'record' THEN greatest(d.record_day, d.day)
        ELSE d.day END AS DATE) AS latest_day,
    d.latest_day_how, d.how AS latest_ask_how,
    coalesce(a.furnished, false) AS furnished, coalesce(a.short_term, false) AS short_term,
    d.known AS description_known, {", ".join(f"d.{f}" for f in TEXT_FLAGS)}
FROM dated d LEFT JOIN read_parquet('{ads}') a USING (listing_id)
ORDER BY d.listing_id
"""


def build(out: Path, state: Path, catalog: Path = CATALOG, rows: Path | None = None):
    import duckdb

    line = pick_build(catalog, rows)
    files = {kind: catalog / line[key]["path"] for kind, key in KINDS.items()}
    out.mkdir(parents=True, exist_ok=False)
    con = duckdb.connect()
    con.execute(f"SET memory_limit = '{os.environ.get('B0DATA_MEMORY', '4GB')}'")
    # The pipeline's sessions run in UTC, so the days here match its own.
    con.execute("SET TimeZone = 'UTC'")
    con.execute("SET threads = 4")
    con.execute("SET preserve_insertion_order = false")
    con.execute(
        f"SET temp_directory = '{os.environ.get('TMPDIR', '/data1/apartments/tmp')}'"
    )
    con.execute(f"ATTACH '{state}' AS pipeline (READ_ONLY)")
    con.execute(record_flags(files["records"]))
    table = con.sql(query(files["rows"], files["ads"])).fetch_arrow_table()
    con.close()
    import pyarrow.parquet as pq

    pq.write_table(table, out / "rows.parquet")
    frame = table.select(
        ["latest_day_how", "furnished", "short_term", "description_known", *TEXT_FLAGS]
    ).to_pandas()
    manifest = {
        "build": {
            kind: {"path": str(path), "sha256": line[KINDS[kind]]["sha256"]}
            for kind, path in files.items()
        },
        "built": line.get("built"),
        "code": line.get("code"),
        "state": str(state),
        "rows": table.num_rows,
        "latest_day_how": frame.latest_day_how.value_counts().to_dict(),
        "flags": {
            name: int(frame[name].sum())
            for name in ("furnished", "short_term", "description_known", *TEXT_FLAGS)
        },
        "rows_sha256": sha256(out / "rows.parquet"),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    return manifest


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("out", type=Path)
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--catalog", type=Path, default=CATALOG)
    p.add_argument("--rows", type=Path)
    args = p.parse_args(argv)
    print(json.dumps(build(args.out, args.state, args.catalog, args.rows), indent=2))


if __name__ == "__main__":
    main()
