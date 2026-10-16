"""Build each fit-ready row's certificates of occupancy as of its date and compare the
buildings they describe with MapPLUTO and StreetEasy's building records.

    pipeline/.venv/bin/python ops/pipeline/certificates_check.py [--rows FILE] [--export DIR]
        [--memory SIZE] [--out FILE]

1. The script reads the rows file FILE, the newest rows-*.parquet under
   /data1/apartments/pipeline/datasets unless given, and puts its listing IDs, buildings and
   dates in a scratch DuckDB database as `analysis.candidates`. It then renders
   `analysis.building_certificates` with each model it reads but the candidates, and the models
   above those, runs them in order, the views as views and the rest as tables, and prints the
   seconds each took. It reads the export and the city cache config.py gives, or the export DIR
   with `--export`, and leaves the build's database alone. DuckDB gets SIZE of memory, 3GB
   unless given, and spills to the scratch folder past it.
2. It counts the rows by their flags, with the rows lacking a BIN apart, and the rows whose
   building has a BIN such as 1000000.
3. It counts the jobs in each set and the jobs in both.
4. For each building of the rows with a certificate by its latest ad, it compares the year of
   the first new building certificate with the year built of the building's lot in the latest
   MapPLUTO release and with the year StreetEasy gives, and the latest count of apartments with
   MapPLUTO's `unitsres` and StreetEasy's count. It prints the differences by size. For the
   years it also counts the buildings whose job DOB NOW files as a new building with existing
   elements to remain, the buildings built before 2012 by the source with a first certificate in
   2012 to 2014, and the buildings within 2 years of the other source's year.
5. With `--out` it writes the step's columns for each row to a Parquet file.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATASETS = Path("/data1/apartments/pipeline/datasets")


def newest_rows() -> Path:
    files = sorted(DATASETS.glob("rows-*.parquet"), key=lambda p: p.stat().st_mtime)
    if not files:
        sys.exit(f"no rows-*.parquet under {DATASETS}")
    return files[-1]


def build(db, export: Path | None) -> None:
    """Run `analysis.building_certificates`, each model it reads but `analysis.candidates`,
    the models above those, and `buildings.latest_record` into `db`, in order."""
    with tempfile.TemporaryDirectory(prefix="certificates-check-") as state:
        os.environ["PIPELINE_STATE"] = state
        if export:
            os.environ["PIPELINE_EXPORT"] = str(export)
        from sqlmesh import Context

        ctx = Context(paths=str(REPO / "pipeline"))
        step = ctx.get_model("analysis.building_certificates")
        candidates = ctx.get_model("analysis.candidates").fqn
        inputs = step.depends_on - {candidates}
        inputs |= {ctx.get_model("buildings.latest_record").fqn}
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


def show(db, title: str, sql: str) -> None:
    print(title)
    text = db.sql(sql).fetchdf().to_string(index=False)
    print("    " + text.replace("\n", "\n    "))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rows", type=Path)
    parser.add_argument("--export", type=Path)
    parser.add_argument("--memory", default="3GB")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(REPO / "pipeline"))
    import duckdb

    rows = args.rows or newest_rows()
    print(f"rows: {rows}")
    scratch = Path(tempfile.mkdtemp(prefix="certificates-check-"))
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
        show(
            db,
            "rows by flags:",
            """
            SELECT c.bin IS NOT NULL AS bin, l.bin LIKE '_000000' AS placeholder_bin,
                c.new_building, c.altered, c.units IS NOT NULL AS units,
                count(*) AS rows, count(DISTINCT c.building_id) AS buildings
            FROM analysis.building_certificates c
            LEFT JOIN buildings.lots l USING (building_id)
            GROUP BY ALL ORDER BY ALL
        """,
        )
        # The step's CTEs aren't tables, so the check reads the latest copies as the step does.
        show(
            db,
            "certificates and jobs in each set's latest copy:",
            """
            WITH earlier AS (
                SELECT DISTINCT trim(job_number) AS job FROM city.dob_co
                WHERE release = (SELECT arg_max(release, published) FROM city.dob_co)
            ), later AS (
                SELECT DISTINCT trim(job_filing_name) AS job FROM city.dob_now_co
                WHERE release = (SELECT arg_max(release, published) FROM city.dob_now_co)
            )
            SELECT (SELECT count(*) FROM earlier) AS dob_co_jobs,
                (SELECT count(*) FROM later) AS dob_now_co_jobs,
                (SELECT count(*) FROM earlier JOIN later USING (job)) AS jobs_in_both
        """,
        )
        db.execute("""
            CREATE TABLE buildings_compared AS
            WITH latest AS (
                SELECT arg_max(release, published) AS release FROM city.pluto
            ), pluto AS (
                SELECT try_cast(bbl AS DOUBLE)::BIGINT::VARCHAR AS bbl,
                    nullif(try_cast(yearbuilt AS INTEGER), 0) AS pluto_year,
                    try_cast(unitsres AS INTEGER) AS pluto_units
                FROM city.pluto WHERE release = (SELECT release FROM latest)
            ), last_ad AS (
                SELECT arg_max(c, c.first_day) AS c FROM analysis.building_certificates c
                WHERE c.bin IS NOT NULL GROUP BY c.building_id
            ), kept AS (
                SELECT DISTINCT trim(bin) AS bin, trim(job_filing_name) AS new_building_job
                FROM city.dob_now_co
                WHERE release = (SELECT arg_max(release, published) FROM city.dob_now_co)
                    AND trim(job_type) = 'CO - New Building with Existing Elements to Remain'
            )
            SELECT c.building_id, c.bin, l.bbl, year(c.new_building_since) AS co_year,
                c.units AS co_units, p.pluto_year, p.pluto_units,
                r.year_built AS streeteasy_year, r.residential_units AS streeteasy_units,
                k.bin IS NOT NULL AS kept_elements
            FROM (SELECT unnest(c) FROM last_ad) c
            JOIN buildings.lots l USING (building_id)
            LEFT JOIN pluto p USING (bbl)
            LEFT JOIN buildings.latest_record r USING (building_id)
            LEFT JOIN kept k ON k.bin = c.bin AND k.new_building_job = c.new_building_job
            WHERE c.new_building OR c.units IS NOT NULL
        """)
        for source, other in (("pluto", "streeteasy"), ("streeteasy", "pluto")):
            show(
                db,
                f"buildings by first new building certificate's year less {source}'s year:",
                f"""
                SELECT CASE WHEN {source}_year IS NULL THEN 'no year'
                    WHEN co_year - {source}_year < -1 THEN 'below -1'
                    WHEN co_year - {source}_year <= 2 THEN (co_year - {source}_year)::TEXT
                    WHEN co_year - {source}_year <= 5 THEN '3 to 5'
                    WHEN co_year - {source}_year <= 30 THEN '6 to 30'
                    ELSE 'above 30' END AS difference,
                    count(*) AS buildings,
                    count(*) FILTER (WHERE kept_elements) AS kept_elements,
                    count(*) FILTER (WHERE {source}_year < 2012 AND co_year <= 2014)
                        AS before_2012_first_by_2014,
                    count(*) FILTER (WHERE abs(co_year - {other}_year) <= 2)
                        AS {other}_within_2
                FROM buildings_compared WHERE co_year IS NOT NULL GROUP BY 1 ORDER BY 1
            """,
            )
            show(
                db,
                f"buildings by latest certificate's apartments against {source}'s count:",
                f"""
                SELECT CASE WHEN {source}_units IS NULL THEN 'no count'
                    WHEN co_units = {source}_units THEN 'same'
                    WHEN abs(co_units - {source}_units) <= 0.05 * {source}_units
                        THEN 'within 5%'
                    WHEN co_units < {source}_units THEN 'fewer'
                    ELSE 'more' END AS comparison,
                    count(*) AS buildings
                FROM buildings_compared WHERE co_units IS NOT NULL GROUP BY 1 ORDER BY 1
            """,
            )
        show(
            db,
            "buildings whose first new building certificate is 3 or more years off both:",
            """
            SELECT building_id, bin, bbl, co_year, pluto_year, streeteasy_year, co_units,
                pluto_units, streeteasy_units
            FROM buildings_compared
            WHERE abs(co_year - pluto_year) >= 3 AND abs(co_year - streeteasy_year) >= 3
            ORDER BY abs(co_year - pluto_year) DESC LIMIT 15
        """,
        )
        if args.out:
            db.execute(
                f"COPY analysis.building_certificates TO '{args.out}' (FORMAT parquet)"
            )
        db.close()
    finally:
        shutil.rmtree(scratch)


if __name__ == "__main__":
    main()
