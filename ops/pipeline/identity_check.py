"""Build the building identity models over an export and check their lots against a lot registry
and a reviewed sample.

    pipeline/.venv/bin/python ops/pipeline/identity_check.py [--export DIR] [--registry FILE]
        [--reviews FILE] [--memory SIZE] [--out FILE]

1. The script loads the pipeline's project with a scratch state folder and renders
   `buildings.lots` and each model above it. It runs them in order in a scratch DuckDB
   database, the views as views and the rest as tables, and prints the seconds each took. It
   reads the export and the city cache config.py gives, or the export DIR with `--export`, and
   leaves the build's database alone. DuckDB gets SIZE of memory, 3GB unless given, and spills
   to the scratch folder past it.
2. It counts the buildings by link and by the strata of the review, which split `both` by the
   lot's facts fit: 2 or more, or less than 2.
3. It compares the lots with the registry, the newest registry.parquet under
   /data1/apartments/external/registry unless given, for each of the registry's methods. A
   person chose the lot of each row of method `override`, and the script lists the overrides
   whose lot differs from the model's.
4. It scores the reviewed sample, config/reviews/building-identity-20261016.jsonl unless given.
   It places each reviewed building in its stratum in the current build, which may differ from
   the stratum it was drawn from, and prints how many moved. For each stratum, it counts the
   reviewed buildings whose lot is the one the reviewers judged right, the ones whose lot they
   judged wrong, and the rest: buildings they left unclear, or whose lot has changed since. It
   then estimates the share of wrong lots in the stratum, with a 95% Wilson interval, and
   multiplies it by the stratum's size in the current build. The total adds the strata's
   estimates. Their intervals don't add up to an interval for the total, so the script leaves
   them out of it.
5. With `--out` it writes the lots, with each building's slug and stratum, to a Parquet file.

The script takes about 17 s and 2.7 GB on the full export on thelio.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REGISTRIES = Path("/data1/apartments/external/registry")
REVIEWS = REPO / "config" / "reviews" / "building-identity-20261016.jsonl"
STRATA = [
    "both_fit",
    "both_lowfit",
    "address_apartments",
    "footprint_apartments",
    "address",
    "footprint",
    "tie",
    "address_only",
    "footprint_only",
]


def newest_registry() -> Path:
    files = sorted(
        REGISTRIES.glob("*/registry.parquet"), key=lambda p: p.stat().st_mtime
    )
    if not files:
        sys.exit(f"no registry.parquet under {REGISTRIES}")
    return files[-1]


def build(db, export: Path | None) -> None:
    """Run `buildings.lots` and the models above it into `db`, in order."""
    with tempfile.TemporaryDirectory(prefix="identity-check-") as state:
        os.environ["PIPELINE_STATE"] = state
        if export:
            os.environ["PIPELINE_EXPORT"] = str(export)
        from sqlmesh import Context

        ctx = Context(paths=str(REPO / "pipeline"))
        lots = ctx.get_model("buildings.lots")
        needed = {lots.fqn, *ctx.dag.upstream(lots.fqn)}
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


def wilson(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p, z = k / n, 1.96
    middle = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, middle - half), min(1.0, middle + half)


def report(db, args) -> None:
    """Print the counts and comparisons of steps 2 to 4, and write `--out`."""
    db.execute("""
        CREATE TABLE checked AS
        SELECT l.*, r.slug,
            CASE WHEN l.link = 'both' AND l.address_fit >= 2 THEN 'both_fit'
                WHEN l.link = 'both' THEN 'both_lowfit' ELSE l.link END AS stratum
        FROM buildings.lots l JOIN buildings.latest_record r USING (building_id)
    """)
    print(
        db.sql("""
        SELECT coalesce(stratum, '(none)') AS stratum, count(*) AS buildings,
            count(*) FILTER (WHERE address_lots > 1) AS address_gives_several_lots,
            count(*) FILTER (WHERE footprint_inside IS false) AS footprint_near_only
        FROM checked GROUP BY ALL ORDER BY buildings DESC
    """)
    )

    registry = args.registry or newest_registry()
    print(f"registry: {registry}")
    db.execute(f"CREATE TABLE registry AS SELECT * FROM read_parquet('{registry}')")
    print(
        db.sql("""
        SELECT r.method, count(*) AS buildings, count(c.building_id) AS built,
            count(*) FILTER (WHERE c.bbl = r.bbl) AS same_lot,
            count(*) FILTER (WHERE c.bbl <> r.bbl) AS other_lot,
            count(*) FILTER (WHERE c.bbl = r.bbl AND c.bin = r.bin) AS same_lot_and_bin
        FROM registry r LEFT JOIN checked c ON c.slug = r.building
        GROUP BY ALL ORDER BY buildings DESC
    """)
    )
    print(
        db.sql("""
        SELECT c.stratum, count(*) AS buildings, count(*) FILTER (WHERE c.bbl = r.bbl) AS same_lot
        FROM registry r JOIN checked c ON c.slug = r.building
        GROUP BY ALL ORDER BY buildings DESC
    """)
    )
    overrides = db.sql("""
        SELECT r.building, r.bbl AS registry_bbl, c.bbl, c.link
        FROM registry r LEFT JOIN checked c ON c.slug = r.building
        WHERE r.method = 'override' AND c.bbl IS DISTINCT FROM r.bbl
    """).fetchall()
    print(f"overrides whose lot differs: {len(overrides)}")
    for row in overrides:
        print("  ", *row)

    reviews = [json.loads(line) for line in args.reviews.read_text().splitlines()]
    lots = dict(db.sql("SELECT building_id, bbl FROM checked").fetchall())
    sizes = dict(
        db.sql("SELECT stratum, count(*) FROM checked GROUP BY ALL").fetchall()
    )
    strata = dict(db.sql("SELECT building_id, stratum FROM checked").fetchall())
    moved = sum(strata.get(r["building_id"]) != r["stratum"] for r in reviews)
    print(f"reviews: {args.reviews}, {moved} of them now in another stratum")
    print(
        f"{'stratum':20} {'size':>7} {'right':>6} {'wrong':>6} {'other':>6}"
        f" {'wrong share (95%)':>20} {'wrong lots (95%)':>22}"
    )
    total = 0.0
    for stratum in STRATA:
        right = wrong = other = 0
        for review in (r for r in reviews if strata.get(r["building_id"]) == stratum):
            lot = lots.get(review["building_id"])
            if lot is not None and lot == review["right"]:
                right += 1
            elif lot is not None and lot in review["wrong"]:
                wrong += 1
            else:
                other += 1
        size = sizes.get(stratum, 0)
        share = wrong / (right + wrong) if right + wrong else 0.0
        low, high = wilson(wrong, right + wrong)
        estimate = [share * size, low * size, high * size]
        total += estimate[0]
        print(
            f"{stratum:20} {size:7,} {right:6} {wrong:6} {other:6}"
            f" {share:8.1%} ({low:5.1%}-{high:5.1%})"
            f" {estimate[0]:7.0f} ({estimate[1]:5.0f}-{estimate[2]:5.0f})"
        )
    print(f"wrong lots in all strata: {total:.0f}")
    if args.out:
        db.execute(f"COPY checked TO '{args.out}' (FORMAT parquet)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--export", type=Path)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--reviews", type=Path, default=REVIEWS)
    parser.add_argument("--memory", default="3GB")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(REPO / "pipeline"))
    import duckdb

    scratch = Path(tempfile.mkdtemp(prefix="identity-check-"))
    db = duckdb.connect(str(scratch / "pipeline.duckdb"))
    db.execute(f"SET memory_limit = '{args.memory}'")
    db.execute(f"SET temp_directory = '{scratch / 'spill'}'")
    db.execute("SET threads = 3")
    db.execute("SET preserve_insertion_order = false")
    try:
        start = time.monotonic()
        build(db, args.export)
        print(f"all models: {time.monotonic() - start:.1f} s")
        report(db, args)
    finally:
        db.close()
        shutil.rmtree(scratch)


if __name__ == "__main__":
    main()
