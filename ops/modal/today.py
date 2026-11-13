"""Write a Price now table for a served run in a Modal CPU container (app.today_cpu).

    today.py [--day YYYY-MM-DD] [--registry PATH] --out DIR --outside-budget COMMIT RUN

`rentfrontier.drift_today publish` rebuilds the run's design, which peaks at about 14 GB on
the served market run and is more than thelio has free, so it runs at COMMIT in a container
with 16 cores and 64 GiB. The run directory, its dataset, the dataset's ads table and the
registry go up as inputs (only what changed since the last sync), the table is written in the
container, and today.parquet and meta.json come down into DIR under temporary names and are
renamed into place back to back once both are down, so a failed download leaves the old pair. The log and the container's
record (today.json) land in MODAL_FIT_STATE/today/<RUN>-<day>/.

Modal spend needs a budget Ben approved, so the launch requires --outside-budget and is
recorded in cap.py's ledger as an outside row: charged its whole timeout (about $1.27) and
settled at what it ran. Run it with the Modal venv, as ops/modal-fit runs fit.py.
"""

from __future__ import annotations

import argparse
import datetime
import fcntl
import importlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cap  # noqa: E402
import fit  # noqa: E402

REGISTRY = (
    "/data1/apartments/external/registry/20261110-f1fc080-extend/registry.parquet"
)


def parse(argv):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("commit")
    p.add_argument("run", help="a served run under FRONTIER_OUTPUT_ROOT/runs")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--day", help="the day to price (default: today in New York)")
    p.add_argument("--registry", default=REGISTRY)
    p.add_argument(
        "--outside-budget",
        action="store_true",
        help="record the launch outside the Modal budget (cap.py), for a budget Ben approved",
    )
    return p.parse_args(argv)


def inputs(run_dir):
    """What the container reads besides fit.INPUTS: the run, the ads table its dataset's
    market manifest names (drift_deals checks that table's sha256) and every snapshot the
    dataset's inputs.json points the feature modules at (rentfrontier.market), such as the
    pipeline's rows parquet."""
    result = json.loads((run_dir / "result.json").read_text())
    dataset = Path(result["dataset"])
    if not dataset.is_dir():
        dataset = run_dir.parent.parent / "datasets" / dataset.name
    manifest = json.loads((dataset / "manifest.json").read_text())
    ads = (manifest.get("market") or {}).get("ads")
    if not ads:
        sys.exit(f"{dataset} is not a market dataset")
    extra = [str(run_dir), str(Path(ads).resolve())]
    pinned = dataset / "inputs.json"
    if pinned.exists():
        for value in json.loads(pinned.read_text()).values():
            path = str(Path(value).resolve())
            if not any(
                path == p or path.startswith(p + "/") for p in fit.INPUTS + extra
            ):
                extra.append(path)
    return str(dataset), extra


def download(volume, name, out, logs):
    """/out/<name>/today.parquet and meta.json -> out, only when both are there: both are
    downloaded under temporary names before either is renamed into place. The log and
    today.json -> logs."""
    prefix = f"out/{name}/"
    have = {
        e.path.lstrip("/").removeprefix(prefix): e.path
        for e in volume.iterdir(f"/out/{name}", recursive=False)
        if e.type.name == "FILE"
    }
    logs.mkdir(parents=True, exist_ok=True)
    for rel in ("today.log", "today.json"):
        if rel in have:
            with open(logs / rel, "wb") as f:
                volume.read_file_into_fileobj(have[rel], f)
    if {"today.parquet", "meta.json"} <= have.keys():
        out.mkdir(parents=True, exist_ok=True)
        tmp = {
            rel: out / f"{rel}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
            for rel in ("today.parquet", "meta.json")
        }
        try:
            for rel, path in tmp.items():
                with open(path, "wb") as f:
                    volume.read_file_into_fileobj(have[rel], f)
            # Both are down: the renames run back to back, the table first.
            for rel, path in tmp.items():
                os.replace(path, out / rel)
        finally:
            for path in tmp.values():
                path.unlink(missing_ok=True)
    volume.remove_file(f"/out/{name}", recursive=True)


def main(argv):
    args = parse(argv)
    if not args.outside_budget:
        sys.exit(
            "Modal spend needs a budget Ben approved: launch with --outside-budget once he has"
        )
    run_dir = fit.OUTPUT_ROOT / "runs" / args.run
    if not (run_dir / "result.json").exists():
        sys.exit(f"{args.run} is not under {fit.OUTPUT_ROOT / 'runs'}")
    sha = subprocess.run(
        ["git", "-C", str(fit.REPO), "rev-parse", f"{args.commit}^{{commit}}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    day = args.day or str(datetime.datetime.now(ZoneInfo("America/New_York")).date())
    dataset, extra = inputs(run_dir)
    spec = {
        "name": args.run,
        "commit": sha,
        "dataset": dataset,
        "inputs": [dataset, *fit.INPUTS, *extra, str(Path(args.registry).resolve())],
        "day": day,
        "registry": str(Path(args.registry).resolve()),
    }
    fit.STATE.mkdir(parents=True, exist_ok=True)
    lock = open(fit.STATE / "launch.lock", "a")
    fcntl.flock(lock, fcntl.LOCK_SH)
    stage = fit.stage_code(sha)
    os.environ["MODAL_FIT_STAGE"] = str(stage)
    modal_app = importlib.import_module("app")
    fit.touch()
    # Charged for the container's whole timeout; settled at the time it ran.
    secs = modal_app.TODAY_TIMEOUT
    usd = round(secs * modal_app.today_usd_per_second(), 2)
    launch, _ = cap.reserve(f"{args.run}-today", "cpu", usd, secs=secs, outside=True)
    print(
        f"Price now table of {args.run} for {day} at {sha[:7]}; up to ${usd:.2f}, "
        "outside the budget",
        flush=True,
    )
    import modal

    name = f"{args.run}-today"
    logs = fit.STATE / "today" / f"{args.run}-{day}"
    started, meta = time.monotonic(), None
    try:
        with modal.enable_output(), modal_app.app.run():
            fit.sync(modal_app.volume, spec, stage)
            meta = modal_app.today_cpu.remote(spec)
        print(json.dumps(meta), flush=True)
    finally:
        try:
            download(modal_app.volume, name, args.out, logs)
        except Exception as e:  # noqa: BLE001
            print(f"no outputs to download: {e!r}", flush=True)
        fit.touch()
        cost = (meta or {}).get("usd_estimate")
        if cost is None:
            cost = (time.monotonic() - started) * modal_app.today_usd_per_second()
        try:
            cap.settle(launch, cost)
        except Exception as e:  # noqa: BLE001
            print(f"could not settle {launch} at ${cost:.2f}: {e}", flush=True)
    print(f"log in {logs}", flush=True)
    return meta["exit"]


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except cap.CapReached as e:
        sys.exit(str(e))
