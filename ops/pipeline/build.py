"""Build the data pipeline from the scraper's export and save its fit-ready rows and its ads.

    pipeline/.venv/bin/python ops/pipeline/build.py [--export DIR] [--state DIR] [--out DIR]

The script works in these steps:

1. It loads the SQLMesh project in `pipeline/`, with `PIPELINE_EXPORT` and `PIPELINE_STATE` set
   from its arguments. `config.py` reads the export's manifest once, as the project loads, so
   a file the exporter lists after that waits for the next build.
2. It plans and applies the `prod` environment. SQLMesh rebuilds each model whose fingerprint
   changed and every model below it, and runs each model's audits as it goes. When an audit
   fails, the script prints the failed models and exits with status 1, and the tables of the
   last good build stay in place. It writes nothing to OUT in that case.
3. It writes `analysis.rows` to a rows file and `analysis.ads` to an ads file in OUT, each
   sorted by `listing_id` and named by the first 16 hex digits of its SHA-256, such as
   `rows-04fe7ad81836fed2.parquet`. Two builds from the same export and the same code write
   the same bytes, so the second one finds its files already there. Both models are views, and
   the script counts their rows as it writes them.
4. It appends a line to `OUT/catalog.ndjson` for the build. The line gives the time the build
   finished, the commit of the code and whether the checkout had changes, each export file it
   read with its SHA-256, each file of the corrections ledger and of the unit ledger with its
   SHA-256 and the count of their entries in each status, each file of the city archive with
   its SHA-256, the seconds each rebuilt model took with its audits, each model's table and row
   count, the rows file and the ads file with their SHA-256, the wall time of each step, and
   the peak memory of the script and of its cgroup.
   The script takes the commit before it loads the project, and the export, ledger and city
   files from the variables `config.py` gave the project.
5. It runs SQLMesh's janitor, which drops the tables no environment has used for a week. When
   the janitor fails, the script prints a warning and still exits 0.

A fit can read the rows file by its name and check its SHA-256 against the catalog. The website
and the reviews of ads read the ads file the same way. The models' tables stay in the state
folder, under the names the catalog gives, for a week after a later build replaces them.
"""

from __future__ import annotations

import argparse
import hashlib
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
    """Run the five steps and return the catalog line, or raise SystemExit on a failed plan."""
    os.environ["PIPELINE_EXPORT"] = str(export)
    os.environ["PIPELINE_STATE"] = str(state)

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
    ctx = Context(paths=str(project))
    steps["load"] = time.time() - started
    variables = ctx.config.variables
    try:
        # The console prints the failed models.
        ctx.plan(auto_apply=True, no_prompts=True)
    except PlanError as error:
        raise SystemExit(f"build stopped: {error}") from error
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

    line = {
        "built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "code": code,
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
            {"rebuilt": rebuilt, "rows": line["rows"], "ads_file": line["ads_file"]},
            indent=1,
        )
    )
    print("seconds", line["seconds"], "peak MiB", line["peak_mib"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
