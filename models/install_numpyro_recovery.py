"""Install a verified CPU-converted posterior for the completed GPU benchmark."""

import argparse
import fcntl
import json
from pathlib import Path
import shutil
import time

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest


def install(benchmark, recovery):
    benchmark, recovery = map(Path, (benchmark, recovery))
    with (benchmark / ".recovery-install.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _, files = _verified_bundle(
            recovery / "validation", retain={"recovery.json", "raw-inventory.json"}
        )
        _, protocol = _verified_bundle(benchmark / "protocol", retain={"settings.json"})
        record = json.loads(files["recovery.json"])
        settings = json.loads(protocol["settings.json"])
        if (
            record["benchmark"] != str(benchmark.resolve())
            or record["settings"] != settings
            or record["new_draws_generated"] != 0
            or not record["original_raw_files_unchanged"]
            or record["conversion"]["chains"] != settings["chains"]
            or record["conversion"]["draws"] != settings["draws_per_chain"]
            or record["sampling_progress"]
            != json.loads((benchmark / "progress.json").read_text())
            or record["posterior_sha256"] != digest(recovery / "posterior.nc")
        ):
            raise ValueError(
                "Recovery source, dimensions, progress or posterior differs"
            )
        inventory = {
            p.name: digest(p)
            for p in sorted((benchmark / "unconstrained-trace").glob("*.npy"))
        }
        if inventory != json.loads(files["raw-inventory.json"]):
            raise ValueError("Original raw draws differ from verified recovery")
        destination = benchmark / "posterior.nc"
        if any(
            p.exists()
            for p in (
                destination,
                benchmark / "posterior.partial",
                benchmark / "sampled.json",
            )
        ):
            raise ValueError(
                "Existing posterior/completion products must not be overwritten"
            )
        start = time.perf_counter()
        shutil.copyfile(recovery / "posterior.nc", benchmark / "posterior.partial")
        if digest(benchmark / "posterior.partial") != record["posterior_sha256"]:
            raise ValueError("Installed posterior differs")
        (benchmark / "posterior.partial").replace(destination)
        timings = {
            k: v
            for k, v in record["sampling_progress"].items()
            if k.endswith("_seconds") or k == "retained_batches"
        }
        timings["recovery_transform_and_write_seconds"] = record[
            "recovery_transform_and_write_seconds"
        ]
        timings["recovery_install_seconds"] = time.perf_counter() - start
        completed = {
            "settings": settings,
            "timings": timings,
            "sample_statistics": {
                k: record["conversion"][k]
                for k in (
                    "divergences",
                    "mean_n_steps",
                    "max_n_steps",
                    "max_tree_depth",
                )
            },
            "posterior_sha256": record["posterior_sha256"],
            "status": "sampled_diagnostics_and_ess_comparison_pending",
            "pymc_call_completed": False,
            "postprocessing_recovery": {
                "directory": str(recovery.resolve()),
                "manifest_sha256": digest(recovery / "validation/complete.json"),
                "reason": "All 6000 retained draws per chain were spilled before PyMC attempted GPU allocation during scan postprocessing. The exact PyMC transform was recovered in CPU batches; no resampling.",
            },
        }
        temporary = benchmark / "sampled.json.partial"
        temporary.write_text(canonical(completed) + "\n")
        temporary.replace(benchmark / "sampled.json")
        print(canonical(completed), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("benchmark", "recovery"):
        parser.add_argument("--" + name, type=Path, required=True)
    install(**vars(parser.parse_args()))
