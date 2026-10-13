"""Score an existing run's new buildings (rentfrontier.newbuilding) in a many-core Modal CPU container.

    newbuilding.py [--only FILE | --holdout] RUN [COMMIT]

A fit launched with ops/modal-fit gets this score as a post-fit step (fit.py); this is for
a run already under FRONTIER_OUTPUT_ROOT/runs. It uploads the run's directory and the fit
inputs that changed, runs rentfrontier.newbuilding at COMMIT (default: REPO's HEAD) with
one worker per core in app.newbuilding_cpu, and downloads the result to
FRONTIER_OUTPUT_ROOT/newbuilding/. The container's cost is charged to the Modal balance
(cap.py). Run it with the Modal venv, as ops/modal-fit runs fit.py.
"""

import argparse
import importlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cap  # noqa: E402
import fit  # noqa: E402

# 32 cores and 128 GiB for 10 minutes, rounded up; settled at the measured cost.
ESTIMATE = 0.45


def spec_for(name, sha, extra):
    return {
        "name": name,
        "commit": sha,
        "dataset": str(Path(fit.DATASET).resolve()),
        "inputs": [str(Path(fit.DATASET).resolve()), *fit.INPUTS],
        "newbuilding_args": extra,
    }


def upload_run(volume, name):
    run = fit.OUTPUT_ROOT / "runs" / name
    if not (run / "result.json").exists():
        sys.exit(f"no run at {run}")
    with volume.batch_upload(force=True) as batch:
        batch.put_directory(str(run), f"/out/{name}/run")


def download(volume, name):
    """/out/<name>/newbuilding/* -> FRONTIER_OUTPUT_ROOT/newbuilding/, the log beside it;
    then the run's copy on the Volume is deleted."""
    prefix = f"out/{name}/"
    for entry in volume.iterdir(f"/out/{name}", recursive=True):
        rel = entry.path.lstrip("/").removeprefix(prefix)
        if entry.type.name != "FILE" or not rel.startswith("newbuilding"):
            continue
        dst = fit.OUTPUT_ROOT / rel
        if rel == "newbuilding.log":
            dst = fit.STATE / "logs" / f"newbuilding-{name}.log"
        dst.parent.mkdir(parents=True, exist_ok=True)
        with open(dst, "wb") as f:
            volume.read_file_into_fileobj(entry.path, f)
    volume.remove_file(f"/out/{name}", recursive=True)


def main(argv):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("run")
    p.add_argument("commit", nargs="?", default="HEAD")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--only")
    g.add_argument("--holdout", action="store_true")
    args = p.parse_args(argv)
    sha = subprocess.run(
        ["git", "-C", str(fit.REPO), "rev-parse", f"{args.commit}^{{commit}}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    extra = ["--holdout"] if args.holdout else []
    if args.only:
        only = str(Path(args.only).resolve())
        extra = ["--only", only]
    spec = spec_for(args.run, sha, extra)
    if args.only:
        spec["inputs"].append(only)
    stage = fit.stage_code(sha)
    os.environ["MODAL_FIT_STAGE"] = str(stage)
    modal_app = importlib.import_module("app")
    fit.touch()
    launch, left = cap.reserve(f"newbuilding:{args.run}", "cpu", ESTIMATE)
    print(
        f"new-building score of {args.run}; Modal balance now ${left:.2f}", flush=True
    )
    import modal

    started, meta = time.monotonic(), None
    try:
        with modal.enable_output(), modal_app.app.run():
            fit.sync(modal_app.volume, spec, stage)
            upload_run(modal_app.volume, args.run)
            meta = modal_app.newbuilding_cpu.remote(spec)
        download(modal_app.volume, args.run)
        print(json.dumps(meta), flush=True)
    finally:
        fit.touch()
        cost = (meta or {}).get("usd_estimate")
        if cost is None:
            cost = (time.monotonic() - started) * modal_app.nb_usd_per_second()
        cap.settle(launch, cost)
    return 0 if meta["exit"] == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except cap.CapReached as e:
        sys.exit(str(e))
