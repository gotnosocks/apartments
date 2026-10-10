"""The Modal side of ops/modal-fit: one frontier fit plus its PSIS-LOO on a cloud GPU.

The launcher (ops/modal/fit.py) syncs the fit's inputs to Volume VOLUME under
/inputs/<absolute thelio path> and a shallow git checkout of the commit under
/code/<sha>, then imports this module with MODAL_FIT_STAGE pointing at that checkout,
so the image installs exactly the commit's frontier/uv.lock. The container copies the
inputs back to their thelio paths, runs rentfrontier.run and rentfrontier.loo as on
thelio, and leaves the run directory, the LOO directory and the log under /out/<name>
for the launcher to download. A fit that finishes also gets its post-fit statistics here,
while the container has its draws (`_post`): the variance decomposition, the summary
bundle (full fits), its predictive coverage by kind of row (rentfrontier.calibration: the
new-unit coverage of a time-split fit) and the explained share of any --explain candidate sets.
"""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import modal

VOLUME = "apartments-modal-fits"
APP = "apartments-modal-fit"
WORK = "/work/apartments"  # the checkout inside the container (any path: run and loo read git there)
RUNS = Path("/data1/apartments/frontier/runs")
LOO = Path("/data1/apartments/frontier/loo")
# USD per GPU-hour from modal.com/pricing, 2026-10-06, for the cost estimate in modal.json.
# Only these GPUs have float64 throughput worth paying for (docs/model/modal.md).
GPUS = {"L4": 0.799, "A100-40GB": 2.099, "A100-80GB": 2.498, "H100": 3.949}
CPU, MEMORY_MIB = 2, 24576  # the served design peaks near 15 GB of host memory
FIT_CAP = {"full": 2 * 3600, "exploration": 30 * 60}  # the fit alone, as on thelio
TIMEOUT = 3 * 3600  # the whole container: staging, fit, PSIS-LOO, post-fit statistics
POST_CAP = 20 * 60  # each post-fit statistic
POST_MARGIN = 10 * 60  # left before TIMEOUT for copying the outputs to the Volume
OUTPUT = Path(
    "/data1/apartments/frontier"
)  # rentfrontier's OUTPUT_ROOT in the container
POST_KINDS = ("variance", "summaries", "calibration", "explained")
USD_PER_CORE_SECOND, USD_PER_GIB_SECOND = 0.0000131, 0.00000222


def usd_per_second(gpu):
    """List price of one container: the GPU plus its reserved cores and memory (about $0.29 an hour)."""
    return (
        GPUS[gpu] / 3600
        + CPU * USD_PER_CORE_SECOND
        + MEMORY_MIB / 1024 * USD_PER_GIB_SECOND
    )


STAGE = Path(os.environ.get("MODAL_FIT_STAGE", "/nonexistent"))
volume = modal.Volume.from_name(VOLUME, create_if_missing=True, version=2)
image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git")
    .pip_install("uv==0.12.15")
    .add_local_file(
        STAGE / "frontier/pyproject.toml", "/build/pyproject.toml", copy=True
    )
    .add_local_file(STAGE / "frontier/uv.lock", "/build/uv.lock", copy=True)
    .run_commands(
        "cd /build && UV_PROJECT_ENVIRONMENT=/venv uv sync --frozen --extra gpu --no-install-project"
    )
)
app = modal.App(APP, image=image)


def _run(cmd, env, log, timeout=None):
    if timeout:
        cmd = ["timeout", str(timeout), *cmd]
    return subprocess.run(
        cmd, cwd=f"{WORK}/frontier", env=env, stdout=log, stderr=subprocess.STDOUT
    ).returncode


def post_steps(spec):
    """The post-fit statistics for a finished fit, as (step, rentfrontier arguments)."""
    name = spec["name"]
    steps = [("variance", ["rentfrontier.variance", name])]
    if spec["tier"] == "full":
        # The site's bundle; only full fits are served.
        steps.append(("summary", ["rentfrontier.summary", name]))
        # Reads the bundle the summary step just wrote, so its path is found at run time.
        steps.append(("calibration", lambda: _calibration_args(name)))
    if spec.get("explain"):
        steps.append(("explained", ["rentfrontier.explained", name, *spec["explain"]]))
    return steps


def _calibration_args(name):
    bundles = sorted(
        str(d)
        for d in (OUTPUT / "summaries").glob(f"{name}-*")
        if (d / "complete.json").exists()
    )
    return ["rentfrontier.calibration", *bundles] if bundles else None


def _post(spec, env, log, deadline):
    """Run each post-fit statistic, capped at POST_CAP and at the container's deadline. A
    failure is recorded and never fails the fit: its run and PSIS-LOO still come back."""
    done = {}
    for step, args in post_steps(spec):
        left = int(min(POST_CAP, deadline - time.time()))
        if left < 60:
            done[step] = {"exit": "skipped: container deadline"}
            continue
        t = time.time()
        try:
            if callable(args):
                args = args()
            if args is None:
                done[step] = {"exit": "skipped: no summary bundle"}
                continue
            code = _run(["/venv/bin/python", "-m", *args], env, log, left)
        except Exception as e:  # noqa: BLE001
            code = repr(e)
        done[step] = {"exit": code, "seconds": round(time.time() - t, 1)}
    return done


def _complete(d):
    """A post-fit record finished writing: a summary bundle has its complete.json (written
    last), and a variance or explained result.json parses (a step its cap killed mid-write
    leaves neither)."""
    if (d / "complete.json").exists():
        return True
    try:
        json.loads((d / "result.json").read_text())
        return True
    except (OSError, ValueError):
        return False


def _fit(spec):
    started = time.time()
    for path in spec["inputs"]:
        src = Path("/vol/inputs") / path.lstrip("/")
        dst = Path(path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
    shutil.copytree(f"/vol/code/{spec['commit']}", WORK)
    # Volume uploads drop empty directories and file modes; without these, git calls the
    # checkout broken or dirty, and rentfrontier.run refuses a dirty tree.
    for d in ("refs/heads", "refs/tags", "objects/info"):
        Path(WORK, ".git", d).mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", WORK, "config", "core.fileMode", "false"], check=True)
    staged = time.time() - started
    out = Path("/vol/out") / spec["name"]
    out.mkdir(parents=True, exist_ok=True)
    env = dict(
        os.environ,
        PYTHONPATH=f"{WORK}/frontier/src",
        FRONTIER_DATASET=spec["dataset"],
        XLA_PYTHON_CLIENT_PREALLOCATE="false",
        PYTHONUNBUFFERED="1",
    )
    gpu = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader",
        ],
        capture_output=True,
        text=True,
    ).stdout.strip()
    stages = {}
    with open(out / "fit.log", "w") as log:
        t = time.time()
        fit_code = code = _run(
            ["/venv/bin/python", "-m", "rentfrontier.run", *spec["run_args"]],
            env,
            log,
            FIT_CAP[spec["tier"]],
        )
        stages["fit"] = time.time() - t
        if code == 0:
            t = time.time()
            code = _run(
                ["/venv/bin/python", "-m", "rentfrontier.loo", spec["name"]], env, log
            )
            stages["loo"] = time.time() - t
        post = (
            _post(spec, env, log, started + TIMEOUT - POST_MARGIN)
            if fit_code == 0
            else {}
        )
    run = RUNS / spec["name"]
    if run.exists():
        shutil.copytree(run, out / "run", dirs_exist_ok=True)
    for d in LOO.glob(f"{spec['name']}-*"):
        shutil.copytree(d, out / "loo" / d.name, dirs_exist_ok=True)
    for kind in POST_KINDS:
        for d in (OUTPUT / kind).glob(f"{spec['name']}-*"):
            if d.is_dir() and _complete(d):
                shutil.copytree(d, out / kind / d.name, dirs_exist_ok=True)
    meta = {
        "name": spec["name"],
        "gpu": gpu,
        "exit": code,
        "fit_exit": fit_code,
        "stage_seconds": staged,
        "stages": stages,
        "post": post,
        "wall_seconds": time.time() - started,
    }
    (out / "modal.json").write_text(json.dumps(meta, indent=2))
    volume.commit()
    return meta


def _function(gpu):
    return app.function(
        gpu=gpu, cpu=CPU, memory=MEMORY_MIB, timeout=TIMEOUT, volumes={"/vol": volume}
    )


# One function per GPU type, at module scope so the container can find them by name.
@_function("L4")
def fit_l4(spec):
    return _fit(spec)


@_function("A100-40GB")
def fit_a100_40gb(spec):
    return _fit(spec)


@_function("A100-80GB")
def fit_a100_80gb(spec):
    return _fit(spec)


@_function("H100")
def fit_h100(spec):
    return _fit(spec)


FITS = {
    "L4": fit_l4,
    "A100-40GB": fit_a100_40gb,
    "A100-80GB": fit_a100_80gb,
    "H100": fit_h100,
}
