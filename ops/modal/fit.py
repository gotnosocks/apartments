"""Run one frontier fit and its PSIS-LOO on a Modal GPU; the results land where a thelio fit's do.

Use it through ops/modal-fit, which runs this in a systemd unit with the Modal venv. The
arguments mirror drive.sh, so the run is named "<model>-<features>-<split>-<commit7>-<label>":

    fit.py [--gpu A100-40GB] [--dataset DIR] [--input PATH]... [--split rows] [--chain-batch N]
           COMMIT LABEL MODEL FEATURES CHAINS WARMUP DRAWS KEEP [rentfrontier.run options...]

With --large --publish-only --run NAME, a run already downloaded here whose run directory is
still on the Volume gets its summary bundle, calibration, rent map and estimate kit built in a
large container at COMMIT (app._publish; --allow-failing for a run that fails the gate), for a
run too large for thelio's memory. The other positional arguments are only parsed.

Steps: refuse if the run already exists here; spend the fit's estimated cost from the Modal balance (cap.py:
dollars accrue at 10 full fits a day; refused until the balance covers it, and refused outright
if the estimate is over the per-fit cap); upload only the inputs that changed since the last sync; ship a
shallow checkout of COMMIT; run the fit (capped at 1 h, or 30 min for an exploration fit)
and PSIS-LOO in the container, then its post-fit statistics (variance decomposition and the
explained share of each --explain SET; each capped, and none can fail the fit); score new
buildings (rentfrontier.newbuilding) in a separate many-core CPU container, which cannot fail
the fit either; download the run to FRONTIER_OUTPUT_ROOT/runs/<name>, the LOO to
FRONTIER_OUTPUT_ROOT/loo/ and the statistics to FRONTIER_OUTPUT_ROOT/{variance,explained,newbuilding}/,
then delete them from the Volume. For a full-tier fit on the row (or all) split, start
ops/modal/summarize in a systemd unit of its own: the summary bundle and its calibration, built
on thelio after the fit's unit has exited.

With --large (an A100-40GB, A100-80GB, H100 or H200), the container has 192 GiB of host memory and a 12 h
timeout, the fit is capped at 9 h, the post-fit statistics only by that timeout, and the
container builds the summary bundle and calibration itself; they download to
FRONTIER_OUTPUT_ROOT/{summaries,calibration}/. The per-fit hour cap leaves large fits out (Ben,
2026-10-16 06:37Z). The Volume itself is deleted after 24 h without a
launch (ops/modal/cleanup).
"""

import argparse
import datetime
import fcntl
import importlib
import json
import os
import shutil
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
    "/data1/apartments/frontier/datasets/chelsea-wv-gv-flatiron-gramercy-stuy-nomad-ev-mw-analysis-20261014-cd891c8",
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
# fit.py --publish-only, charged up front: the all-scraped run's PSIS-LOO took 27 min in its
# container, and its summary, kit and rent map each read every draw of every row as it does.
PUBLISH_SECONDS = 3 * 3600
LAST_USE = STATE / "last-use"  # ops/modal/cleanup deletes the Volume 24 h after this


def parse(argv):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    p.add_argument(
        "--gpu",
        default="A100-40GB",
        help="L4, A100-40GB (default), A100-80GB or H100; H200 with --large",
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
    p.add_argument(
        "--large",
        action="store_true",
        help="a large container (app.LARGE_FITS) that also builds the summary bundle",
    )
    p.add_argument(
        "--outside-budget",
        action="store_true",
        help="record the fit outside the Modal budget (cap.py; Ben, 2026-10-16 14:55Z)",
    )
    p.add_argument(
        "--no-summary",
        action="store_true",
        help="a large fit stops after its post-fit statistics, before the summary bundle",
    )
    p.add_argument(
        "--publish-only",
        action="store_true",
        help="with --large: build the summary bundle, calibration, rent map and kit of a run "
        "already downloaded whose run is still on the Volume, instead of fitting it",
    )
    p.add_argument(
        "--run",
        help="with --publish-only: the run's name, fit at another commit (COMMIT is the code "
        "the steps run at)",
    )
    p.add_argument(
        "--allow-failing",
        action="store_true",
        help="with --publish-only: build them for a run that fails the convergence gate",
    )
    p.add_argument(
        "--explain",
        action="append",
        default=[],
        help="a candidate feature set to screen on the fit's building levels afterwards "
        "(rentfrontier.explained; repeatable)",
    )
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
    name = args.run or (
        f"{args.model}-{args.features}-{args.split}-{short or sha[:7]}-{args.label}"
    )
    joined = " ".join(run_args)
    exploration = (
        "--tier exploration" in joined
        # A tuning subset is an exploration fit unless it asks for the full tier
        # (a held-out-lots fit: full draws on most buildings, never served).
        or ("tune-" in joined and "--tier full" not in joined)
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
        "explain": list(args.explain),
        "large": args.large,
        "summary": not args.no_summary,
        "publish_only": args.publish_only,
        "allow_failing": args.allow_failing,
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


POST_KINDS = (
    "variance",
    "explained",
    "newbuilding",
    "summaries",
    "calibration",
    "maps",
    "kits",
)


def download(volume, name, root, local=None):
    """/out/<name>/run -> runs/<name>, /out/<name>/loo/* -> loo/, the post-fit statistics'
    /out/<name>/{variance,explained,newbuilding,summaries,calibration}/* -> the same
    directories under root, log and
    modal.json into runs/<local>/modal/ (local: name unless given). A post-fit directory lands whole: it is written under
    root/.incoming/<name>/ (out of every reader's glob) and renamed into place once every
    file is down."""
    prefix = f"out/{name}/"
    local = local or name
    incoming = root / ".incoming" / name
    shutil.rmtree(incoming, ignore_errors=True)  # an interrupted download's leftovers
    staged = set()
    for entry in volume.iterdir(f"/out/{name}", recursive=True):
        if entry.type.name != "FILE":
            continue
        rel = entry.path.lstrip("/").removeprefix(prefix)
        kind, _, rest = rel.partition("/")
        if kind == "run":
            dst = root / "runs" / local / rest
        elif kind == "loo":
            dst = root / "loo" / rest
        elif kind in POST_KINDS and "/" in rest:
            d, _, inner = rest.partition("/")
            staged.add((kind, d))
            dst = incoming / kind / d / inner
        else:
            dst = root / "runs" / local / "modal" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        with open(dst, "wb") as f:
            volume.read_file_into_fileobj(entry.path, f)
    for kind, d in sorted(staged):
        final = root / kind / d
        if final.exists():
            print(f"kept {final}: it already exists", flush=True)
        else:
            final.parent.mkdir(parents=True, exist_ok=True)
            (incoming / kind / d).rename(final)
    shutil.rmtree(incoming, ignore_errors=True)
    try:
        incoming.parent.rmdir()  # only when no other download is in flight
    except OSError:
        pass
    volume.remove_file(f"/out/{name}", recursive=True)


def score_new_buildings(modal_app, spec):
    """The new-building score of a fit that finished, in a many-core CPU container
    (app.newbuilding_cpu) while its run is still on the Volume. Never fails the fit."""
    started = time.monotonic()
    try:
        return modal_app.newbuilding_cpu.remote(spec)
    except Exception as e:  # noqa: BLE001
        print(f"new-building score failed: {e!r}", flush=True)
        # The balance still pays for the container time it ran.
        seconds = time.monotonic() - started
        return {
            "exit": repr(e),
            "wall_seconds": round(seconds, 1),
            "usd_estimate": round(seconds * modal_app.nb_usd_per_second(), 2),
        }


def wants_summary(spec, split):
    """Whether a downloaded fit gets a summary bundle: only full-tier fits are served, and
    rentfrontier.summary refuses the unit and latest splits."""
    return spec["tier"] == "full" and split in ("rows", "all") and not spec.get("large")


def summarize(spec):
    """Start ops/modal/summarize for the fit in a systemd unit of its own and return its name.
    The unit outlives this one, so neither the queue runners (which wait on modal-fit-*
    units) nor the Modal balance wait for the bundle. Never fails the fit."""
    unit = f"modal-summary-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
    log = STATE / "logs" / f"{unit}.log"
    env = {
        "FRONTIER_OUTPUT_ROOT": str(OUTPUT_ROOT),
        "FRONTIER_DATASET": spec["dataset"],
        "MODAL_FIT_REPO": str(REPO),
    }
    cmd = [
        "systemd-run", "--user", "--quiet", "--collect", f"--unit={unit}",
        "-p", f"StandardOutput=append:{log}", "-p", f"StandardError=append:{log}",
        *(f"--setenv={k}={v}" for k, v in env.items()),
        str(HERE / "summarize"), spec["name"],
    ]  # fmt: skip
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(cmd, check=True)
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"could not start the summary: {e!r}", flush=True)
        return None
    print(f"summary and calibration on thelio: {unit}; log {log}", flush=True)
    return unit


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
    if args.publish_only:
        return publish(args, spec, sha)
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
    fits = modal_app.LARGE_FITS if args.large else modal_app.FITS
    if args.gpu not in fits:
        sys.exit(f"--gpu must be one of {', '.join(fits)}")
    touch()
    # At the model's own fit-stage rate on its last Modal fit, if that was slower.
    rate = cap.measured_rate(args.model, args.features, OUTPUT_ROOT / "runs")
    usd = cap.estimate(args.chains, args.warmup, args.draws, args.gpu, rate, args.large)
    secs = cap.seconds(args.chains, args.warmup, args.draws, rate, args.large)
    # Raises CapReached if the estimate is over the per-fit cap or the balance is short.
    launch, left = cap.reserve(
        spec["name"],
        args.gpu,
        usd,
        secs=secs,
        large=args.large,
        outside=args.outside_budget,
    )
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
            meta = fits[args.gpu].remote(spec)
            # The new-building container's 128 GiB and hour don't stretch to a large run.
            if meta.get("fit_exit", meta["exit"]) == 0 and not args.large:
                meta["newbuilding"] = score_new_buildings(modal_app, spec)
        meta["usd_estimate"] = round(
            meta["wall_seconds"] * modal_app.usd_per_second(args.gpu, args.large)
            + meta.get("newbuilding", {}).get("usd_estimate", 0),
            2,
        )
        root = finish(modal_app.volume, spec["name"], meta)
        if root == OUTPUT_ROOT and wants_summary(spec, args.split):
            summarize(spec)
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
            cost = (time.monotonic() - started) * modal_app.usd_per_second(
                args.gpu, args.large
            )
        try:
            cap.settle(launch, cost)
        except Exception as e:  # noqa: BLE001 (keep the fit's own error; the estimate stays charged)
            print(f"could not settle {launch} at ${cost:.2f}: {e}", flush=True)
    return meta["exit"]


def publish(args, spec, sha):
    """fit.py --publish-only: the summary bundle, calibration, rent map and kit of a run already
    under OUTPUT_ROOT/runs whose run is still on the Volume, built in a large container
    (app._publish) and downloaded to OUTPUT_ROOT/{summaries,calibration,maps,kits}/. The record
    lands in runs/<name>/modal/publish.json."""
    name = spec["name"]
    if not args.large:
        sys.exit("--publish-only needs --large")
    if not (OUTPUT_ROOT / "runs" / name / "result.json").exists():
        sys.exit(f"{name} is not under {OUTPUT_ROOT / 'runs'}")
    STATE.mkdir(parents=True, exist_ok=True)
    lock = open(STATE / "launch.lock", "a")
    fcntl.flock(lock, fcntl.LOCK_SH)
    stage = stage_code(sha)
    os.environ["MODAL_FIT_STAGE"] = str(stage)
    modal_app = importlib.import_module("app")
    if args.gpu not in modal_app.LARGE_FITS:
        sys.exit(f"--gpu must be one of {', '.join(modal_app.LARGE_FITS)}")
    touch()
    secs = PUBLISH_SECONDS
    usd = round(secs * modal_app.usd_per_second(args.gpu, True), 2)
    launch, left = cap.reserve(
        f"{name}-publish",
        args.gpu,
        usd,
        secs=secs,
        large=True,
        outside=args.outside_budget,
    )
    print(
        f"publish {name} on {args.gpu}; estimated ${usd:.2f}, Modal balance now ${left:.2f}",
        flush=True,
    )
    import modal

    started, meta = time.monotonic(), None
    try:
        with modal.enable_output(), modal_app.app.run():
            sync(modal_app.volume, spec, stage)
            meta = modal_app.LARGE_FITS[args.gpu].remote(spec)
        meta["usd_estimate"] = round(
            meta["wall_seconds"] * modal_app.usd_per_second(args.gpu, True), 2
        )
        download(modal_app.volume, f"{name}-publish", OUTPUT_ROOT, local=name)
        (OUTPUT_ROOT / "runs" / name / "modal" / "publish.json").write_text(
            json.dumps(meta, indent=2)
        )
        print(json.dumps(meta), flush=True)
    finally:
        touch()
        cost = (meta or {}).get("usd_estimate")
        if cost is None:
            cost = (time.monotonic() - started) * modal_app.usd_per_second(
                args.gpu, True
            )
        try:
            cap.settle(launch, cost)
        except Exception as e:  # noqa: BLE001
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
