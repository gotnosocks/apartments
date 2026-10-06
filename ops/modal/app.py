"""The Modal side of ops/modal-fit: one frontier fit plus its PSIS-LOO on a cloud GPU.

The launcher (ops/modal/fit.py) syncs the fit's inputs to Volume VOLUME under
/inputs/<absolute thelio path> and a shallow git checkout of the commit under
/code/<sha>, then imports this module with MODAL_FIT_STAGE pointing at that checkout,
so the image installs exactly the commit's frontier/uv.lock. The container copies the
inputs back to their thelio paths, runs rentfrontier.run and rentfrontier.loo as on
thelio, and leaves the run directory, the LOO directory and the log under /out/<name>
for the launcher to download.
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
TIMEOUT = 3 * 3600  # the whole container: staging, fit, PSIS-LOO
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
    run = RUNS / spec["name"]
    if run.exists():
        shutil.copytree(run, out / "run", dirs_exist_ok=True)
    for d in LOO.glob(f"{spec['name']}-*"):
        shutil.copytree(d, out / "loo" / d.name, dirs_exist_ok=True)
    meta = {
        "name": spec["name"],
        "gpu": gpu,
        "exit": code,
        "fit_exit": fit_code,
        "stage_seconds": staged,
        "stages": stages,
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
