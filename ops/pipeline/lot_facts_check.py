"""Build each fit-ready row's MapPLUTO facts as of its date and compare them with the served
model's `released_lots`.

    pipeline/.venv/bin/python ops/pipeline/lot_facts_check.py [--rows FILE] [--export DIR]
        [--frontier DIR] [--files DIR] [--memory SIZE] [--out FILE]

1. The script reads the rows file FILE, the newest rows-*.parquet under
   /data1/apartments/pipeline/datasets unless given, and puts its listing IDs, buildings and
   dates in a scratch DuckDB database as `analysis.candidates`. It then renders
   `analysis.lot_facts`, `buildings.lot_releases` and each model above them but the candidates,
   runs them in order, the views as views and the rest as tables, and prints the seconds each
   took. It reads the export and the city cache config.py gives, or the export DIR with
   `--export`, and leaves the build's database alone. DuckDB gets SIZE of memory, 3GB unless
   given, and spills to the scratch folder past it.
2. It counts the rows by the release they read and by their fallback.
3. It hands each distinct pair of lot and date to `released_lots` from the frontier code in DIR,
   /data1/apartments/serve/master/frontier unless given, run in the frontier's venv. That
   function reads Data improvements' MapPLUTO files in the folders named by `--files`, the
   20261016-5f07157-all copies unless given: today's release and every release of the lots of
   the registry. It runs twice, once with each row's month as the served model gives it and
   once with the row's first day, as this step does.
4. It compares this step's facts with those of the run by first day, field by field. Numbers
   compare as numbers, text as trimmed text, so a fact differs only when the values differ.
   It prints the rows each field differs on. It leaves out two kinds of rows and counts them:
   rows whose lot isn't in Data improvements' file of today's release, and rows whose lot's
   record in their release is missing from its releases file though the city's archive has
   it. `released_lots` gives those rows today's facts. The script also counts the rows whose
   facts change between the run by month and the run by first day.
5. With `--out` it writes the step's facts for each row to a Parquet file.

The script takes about 4 minutes and 4.4 GB on the full rows file on thelio, most of both in
`released_lots`. The models take about 35 s of it.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATASETS = Path("/data1/apartments/pipeline/datasets")
FRONTIER = Path("/data1/apartments/serve/master/frontier")
FRONTIER_PYTHON = "/data1/apartments/venvs/serve-frontier/bin/python"
FILES = "20261016-5f07157-all"
EXTERNAL = Path("/data1/apartments/external")
# The facts `analysis.lot_facts` reads from the release of each row, and those it reads from the
# latest release.
DATED = [
    "yearalter1",
    "yearalter2",
    "numfloors",
    "numbldgs",
    "unitsres",
    "unitstotal",
    "lotarea",
    "bldgarea",
    "resarea",
    "comarea",
    "retailarea",
    "lotfront",
    "lotdepth",
    "bldgfront",
    "bldgdepth",
    "bldgclass",
    "landuse",
    "landmark",
    "histdist",
    "zonedist1",
    "builtfar",
    "residfar",
    "proxcode",
    "irrlotcode",
    "lottype",
    "bsmtcode",
    "pfirm15_flag",
    "firm07_flag",
    "schooldist",
    "policeprct",
]
LATEST = ["address", "yearbuilt", "latitude", "longitude"]
TEXT = {"address", "bldgclass", "landmark", "histdist", "zonedist1"}


def newest_rows() -> Path:
    files = sorted(DATASETS.glob("rows-*.parquet"), key=lambda p: p.stat().st_mtime)
    if not files:
        sys.exit(f"no rows-*.parquet under {DATASETS}")
    return files[-1]


def build(db, export: Path | None) -> None:
    """Run `analysis.lot_facts`, `buildings.lot_releases` and the models above them but
    `analysis.candidates` into `db`, in order."""
    with tempfile.TemporaryDirectory(prefix="lot-facts-check-") as state:
        os.environ["PIPELINE_STATE"] = state
        if export:
            os.environ["PIPELINE_EXPORT"] = str(export)
        from sqlmesh import Context

        ctx = Context(paths=str(REPO / "pipeline"))
        targets = [
            ctx.get_model(n).fqn
            for n in ("analysis.lot_facts", "buildings.lot_releases")
        ]
        candidates = ctx.get_model("analysis.candidates").fqn
        needed = {*targets, *ctx.dag.upstream(targets[1])}
        for fqn in [f for f in ctx.dag.sorted if f in needed and f != candidates]:
            model = ctx.get_model(fqn)
            schema = model.name.split(".")[0]
            sql = ctx.render(fqn).sql(dialect="duckdb")
            kind = "VIEW" if model.kind.is_view else "TABLE"
            start = time.monotonic()
            db.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
            db.execute(f"CREATE {kind} {model.name} AS {sql}")
            if kind == "TABLE":
                print(f"{model.name}: {time.monotonic() - start:.1f} s")


def compare(args) -> None:
    """Steps 3 and 4, in the frontier's venv: run `released_lots` over the pairs of lot and date
    in `args.pairs`, and compare its facts with the step's."""
    import numpy as np
    import pandas as pd

    sys.path.insert(0, str(args.frontier / "src"))
    from rentfrontier.features import released_lots

    pairs = pd.read_parquet(args.pairs)
    releases = EXTERNAL / "plutoreleases" / args.files / "plutoreleases.parquet"
    today = pd.read_parquet(EXTERNAL / "pluto" / args.files / "pluto.parquet")
    today = today.set_index("bbl")
    known = pairs.bbl.isin(today.index) & pairs.bbl.notna()
    print(f"pairs of lot and date: {len(pairs):,}, rows: {pairs.rows.sum():,}")
    print(
        f"  rows whose lot isn't in {args.files}: {pairs.rows[~known].sum():,}"
        f" ({(~known).sum():,} pairs)"
    )
    pairs = pairs[known].reset_index(drop=True)
    held = pd.read_parquet(releases, columns=["release", "bbl"])
    keys = pd.MultiIndex.from_arrays([pairs.pluto_release, pairs.bbl])
    gap = pairs.pluto_fallback.isna().to_numpy() & ~keys.isin(
        pd.MultiIndex.from_frame(held)
    )
    print(
        f"  rows whose lot's record in their release is missing from {args.files}:"
        f" {pairs.rows[gap].sum():,} ({pairs.bbl[gap].nunique():,} lots)"
    )
    pairs = pairs[~gap].reset_index(drop=True)
    lots = today.reindex(pairs.bbl.to_numpy()).reset_index(drop=True)

    def run(dates):
        frame = pd.DataFrame({"period": pd.to_datetime(dates)})
        return released_lots(frame, pairs.bbl.to_numpy(), lots, str(releases))

    by_month, by_day = run(pairs.period), run(pairs.first_day)

    def normal(column, values):
        """`values` as trimmed text for a text field, else as floats, with Y and N as 1 and 0."""
        text = values.astype("string").str.strip().replace("", pd.NA)
        if column in TEXT:
            return text
        if column == "irrlotcode":
            text = text.str.upper().map({"Y": "1", "TRUE": "1", "N": "0", "FALSE": "0"})
        number = pd.to_numeric(text, errors="coerce")
        return number.to_numpy(dtype=float, na_value=np.nan)

    def same(column, a, b):
        a, b = normal(column, a), normal(column, b)
        if column in TEXT:
            return ((a == b).fillna(False) | (a.isna() & b.isna())).to_numpy()
        return np.isclose(a, b, rtol=0, atol=1e-9) | (np.isnan(a) & np.isnan(b))

    print("rows on which a field differs from released_lots by first day:")
    for column in LATEST + DATED:
        differ = ~same(column, by_day[column], pairs[column])
        rows = pairs.rows[differ].sum()
        example = ""
        if rows:
            i = np.flatnonzero(differ)[0]
            example = (
                f"  e.g. {pairs.bbl[i]} on {pairs.first_day[i]}:"
                f" {by_day[column][i]!r} against {pairs[column][i]!r}"
            )
        print(f"  {column:13} {rows:9,}{example}")
    moved = np.zeros(len(pairs), dtype=bool)
    for column in DATED:
        moved |= ~same(column, by_month[column], by_day[column])
    print(
        f"rows whose facts change from the month to the first day: {pairs.rows[moved].sum():,}"
        f" of {pairs.rows.sum():,}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rows", type=Path)
    parser.add_argument("--export", type=Path)
    parser.add_argument("--frontier", type=Path, default=FRONTIER)
    parser.add_argument("--files", default=FILES)
    parser.add_argument("--memory", default="3GB")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--pairs", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.pairs:
        compare(args)
        return
    sys.path.insert(0, str(REPO / "pipeline"))
    import duckdb

    rows = args.rows or newest_rows()
    print(f"rows: {rows}")
    scratch = Path(tempfile.mkdtemp(prefix="lot-facts-check-"))
    db = duckdb.connect(str(scratch / "pipeline.duckdb"))
    db.execute(f"SET memory_limit = '{args.memory}'")
    db.execute(f"SET temp_directory = '{scratch / 'spill'}'")
    db.execute("SET threads = 3")
    db.execute("SET preserve_insertion_order = false")
    db.execute("SET TimeZone = 'UTC'")
    try:
        db.execute("CREATE SCHEMA analysis")
        db.execute(f"""
            CREATE TABLE analysis.candidates AS
            SELECT listing_id, building_id, price_at, period FROM read_parquet('{rows}')
        """)
        start = time.monotonic()
        build(db, args.export)
        print(f"all models: {time.monotonic() - start:.1f} s")
        print(
            db.sql("""
            SELECT pluto_release, coalesce(pluto_fallback, '') AS fallback,
                count(*) AS rows, count(DISTINCT bbl) AS lots
            FROM analysis.lot_facts GROUP BY ALL ORDER BY pluto_release, fallback
        """)
            .fetchdf()
            .to_string(index=False)
        )
        if args.out:
            db.execute(f"COPY analysis.lot_facts TO '{args.out}' (FORMAT parquet)")
        pairs = scratch / "pairs.parquet"
        db.execute(f"""
            COPY (
                SELECT f.bbl, c.period, (c.price_at AT TIME ZONE 'UTC')::DATE AS first_day,
                    count(*) AS rows, any_value(COLUMNS(f.* EXCLUDE (listing_id, bbl)))
                FROM analysis.lot_facts f JOIN analysis.candidates c USING (listing_id)
                WHERE f.bbl IS NOT NULL
                GROUP BY ALL
            ) TO '{pairs}' (FORMAT parquet)
        """)
        db.close()
        sys.stdout.flush()
        subprocess.run(
            [
                FRONTIER_PYTHON,
                __file__,
                "--pairs",
                str(pairs),
                "--frontier",
                str(args.frontier),
                "--files",
                args.files,
            ],
            check=True,
        )
    finally:
        shutil.rmtree(scratch)


if __name__ == "__main__":
    main()
