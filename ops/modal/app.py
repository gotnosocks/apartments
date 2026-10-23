"""The Modal side of ops/modal-fit: one frontier fit plus its PSIS-LOO on a cloud GPU.

The launcher (ops/modal/fit.py) syncs the fit's inputs to Volume VOLUME under
/inputs/<absolute thelio path> and a shallow git checkout of the commit under
/code/<sha>, then imports this module with MODAL_FIT_STAGE pointing at that checkout,
so the image installs exactly the commit's frontier/uv.lock. The container copies the
inputs back to their thelio paths, runs rentfrontier.run and rentfrontier.loo as on
thelio, and leaves the run directory, the LOO directory and the log under /out/<name>
for the launcher to download. A fit that finishes also gets its post-fit statistics here,
while the container has its draws (`_post`): the variance decomposition and the explained
share of any --explain candidate sets. The summary bundle and its calibration are built on
thelio after the download (ops/modal/summarize), except for a large fit, which builds them here.
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
GPUS = {
    "L4": 0.799,
    "A100-40GB": 2.099,
    "A100-80GB": 2.498,
    "H100": 3.949,
    "H200": 4.54,
}
CPU, MEMORY_MIB = 2, 24576  # the served design peaks near 15 GB of host memory
FIT_CAP = {"full": 3600, "exploration": 30 * 60}  # the fit alone
# The whole container: staging, fit, PSIS-LOO, post-fit statistics. Launches are capped at an
# estimated hour (cap.PER_FIT_SECONDS); this stops a runaway at 75 min, past the 69 min of the
# slowest C-sized fit so far (bigbed, 2026-10-12, which then built its summary bundle here).
TIMEOUT = 75 * 60
POST_CAP = 20 * 60  # each post-fit statistic
POST_MARGIN = 10 * 60  # left before TIMEOUT for copying the outputs to the Volume
OUTPUT = Path(
    "/data1/apartments/frontier"
)  # rentfrontier's OUTPUT_ROOT in the container
POST_KINDS = (
    "variance",
    "explained",
    "newbuilding",
    "summaries",
    "calibration",
    "maps",
    "kits",
)
USD_PER_CORE_SECOND, USD_PER_GIB_SECOND = 0.0000131, 0.00000222
# The new-building score (rentfrontier.newbuilding) is numpy over row chunks, one process
# per core: a CPU container scores a run's kept draws in parallel after its fit.
NB_CPU, NB_MEMORY_MIB, NB_TIMEOUT = 32, 131072, 3600
# The baseline models' scoring (rentfrontier.loo: PSIS-LOO, held-out predictive quantiles and
# coverage) after a fit with --cpu-score: threads over blocks of rows, numpy only, on the draws
# the GPU container left on the Volume (9.5 MB for 656 draws), so the A100 isn't billed for it.
# SCORE_CPU threads each hold a (draws x rows) block of about 50 MB and a few copies of it.
SCORE_CPU, SCORE_MEMORY_MIB, SCORE_TIMEOUT = 16, 32768, 30 * 60
# A run's design alone (fit.py --design-only), for a run whose prep runs out of thelio's memory:
# the all-scraped run's prep took 15 min in its large container and was killed at 9 GB on thelio.
DESIGN_CPU, DESIGN_MEMORY_MIB, DESIGN_TIMEOUT = 4, 65536, 3600
# A large fit (fit.py --large; Ben, 2026-10-16 06:37Z: a fit on all the scraped data, 1.75M rows,
# with no hour cap). Host memory scales with the rows from the served design's 15 GB on NB9's
# 266k, and the fit, PSIS-LOO, post-fit statistics and summary bundle each run for an hour or
# more, so the container builds the bundle and its calibration itself (thelio has 15 GB).
LARGE_CPU, LARGE_MEMORY_MIB = 8, 196608
LARGE_FIT_CAP, LARGE_TIMEOUT = 9 * 3600, 12 * 3600
LARGE_POST_MARGIN = 45 * 60  # copying a 1.75M-row run, LOO and bundle to the Volume
PUBLISH_MARGIN = 15 * 60  # copying a bundle, kit and rent map to the Volume
# Processes for the summary's per-chunk row tables in a publish: one core of LARGE_CPU stays
# with the main process and its JAX work.
SUMMARY_WORKERS = LARGE_CPU - 1


def usd_per_second(gpu, large=False):
    """List price of one container: the GPU plus its reserved cores and memory (about $0.29 an
    hour, or $1.90 for a large fit)."""
    cpu, memory = (LARGE_CPU, LARGE_MEMORY_MIB) if large else (CPU, MEMORY_MIB)
    return (
        GPUS[gpu] / 3600
        + cpu * USD_PER_CORE_SECOND
        + memory / 1024 * USD_PER_GIB_SECOND
    )


def nb_usd_per_second():
    return NB_CPU * USD_PER_CORE_SECOND + NB_MEMORY_MIB / 1024 * USD_PER_GIB_SECOND


def score_usd_per_second():
    """List price of the scoring container (about $1.01 an hour)."""
    return (
        SCORE_CPU * USD_PER_CORE_SECOND + SCORE_MEMORY_MIB / 1024 * USD_PER_GIB_SECOND
    )


def design_usd_per_second():
    """List price of the design container (about $0.70 an hour)."""
    return (
        DESIGN_CPU * USD_PER_CORE_SECOND + DESIGN_MEMORY_MIB / 1024 * USD_PER_GIB_SECOND
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


# The baseline models, which carry their own scoring and no frontier design.
BASELINES = (
    ("--model", "b0"),
    ("--model", "b0.1"),
    ("--model", "b0.2"),
    ("--model", "b0.3"),
    ("--model", "b0.4"),
    ("--model", "centered-walk"),
    ("--model", "level-walk"),
    ("--model", "total-walk"),
    ("--model", "normal-walk"),
    ("--model", "two-zone"),
    ("--model", "two-zone-1k"),
    ("--model", "whitened-zones"),
    ("--model", "building-zones"),
    ("--model", "building-attrs"),
    ("--model", "building-zones-gibbs"),
    ("--model", "building-zones-attrs"),
    ("--model", "building-zones-attrs-500m"),
    ("--model", "building-zones-front"),
    ("--model", "building-zones-unit"),
    ("--model", "building-zones-gym"),
    ("--model", "building-zones-age"),
    ("--model", "building-zones-floor"),
    ("--model", "building-zones-mundlak"),
    ("--model", "building-zones-transit"),
    ("--model", "building-zones-parks"),
    ("--model", "building-zones-noise"),
    ("--model", "building-zones-location"),
    ("--model", "building-zones-avenue"),
    ("--model", "building-zones-parkfront"),
    ("--model", "building-zones-waterfront"),
    ("--model", "building-zones-elevated"),
    ("--model", "building-zones-floor-parkfront"),
    ("--model", "building-zones-floor-asof"),
    ("--model", "building-zones-floor-asof-amp1"),
    ("--model", "building-zones-floor-asof2"),
    ("--model", "building-zones-floor-asof2-cap64"),
    ("--model", "building-zones-floor-asof3"),
    ("--model", "building-zones-floor-asof3-cap64"),
    ("--model", "building-zones-floor-asof3-unit"),
    ("--model", "building-zones-floor-asof3-periods"),
    ("--model", "building-zones-floor-asof3-unitmean"),
    ("--model", "building-zones-mundlak-asof"),
)


def post_steps(spec):
    """The post-fit statistics for a finished fit, as (step, rentfrontier arguments)."""
    name = spec["name"]
    # The B0 baselines (rentfrontier.b0 to b0_4) write their own statistics; the variance
    # and explained shares read the frontier model's design, which their runs have none of.
    run_args = spec.get("run_args", [])
    if any(pair in zip(run_args, run_args[1:]) for pair in BASELINES):
        return []
    steps = [("variance", ["rentfrontier.variance", name])]
    if spec.get("explain"):
        steps.append(("explained", ["rentfrontier.explained", name, *spec["explain"]]))
    return steps


def loo_command(spec, workers=None):
    """rentfrontier.loo for the run, with the scoring steps the spec leaves on (B0 family runs)."""
    return [
        "/venv/bin/python",
        "-m",
        "rentfrontier.loo",
        *(["--workers", str(workers)] if workers else []),
        *(["--no-loo"] if not spec.get("loo", True) else []),
        *(["--no-heldout"] if not spec.get("heldout", True) else []),
        spec["name"],
    ]


def _post(spec, env, log, deadline):
    """Run each post-fit statistic, capped at POST_CAP (a large fit: only the deadline) and at
    the container's deadline. A failure is recorded and never fails the fit: its run and
    PSIS-LOO still come back."""
    done = {}
    cap = LARGE_TIMEOUT if spec.get("large") else POST_CAP
    for step, args in post_steps(spec):
        left = int(min(cap, deadline - time.time()))
        if left < 60:
            done[step] = {"exit": "skipped: container deadline"}
            continue
        t = time.time()
        try:
            code = _run(["/venv/bin/python", "-m", *args], env, log, left)
        except Exception as e:  # noqa: BLE001
            code = repr(e)
        done[step] = {"exit": code, "seconds": round(time.time() - t, 1)}
    return done


def _summarize(spec, env, log, deadline):
    """A large fit's summary bundle (rentfrontier.summary) and its calibration, as
    ops/modal/summarize builds them on thelio, within the container's deadline. A failure is
    recorded and never fails the fit."""
    done = {}
    for step in ("summary", "calibration"):
        left = int(deadline - time.time())
        bundles = sorted((OUTPUT / "summaries").glob(f"{spec['name']}-*/complete.json"))
        if left < 60 or (step == "calibration" and not bundles):
            done[step] = {"exit": "skipped"}
            continue
        args = (
            [spec["name"], *_range_flags(spec)]
            if step == "summary"
            else [str(bundles[-1].parent)]
        )
        t = time.time()
        try:
            code = _run(
                ["/venv/bin/python", "-m", f"rentfrontier.{step}", *args],
                env,
                log,
                left,
            )
        except Exception as e:  # noqa: BLE001
            code = repr(e)
        done[step] = {"exit": code, "seconds": round(time.time() - t, 1)}
    return done


def _complete(d):
    """A post-fit record finished writing: its result.json (a summary bundle or kit:
    complete.json; a rent map: map.json) parses (a step its cap killed mid-write leaves none)."""
    try:
        record = {
            "summaries": "complete.json",
            "kits": "complete.json",
            "maps": "map.json",
        }
        record = record.get(d.parent.name, "result.json")
        json.loads((d / record).read_text())
        return True
    except (OSError, ValueError):
        return False


def _stage(spec, inputs=None):
    """Copy the fit's inputs (or just `inputs`) back to their thelio paths and check out the
    commit at WORK."""
    for path in spec["inputs"] if inputs is None else inputs:
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


def publish_steps(spec):
    """The publish steps for a fit already on the Volume (fit.py --publish-only), as
    ops/autoselect-publish.sh runs them on thelio, as (step, steps it needs, rentfrontier
    arguments). The kit and calibration read the bundle the summary writes, found once it
    exists. The rent map reads only the run, so it runs last and alone."""
    name = spec["name"]
    failing = ["--allow-failing"] if spec.get("allow_failing") else []
    ranges = _range_flags(spec)
    return [
        ("summary", (), lambda: ["rentfrontier.summary", name, "--workers", str(SUMMARY_WORKERS), *failing, *ranges]),
        ("kit", ("summary",), lambda: ["rentfrontier.kit", name, "--summary", str(_bundle(name)), *failing]),
        ("calibration", ("summary",), lambda: ["rentfrontier.calibration", str(_bundle(name))]),
        ("rentmap", (), lambda: ["rentfrontier.rentmap", name]),
    ]  # fmt: skip


def _range_flags(spec):
    """The summary's range options the spec asks for (fit.py --range-sample, --range-atoms)."""
    return [
        flag
        for key, flag in (
            ("range_sample", "--range-sample"),
            ("range_atoms", "--range-atoms"),
        )
        if spec.get(key)
    ]


def _bundle(name):
    bundles = sorted((OUTPUT / "summaries").glob(f"{name}-*/complete.json"))
    return bundles[-1].parent


def _publish(spec):
    """Build a downloaded fit's summary bundle, calibration, rent map and estimate kit from its
    run on the Volume, for a run too large for thelio's memory. The run and LOO stay on the
    Volume as they are; the new directories go to /vol/out/<name>-publish/. A step whose
    summary failed is skipped, and so is every step left once spec["publish_seconds"] or the
    container's timeout runs out. The exit is 0 only if every step succeeded."""
    started = time.time()
    _stage(spec)
    name = spec["name"]
    src = Path("/vol/out") / name
    shutil.copytree(src / "run", RUNS / name, dirs_exist_ok=True)
    for kind, dst in (("loo", LOO), ("variance", OUTPUT / "variance")):
        if (src / kind).is_dir():
            shutil.copytree(src / kind, dst, dirs_exist_ok=True)
    # A design the fit saved (fit.py --save-design) spares the summary its prep, if this
    # commit's package and config match the fit's.
    for p in sorted((src / "design").glob("design-*.pkl")):
        (OUTPUT / "cache").mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, OUTPUT / "cache" / p.name)
    out = Path("/vol/out") / f"{name}-publish"
    out.mkdir(parents=True, exist_ok=True)
    env = dict(
        os.environ,
        PYTHONPATH=f"{WORK}/frontier/src",
        FRONTIER_DATASET=spec["dataset"],
        XLA_PYTHON_CLIENT_PREALLOCATE="false",
        PYTHONUNBUFFERED="1",
        # The kit and rent map then read the design the summary built (rentfrontier.design).
        FRONTIER_DESIGN_CACHE="1",
    )
    deadline = started + min(
        LARGE_TIMEOUT - PUBLISH_MARGIN, spec.get("publish_seconds", LARGE_TIMEOUT)
    )
    done = {}
    with open(out / "publish.log", "w") as log:
        for step, needs, args in publish_steps(spec):
            left = int(deadline - time.time())
            if left < 60 or any(done[n]["exit"] != 0 for n in needs):
                done[step] = {"exit": "skipped"}
                continue
            t = time.time()
            try:
                code = _run(["/venv/bin/python", "-m", *args()], env, log, left)
            except Exception as e:  # noqa: BLE001
                code = repr(e)
            done[step] = {"exit": code, "seconds": round(time.time() - t, 1)}
    for kind in POST_KINDS:
        for d in (OUTPUT / kind).glob(f"{name}-*"):
            if d.is_dir() and _complete(d):
                shutil.copytree(d, out / kind / d.name, dirs_exist_ok=True)
    meta = {
        "name": name,
        "exit": next((d["exit"] for d in done.values() if d["exit"] != 0), 0),
        "post": done,
        "wall_seconds": time.time() - started,
    }
    (out / "publish.json").write_text(json.dumps(meta, indent=2))
    volume.commit()
    return meta


def _fit(spec):
    if spec.get("publish_only"):
        return _publish(spec)
    started = time.time()
    _stage(spec)
    staged = time.time() - started
    out = Path("/vol/out") / spec["name"]
    out.mkdir(parents=True, exist_ok=True)
    env = dict(
        os.environ,
        PYTHONPATH=f"{WORK}/frontier/src",
        FRONTIER_DATASET=spec["dataset"],
        XLA_PYTHON_CLIENT_PREALLOCATE="false",
        # JAX caps its allocator at 75% of the card unless told otherwise; the fit is the only
        # process on it.
        XLA_PYTHON_CLIENT_MEM_FRACTION="0.95",
        PYTHONUNBUFFERED="1",
        # rentfrontier.loo and the post-fit statistics then read the design rentfrontier.run
        # built (rentfrontier.design).
        FRONTIER_DESIGN_CACHE="1",
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
    # Designs staged with the inputs, so only the one the fit adds is saved.
    staged_designs = set((OUTPUT / "cache").glob("design-*.pkl"))
    large = spec.get("large", False)
    deadline = (
        started + LARGE_TIMEOUT - LARGE_POST_MARGIN
        if large
        else started + TIMEOUT - POST_MARGIN
    )
    with open(out / "fit.log", "w") as log:
        t = time.time()
        fit_code = code = _run(
            ["/venv/bin/python", "-m", "rentfrontier.run", *spec["run_args"]],
            env,
            log,
            LARGE_FIT_CAP if large else FIT_CAP[spec["tier"]],
        )
        stages["fit"] = time.time() - t
        if code == 0 and spec.get("save_design"):
            # Right after the fit, the run's design is the only new one in the cache.
            for p in sorted(
                set((OUTPUT / "cache").glob("design-*.pkl")) - staged_designs
            ):
                (out / "design").mkdir(exist_ok=True)
                shutil.copy2(p, out / "design" / p.name)
        # With cpu_score the draws leave on the Volume and score_cpu scores them; with both
        # scoring steps off, nothing scores them.
        if code == 0 and spec.get("score", True) and not spec.get("cpu_score"):
            t = time.time()
            code = _run(
                loo_command(spec),
                env,
                log,
                int(max(deadline - time.time(), 60)) if large else None,
            )
            stages["loo"] = time.time() - t
        if large:
            # Saved before the hours of post-fit work, so a container timeout keeps them.
            _save_fit(spec, out)
        post = _post(spec, env, log, deadline) if fit_code == 0 else {}
        if large and code == 0 and spec.get("summary", True):
            post |= _summarize(spec, env, log, deadline)
    _save_fit(spec, out)
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


def _save_fit(spec, out):
    """Copy the run and its LOO directories to the Volume and commit them."""
    run = RUNS / spec["name"]
    if run.exists():
        shutil.copytree(run, out / "run", dirs_exist_ok=True)
    for d in LOO.glob(f"{spec['name']}-*"):
        shutil.copytree(d, out / "loo" / d.name, dirs_exist_ok=True)
    volume.commit()


def _function(gpu):
    return app.function(
        gpu=gpu, cpu=CPU, memory=MEMORY_MIB, timeout=TIMEOUT, volumes={"/vol": volume}
    )


@app.function(
    cpu=NB_CPU, memory=NB_MEMORY_MIB, timeout=NB_TIMEOUT, volumes={"/vol": volume}
)
def newbuilding_cpu(spec):
    """Score the run under /vol/out/<name>/run with rentfrontier.newbuilding, NB_CPU
    workers, and leave its result under /vol/out/<name>/newbuilding/ for the download."""
    started = time.time()
    volume.reload()
    _stage(spec)
    out = Path("/vol/out") / spec["name"]
    shutil.copytree(out / "run", RUNS / spec["name"], dirs_exist_ok=True)
    staged = time.time() - started
    env = dict(
        os.environ,
        PYTHONPATH=f"{WORK}/frontier/src",
        FRONTIER_DATASET=spec["dataset"],
        JAX_PLATFORMS="cpu",
        PYTHONUNBUFFERED="1",
        # One thread per worker process: the workers already fill the cores.
        OMP_NUM_THREADS="1",
        OPENBLAS_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
    )
    args = ["--workers", str(NB_CPU), *spec.get("newbuilding_args", ()), spec["name"]]
    with open(out / "newbuilding.log", "w") as log:
        code = _run(
            ["/venv/bin/python", "-m", "rentfrontier.newbuilding", *args],
            env,
            log,
            NB_TIMEOUT - 5 * 60,
        )
    for d in (OUTPUT / "newbuilding").glob(f"{spec['name']}-*"):
        if d.is_dir() and _complete(d):
            shutil.copytree(d, out / "newbuilding" / d.name, dirs_exist_ok=True)
    wall = time.time() - started
    meta = {
        "exit": code,
        "cpu": NB_CPU,
        "stage_seconds": round(staged, 1),
        "wall_seconds": round(wall, 1),
        "usd_estimate": round(wall * nb_usd_per_second(), 2),
    }
    volume.commit()
    return meta


@app.function(
    cpu=SCORE_CPU,
    memory=SCORE_MEMORY_MIB,
    timeout=SCORE_TIMEOUT,
    volumes={"/vol": volume},
)
def score_cpu(spec):
    return _score(spec)


def _score(spec):
    """Score the baseline run under /vol/out/<name>/run with rentfrontier.loo on SCORE_CPU
    threads, and leave its PSIS-LOO directory under /vol/out/<name>/loo/ for the download.
    The container stages the code and the run's dataset only: scoring reads no other input."""
    started = time.time()
    volume.reload()
    _stage(spec, inputs=spec["inputs"][:1])
    out = Path("/vol/out") / spec["name"]
    shutil.copytree(out / "run", RUNS / spec["name"], dirs_exist_ok=True)
    staged = time.time() - started
    env = dict(
        os.environ,
        PYTHONPATH=f"{WORK}/frontier/src",
        FRONTIER_DATASET=spec["dataset"],
        JAX_PLATFORMS="cpu",
        PYTHONUNBUFFERED="1",
        # The scoring threads fill the cores; a BLAS pool in each would oversubscribe them.
        OMP_NUM_THREADS="1",
        OPENBLAS_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
    )
    t = time.time()
    with open(out / "score.log", "w") as log:
        code = _run(loo_command(spec, SCORE_CPU), env, log, SCORE_TIMEOUT - 3 * 60)
    scored = time.time() - t
    for d in LOO.glob(f"{spec['name']}-*"):
        shutil.copytree(d, out / "loo" / d.name, dirs_exist_ok=True)
    wall = time.time() - started
    meta = {
        "exit": code,
        "cpu": SCORE_CPU,
        "stage_seconds": round(staged, 1),
        "score_seconds": round(scored, 1),
        "wall_seconds": round(wall, 1),
        "usd_estimate": round(wall * score_usd_per_second(), 2),
    }
    volume.commit()
    return meta


@app.function(
    cpu=DESIGN_CPU,
    memory=DESIGN_MEMORY_MIB,
    timeout=DESIGN_TIMEOUT,
    volumes={"/vol": volume},
)
def design_cpu(spec):
    return _design(spec)


def _design(spec):
    """Prepare the design of a finished run (python -m rentfrontier.design) at the spec's
    commit and leave the pickle under /vol/out/<name>-design/design/ for the download, with
    the log and a design.json record."""
    started = time.time()
    _stage(spec)
    name = spec["name"]
    (RUNS / name).mkdir(parents=True, exist_ok=True)
    (RUNS / name / "result.json").write_text(json.dumps(spec["result"]))
    out = Path("/vol/out") / f"{name}-design"
    out.mkdir(parents=True, exist_ok=True)
    staged_designs = set((OUTPUT / "cache").glob("design-*.pkl"))
    env = dict(
        os.environ,
        PYTHONPATH=f"{WORK}/frontier/src",
        FRONTIER_DATASET=spec["dataset"],
        FRONTIER_DESIGN_CACHE="1",
        JAX_PLATFORMS="cpu",
        PYTHONUNBUFFERED="1",
    )
    with open(out / "design.log", "w") as log:
        code = _run(
            ["/venv/bin/python", "-m", "rentfrontier.design", name],
            env,
            log,
            DESIGN_TIMEOUT - 10 * 60,
        )
    saved = []
    if code == 0:
        for p in sorted(set((OUTPUT / "cache").glob("design-*.pkl")) - staged_designs):
            (out / "design").mkdir(exist_ok=True)
            shutil.copy2(p, out / "design" / p.name)
            saved.append({"file": p.name, "bytes": p.stat().st_size})
        if not saved:
            # The prep loaded a staged design of the same key: nothing new comes down.
            code = "no new design"
    try:
        # The CLI's record (key, rows, seconds) is the log's last line.
        record = json.loads((out / "design.log").read_text().splitlines()[-1])
    except (OSError, ValueError, IndexError):
        record = None
    try:
        # cgroup v2's high-water mark of the container's memory
        peak = int(Path("/sys/fs/cgroup/memory.peak").read_text())
    except (OSError, ValueError):
        peak = None
    wall = time.time() - started
    meta = {
        "name": name,
        "exit": code,
        "designs": saved,
        "record": record,
        "memory_peak_bytes": peak,
        "wall_seconds": round(wall, 1),
        "usd_estimate": round(wall * design_usd_per_second(), 2),
    }
    (out / "design.json").write_text(json.dumps(meta, indent=2))
    volume.commit()
    return meta


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


def _large_function(gpu):
    return app.function(
        gpu=gpu,
        cpu=LARGE_CPU,
        memory=LARGE_MEMORY_MIB,
        timeout=LARGE_TIMEOUT,
        volumes={"/vol": volume},
    )


# Large fits, for datasets several times the size of NB9, get a large container's host memory on
# any of these GPUs. The all-scraped design (1.6M rows, 68k buildings) outgrew the H100's 80 GB on
# 2026-10-16 while the sampler held its design and kept draws on the card; with those off the card
# it fits an A100-40GB.
@_large_function("A100-40GB")
def fit_a100_40gb_large(spec):
    return _fit(spec)


@_large_function("A100-80GB")
def fit_a100_80gb_large(spec):
    return _fit(spec)


@_large_function("H100")
def fit_h100_large(spec):
    return _fit(spec)


@_large_function("H200")
def fit_h200_large(spec):
    return _fit(spec)


LARGE_FITS = {
    "A100-40GB": fit_a100_40gb_large,
    "A100-80GB": fit_a100_80gb_large,
    "H100": fit_h100_large,
    "H200": fit_h200_large,
}
