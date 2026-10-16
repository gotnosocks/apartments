"""Build each fit-ready row's landmark and historic district flags as of its date and compare
them with the served model's `lpc_as_of`.

    pipeline/.venv/bin/python ops/pipeline/landmarks_check.py [--rows FILE] [--export DIR]
        [--frontier DIR] [--files DIR] [--memory SIZE] [--out FILE]

1. The script reads the rows file FILE, the newest rows-*.parquet under
   /data1/apartments/pipeline/datasets unless given, and puts its listing IDs, buildings and
   dates in a scratch DuckDB database as `analysis.candidates`. It then renders
   `analysis.lot_landmarks` with each model it reads but the candidates, and the models above
   those, runs them in order, the views as views and the rest as tables, and prints the seconds
   each took. It reads the export and the city cache config.py gives, or the export DIR with
   `--export`, and leaves the build's database alone. DuckDB gets SIZE of memory, 3GB unless
   given, and spills to the scratch folder past it.
2. It counts the rows by their flags, with the rows lacking a lot apart.
3. It compares the designations of the step's copy with Data improvements' LPC file in the
   folder named by `--files`, the 20261016-5f07157-all copy unless given, on the lots of the
   rows: the designations each has and the other lacks.
4. In the frontier's venv it runs `lpc_as_of` from the frontier code in DIR,
   /data1/apartments/serve/master/frontier unless given, on that LPC file twice:
   - once on each row's building as the served model does, with the lot registry of the same
     folder,
   - once on the step's lot for each row, through a registry giving each lot itself.
   The second run reads the same lots as the step, so its flags differ from the step's only
   through the copy and the rules. The first run differs from the second only through the lot
   each reads.
5. It prints the rows each flag differs on for each comparison, and the lots behind them. The
   step leaves both flags missing for a row without a lot, where `lpc_as_of` gives false, and
   the script counts those rows apart.
6. With `--out` it writes the step's flags for each row to a Parquet file.
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
FLAGS = ["landmark", "historic_district"]


def newest_rows() -> Path:
    files = sorted(DATASETS.glob("rows-*.parquet"), key=lambda p: p.stat().st_mtime)
    if not files:
        sys.exit(f"no rows-*.parquet under {DATASETS}")
    return files[-1]


def build(db, export: Path | None) -> None:
    """Run `analysis.lot_landmarks`, each model it reads but `analysis.candidates`, and the
    models above those into `db`, in order."""
    with tempfile.TemporaryDirectory(prefix="landmarks-check-") as state:
        os.environ["PIPELINE_STATE"] = state
        if export:
            os.environ["PIPELINE_EXPORT"] = str(export)
        from sqlmesh import Context

        ctx = Context(paths=str(REPO / "pipeline"))
        step = ctx.get_model("analysis.lot_landmarks")
        candidates = ctx.get_model("analysis.candidates").fqn
        inputs = step.depends_on - {candidates}
        needed = {step.fqn, *inputs, *(u for i in inputs for u in ctx.dag.upstream(i))}
        for fqn in [f for f in ctx.dag.sorted if f in needed]:
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
    """Steps 4 and 5, in the frontier's venv: run `lpc_as_of` on the rows in `args.pairs` and
    compare its flags with the step's."""
    import pandas as pd

    sys.path.insert(0, str(args.frontier / "src"))
    from rentfrontier import features

    rows = pd.read_parquet(args.pairs)
    lpc = str(EXTERNAL / "lpc" / args.files / "lpc.parquet")
    registry = EXTERNAL / "registry" / args.files / "registry.parquet"
    pluto = EXTERNAL / "pluto" / args.files / "pluto.parquet"

    def served(frame, registry_file):
        token = features._LOTS.set((str(registry_file), str(pluto)))
        try:
            return features.lpc_as_of(frame, lpc)
        finally:
            features._LOTS.reset(token)

    by_building = served(rows[["building", "price_at"]], registry)
    with tempfile.TemporaryDirectory(prefix="landmarks-check-") as scratch:
        itself = Path(scratch) / "registry.parquet"
        lots = rows.bbl.dropna().unique()
        pd.DataFrame({"building": lots, "bbl": lots}).to_parquet(itself)
        frame = pd.DataFrame(
            {"building": rows.bbl.fillna(""), "price_at": rows.price_at}
        )
        by_lot = served(frame, itself)
    served_bbl = (
        pd.read_parquet(registry, columns=["building", "bbl"])
        .set_index("building")
        .bbl.astype(object)
        .reindex(rows.building.to_numpy())
    )

    lotted = rows.bbl.notna().to_numpy()
    print(f"rows: {len(rows):,}, with a lot: {lotted.sum():,}")
    same_lot = lotted & rows.bbl.astype(object).eq(served_bbl.to_numpy()).to_numpy(bool)
    print(f"  rows whose lot is the registry's lot: {same_lot.sum():,}")
    for i, flag in enumerate(FLAGS):
        step = rows[flag].astype("boolean").fillna(False).to_numpy(bool)
        print(f"{flag}:")
        print(
            f"  rows without a lot, where lpc_as_of on the building gives true:"
            f" {(~lotted & by_building[i]).sum():,}"
        )
        differ = lotted & (step != by_lot[i])
        print(f"  rows differing from lpc_as_of on the step's lot: {differ.sum():,}")
        show(rows[differ], step[differ], by_lot[i][differ])
        differ = lotted & (step != by_building[i])
        print(
            f"  rows differing from lpc_as_of on the building: {differ.sum():,},"
            f" {(differ & same_lot).sum():,} of them reading the registry's lot"
        )
        show(
            rows[differ & same_lot],
            step[differ & same_lot],
            by_building[i][differ & same_lot],
        )
        changed = by_building[i] != by_lot[i]
        print(
            f"  rows where lpc_as_of gives the building another value than the step's lot:"
            f" {(lotted & changed).sum():,}"
        )


def show(rows, step, served, limit=10) -> None:
    """Print the lots behind the differing rows, the most rows first."""
    if not len(rows):
        return
    import pandas as pd

    table = pd.DataFrame({"bbl": rows.bbl.to_numpy(), "step": step, "served": served})
    counts = table.value_counts().rename("rows").reset_index().head(limit)
    print("    " + counts.to_string(index=False).replace("\n", "\n    "))


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
    scratch = Path(tempfile.mkdtemp(prefix="landmarks-check-"))
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
            SELECT listing_id, building, building_id, price_at FROM read_parquet('{rows}')
        """)
        start = time.monotonic()
        build(db, args.export)
        print(f"all models: {time.monotonic() - start:.1f} s")
        print(
            db.sql("""
            SELECT bbl IS NOT NULL AS lot, landmark, historic_district,
                count(*) AS rows, count(DISTINCT bbl) AS lots
            FROM analysis.lot_landmarks GROUP BY ALL ORDER BY ALL
        """)
            .fetchdf()
            .to_string(index=False)
        )
        lpc = EXTERNAL / "lpc" / args.files / "lpc.parquet"
        print(
            f"designations on the rows' lots, in the step's copy and in {args.files}:"
        )
        print(
            db.sql(f"""
            WITH lots AS (
                SELECT DISTINCT bbl FROM analysis.lot_landmarks WHERE bbl IS NOT NULL
            ), copy AS (
                SELECT DISTINCT trim(bbl) AS bbl, trim(lp_number) AS lp_number,
                    trim(lm_type) AS lm_type, trim(desdate) AS desdate
                FROM city.landmarks
                WHERE release = (SELECT max(release) FROM city.landmarks)
                    AND trim(status) = 'DESIGNATED'
            ), served AS (
                SELECT DISTINCT bbl, lp_number, lm_type, desdate
                FROM read_parquet('{lpc}') WHERE status = 'DESIGNATED'
            )
            SELECT 'both' AS side, count(*) AS designations
            FROM (FROM copy SEMI JOIN lots USING (bbl) INTERSECT FROM served SEMI JOIN lots USING (bbl))
            UNION ALL
            SELECT 'step only', count(*)
            FROM (FROM copy SEMI JOIN lots USING (bbl) EXCEPT FROM served SEMI JOIN lots USING (bbl))
            UNION ALL
            SELECT '{args.files} only', count(*)
            FROM (FROM served SEMI JOIN lots USING (bbl) EXCEPT FROM copy SEMI JOIN lots USING (bbl))
        """)
            .fetchdf()
            .to_string(index=False)
        )
        if args.out:
            db.execute(f"COPY analysis.lot_landmarks TO '{args.out}' (FORMAT parquet)")
        pairs = scratch / "pairs.parquet"
        db.execute(f"""
            COPY (
                SELECT l.listing_id, c.building, c.price_at, l.bbl, l.landmark,
                    l.historic_district
                FROM analysis.lot_landmarks l JOIN analysis.candidates c USING (listing_id)
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
