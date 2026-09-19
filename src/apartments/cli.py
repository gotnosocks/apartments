from pathlib import Path

import duckdb
import typer
from dotenv import load_dotenv

from .csv_import import ingest_csv
from .archive_import import import_archive
from .db import DEFAULT_DB, connect
from .nyc import ingest_pluto
from .rentcast import collect
from .streeteasy import infer_furnishing_periods, ingest_export, reparse_capture_histories

app = typer.Typer(no_args_is_help=True, help="Collect, correct, model, and compare NYC rental data.")
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


@app.command("import-archive")
def import_streeteasy_archive(
    root: Path = typer.Argument(
        Path(__file__).resolve().parents[2] / "data/archive",
        help="Live StreetEasy Archive data directory.",
    ),
    db: Path = typer.Option(DEFAULT_DB),
    limit: int = typer.Option(0, min=0, help="Stop after this many new captures; zero imports all."),
):
    counts = import_archive(root, db, limit)
    typer.echo(
        "Imported {imported} new captures and {events} history events "
        "({skipped} already present, {unrecognized} non-detail pages, {failed} failures).".format(**counts)
    )
    if counts["failed"]:
        raise typer.Exit(1)


@app.command("reparse-history")
def reparse_history(
    root: Path = typer.Argument(Path("data")),
    db: Path = typer.Option(DEFAULT_DB),
):
    units, events = reparse_capture_histories(root, str(db))
    typer.echo(f"Reparsed {events} history events for {units} units into {db}")


@app.command("backfill-temporal")
def backfill_temporal(
    archive: Path = typer.Option(Path(__file__).resolve().parents[2] / "data/archive"),
    db: Path = typer.Option(DEFAULT_DB),
):
    """Retain attribute versions and fetch evidence from existing local data."""
    import sqlite3
    from .temporal import backfill_capture_history, sync_observations
    source = sqlite3.connect((archive.resolve() / 'archive.sqlite3').as_uri() + '?mode=ro', uri=True)
    target = connect(db)
    try:
        target.execute('BEGIN TRANSACTION')
        try:
            observations = sync_observations(source, target)
            target.execute('COMMIT')
        except Exception:
            target.execute('ROLLBACK')
            raise
        versions = backfill_capture_history(target, source)
    finally:
        target.close()
        source.close()
    typer.echo(f"Added {versions} attribute versions and {observations} collection observations; no pages downloaded.")


@app.command("infer-furnishing-periods")
def infer_furnishing(
    db: Path = typer.Option(DEFAULT_DB),
    building_slug: str = typer.Option("the-sierra-chelsea"),
):
    periods = infer_furnishing_periods(str(db), building_slug)
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


corrections_app = typer.Typer(no_args_is_help=True, help="Append-only human correction overlays.")
app.add_typer(corrections_app, name="corrections")


@corrections_app.command("add")
def correction_add(
    spec: Path,
    author: str = typer.Option(...),
    reason: str = typer.Option(...),
    ledger: Path = typer.Option(Path("config/corrections.jsonl")),
    evidence: list[str] = typer.Option(None),
):
    """Append an edit or explicit revision from a JSON specification."""
    import json
    from .corrections import append
    record = append(ledger, author=author, reason=reason,
                    edit=json.loads(spec.read_text()), evidence=evidence)
    typer.echo(json.dumps(record, indent=2))


@corrections_app.command("retract")
def correction_retract(
    correction_id: str,
    author: str = typer.Option(...),
    reason: str = typer.Option(...),
    ledger: Path = typer.Option(Path("config/corrections.jsonl")),
):
    """Withdraw an active correction without deleting its history."""
    import json
    from .corrections import append
    typer.echo(json.dumps(append(ledger, author=author, reason=reason,
                                 retracts=correction_id), indent=2))


@corrections_app.command("list")
def correction_list(
    ledger: Path = typer.Option(Path("config/corrections.jsonl")),
    as_of: str | None = typer.Option(None),
):
    """Inspect the ledger and active edits at a knowledge-time cutoff."""
    import json
    from .corrections import Overlay
    overlay = Overlay(ledger, as_of=as_of)
    typer.echo(json.dumps({'manifest': overlay.manifest, 'history': overlay.records}, indent=2))


@app.command("export-observations")
def observation_export(
    output: Path,
    db: Path = typer.Option(DEFAULT_DB),
    ledger: Path = typer.Option(Path("config/corrections.jsonl")),
    corrections_as_of: str | None = typer.Option(None),
    known_as_of: str | None = typer.Option(None, help="One cutoff for collection, interpretation and human corrections."),
    collected_as_of: str | None = typer.Option(None),
    interpreted_as_of: str | None = typer.Option(None),
    effective_at: str | None = typer.Option(None),
    version_id: str | None = typer.Option(None),
    raw_only: bool = typer.Option(False),
):
    """Export raw and corrected attribute observations; run large exports on Modal."""
    import json
    from .corrections import Overlay
    from .observation_dataset import export_observations
    overlay = Overlay(ledger, as_of=corrections_as_of or known_as_of or interpreted_as_of, enabled=not raw_only)
    manifest = export_observations(db, output, overlay,
        collected_as_of=collected_as_of, interpreted_as_of=interpreted_as_of,
        effective_at=effective_at, version_id=version_id, known_as_of=known_as_of)
    typer.echo(json.dumps(manifest, indent=2))


@app.command("build-analytical")
def analytical_build(
    output: Path,
    as_of: str = typer.Option(..., help="Inclusive knowledge cutoff, ISO date or zoned timestamp."),
    db: Path = typer.Option(DEFAULT_DB),
    ledger: Path = typer.Option(Path("config/corrections.jsonl")),
):
    """Build dated attributes and contemporary price observations; identical reruns verify and reuse."""
    import json
    from .analytical import build_dataset
    typer.echo(json.dumps(build_dataset(db, output, as_of=as_of, ledger=ledger), indent=2))


@app.command("fit-pricing-legacy")
def pricing_fit_legacy(
    dataset: Path,
    output: Path,
    holdout_fraction: float = typer.Option(.2, min=0, max=.99, help="Later-month holdout; 0 explicitly fits descriptively without validation."),
    ridge: float = typer.Option(1.0, min=.000001),
):
    """Fit the archived robust/ridge baseline; not the main Bayesian model."""
    import json
    from .research_pipeline import fit_dataset
    typer.echo(json.dumps(fit_dataset(dataset, output, holdout_fraction=holdout_fraction, ridge=ridge), indent=2))


@app.command("fit-pricing")
def pricing_fit(
    dataset: Path,
    output: Path,
    draws: int = typer.Option(4000, min=1, help="Retained posterior draws per chain."),
    tune: int = typer.Option(2000, min=1, help="Warmup draws per chain."),
    chains: int = typer.Option(4, min=2, help="Independent PyMC/NUTS chains."),
    seed: int = typer.Option(20260918, min=0),
    spec: str = typer.Option("full_half_balance", help="Bathroom encoding: full_half_balance, full_half, incremental_total or linear_total."),
    residual_scale: str = typer.Option("shared", help="shared or bedroom; changes the observation-noise model."),
    target_accept: float = typer.Option(.93, help="NUTS target acceptance, strictly between zero and one."),
    adaptation: str = typer.Option("diag", help="Exact NUTS adaptation: diag or low_rank."),
    prior_multiplier: float = typer.Option(1., help="Positive feature prior scale multiplier."),
    building_prior_scale: float = typer.Option(.35, help="Positive building hierarchy scale prior."),
    unit_prior_scale: float = typer.Option(.25, help="Positive within-building unit hierarchy scale prior."),
    residual_parameterization: str = typer.Option("centered", help="centered or noncentered bedroom-noise hierarchy; inert with shared noise."),
    graph_validation: Path | None = typer.Option(None, help="Optional verified graph parity bundle bound into the protocol."),
    execution: str = typer.Option("disk", help="disk for durable traces and bounded reports; memory to replay older execution protocols."),
    floor_increments: bool = typer.Option(True, '--floor-increments/--linear-floor',
        help="Use listed-floor threshold increments by default; linear-floor is for explicit legacy research/replay."),
    floor_increment_prior_scale: float = typer.Option(.15, help="Positive prior scale for each floor threshold increment."),
):
    """Fit the main exact PyMC model from a verified bathroom source projection.

    Publishes immutable protocol/posterior products; never promotes a fit or
    falls back to another model. Existing matching checkpoints may be resumed.
    """
    import json
    from argparse import Namespace
    from models import bayesian_disk_experiment as disk_runner
    from threadpoolctl import threadpool_limits
    args = Namespace(dataset=dataset, output=output, draws=draws, tune=tune,
        chains=chains, seed=seed, spec=spec, residual_scale=residual_scale,
        target_accept=target_accept, adaptation=adaptation, prior_multiplier=prior_multiplier,
        building_prior_scale=building_prior_scale, unit_prior_scale=unit_prior_scale,
        residual_parameterization=residual_parameterization, graph_validation=graph_validation,
        floor_increments=floor_increments, floor_increment_prior_scale=floor_increment_prior_scale)
    try:
        if execution not in ('disk', 'memory'):
            raise ValueError('execution must be disk or memory')
        model_runner = disk_runner.increments if floor_increments else disk_runner.linear
        model_runner.validate_args(args)
        runner = disk_runner if execution == 'disk' else model_runner
        # Match the arithmetic used by exact design reconstruction in analysis.
        with threadpool_limits(limits=1, user_api='blas'):
            result = runner.run(args)
    except (ValueError, OSError) as error:
        typer.echo(f"PyMC fit failed: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(json.dumps(result, indent=2, allow_nan=False))


@app.command("analyze-apartment")
def apartment_analyze(
    audit_id: str,
    selection: Path | None = typer.Option(None, help="Main PyMC selection JSON; defaults to config/main-analysis.json."),
    changes: str | None = typer.Option(None, help='Optional simultaneous source-valued JSON changes, e.g. {"bedrooms":2,"full_bathrooms":2}.'),
):
    """Inspect a selected, verified posterior and optional joint counterfactual.

    Uses all retained draws and the same diagnostic/support gates as the main
    UI. This command never fits, scrapes, edits source data or selects a new fit.
    """
    import json
    from . import main_analysis
    from .bayesian_analysis import BayesianAnalysis
    def object_without_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON change key: '+key)
            result[key] = value
        return result
    def reject_constant(value):
        raise ValueError('Nonfinite JSON value: '+value)
    def finite_float(value):
        import math
        number = float(value)
        if not math.isfinite(number):
            reject_constant(value)
        return number
    try:
        requested = None
        if changes is not None:
            requested = json.loads(changes, object_pairs_hook=object_without_duplicates,
                                   parse_constant=reject_constant, parse_float=finite_float)
            if not isinstance(requested, dict) or not requested:
                raise ValueError('Changes must be a nonempty JSON object of source-valued fields')
        selected, experiment, dataset = main_analysis.load_selection(selection or main_analysis.DEFAULT_SELECTION)
        workspace = BayesianAnalysis.load(experiment, dataset)
        try:
            result = {'selection': selected, 'detail': workspace.detail(audit_id)}
            if requested is not None:
                result['counterfactual'] = workspace.counterfactual(audit_id, requested)
        finally:
            workspace.close()
        typer.echo(json.dumps(result, indent=2, allow_nan=False))
    except (ValueError, OSError, KeyError) as error:
        typer.echo(f"Bayesian analysis failed: {error}", err=True)
        raise typer.Exit(1) from error


@app.command("build-historical")
def historical_build(
    dataset: Path,
    output: Path,
    as_of: str = typer.Option(..., help="Knowledge cutoff no earlier than the canonical dataset completion."),
    ledger: Path = typer.Option(Path('config/corrections.jsonl')),
    start: str = typer.Option('2010-01-01'),
    end: str | None = typer.Option(None),
    description_recovery: Path | None = typer.Option(None, help="Verified immutable archive-description recovery bundle."),
):
    """Reconstruct historical own-advertisement asking rents with dated corrections."""
    import json
    from .historical_dataset import build_historical_dataset
    typer.echo(json.dumps(build_historical_dataset(dataset, output, as_of=as_of,
        ledger=ledger, start=start, end=end, description_recovery=description_recovery), indent=2))


@app.command("rank-apartments")
def apartment_rank(
    candidates: Path,
    preferences: Path,
    output: Path,
    unknown_policy: str = typer.Option('exclude', help="exclude or zero for missing valued attributes."),
    budget: float | None = typer.Option(None, min=.01, help="Maximum monthly asking rent."),
    model: Path | None = typer.Option(None, help="Optional verified pricing bundle for a separate market comparison."),
):
    """Rank an explicit candidate JSONL snapshot by dollar preferences and Pareto efficiency."""
    import json
    from .research_pipeline import rank_candidates
    typer.echo(json.dumps(rank_candidates(candidates, preferences, output,
        unknown_policy=unknown_policy, budget=budget, model_bundle=model), indent=2))


@app.command("score-apartments")
def apartment_score(
    candidates: Path,
    preferences: Path,
    model: Path,
    output: Path,
    as_of: str = typer.Option(..., help="Explicit collection/knowledge cutoff for this candidate snapshot."),
    max_age_days: float = typer.Option(7, min=0, help="Maximum age of an ACTIVE capture."),
    budget: float | None = typer.Option(None, min=.01),
    unknown_policy: str = typer.Option('exclude', help="exclude or zero for missing valued attributes."),
):
    """Legacy robust scoring; use rank-current-apartments for the selected PyMC fit."""
    import json
    from .candidate_search import score_candidates
    typer.echo(json.dumps(score_candidates(candidates, preferences, output, model_bundle=model,
        as_of=as_of, max_age_days=max_age_days, budget=budget, unknown_policy=unknown_policy), indent=2))


@app.command("rank-current-apartments")
def current_apartment_rank(
    preferences: Path,
    output: Path,
    selection: Path | None = typer.Option(None, help="Selected accepted PyMC fit; defaults to the repository main selection."),
    as_of: str = typer.Option(..., help="Capture/knowledge cutoff; this is not a historical model backtest."),
    max_age_days: float = typer.Option(7, min=0),
    budget: float | None = typer.Option(None, min=.01),
    unknown_policy: str = typer.Option('exclude', help="exclude or explicit zero for unknown valued attributes."),
):
    """Rank fitted current listings by preferences with separate PyMC posterior diagnostics."""
    import json
    from .bayesian_candidate_search import run
    from .main_analysis import DEFAULT_SELECTION
    try:
        result = run(preferences, output, selection=selection or DEFAULT_SELECTION, as_of=as_of,
                     max_age_days=max_age_days, budget=budget, unknown_policy=unknown_policy)
        typer.echo(json.dumps(result, indent=2, allow_nan=False))
    except (ValueError, OSError, KeyError) as error:
        typer.echo(f"Bayesian ranking failed: {error}", err=True)
        raise typer.Exit(1) from error


@app.command("build-candidates")
def candidate_build(
    dataset: Path,
    historical_reference: Path,
    output: Path,
    as_of: str = typer.Option(...),
    ledger: Path = typer.Option(Path('config/corrections.jsonl')),
    description_recovery: Path | None = typer.Option(None),
):
    """Build canonical capture-time search records, retaining active and inactive ads."""
    import json
    from .candidate_snapshot import build_snapshot
    typer.echo(json.dumps(build_snapshot(dataset,historical_reference,output,as_of=as_of,
        ledger=ledger,description_recovery=description_recovery),indent=2))


if __name__ == "__main__":
    app()
