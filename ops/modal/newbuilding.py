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
import shutil
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
    """The container's spec, with the dataset the run was fit on (newbuilding checks its hash)."""
    result = json.loads((fit.OUTPUT_ROOT / "runs" / name / "result.json").read_text())
    dataset = str(Path(result["dataset"]).resolve())
    return {
        "name": name,
        "commit": sha,
        "dataset": dataset,
        "inputs": [dataset, *fit.INPUTS],
        "newbuilding_args": extra,
    }


def upload_run(volume, name):
    run = fit.OUTPUT_ROOT / "runs" / name
    if not (run / "result.json").exists():
        sys.exit(f"no run at {run}")
    with volume.batch_upload(force=True) as batch:
        batch.put_directory(str(run), f"/out/{name}/run")


def download(volume, name):
    """Copy /out/<name>/newbuilding/<dir> to FRONTIER_OUTPUT_ROOT/newbuilding/<dir> and the
    log to the Modal logs, then delete /out/<name> from the Volume. Each result directory
    is written under .incoming and renamed into place whole; an existing one is kept."""
    prefix = f"out/{name}/"
    incoming = fit.OUTPUT_ROOT / ".incoming" / f"newbuilding-{name}"
    shutil.rmtree(incoming, ignore_errors=True)
    staged = set()
    for entry in volume.iterdir(f"/out/{name}", recursive=True):
        rel = entry.path.lstrip("/").removeprefix(prefix)
        if entry.type.name != "FILE":
            continue
        if rel == "newbuilding.log":
            dst = fit.STATE / "logs" / f"newbuilding-{name}.log"
        elif rel.startswith("newbuilding/") and rel.count("/") >= 2:
            d = rel.split("/")[1]
            staged.add(d)
            dst = incoming / rel.removeprefix("newbuilding/")
        else:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        with open(dst, "wb") as f:
            volume.read_file_into_fileobj(entry.path, f)
    for d in sorted(staged):
        final = fit.OUTPUT_ROOT / "newbuilding" / d
        if final.exists():
            print(f"kept {final}: it already exists", flush=True)
        else:
            final.parent.mkdir(parents=True, exist_ok=True)
            (incoming / d).rename(final)
    shutil.rmtree(incoming, ignore_errors=True)
    try:
        incoming.parent.rmdir()  # only when no other download is in flight
    except OSError:
        pass
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
            # A failed earlier attempt can leave its outputs on the Volume.
            try:
                modal_app.volume.remove_file(f"/out/{args.run}", recursive=True)
            except Exception:  # noqa: BLE001 (nothing there)
                pass
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
        try:
            cap.settle(launch, cost)
        except Exception as e:  # noqa: BLE001 (keep the run's own error; the estimate stays charged)
            print(f"could not settle {launch} at ${cost:.2f}: {e}", flush=True)
    return 0 if meta["exit"] == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except cap.CapReached as e:
        sys.exit(str(e))
