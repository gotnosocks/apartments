"""Build the data pipeline from the scraper's export and save its fit-ready rows, its ads and its
records.

    pipeline/.venv/bin/python ops/pipeline/build.py [--export DIR] [--state DIR] [--out DIR]

The script works in these steps:

1. It loads the SQLMesh project in `pipeline/`, with `PIPELINE_EXPORT` and `PIPELINE_STATE` set
   from its arguments. `config.py` reads the export's manifest once, as the project loads, so
   a file the exporter lists after that waits for the next build.
   It first loads the project with `PIPELINE_INCREMENTAL` set to 1 and checks, in `can_top_up`,
   whether the prod build's tables allow a top-up build, one that reads only the answers
   missing from them. When the check fails, it loads the project again with the variable set
   to 0, and the build reads every answer.
2. It plans and applies the `prod` environment. SQLMesh rebuilds each model whose fingerprint
   changed and every model below it, and runs each model's audits as it goes. When an audit
   fails, the script prints the failed models and exits with status 1, and the tables of the
   last good build stay in place. It writes nothing to OUT in that case. After a plan that
   applies, it writes the SHA-256 of the code merging a top-up's rows to `STATE/merge.json`,
   with the value of `PIPELINE_INCREMENTAL` it loaded the project with and the mode that ran,
   from the column `incremental` of `ads.changes`. The two differ when `ads.changes` finds the
   previous answers changed and reads every answer. With that file deleted, the next build
   reads every answer.
3. It writes `analysis.rows` to a rows file and `analysis.ads` to an ads file in OUT, each
   sorted by `listing_id` and named by the first 16 hex digits of its SHA-256, such as
   `rows-04fe7ad81836fed2.parquet`. Two builds from the same export and the same code write
   the same bytes, so the second one finds its files already there. Both models are views, and
   the script counts their rows as it writes them.
4. It writes the records file, `records-<hash>.parquet`, with `steps/records.py`: each distinct
   API record of an ad, in the form the frontier builders read from the granular export. The
   step keeps the records it has read in `STATE/records/`, so a build reads only the records
   missing from them.
5. It appends a line to `OUT/catalog.ndjson` for the build. The line gives the time the build
   finished, the commit of the code and whether the checkout had changes, whether the build was
   a top-up, the value of `PIPELINE_STALE_DAYS` it built with, each export file it read with its
   SHA-256, each file of the corrections ledger and of the unit ledger with its SHA-256 and the
   count of their entries in each status, each file of the city archive with its SHA-256, the
   seconds each rebuilt model took with its audits, each model's table and row count, the rows,
   ads and records files with their SHA-256, the wall time of each step, and the peak memory of
   the script and of its cgroup.
   The script takes the commit before it loads the project, and the export, ledger and city
   files from the variables `config.py` gave the project.
6. It runs SQLMesh's janitor, which drops the tables no environment has used for a week. When
   the janitor fails, the script prints a warning and still exits 0.

A fit can read the rows file by its name and check its SHA-256 against the catalog. The website
and the reviews of ads read the ads file the same way, and the frontier builders the records
file. The models' tables stay in the state folder, under the names the catalog gives, for a week
after a later build replaces them.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import resource
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PROJECT = REPO / "pipeline"
DEFAULT_EXPORT = Path("/data1/apartments/archive/crawls/api/export")
DEFAULT_STATE = Path("/data1/apartments/pipeline/state")
DEFAULT_OUT = Path("/data1/apartments/pipeline/datasets")
# The files each build writes, by the stem of their names.
FILES = {"rows": "analysis.rows", "ads": "analysis.ads"}
WRITE_THREADS = 8
# The code merging a top-up build's rows into the previous tables. The state folder keeps its
# SHA-256 as of the last finished build in MERGE_RECORD, with that build's variable and mode.
MERGE_CODE = ("materializations/merge.py", "models/ads/changes.py")
MERGE_RECORD = "merge.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def code_version(project: Path) -> dict:
    """The checkout's commit, and whether the pipeline or the chain's code differs from it."""

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(project), *args],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    changes = git("status", "--porcelain", "--", ".", "../src", "../ops/pipeline")
    return {"commit": git("rev-parse", "HEAD"), "clean": not changes}


def peak_mib() -> dict:
    """The script's peak resident memory, DuckDB's included, and the peak of its cgroup.

    The cgroup's peak counts the worker processes and the page cache too. Run as its own unit,
    the script's cgroup is the unit's, and its peak is the memory peak systemd reports."""
    script = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)
    # The unified hierarchy's line reads `0::/path`. Without one, the cgroup is left out.
    lines = Path("/proc/self/cgroup").read_text().splitlines()
    groups = [line[3:] for line in lines if line.startswith("0::")]
    if not groups:
        return {"script": script, "cgroup": None, "cgroup_peak": None}
    peak = Path("/sys/fs/cgroup", groups[0].lstrip("/"), "memory.peak")
    return {
        "script": script,
        "cgroup": groups[0].rsplit("/", 1)[-1],
        "cgroup_peak": round(int(peak.read_text()) / 2**20) if peak.exists() else None,
    }


def merge_code(project: Path) -> str:
    digest = hashlib.sha256()
    for name in MERGE_CODE:
        digest.update((project / name).read_bytes())
    return digest.hexdigest()


def can_top_up(ctx, state: Path, project: Path) -> bool:
    """Whether this build reads only the answers missing from the prod build's tables.

    The context is loaded with `PIPELINE_INCREMENTAL` set to 1. A top-up needs the state
    folder's record to give the checkout's merge code, and each model of kind `merge`, and each
    model above one, to have the definition of its prod snapshot. A top-up gives raw.ads new
    variables, so for raw.ads the check compares the query alone. The merge code covers
    ads.changes, whose variable `incremental` gives the mode.

    When raw.ads has its prod fingerprint, the build has no new answers to read, and the
    function returns the variable the last build loaded with, from the record. ads.changes
    then keeps its prod fingerprint, and the plan leaves its table in place and rebuilds only
    the models below an edit."""
    try:
        record = json.loads((state / MERGE_RECORD).read_text())
    except (OSError, ValueError):
        return False
    if not isinstance(record, dict) or record.get("code") != merge_code(project):
        return False
    env = ctx.state_reader.get_environment("prod")
    if env is None or env.finalized_ts is None:
        return False
    before = {s.name: s for s in ctx.state_reader.get_snapshots(env.snapshots).values()}
    names, new_answers = set(), True
    for model in ctx.models.values():
        if model.kind.is_custom and model.kind.materialization == "merge":
            names.update([model.fqn, *ctx.dag.upstream(model.fqn)])
    for name in names:
        now, then = ctx.snapshots[name], before.get(name)
        if then is None:
            return False
        if now.model.name == "raw.ads":
            same = now.model.query.sql() == then.model.query.sql()
            new_answers = now.fingerprint.data_hash != then.fingerprint.data_hash
        elif now.model.name == "ads.changes":
            same = True
        else:
            same = now.fingerprint.data_hash == then.fingerprint.data_hash
        if not same:
            return False
    return new_answers or record.get("incremental") is True


def write(ctx, name: str, stem: str, out: Path) -> dict:
    """Write the model `name`, sorted by `listing_id`, to OUT/<stem>-<hash>.parquet and return
    the file's name, SHA-256 and row count."""
    part = out / f"{stem}-{os.getpid()}.parquet.part"
    # On Oct 16, sorting the ads file's 2.1M rows with all twelve threads ran out of a 3 GB
    # limit, and eight threads wrote it in 8 s.
    ctx.engine_adapter.execute(f"SET threads = {WRITE_THREADS}")
    try:
        (rows,) = ctx.engine_adapter.fetchone(
            f"""COPY (SELECT * FROM {name} ORDER BY listing_id) TO '{part}'
            (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 122880)"""
        )
        digest = sha256(part)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    finally:
        ctx.engine_adapter.execute("RESET threads")
    target = out / f"{stem}-{digest[:16]}.parquet"
    if target.exists() and sha256(target) == digest:
        part.unlink()
    else:
        part.rename(target)
    return {"path": target.name, "sha256": digest, "rows": rows}


def build(export: Path, state: Path, out: Path, project: Path = PROJECT) -> dict:
    """Run the six steps and return the catalog line, or raise SystemExit on a failed plan."""
    os.environ["PIPELINE_EXPORT"] = str(export)
    os.environ["PIPELINE_STATE"] = str(state)

    records = importlib.import_module("steps.records")
    # The venv's editable install can load the step from another checkout, whose records would
    # then go into the catalog line of this one. The check runs before the plan, so a wrong
    # venv stops the build at once.
    if (
        Path(records.__file__).read_bytes()
        != (project / "steps" / "records.py").read_bytes()
    ):
        raise SystemExit(
            f"the build loaded steps.records from {records.__file__}, which differs from "
            f"{project / 'steps' / 'records.py'}; run `uv sync` in the pipeline folder of the "
            "checkout to build"
        )

    import sqlmesh.core.console
    from sqlmesh import Context
    from sqlmesh.core.console import TerminalConsole
    from sqlmesh.utils.errors import PlanError

    class Console(TerminalConsole):
        """The terminal console, keeping each model's evaluation time."""

        seconds: dict[str, float] = {}

        def update_snapshot_evaluation_progress(
            self, snapshot, interval, batch_idx, duration_ms, *args, **kwargs
        ):
            if duration_ms is not None:
                name = snapshot.name.replace('"', "").removeprefix("pipeline.")
                self.seconds[name] = self.seconds.get(name, 0) + duration_ms / 1000
            super().update_snapshot_evaluation_progress(
                snapshot, interval, batch_idx, duration_ms, *args, **kwargs
            )

    console = Console()
    sqlmesh.core.console.set_console(console)
    started = time.time()
    steps = {}

    code = code_version(project)
    merge = merge_code(project)
    mode = os.environ.get("PIPELINE_INCREMENTAL")
    try:
        os.environ["PIPELINE_INCREMENTAL"] = "1"
        ctx = Context(paths=str(project))
        incremental = can_top_up(ctx, state, project)
        if not incremental:
            ctx.close()
            os.environ["PIPELINE_INCREMENTAL"] = "0"
            ctx = Context(paths=str(project))
    finally:
        if mode is None:
            os.environ.pop("PIPELINE_INCREMENTAL")
        else:
            os.environ["PIPELINE_INCREMENTAL"] = mode
    steps["load"] = time.time() - started
    variables = ctx.config.variables
    try:
        # The console prints the failed models.
        ctx.plan(auto_apply=True, no_prompts=True)
    except PlanError as error:
        raise SystemExit(f"build stopped: {error}") from error
    # ads.changes reads every answer when the previous ones no longer hold, so the mode that
    # ran comes from its table, as the materialization `merge` reads it.
    (top_up,) = ctx.engine_adapter.fetchone(
        "SELECT coalesce(bool_and(incremental), true) FROM ads.changes"
    )
    record = {"code": merge, "incremental": incremental, "top_up": top_up}
    (state / MERGE_RECORD).write_text(json.dumps(record) + "\n")
    steps["plan"] = time.time() - started - steps["load"]

    mark = time.time()
    models = {}
    for snapshot in sorted(ctx.snapshots.values(), key=lambda s: s.name):
        name = snapshot.name.replace('"', "").removeprefix("pipeline.")
        # The models written to files are counted as they're written.
        if name in FILES.values():
            rows = None
        else:
            (rows,) = ctx.engine_adapter.fetchone(f"SELECT count(*) FROM {name}")
        models[name] = {
            "table": snapshot.table_name(),
            "rows": rows,
            "seconds": round(console.seconds[name], 1)
            if name in console.seconds
            else None,
        }
    # The entries of the ledger and of the unit ledger, counted by status and then by change.
    ledger = {}
    for status, change, count in ctx.engine_adapter.fetchall(
        "SELECT status, change, count(*) FROM ledger.status GROUP BY ALL ORDER BY ALL"
    ):
        ledger.setdefault(status, {})[change] = count
    units = {}
    for status, change, count in ctx.engine_adapter.fetchall(
        "SELECT status, change, count(*) FROM ledger.unit_status GROUP BY ALL ORDER BY ALL"
    ):
        units.setdefault(status, {})[change] = count
    steps["count"] = time.time() - mark

    mark = time.time()
    out.mkdir(parents=True, exist_ok=True)
    files = {stem: write(ctx, name, stem, out) for stem, name in FILES.items()}
    for stem, name in FILES.items():
        models[name]["rows"] = files[stem]["rows"]
    steps["write"] = time.time() - mark

    mark = time.time()
    files["records"] = records.write(
        ctx.engine_adapter.connection.cursor(), variables["ads"], state / "records", out
    )
    steps["records"] = time.time() - mark

    line = {
        "built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "code": code,
        "top_up": top_up,
        "stale_days": variables["stale_days"],
        "export": str(export),
        **{
            table: {
                "version": variables[f"{table}_version"],
                "files": variables["export_files"][table],
            }
            for table in ("ads", "buildings")
        },
        "ledger": {
            "files": variables["ledger"],
            "entries": ledger,
            "units": {"files": variables["ledger_units"], "entries": units},
        },
        "city": variables["city_files"],
        "models": models,
        "rows": files["rows"],
        # The export's files are under "ads", so the ads file goes under "ads_file".
        "ads_file": files["ads"],
        "records": files["records"],
        "seconds": {step: round(value, 1) for step, value in steps.items()}
        | {"total": round(time.time() - started, 1)},
        "peak_mib": peak_mib(),
    }
    with open(out / "catalog.ndjson", "a") as f:
        f.write(json.dumps(line, sort_keys=True) + "\n")
    try:
        ctx.run_janitor(ignore_ttl=False)
    except Exception as error:
        # By now the files and their catalog line are written. The next build runs the janitor
        # again.
        print(f"janitor failed: {error}", file=sys.stderr)
    ctx.close()
    return line


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--export", type=Path, default=DEFAULT_EXPORT)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    line = build(args.export.resolve(), args.state.resolve(), args.out.resolve())
    rebuilt = {
        name: model["seconds"]
        for name, model in line["models"].items()
        if model["seconds"] is not None
    }
    print(
        json.dumps(
            {
                "rebuilt": rebuilt,
                "rows": line["rows"],
                "ads_file": line["ads_file"],
                "records": line["records"],
            },
            indent=1,
        )
    )
    print("seconds", line["seconds"], "peak MiB", line["peak_mib"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
