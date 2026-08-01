from pathlib import Path

import duckdb
import typer
from dotenv import load_dotenv

from .csv_import import ingest_csv
from .db import DEFAULT_DB, connect
from .nyc import ingest_pluto
from .rentcast import collect
from .streeteasy import infer_furnishing_periods, ingest_export, reparse_capture_histories

app = typer.Typer(no_args_is_help=True, help="Collect and inspect Chelsea rental data.")
load_dotenv()


@app.command("init")
def init(db: Path = typer.Option(DEFAULT_DB)):
    connect(db).close()
    typer.echo(f"Initialized {db}")


@app.command("fetch-nyc")
def fetch_nyc(db: Path = typer.Option(DEFAULT_DB)):
    count = ingest_pluto(str(db))
    typer.echo(f"Loaded {count} PLUTO building lots into {db}")


@app.command("collect-rentcast")
def collect_rentcast(
    scope: str = typer.Option("building", help="building or street"),
    db: Path = typer.Option(DEFAULT_DB),
):
    if scope not in {"building", "street"}:
        raise typer.BadParameter("scope must be building or street")
    requested, accepted, raw_path = collect(scope, str(db))
    typer.echo(f"Received {requested}; accepted {accepted} for {scope}; raw: {raw_path}")


@app.command("import-csv")
def import_csv(
    path: Path,
    scope: str = typer.Option("building", help="building or street"),
    db: Path = typer.Option(DEFAULT_DB),
):
    count = ingest_csv(path, scope, str(db))
    typer.echo(f"Imported {count} rows into {db}")


@app.command("import-streeteasy-json")
def import_streeteasy_json(
    path: Path,
    db: Path = typer.Option(DEFAULT_DB),
):
    source_id, events = ingest_export(path, str(db))
    typer.echo(f"Imported {source_id} with {events} price-history events into {db}")


@app.command("import-captures")
def import_captures(
    root: Path = typer.Argument(Path("data/captures")),
    db: Path = typer.Option(DEFAULT_DB),
):
    files = sorted(root.rglob("structured.json"))
    imported = 0
    failures = []
    connection = connect(db)
    for path in files:
        try:
            ingest_export(path, str(db), connection=connection)
            imported += 1
        except Exception as error:  # Report all malformed bundles after processing.
            failures.append((path, error))
    connection.close()
    typer.echo(f"Imported {imported}/{len(files)} capture bundles into {db}")
    for path, error in failures:
        typer.echo(f"FAILED {path}: {error}", err=True)
    if failures:
        raise typer.Exit(1)


@app.command("reparse-history")
def reparse_history(
    root: Path = typer.Argument(Path("data")),
    db: Path = typer.Option(DEFAULT_DB),
):
    units, events = reparse_capture_histories(root, str(db))
    typer.echo(f"Reparsed {events} history events for {units} units into {db}")


@app.command("infer-furnishing-periods")
def infer_furnishing(
    db: Path = typer.Option(DEFAULT_DB),
):
    periods = infer_furnishing_periods(str(db))
    typer.echo(f"Created {len(periods)} historical furnishing periods in {db}")


@app.command("summary")
def summary(db: Path = typer.Option(DEFAULT_DB)):
    connection = connect(db)
    row = connection.execute(
        """SELECT count(DISTINCT source_listing_id) listings,
                  min(asking_rent) minimum_rent,
                  round(median(asking_rent)) median_rent,
                  max(asking_rent) maximum_rent
           FROM listing_snapshots"""
    ).fetchone()
    typer.echo("listings  minimum_rent  median_rent  maximum_rent")
    typer.echo(f"{row[0]:8}  {str(row[1]):>12}  {str(row[2]):>11}  {str(row[3]):>12}")
    connection.close()


if __name__ == "__main__":
    app()
