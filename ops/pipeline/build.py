"""Build the data pipeline from the scraper's export and save its fit-ready rows.

    pipeline/.venv/bin/python ops/pipeline/build.py [--export DIR] [--state DIR] [--out DIR]

The script works in these steps:

1. It loads the SQLMesh project in `pipeline/`, with `PIPELINE_EXPORT` and `PIPELINE_STATE` set
   from its arguments. `config.py` reads the export's manifest once, as the project loads, so
   a file the exporter lists after that waits for the next build.
2. It plans and applies the `prod` environment. SQLMesh rebuilds each model whose fingerprint
   changed and every model below it, and runs each model's audits as it goes. When an audit
   fails, the script prints the failed models and exits with status 1, and the tables of the
   last good build stay in place. It writes nothing to OUT in that case.
3. It writes `analysis.rows`, sorted by `listing_id`, to a Parquet file in OUT, and names the
   file by the first 16 hex digits of its SHA-256. Two builds from the same export and the same
   code write the same bytes, so the second one finds its file already there.
4. It appends a line to `OUT/catalog.ndjson` for the build. The line gives the time the build
   finished, the commit of the code and whether the checkout had changes, each export file it
   read with its SHA-256, the seconds each rebuilt model took with its audits, each model's
   table and row count, the rows file with its SHA-256, the wall time of each step, and the
   peak memory of the script and of its cgroup.

A fit reads the rows file by its name and checks the SHA-256 against the catalog. The models'
tables stay in the state folder, under the names the catalog gives, until a later build
replaces them and SQLMesh's janitor drops them.
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
    group = Path("/proc/self/cgroup").read_text().split("::", 1)[1].strip()
    peak = Path("/sys/fs/cgroup", group.lstrip("/"), "memory.peak")
    return {
        "script": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024),
        "cgroup": group.rsplit("/", 1)[-1],
        "cgroup_peak": round(int(peak.read_text()) / 2**20) if peak.exists() else None,
    }


def build(export: Path, state: Path, out: Path, project: Path = PROJECT) -> dict:
    """Run the four steps and return the catalog line, or raise SystemExit on a failed plan."""
    os.environ["PIPELINE_EXPORT"] = str(export)
    os.environ["PIPELINE_STATE"] = str(state)

    import sqlmesh.core.console
    from sqlmesh import Context
    from sqlmesh.core.console import TerminalConsole
    from sqlmesh.utils.errors import PlanError

    class Console(TerminalConsole):
        """The terminal console, keeping each model's evaluation time and the failures."""

        seconds: dict[str, float] = {}
        failed = ()

        def update_snapshot_evaluation_progress(
            self, snapshot, interval, batch_idx, duration_ms, *args, **kwargs
        ):
            if duration_ms is not None:
                name = snapshot.name.replace('"', "").removeprefix("pipeline.")
                self.seconds[name] = self.seconds.get(name, 0) + duration_ms / 1000
            super().update_snapshot_evaluation_progress(
                snapshot, interval, batch_idx, duration_ms, *args, **kwargs
            )

        def log_failed_models(self, errors):
            self.failed = errors
            super().log_failed_models(errors)

    console = Console()
    sqlmesh.core.console.set_console(console)
    started = time.time()
    steps = {}

    ctx = Context(paths=str(project))
    steps["load"] = time.time() - started
    variables = ctx.config.variables
    try:
        ctx.plan(auto_apply=True, no_prompts=True)
    except PlanError as error:
        for failure in console.failed:
            print(
                "failed", failure.node.snapshot_name, failure.__cause__, file=sys.stderr
            )
        raise SystemExit(f"build stopped: {error}") from error
    steps["plan"] = time.time() - started - steps["load"]

    mark = time.time()
    models = {}
    for snapshot in sorted(ctx.snapshots.values(), key=lambda s: s.name):
        name = snapshot.name.replace('"', "").removeprefix("pipeline.")
        (rows,) = ctx.engine_adapter.fetchone(f"SELECT count(*) FROM {name}")
        models[name] = {
            "table": snapshot.table_name(),
            "rows": rows,
            "seconds": round(console.seconds[name], 1)
            if name in console.seconds
            else None,
        }
    steps["count"] = time.time() - mark

    mark = time.time()
    out.mkdir(parents=True, exist_ok=True)
    part = out / f"rows-{os.getpid()}.parquet.part"
    ctx.engine_adapter.execute(
        f"""COPY (SELECT * FROM analysis.rows ORDER BY listing_id) TO '{part}'
        (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 122880)"""
    )
    digest = sha256(part)
    target = out / f"rows-{digest[:16]}.parquet"
    if target.exists() and sha256(target) == digest:
        part.unlink()
    else:
        part.rename(target)
    steps["write"] = time.time() - mark

    def listed(table):
        paths = variables[table]
        manifest = {}
        for line in (export / "manifest.ndjson").read_text().splitlines():
            if line.strip():
                entry = json.loads(line)
                manifest[str(export / entry["path"])] = entry["sha256"]
        return {
            "version": variables[f"{table}_version"],
            "files": {
                str(Path(path).relative_to(export)): manifest[path] for path in paths
            },
        }

    line = {
        "built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "code": code_version(project),
        "export": str(export),
        "ads": listed("ads"),
        "buildings": listed("buildings"),
        "models": models,
        "rows": {
            "path": target.name,
            "sha256": digest,
            "rows": models["analysis.rows"]["rows"],
        },
        "seconds": {step: round(value, 1) for step, value in steps.items()}
        | {"total": round(time.time() - started, 1)},
        "peak_mib": peak_mib(),
    }
    with open(out / "catalog.ndjson", "a") as f:
        f.write(json.dumps(line, sort_keys=True) + "\n")
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
    print(json.dumps({"rebuilt": rebuilt, "rows": line["rows"]}, indent=1))
    print("seconds", line["seconds"], "peak MiB", line["peak_mib"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
