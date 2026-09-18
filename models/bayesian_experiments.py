"""Run a bounded sequence of local Bayesian ablations with durable status.

Every fit has its own new output directory and log. This controller never changes
source data, the review app, or deployed reports. Failed diagnostics stop the
sequence so a human or supervising agent can inspect the model before proceeding.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time


VARIANTS = {
    "building": ["--no-units"],
    "unit": [],
    "unit-no-size": ["--no-size"],
    "unit-normal": ["--likelihood", "normal"],
    "unit-drift": ["--linear-drift"],
    "building-drift": ["--linear-drift", "--no-units"],
    "unit-drift-no-size": ["--linear-drift", "--no-size"],
    "unit-drift-normal": ["--linear-drift", "--likelihood", "normal"],
}


def write_state(path, state):
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2))
    temporary.replace(path)


def run(args):
    root = args.output
    root.mkdir(parents=True, exist_ok=False)
    deadline = datetime.fromisoformat(args.deadline).timestamp()
    state = {"status": "starting", "runs": [], "deadline": args.deadline}
    status_path = root / "progress.json"
    write_state(status_path, state)
    runner = root / "bayesian_rent_model.py"
    runner.write_bytes(Path(__file__).with_name("bayesian_rent_model.py").read_bytes())
    (root / "bayesian_experiments.py").write_bytes(Path(__file__).read_bytes())
    environment = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")
    for name in args.variants:
        remaining = deadline - time.time()
        if remaining < 900:
            state.update(
                status="deadline",
                message="Less than 15 minutes remain; no new fit launched",
            )
            write_state(status_path, state)
            return
        output = root / name
        command = [
            sys.executable,
            str(runner),
            "--input",
            str(args.input),
            "--output",
            str(output),
            "--train-end",
            "2024-12-01",
            "--predict-end",
            "2025-12-01",
            "--draws",
            str(args.draws),
            "--tune",
            str(args.tune),
            "--chains",
            "4",
            "--target-accept",
            ".95",
            "--adaptation",
            args.adaptation,
            *VARIANTS[name],
        ]
        record = {
            "variant": name,
            "command": command,
            "output": str(output),
            "status": "running",
        }
        state["runs"].append(record)
        state.update(status="running", active_variant=name)
        write_state(status_path, state)
        started = time.monotonic()
        try:
            with (root / f"{name}.log").open("w") as log:
                result = subprocess.run(
                    command,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    env=environment,
                    timeout=min(args.fit_timeout, remaining),
                )
            record["returncode"] = result.returncode
            if result.returncode:
                record["status"] = "failed"
            else:
                diagnostics = json.loads((output / "diagnostics.json").read_text())
                record["diagnostics"] = diagnostics
                record["status"] = (
                    "accepted" if diagnostics["acceptable"] else "needs_diagnostics"
                )
        except subprocess.TimeoutExpired:
            record["status"] = "timeout"
        record["seconds"] = time.monotonic() - started
        write_state(status_path, state)
        if record["status"] != "accepted":
            state["status"] = "needs_attention"
            write_state(status_path, state)
            return
    state.update(status="complete", active_variant=None)
    write_state(status_path, state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--deadline", required=True, help="ISO timestamp with explicit UTC offset"
    )
    parser.add_argument(
        "--variants",
        nargs="+",
        choices=VARIANTS,
        default=["building", "unit", "unit-no-size", "unit-normal"],
    )
    parser.add_argument("--draws", type=int, default=2000)
    parser.add_argument("--tune", type=int, default=1500)
    parser.add_argument("--adaptation", choices=["diag", "low_rank"], default="diag")
    parser.add_argument("--fit-timeout", type=int, default=3600)
    args = parser.parse_args()
    if datetime.fromisoformat(args.deadline).tzinfo is None:
        parser.error("--deadline must include a UTC offset")
    run(args)


if __name__ == "__main__":
    main()
