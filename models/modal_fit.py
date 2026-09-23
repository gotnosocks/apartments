"""Batch posterior fitting on Modal; local entrypoint only submits/downloads files."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time

import modal

MODEL_FILE = Path(__file__).with_name("rent_model.py")
PACKAGES = [
    "pymc==6.2.0",
    "pytensor==3.2.3",
    "nutpie==0.16.11",
    "arviz==1.2.0",
    "numpy==2.4.6",
    "pandas==3.0.5",
    "pyarrow==24.0.0",
    "h5netcdf==1.8.1",
    "h5py==3.16.0",
    "duckdb==1.5.5",
    "scipy==1.18.0",
]
base_image = modal.Image.debian_slim(python_version="3.12").pip_install(*PACKAGES)


def add_source(image):
    return image.add_local_file(MODEL_FILE, "/root/rent_model.py").add_local_file(
        Path(__file__), "/root/modal_fit.py"
    )


cpu_image = add_source(
    base_image.env(
        {
            "PYTENSOR_FLAGS": "floatX=float64,cxx=",
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
        }
    )
)
gpu_image = add_source(
    base_image.pip_install("jax[cuda13]==0.11.1").env(
        {
            "JAX_ENABLE_X64": "true",
            "JAX_PLATFORMS": "cuda",
            "XLA_PYTHON_CLIENT_PREALLOCATE": "false",
            "PYTENSOR_FLAGS": "floatX=float64,cxx=",
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
        }
    )
)
app = modal.App("chelsea-nutpie-fit")
volume = modal.Volume.from_name("chelsea-archive", create_if_missing=True)


def safe_id(value):
    import re

    if not re.fullmatch(r"[a-zA-Z0-9_-]+", value):
        raise ValueError("IDs may contain letters, digits, dash and underscore only")
    return value


def validate_settings(draws, tune, chains):
    if not (20 <= draws <= 10000 and 20 <= tune <= 10000 and 2 <= chains <= 8):
        raise ValueError("Require 20–10000 draws/tune and 2–8 chains")


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def run_fit(snapshot, run_id, settings, backend):
    """Executed only inside the bounded Modal worker, including all preparation reads."""
    import importlib.metadata
    import shutil
    import sys
    import tempfile
    from datetime import datetime, timezone
    import pandas as pd

    sys.path.insert(0, "/root")
    from rent_model import fit_model, save_outputs

    validate_settings(settings["draws"], settings["tune"], settings["chains"])
    source = Path("/archive/snapshots") / safe_id(snapshot) / "prepared"
    destination = Path("/archive/fits") / safe_id(run_id)
    volume.reload()
    if destination.exists():
        raise ValueError("Fit ID already exists; outputs are never overwritten")
    metadata = json.loads((source / "metadata.json").read_text())
    frequency = metadata["frequency"]
    if frequency not in ("monthly", "weekly"):
        raise ValueError("Unsupported frequency")
    input_digest = digest(source / "training_data.parquet")
    expected = metadata.get("snapshot", {}).get("training_sha256")
    if expected and expected != input_digest:
        raise ValueError("Prepared snapshot digest mismatch")
    settings = {**settings, "frequency": frequency}
    devices = ["CPU"]
    versions = ["pymc", "pytensor", "nutpie", "numpy", "arviz"]
    if backend == "jax":
        import jax

        if jax.default_backend() != "gpu" or not jax.config.x64_enabled:
            raise RuntimeError("GPU fitting requires an actual CUDA GPU and float64")
        devices = [str(device) for device in jax.devices()]
        versions += ["jax", "jaxlib"]
    started = time.monotonic()
    print(
        json.dumps({"devices": devices, "backend": backend, "snapshot": snapshot}),
        flush=True,
    )
    data = pd.read_parquet(source / "training_data.parquet")
    for key in ("coverage", "excluded_furnished_units", "size_log_scale"):
        data.attrs.setdefault(key, metadata[key])
    data.attrs.setdefault("names", metadata["buildings"])
    periods = pd.date_range(
        data.period.min(),
        data.period.max(),
        freq="MS" if frequency == "monthly" else "W-MON",
    )
    # Keep PyTensor's tested gradient construction; JAX still executes the graph on GPU.
    inference = fit_model(data, periods, **settings, backend=backend)
    sampling_seconds = time.monotonic() - started
    with tempfile.TemporaryDirectory() as folder:
        output = Path(folder)
        save_outputs(inference, data, periods, frequency, output)
        result = json.loads((output / "metadata.json").read_text())
        elapsed = time.monotonic() - started
        result["execution"] = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "snapshot": snapshot,
            "run_id": run_id,
            "input_sha256": input_digest,
            "model_sha256": digest(MODEL_FILE),
            "source_metadata_sha256": digest(source / "metadata.json"),
            "input_snapshot_metadata": metadata.get("snapshot", {}),
            "sampler": "nutpie",
            "backend": backend,
            "gradient_backend": "pytensor",
            "float_precision": 64,
            "devices": devices,
            "settings": settings,
            "sampling_compile_seconds": sampling_seconds,
            "worker_seconds": elapsed,
            "min_ess_bulk_per_sampling_second": result["min_ess_bulk"]
            / sampling_seconds,
            "estimated_worker_compute_usd": elapsed
            * (4 * 0.0000131 + 8 * 0.00000222 + (0.000164 if backend == "jax" else 0)),
            "cost_note": "Estimate at 2026-09-08 rates; excludes startup, build, storage and transfer.",
            "versions": {name: importlib.metadata.version(name) for name in versions},
        }
        (output / "metadata.json").write_text(json.dumps(result, indent=2))
        shutil.copyfile(source / "training_data.parquet", output / "input.parquet")
        (output / "environment.txt").write_text(
            "\n".join(
                sorted(
                    f"{dist.metadata['Name']}=={dist.version}"
                    for dist in importlib.metadata.distributions()
                )
            )
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(output, destination)
        volume.commit()
    return {
        "volume": "chelsea-archive",
        "path": str(destination.relative_to("/archive")),
        "files": sorted(path.name for path in destination.iterdir()),
        "execution": result["execution"],
        "max_rhat": result["max_rhat"],
        "min_ess_bulk": result["min_ess_bulk"],
        "divergences": result["divergences"],
    }


@app.function(
    image=cpu_image,
    cpu=(4, 4),
    memory=(8192, 8192),
    timeout=1800,
    max_containers=1,
    retries=0,
    volumes={"/archive": volume},
    include_source=False,
)
def fit_cpu(snapshot: str, run_id: str, settings: dict):
    return run_fit(snapshot, run_id, settings, "numba")


def fit_gpu(snapshot: str, run_id: str, settings: dict):
    return run_fit(snapshot, run_id, settings, "jax")


def run_gpu(snapshot, run_id, settings):
    # Register a separate ephemeral app only when explicitly requested.
    # Constructing an Image object does not build it; the CPU app never owns it.
    gpu_app = modal.App("chelsea-nutpie-fit-gpu")
    worker = gpu_app.function(
        image=gpu_image,
        gpu="T4",
        cpu=(4, 4),
        memory=(8192, 8192),
        timeout=1800,
        max_containers=1,
        retries=0,
        volumes={"/archive": volume},
        include_source=False,
    )(fit_gpu)
    with gpu_app.run():
        return worker.remote(snapshot, run_id, settings)


@app.local_entrypoint()
def main(
    snapshot: str = "chelsea-20260908",
    run_id: str = "",
    gpu: bool = False,
    output: str = "",
    draws: int = 1000,
    tune: int = 1000,
    chains: int = 4,
):
    """Submit a prepared Volume snapshot; optionally stream outputs to a new directory."""
    from datetime import datetime, timezone

    validate_settings(draws, tune, chains)
    safe_id(snapshot)
    run_id = safe_id(run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    destination = Path(output) if output else None
    if destination and destination.exists():
        raise ValueError(
            "Output must be a new directory; existing fits are never overwritten"
        )
    settings = dict(draws=draws, tune=tune, chains=chains)
    result = (
        run_gpu(snapshot, run_id, settings)
        if gpu
        else fit_cpu.remote(snapshot, run_id, settings)
    )
    if destination:
        destination.mkdir(parents=True, exist_ok=False)
        for name in result["files"]:
            if Path(name).name != name:
                raise ValueError("Unexpected artifact path")
            with (destination / name).open("wb") as stream:
                for chunk in volume.read_file("/" + result["path"] + "/" + name):
                    stream.write(chunk)
    print(json.dumps(result, indent=2))
