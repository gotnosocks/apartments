# Modal posterior fitting

**Fits run locally by default; Modal is opt-in.** A full-length remote refit of the product-scope spline model ran in 55.4 minutes against about 56 locally, reproduced the local protocol hash, and was billed $0.38 ([September 23 record](../analysis/modal-remote-fitting-2026-09-23.md)). One Modal core samples at local speed and the disk sampler uses at most four, so Modal helps only to run several fits at once or to keep load off the local machine.

```sh
# Main model through the CLI: same runner, same options, same protocol hash as a local run.
uv run --locked --extra model --extra modal apartments fit-pricing DATASET OUTPUT --executor modal [--modal-detach]
# Other protocol runners (e.g. structure or bedroom-time experiments):
uv run --locked --extra model --extra modal python -m models.modal_remote_fit run --detach \
  --runner models.<runner> --dataset DATASET --output OUTPUT -- <runner options>
```

`--executor modal` passes every `fit-pricing` option explicitly to the runner, because `fit-pricing` defaults differ from the runners' own; it supports only `--execution disk`. `--modal-cpu`, `--modal-memory`, `--modal-timeout`, `--modal-full` and `--modal-detach` are refused for local runs. Downloads leave `posterior.nc`/`prior.nc` on the Modal Volume unless `--modal-full` is given; run `python -m models.modal_remote_fit complete --output OUTPUT` before promoting a fit or opening it on the main page. Local runs never import Modal or need `--extra modal`. Code is sent with `git ls-files`, so run from a git checkout (jj-only workspaces are not supported yet).

The rest of this page describes the earlier `models/modal_fit.py` workflow for the legacy monthly model.

This document describes the earlier optional Modal workflow. Current Chelsea research also runs locally; the September 18 backend reassessment uses the full current model on the Ryzen CPU and RTX 2060 SUPER. The Modal worker defaults to **Nutpie/Numba on four cloud CPU cores**. `--gpu` selects **Nutpie/JAX on one T4** through a separately registered ephemeral app. Default CPU runs never build the CUDA image; GPU registration and image building happen only when requested. The rent model's priors, likelihoods, exclusions and historical attribute assumptions are unchanged.

The old 2,386-observation execution checks recorded about 110 seconds on T4 versus 12.5 seconds for an earlier local M1/Numba run, with two chains of only 50 warmup and 50 retained draws. **These timings do not establish relative sampling speed or justify a CPU/GPU choice.** Startup and compilation can dominate, and the hardware differs. A meaningful comparison requires the same current posterior, production-length chains, separate warmup/retained/postprocessing costs, convergence checks and bulk/tail effective samples per second. See the [current reassessment](../analysis/chelsea-sampler-reassessment-2026-09-18.md).

## Run from the prepared cloud snapshot

Install the Modal client using the project's `modal` extra, then authenticate once with `uv run --locked --extra modal modal setup`. The [remote archive processing workflow](../data/modal-processing.md) writes `training_data.parquet` and `metadata.json` to Volume `chelsea-archive`, under `/snapshots/{snapshot}/prepared/`.

```sh
# Cloud CPU is the cost-conscious default.
uv run --locked --extra modal modal run models/modal_fit.py --snapshot chelsea-20260908 --draws 1000 --tune 1000 --chains 4

# Optional CUDA/Nutpie experiment; otherwise identical model.
uv run --locked --extra modal modal run models/modal_fit.py --snapshot chelsea-20260908 --gpu --draws 1000 --tune 1000 --chains 4

# Small remote execution test, optionally streaming results for local browsing.
uv run --locked --extra modal modal run models/modal_fit.py --snapshot chelsea-20260908 --draws 20 --tune 20 --chains 2 --output data/model/modal/cloud-smoke
```

Results persist in Volume `/fits/{run_id}/`; each run gets a unique ID unless `--run-id` is supplied. Existing IDs and local output directories are rejected. The worker reads prepared inputs directly from the Volume, validates their digest and retains snapshot provenance. There is no cloud-to-laptop-to-cloud data processing step. The laptop does not import pandas, parse parquet, build models, or load posterior arrays. Optional downloads use bounded chunks.

The fit image includes only the two model Python files and pinned scientific dependencies. It does not upload the project directory, archive, credentials or logs. The mounted Volume already contains the archive; the fitting function reads only its selected prepared inputs and writes its own fit directory. It does not import or modify the archive database.

Returned NetCDF, parquet tables and metadata use the analysis app's existing format; the production monthly fit is never replaced automatically. `input.parquet`, input/model hashes, source preparation metadata, sampler settings, dependency versions, timing and diagnostics accompany the result. `environment.txt` records resolved packages. Source unit labels are not necessarily resolved physical unit identities; inspect the preparation quality flags before interpreting a fit.

## Limits and backend details

Both workers cap CPU at four cores and host memory at 8 GiB. Each function allows one container at a time, has a 30-minute timeout, and does not automatically retry failures. `modal run` ends its ephemeral app afterward; there is no idle endpoint. Interrupting the attached command stops the app. GPU execution uses an attached nested app: do not rely on outer `modal run --detach` to keep that GPU job alive after the local command disconnects. Keep the GPU command connected until it returns. For a larger fit, review and explicitly increase the timeout instead of silently retrying.

As checked September 8, 2026, [Nutpie supports JAX GPU compilation](https://pymc-devs.github.io/nutpie/pymc-usage.html). PyMC 6.2 accepts `pm.sample(nuts_sampler='nutpie', backend='jax')`; the older nested `nuts_sampler_kwargs` syntax is deprecated. The CPU image pins PyMC 6.2.0, Nutpie 0.16.11 and PyTensor 3.2.3. The optional GPU image adds JAX 0.11.1 with [the recommended pip CUDA 13 wheels](https://docs.jax.dev/en/latest/installation.html). This combination successfully ran on a Modal T4. GPU runs fail if CUDA or float64 is unavailable. PyTensor constructs gradients, and JAX compiles and executes those gradients on the GPU. The local `fit_model` API also exposes `gradient_backend` for future controlled experiments; an interrupted JAX-autodiff comparison did not establish a benefit, so the tested default remains PyTensor gradients.

Both backends use float64. Cheap GPUs have limited float64 throughput and transfer/dispatch overhead, so GPU speedups are not assumed. Compare effective samples per second and per dollar, convergence and total elapsed time on identical workloads. Short smoke diagnostics are not reliable convergence estimates.

[Modal rates](https://modal.com/pricing) were $0.000164/T4-second, $0.0000131/CPU-core-second and $0.00000222/GiB-second. At the requested limits, 30 minutes of worker compute is approximately $0.13 CPU-only or $0.43 with T4, excluding startup, builds, storage and transfer. The completed T4 smoke estimated $0.027 worker compute. A job's metadata records its own runtime and estimate; these are estimates, not billing records.
