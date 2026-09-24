"""Run `rentfrontier.run` on a Modal GPU worker, pinned to a clean commit.

    uv run --with modal==1.5.5 python scripts/modal_run.py --gpu H100 \
        --name <run-name> -- --split rows --chains 32 ...

- Refuses a dirty working tree. The worker gets `git archive HEAD` of
  frontier/src, so the code that ran is exactly the recorded commit.
- Dataset and promoted-model reference files live on the `frontier-work`
  Volume (uploaded once with --upload-inputs, SHA-256 checked by the loader).
- The run directory is downloaded to /data1/apartments/frontier/runs/<name>,
  and `remote.json` beside result.json records GPU, container seconds and cost.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

import modal

VOLUME = "frontier-work"
DATASET = Path(
    "/home/ben/code/apartments/data/model/chelsea-product-scope-analysis-20260921"
)
REFERENCE_ROOT = Path("/home/ben/code/apartments/data/model/feature-screen-20260923")
DESCRIPTIONS = Path(
    "/home/ben/code/apartments/data/model/chelsea-refreshed-bayesian-descriptions-20260918/evidence.jsonl"
)
LOCAL_RUNS = Path("/data1/apartments/frontier/runs")
PACKAGES = [
    "jax[cuda12]==0.11.2",
    "numpyro==0.22.0",
    "blackjax==1.6.2",
    "optax==0.2.8",
    "numpy==2.5.3",
    "scipy==1.18.1",
    "pandas==3.0.6",
    "pyarrow==25.0.1",
    "arviz==1.3.0",
]
# Modal list prices (modal billing rates, 2026-09-23), USD per hour.
GPU_RATES = {
    "H100": 3.95,
    "A100-40GB": 2.10,
    "A100-80GB": 2.50,
    "L4": 0.80,
    "L40S": 1.95,
    "A10G": 1.10,
}
CPU_RATE, MEM_RATE = 0.0473, 0.008  # per core-hour, per GiB-hour
CPU_CORES, MEMORY_GIB = 4, 16


def git(*args):
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def upload_inputs():
    vol = modal.Volume.from_name(VOLUME, create_if_missing=True)
    with vol.batch_upload(force=True) as batch:
        batch.put_file(
            str(DATASET / "observations.jsonl"),
            f"data/{DATASET.name}/observations.jsonl",
        )
        batch.put_file(str(DESCRIPTIONS), "data/descriptions/evidence.jsonl")
        for split_dir in ("nuts-hwalk", "nuts-hwalk-units"):
            ref = REFERENCE_ROOT / split_dir / "heldout.npz"
            if ref.exists():
                batch.put_file(str(ref), f"refs/{split_dir}/heldout.npz")
                print("uploaded reference", ref)
    print("uploaded dataset", DATASET)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gpu", default="H100", choices=sorted(GPU_RATES))
    parser.add_argument("--name", required=True)
    parser.add_argument("--timeout", type=int, default=3 * 3600)
    parser.add_argument("--upload-inputs", action="store_true")
    parser.add_argument("run_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    run_args = [a for a in args.run_args if a != "--"]

    if args.upload_inputs:
        upload_inputs()
    if git("status", "--porcelain"):
        raise SystemExit("Refusing to submit from a dirty working tree; commit first.")
    commit = git("rev-parse", "HEAD")
    root = git("rev-parse", "--show-toplevel")

    export = Path(tempfile.mkdtemp(prefix=f"frontier-{commit[:12]}-"))
    archive = export / "src.tar"
    subprocess.run(
        ["git", "-C", root, "archive", "-o", str(archive), commit, "frontier/src"],
        check=True,
    )
    with tarfile.open(archive) as tar:
        tar.extractall(export, filter="data")
    src = export / "frontier" / "src"

    app = modal.App("rentfrontier")
    vol = modal.Volume.from_name(VOLUME, create_if_missing=True)
    image = (
        modal.Image.debian_slim(python_version="3.12")
        .apt_install("git")
        .uv_pip_install(*PACKAGES)
        .add_local_dir(str(src), "/root/src")
    )

    @app.function(
        image=image,
        gpu=args.gpu,
        cpu=CPU_CORES,
        memory=MEMORY_GIB * 1024,
        volumes={"/vol": vol},
        timeout=args.timeout,
        serialized=True,
    )
    def remote_run(run_args, commit, name):
        import subprocess
        import time

        env = {
            **os.environ,
            "PYTHONPATH": "/root/src",
            "FRONTIER_COMMIT": commit,
            "FRONTIER_DATASET": f"/vol/data/{DATASET.name}",
            "FRONTIER_OUTPUT_ROOT": "/vol/out",
            "FRONTIER_REFERENCE_ROOT": "/vol/refs",
            "FRONTIER_DESCRIPTIONS": "/vol/data/descriptions/evidence.jsonl",
            "XLA_PYTHON_CLIENT_PREALLOCATE": "false",
        }
        t0 = time.time()
        proc = subprocess.run(
            [sys.executable, "-m", "rentfrontier.run", "--name", name, *run_args],
            env=env,
            capture_output=True,
            text=True,
            check=False,  # the return code is reported to the caller
        )
        vol.commit()
        gpu = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        return {
            "returncode": proc.returncode,
            "seconds": time.time() - t0,
            "stdout": proc.stdout[-20000:],
            "stderr": proc.stderr[-20000:],
            "gpu": gpu,
        }

    started = time.time()
    with modal.enable_output(), app.run():
        out = remote_run.remote(run_args, commit, args.name)
    wall = time.time() - started
    print(out["stdout"])
    if out["returncode"] != 0:
        print(out["stderr"], file=sys.stderr)
    # Estimate from list prices over the client-side wall time, which covers
    # container start-up and shutdown too (Modal bills whole container life).
    hours = wall / 3600
    cost = hours * (GPU_RATES[args.gpu] + CPU_CORES * CPU_RATE + MEMORY_GIB * MEM_RATE)
    remote = {
        "gpu_requested": args.gpu,
        "gpu_reported": out["gpu"],
        "remote_seconds": out["seconds"],
        "client_wall_seconds": wall,
        "cost_usd_estimate": round(cost, 4),
        "cost_basis": "list price x client wall time; an estimate (actual Modal billing ran ~6% higher over 2026-09-23 runs)",
        "commit": commit,
        "returncode": out["returncode"],
    }
    print(json.dumps(remote, indent=2))
    dest = LOCAL_RUNS / args.name
    if out["returncode"] == 0:
        LOCAL_RUNS.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "modal",
                "volume",
                "get",
                "--force",
                VOLUME,
                f"out/runs/{args.name}",
                str(LOCAL_RUNS),
            ],
            check=True,
        )
        result = json.loads((dest / "result.json").read_text())
        result["cost_usd"] = remote["cost_usd_estimate"]
        result["remote"] = remote
        (dest / "result.json").write_text(json.dumps(result, indent=2))
    else:
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "failed-stderr.txt").write_text(out["stderr"])
    (dest / "remote.json").write_text(json.dumps(remote, indent=2))
    sys.exit(out["returncode"])


if __name__ == "__main__":
    main()
