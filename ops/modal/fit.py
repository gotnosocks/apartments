"""Run one frontier fit and its PSIS-LOO on a Modal GPU; the results land where a thelio fit's do.

Use it through ops/modal-fit, which runs this in a systemd unit with the Modal venv. The
arguments mirror drive.sh, so the run is named "<model>-<features>-<split>-<commit7>-<label>":

    fit.py [--gpu A100-40GB] [--dataset DIR] [--input PATH]... [--split rows] [--chain-batch N]
           COMMIT LABEL MODEL FEATURES CHAINS WARMUP DRAWS KEEP [rentfrontier.run options...]

Steps: refuse if the run already exists here; spend the fit's estimated cost from the Modal balance (cap.py:
dollars accrue at 10 full fits a day; refused until the balance covers it); upload only the inputs that changed since the last sync; ship a
shallow checkout of COMMIT; run the fit (capped at 2 h, or 30 min for an exploration fit)
and PSIS-LOO in the container; download the run to FRONTIER_OUTPUT_ROOT/runs/<name> and the
LOO to FRONTIER_OUTPUT_ROOT/loo/, then delete them from the Volume. The Volume itself is
deleted after 24 h without a launch (ops/modal/cleanup).
"""

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

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cap  # noqa: E402

STATE = Path(os.environ.get("MODAL_FIT_STATE", "/data1/apartments/modal"))
OUTPUT_ROOT = Path(os.environ.get("FRONTIER_OUTPUT_ROOT", "/data1/apartments/frontier"))
REPO = Path(os.environ.get("MODAL_FIT_REPO", "/home/ben/code/apartments"))
DATASET = os.environ.get(
    "FRONTIER_DATASET",
    "/data1/apartments/frontier/datasets/chelsea-wv-gv-flatiron-gramercy-analysis-20261008-0a23057",
)
# Everything else the feature code reads, by absolute path (87 + 49 + 45 MB and a few files).
# A fit that needs another file fails with FileNotFoundError naming it; add it with --input.
INPUTS = [
    "/data1/apartments/external",
    "/data1/apartments/frontier/cache",
    "/data1/apartments/frontier/descriptions",
    "/home/ben/code/apartments/data/model/chelsea-refreshed-bayesian-descriptions-20260918/evidence.jsonl",
    "/home/ben/code/apartments/data/model/building-covariates-20260923/buildings.csv",
    "/home/ben/code/apartments/data/model/feature-screen-20260923/nuts-hwalk/heldout.npz",
    "/home/ben/code/apartments/data/model/feature-screen-20260923/nuts-hwalk-units/heldout.npz",
]
MANIFEST = (
    STATE / "manifest.json"
)  # what the Volume holds: {"volume_id": ..., "files": {path: [size, mtime_ns]}, "code": [sha]}
LAST_USE = STATE / "last-use"  # ops/modal/cleanup deletes the Volume 24 h after this


def parse(argv):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    p.add_argument(
        "--gpu", default="A100-40GB", help="L4, A100-40GB (default), A100-80GB or H100"
    )
    p.add_argument("--dataset", default=DATASET)
    p.add_argument(
        "--input",
        action="append",
        default=[],
        help="another file or directory the fit reads",
    )
    p.add_argument("--split", default="rows")
    p.add_argument("--chain-batch", type=int)
    for name in (
        "commit",
        "label",
        "model",
        "features",
        "chains",
        "warmup",
        "draws",
        "keep",
    ):
        p.add_argument(name)
    args, run_args = p.parse_known_args(argv)
    return args, run_args


def plan(args, run_args, sha, short=None):
    """The container's spec: run name, tier and the rentfrontier.run arguments, as drive.sh builds them."""
    name = f"{args.model}-{args.features}-{args.split}-{short or sha[:7]}-{args.label}"
    joined = " ".join(run_args)
    exploration = (
        "--tier exploration" in joined
        or "tune-" in joined
        or args.label.startswith("x-")
    )
    run = [
        "--split", args.split, "--model", args.model, "--features", args.features,
        "--chains", args.chains, "--chain-batch", str(args.chain_batch or args.chains),
        "--warmup", args.warmup, "--draws", args.draws, "--keep-every", args.keep,
        "--name", name, *run_args,
    ]  # fmt: skip
    inputs = [
        str(Path(args.dataset).resolve()),
        *INPUTS,
        *(str(Path(i).resolve()) for i in args.input),
    ]
    return {
        "name": name,
        "commit": sha,
        "tier": "exploration" if exploration else "full",
        "dataset": inputs[0],
        "inputs": inputs,
        "run_args": run,
    }


def stage_code(sha):
    """A shallow git checkout of sha (rentfrontier.run and loo read git status and HEAD).

    It is on a branch so .git/refs holds a file: Volume uploads skip empty directories, and
    git refuses a .git without refs/.
    """
    stage = STATE / "code" / sha
    if not (stage / ".git").exists():
        stage.mkdir(parents=True, exist_ok=True)
        for cmd in (
            ["init", "-q"],
            ["fetch", "-q", "--depth", "1", f"file://{REPO}", sha],
            ["checkout", "-q", "-B", "modal-fit", "FETCH_HEAD"],
        ):
            subprocess.run(["git", "-C", str(stage), *cmd], check=True)
    return stage


def files_under(paths):
    for path in map(Path, paths):
        if not path.exists():
            raise FileNotFoundError(path)
        for f in (
            [path]
            if path.is_file()
            else sorted(p for p in path.rglob("*") if p.is_file())
        ):
            st = f.stat()
            yield str(f), [st.st_size, st.st_mtime_ns]


def changed(manifest, current):
    """Files whose size or mtime differ from what the Volume holds."""
    return [path for path, sig in current.items() if manifest.get(path) != sig]


def load_manifest(volume):
    """The local manifest, or an empty one if the Volume was deleted or recreated since."""
    try:
        marker = b"".join(volume.read_file("/inputs/.volume-id")).decode()
    except Exception:  # noqa: BLE001 (a new or recreated Volume has no marker yet)
        marker = None
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    if marker is None or manifest.get("volume_id") != marker:
        manifest = {"volume_id": marker or uuid.uuid4().hex, "files": {}, "code": []}
    return manifest


def sync(volume, spec, stage):
    manifest = load_manifest(volume)
    current = dict(files_under(spec["inputs"]))
    todo = changed(manifest["files"], current)
    code = spec["commit"] not in manifest["code"]
    if todo or code or not manifest["files"]:
        with volume.batch_upload(force=True) as batch:
            batch.put_file(_marker(manifest["volume_id"]), "/inputs/.volume-id")
            for path in todo:
                batch.put_file(path, "/inputs/" + path.lstrip("/"))
            if code:
                batch.put_directory(str(stage), f"/code/{spec['commit']}")
    manifest["files"].update(current)
    if code:
        manifest["code"].append(spec["commit"])
    MANIFEST.write_text(json.dumps(manifest))
    print(
        f"synced {len(todo)} changed input files{' and the code' if code else ''}",
        flush=True,
    )


def _marker(volume_id):
    path = STATE / ".volume-id"
    path.write_text(volume_id)
    return str(path)


def download(volume, name, root):
    """/out/<name>/run -> runs/<name>, /out/<name>/loo/* -> loo/, log and modal.json into runs/<name>/modal/."""
    prefix = f"out/{name}/"
    for entry in volume.iterdir(f"/out/{name}", recursive=True):
        if entry.type.name != "FILE":
            continue
        rel = entry.path.lstrip("/").removeprefix(prefix)
        if rel.startswith("run/"):
            dst = root / "runs" / name / rel.removeprefix("run/")
        elif rel.startswith("loo/"):
            dst = root / "loo" / rel.removeprefix("loo/")
        else:
            dst = root / "runs" / name / "modal" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        with open(dst, "wb") as f:
            volume.read_file_into_fileobj(entry.path, f)
    volume.remove_file(f"/out/{name}", recursive=True)


def touch():
    LAST_USE.parent.mkdir(parents=True, exist_ok=True)
    LAST_USE.write_text(datetime.datetime.now(datetime.UTC).isoformat())


def main(argv):
    args, run_args = parse(argv)
    short = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "--short", f"{args.commit}^{{commit}}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    sha = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", f"{args.commit}^{{commit}}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    spec = plan(args, run_args, sha, short)
    if (OUTPUT_ROOT / "runs" / spec["name"]).exists():
        sys.exit(f"{spec['name']} already exists under {OUTPUT_ROOT / 'runs'}")
    STATE.mkdir(parents=True, exist_ok=True)
    # Held until exit, from before the code is staged: ops/modal/cleanup waits for it.
    lock = open(STATE / "launch.lock", "a")
    fcntl.flock(lock, fcntl.LOCK_SH)
    stage = stage_code(sha)
    # The image installs this commit's uv.lock.
    os.environ["MODAL_FIT_STAGE"] = str(stage)
    modal_app = importlib.import_module("app")
    if args.gpu not in modal_app.FITS:
        sys.exit(f"--gpu must be one of {', '.join(modal_app.FITS)}")
    touch()
    usd = cap.estimate(args.chains, args.warmup, args.draws, args.gpu)
    # Raises CapReached if the balance is short.
    launch, left = cap.reserve(spec["name"], args.gpu, usd)
    print(
        f"{spec['name']} on {args.gpu} ({spec['tier']}); estimated ${usd:.2f}, "
        f"Modal balance now ${left:.2f}",
        flush=True,
    )
    import modal

    started, meta = time.monotonic(), None
    try:
        with modal.enable_output(), modal_app.app.run():
            sync(modal_app.volume, spec, stage)
            meta = modal_app.FITS[args.gpu].remote(spec)
        meta["usd_estimate"] = round(
            meta["wall_seconds"] * modal_app.usd_per_second(args.gpu), 2
        )
        finish(modal_app.volume, spec["name"], meta)
    except Exception:
        # A container timeout or Modal error: keep whatever reached the Volume, log included.
        try:
            download(modal_app.volume, spec["name"], STATE / "failed")
        except Exception as e:  # noqa: BLE001
            print(f"no outputs to download: {e}", flush=True)
        raise
    finally:
        touch()
        # The balance pays what the fit cost: its container time, or the time it ran if it failed.
        cost = (meta or {}).get("usd_estimate")
        if cost is None:
            cost = (time.monotonic() - started) * modal_app.usd_per_second(args.gpu)
        try:
            cap.settle(launch, cost)
        except Exception as e:  # noqa: BLE001 (keep the fit's own error; the estimate stays charged)
            print(f"could not settle {launch} at ${cost:.2f}: {e}", flush=True)
    return meta["exit"]


def finish(volume, name, meta):
    """Download the run. A failed fit goes aside, off the research board, so a retry isn't
    blocked; a good fit whose PSIS-LOO failed is kept, as drive.sh keeps it."""
    root = OUTPUT_ROOT if meta.get("fit_exit", meta["exit"]) == 0 else STATE / "failed"
    download(volume, name, root)
    (root / "runs" / name / "modal").mkdir(parents=True, exist_ok=True)
    (root / "runs" / name / "modal" / "modal.json").write_text(
        json.dumps(meta, indent=2)
    )
    print(json.dumps(meta), flush=True)
    print(f"results in {root / 'runs' / name}", flush=True)
    return root


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except cap.CapReached as e:
        sys.exit(str(e))
