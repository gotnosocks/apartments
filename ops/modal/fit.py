"""Run one frontier fit and its PSIS-LOO on a Modal GPU; the results land where a thelio fit's do.

Use it through ops/modal-fit, which runs this in a systemd unit with the Modal venv. The
arguments mirror drive.sh, so the run is named "<model>-<features>-<split>-<commit7>-<label>":

    fit.py [--gpu A100-40GB] [--dataset DIR] [--input PATH]... [--split rows] [--chain-batch N]
           COMMIT LABEL MODEL FEATURES CHAINS WARMUP DRAWS KEEP [rentfrontier.run options...]

With --large --publish-only --run NAME, a run already downloaded here whose run directory is
still on the Volume gets its summary bundle, calibration, rent map and estimate kit built in a
large container at COMMIT (app._publish; --allow-failing for a run that fails the gate), for a
run too large for thelio's memory. The other positional arguments are only parsed.

With --design-only --run NAME, a run already downloaded here gets its design prepared
(python -m rentfrontier.design) at COMMIT in a Modal CPU container (app.design_cpu), and the
pickle downloads to FRONTIER_OUTPUT_ROOT/designs, where a summary at the same commit run with
FRONTIER_DESIGN_CACHE=read loads it. It is for a run whose prep runs out of thelio's memory.

A baseline fit (b0, b0.1, b0.2, ...) runs fit-only unless --score asks for its scoring (Ben,
2026-10-19 14:30Z): nothing runs after the fit, with no rentfrontier.loo step, no scoring
container and no loo/ record, and the run can be scored later with rentfrontier.loo. With
--score, --no-loo and --no-heldout leave out PSIS-LOO or the held-out scoring. With --score
--cpu-score, the GPU container stops after the fit and saves its draws to the Volume, and a
second container with 16 CPU cores and no GPU (app.score_cpu) then runs rentfrontier.loo on
them, so the A100 is not billed for that work. cap.py prices the two containers apart and
applies the per-fit cap to the sum of their seconds.

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
# The container stops starting steps an hour past this.
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
        help="a large container (app.LARGE_FITS) that also builds the summary bundle (none for "
        "a baseline)",
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
        "--design-only",
        action="store_true",
        help="prepare the design of a run already downloaded, in a CPU container, and "
        "download it to OUTPUT_ROOT/designs, instead of fitting it",
    )
    p.add_argument(
        "--run",
        help="with --publish-only or --design-only: the run's name, fit at another commit (COMMIT is the code "
        "the steps run at)",
    )
    p.add_argument(
        "--allow-failing",
        action="store_true",
        help="with --publish-only: build them for a run that fails the convergence gate",
    )
    p.add_argument(
        "--range-sample",
        action="store_true",
        help="the summary also writes range-sample.npz (rentfrontier.summary --range-sample), "
        "on thelio, in a large container or with --publish-only; a COMMIT whose summary "
        "lacks the flag fails its summary",
    )
    p.add_argument(
        "--range-atoms",
        action="store_true",
        help="the summary writes range atoms and noise.json in place of the predictive "
        "intervals (rentfrontier.summary --range-atoms), in the same places as --range-sample",
    )
    p.add_argument(
        "--cpu-score",
        action="store_true",
        help="B0 family only: the GPU container stops after the fit and leaves its draws on "
        "the Volume, and a CPU container (app.score_cpu) scores them (PSIS-LOO, held-out "
        "predictive quantiles and coverage), priced at its own rate",
    )
    p.add_argument(
        "--score",
        action="store_true",
        help="B0 family only: score the fit after it (PSIS-LOO, held-out predictive quantiles "
        "and coverage); without it a baseline fit runs fit-only",
    )
    p.add_argument(
        "--no-loo",
        action="store_true",
        help="B0 family only, with --score: score without PSIS-LOO (the record and its pointwise file lack it)",
    )
    p.add_argument(
        "--no-heldout",
        action="store_true",
        help="B0 family only, with --score: score without the held-out rows' quantiles and coverage",
    )
    p.add_argument(
        "--save-design",
        action="store_true",
        help="copy the fit's prepared design (rentfrontier.design) to the Volume and down to "
        "OUTPUT_ROOT/designs, where the summary on thelio loads it if its checkout matches",
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
    loo, heldout = cap.scoring_steps(
        args.model, args.large, args.score, args.no_loo, args.no_heldout
    )
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
        # rentfrontier.summary reads no baseline run.
        "summary": not args.no_summary and args.model not in BASELINE_MODELS,
        "publish_only": args.publish_only,
        "allow_failing": args.allow_failing,
        "range_sample": args.range_sample,
        "range_atoms": args.range_atoms,
        "save_design": args.save_design,
        "cpu_score": args.cpu_score,
        "loo": loo,
        "heldout": heldout,
        # With both steps off, nothing runs after the fit.
        "score": loo or heldout,
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


def download(volume, name, root, local=None, design=True):
    """/out/<name>/run -> runs/<name>, /out/<name>/loo/* -> loo/, the post-fit statistics'
    /out/<name>/{variance,explained,newbuilding,summaries,calibration}/* -> the same
    directories under root, log and
    modal.json into runs/<local>/modal/ (local: name unless given). A post-fit directory lands whole: it is written under
    root/.incoming/<name>/ (out of every reader's glob) and renamed into place once every
    file is down. A saved design (/out/<name>/design/*) goes to root/designs/ through a
    temporary name, unless design is False. It stays out of root/cache/, which every fit
    uploads as an input (INPUTS)."""
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
        if kind == "design":
            if design and "/" not in rest:
                dst = root / "designs" / rest
                tmp = dst.with_name(f"{rest}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
                tmp.parent.mkdir(parents=True, exist_ok=True)
                with open(tmp, "wb") as f:
                    volume.read_file_into_fileobj(entry.path, f)
                os.replace(tmp, dst)
            continue
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


def score_on_cpu(modal_app, spec):
    """The scoring (PSIS-LOO and the held-out rows' statistics) of a baseline fit that finished,
    in a CPU container (app.score_cpu) while its run is on the Volume. A failure comes back as
    the stage's record and leaves the fit's run in place, as a GPU container's failed PSIS-LOO
    does."""
    started = time.monotonic()
    try:
        return modal_app.score_cpu.remote(spec)
    except Exception as e:  # noqa: BLE001
        print(f"scoring failed: {e!r}", flush=True)
        # The balance still pays for the container time it ran.
        seconds = time.monotonic() - started
        return {
            "exit": repr(e),
            "wall_seconds": round(seconds, 1),
            "usd_estimate": round(seconds * modal_app.score_usd_per_second(), 2),
        }


BASELINE_MODELS = cap.BASELINES


def wants_summary(spec, split):
    """Whether a downloaded fit gets a summary bundle: only full-tier fits are served, and
    rentfrontier.summary refuses the unit and latest splits, and reads no baseline run."""
    run_args = spec.get("run_args", [])
    b0 = any(
        pair in zip(run_args, run_args[1:])
        for pair in (("--model", name) for name in BASELINE_MODELS)
    )
    return (
        spec["tier"] == "full"
        and split in ("rows", "all")
        and not spec.get("large")
        and not b0
    )


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
        **({"FRONTIER_RANGE_SAMPLE": "1"} if spec.get("range_sample") else {}),
        **({"FRONTIER_RANGE_ATOMS": "1"} if spec.get("range_atoms") else {}),
        # Loads the fit's design that the download put in OUTPUT_ROOT/designs, and writes none.
        **({"FRONTIER_DESIGN_CACHE": "read"} if spec.get("save_design") else {}),
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
    if (args.score or args.cpu_score or args.no_loo or args.no_heldout) and (
        args.model not in BASELINE_MODELS
    ):
        sys.exit(
            "--score, --cpu-score, --no-loo and --no-heldout apply to a baseline fit (b0 to "
            "b0.4, the building-zones family)"
        )
    if args.publish_only:
        return publish(args, spec, sha)
    if args.design_only:
        return design_only(spec, sha)
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
    stages = cap.fit_stages(
        args.model,
        args.features,
        args.chains,
        args.warmup,
        args.draws,
        args.gpu,
        args.large,
        OUTPUT_ROOT / "runs",
        keep=args.keep,
        max_leapfrog_steps=cap.max_leapfrog_steps(run_args),
        cpu_score=args.cpu_score,
        scoring=spec["score"],
    )
    usd = round(sum(u for u, _ in stages.values()), 2)
    secs = sum(t for _, t in stages.values())
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
    if len(stages) > 1:
        print(
            "  "
            + "; ".join(
                f"{name} {t / 60:.0f} min ${u:.2f}" for name, (u, t) in stages.items()
            ),
            flush=True,
        )
    import modal

    started, meta = time.monotonic(), None
    try:
        with modal.enable_output(), modal_app.app.run():
            sync(modal_app.volume, spec, stage)
            meta = fits[args.gpu].remote(spec)
            meta["steps"] = {"loo": spec["loo"], "heldout": spec["heldout"]}
            if (
                args.cpu_score
                and spec["score"]
                and meta.get("fit_exit", meta["exit"]) == 0
            ):
                meta["score"] = score_on_cpu(modal_app, spec)
                if meta["score"]["exit"] != 0:
                    # The fit and its draws stay; finish() keeps a good fit whose scoring failed.
                    meta["exit"] = (
                        meta["score"]["exit"]
                        if isinstance(meta["score"]["exit"], int)
                        else 1
                    )
            # The new-building container's 128 GiB and hour don't stretch to a large run.
            # rentfrontier.newbuilding reads the frontier model's posterior, which a B0
            # baseline run has none of.
            if (
                meta.get("fit_exit", meta["exit"]) == 0
                and not args.large
                and args.model not in BASELINE_MODELS
            ):
                meta["newbuilding"] = score_new_buildings(modal_app, spec)
        meta["usd_estimate"] = round(
            meta["wall_seconds"] * modal_app.usd_per_second(args.gpu, args.large)
            + meta.get("newbuilding", {}).get("usd_estimate", 0)
            + meta.get("score", {}).get("usd_estimate", 0),
            2,
        )
        # A large fit gets no summary on thelio, so its design would have no reader there.
        root = finish(modal_app.volume, spec["name"], meta, design=not args.large)
        if root == OUTPUT_ROOT and wants_summary(spec, args.split):
            summarize(spec)
    except Exception:
        # A container timeout or Modal error: keep whatever reached the Volume, log included.
        try:
            download(modal_app.volume, spec["name"], STATE / "failed", design=False)
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
    result = OUTPUT_ROOT / "runs" / name / "result.json"
    if not result.exists():
        sys.exit(f"{name} is not under {OUTPUT_ROOT / 'runs'}")
    # The summary, kit and rent map load the run's own dataset, which is the one to stage.
    dataset = json.loads(result.read_text())["dataset"]
    spec["dataset"] = spec["inputs"][0] = dataset
    spec["publish_seconds"] = PUBLISH_SECONDS + 3600
    STATE.mkdir(parents=True, exist_ok=True)
    lock = open(STATE / "launch.lock", "a")
    fcntl.flock(lock, fcntl.LOCK_SH)
    stage = stage_code(sha)
    os.environ["MODAL_FIT_STAGE"] = str(stage)
    modal_app = importlib.import_module("app")
    if args.gpu not in modal_app.LARGE_FITS:
        sys.exit(f"--gpu must be one of {', '.join(modal_app.LARGE_FITS)}")
    try:
        on_volume = any(True for _ in modal_app.volume.iterdir(f"/out/{name}/run"))
    except Exception:  # noqa: BLE001 (Modal raises NotFoundError for a missing path)
        on_volume = False
    if not on_volume:
        sys.exit(f"/out/{name}/run is not on the Volume")
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


def design_only(spec, sha):
    """fit.py --design-only: the design of a run already under OUTPUT_ROOT/runs, prepared at
    sha in a CPU container (app.design_cpu) and downloaded to OUTPUT_ROOT/designs. The record
    lands in runs/<name>/modal/design.json."""
    name = spec["name"]
    result = OUTPUT_ROOT / "runs" / name / "result.json"
    if not result.exists():
        sys.exit(f"{name} is not under {OUTPUT_ROOT / 'runs'}")
    spec["result"] = json.loads(result.read_text())
    # The summary loads the run's recorded dataset, which the key holds by its sha256.
    spec["dataset"] = spec["inputs"][0] = spec["result"]["dataset"]
    STATE.mkdir(parents=True, exist_ok=True)
    lock = open(STATE / "launch.lock", "a")
    fcntl.flock(lock, fcntl.LOCK_SH)
    stage = stage_code(sha)
    os.environ["MODAL_FIT_STAGE"] = str(stage)
    modal_app = importlib.import_module("app")
    touch()
    # Charged for the container's whole timeout; settled at the time it ran.
    secs = modal_app.DESIGN_TIMEOUT
    usd = round(secs * modal_app.design_usd_per_second(), 2)
    launch, left = cap.reserve(f"{name}-design", "cpu", usd, secs=secs)
    print(
        f"design of {name} at {sha[:7]}; estimated ${usd:.2f}, Modal balance now ${left:.2f}",
        flush=True,
    )
    import modal

    started, meta = time.monotonic(), None
    try:
        with modal.enable_output(), modal_app.app.run():
            sync(modal_app.volume, spec, stage)
            meta = modal_app.design_cpu.remote(spec)
        download(modal_app.volume, f"{name}-design", OUTPUT_ROOT, local=name)
        print(json.dumps(meta), flush=True)
    except Exception:
        # A container timeout or Modal error: keep the log that reached the Volume.
        try:
            download(
                modal_app.volume,
                f"{name}-design",
                STATE / "failed",
                local=name,
                design=False,
            )
        except Exception as e:  # noqa: BLE001
            print(f"no outputs to download: {e}", flush=True)
        raise
    finally:
        touch()
        cost = (meta or {}).get("usd_estimate")
        if cost is None:
            cost = (time.monotonic() - started) * modal_app.design_usd_per_second()
        try:
            cap.settle(launch, cost)
        except Exception as e:  # noqa: BLE001
            print(f"could not settle {launch} at ${cost:.2f}: {e}", flush=True)
    return meta["exit"]


def finish(volume, name, meta, design=True):
    """Download the run. A failed fit goes aside, off the research board, so a retry isn't
    blocked; a good fit whose PSIS-LOO failed is kept, as drive.sh keeps it. A saved design
    comes down only for a good fit and when design is True."""
    root = OUTPUT_ROOT if meta.get("fit_exit", meta["exit"]) == 0 else STATE / "failed"
    download(volume, name, root, design=design and root == OUTPUT_ROOT)
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
