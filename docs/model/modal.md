# Modal posterior fitting

## Frontier fits on Modal

Since 2026-10-06 (Ben), frontier fits may run on a Modal GPU, **at most one launch every 144 minutes, with no daily cap** (Ben, 2026-10-07). `ops/modal-fit` takes drive.sh's arguments, runs the fit and its PSIS-LOO in one Modal container, and puts the results where a thelio fit's go:

```sh
ops/modal-fit [--gpu A100-40GB] [--dataset DIR] [--input PATH]... [--split rows] [--chain-batch N] \
  COMMIT LABEL MODEL FEATURES CHAINS WARMUP DRAWS KEEP [rentfrontier.run options...]
python3 ops/modal/cap.py                       # recent Modal launches and when the next may start
ops/team/wait-next --unit 'modal-fit-*'        # wake when it lands
```

- **Limit.** Every launch is recorded in `/data1/apartments/modal/ledger.jsonl` before its container starts, whether it later succeeds or fails. A launch less than 144 minutes after the previous one is refused (`ops/modal/cap.py`), which allows at most 10 a day. There is no daily cap. A queue script polls `python3 ops/modal/cap.py --check` before calling `ops/modal-fit`.
- **What runs.** `ops/modal-fit` starts `ops/modal/fit.py` in a `systemd-run --user` unit `modal-fit-<time>`, logging to `/data1/apartments/modal/logs/`. It ships a shallow git checkout of COMMIT, uploads only the inputs that changed since the last launch (the dataset, `/data1/apartments/external`, the frontier cache and descriptions, and a few files under `data/model/`), and runs `rentfrontier.run` then `rentfrontier.loo` in the container. The fit alone is capped at 2 h (30 min for an exploration fit, chosen as in drive.sh), the container at 3 h.
- **Results.** The run directory lands in `FRONTIER_OUTPUT_ROOT/runs/<name>`, with the container log and `modal.json` (GPU, stage times, list-price estimate) under `modal/`, and the LOO directory in `FRONTIER_OUTPUT_ROOT/loo/`. Both are then deleted from the Volume. The variance decomposition of a full fit is light work; run it on thelio from a checkout of COMMIT as drive.sh does (`JAX_PLATFORMS=cpu uv run python -m rentfrontier.variance NAME`).
- **Fit time.** A Modal fit's time is not comparable with a thelio fit's: the served design took 822 s on an A100-40GB against 6,578 s on the RTX 2060 SUPER. `result.json` records the GPU under `hardware`.
- **Cleanup.** Inputs and code stay on Volume `apartments-modal-fits` between fits. `apartments-modal-cleanup.timer` checks hourly and deletes the Volume once 24 h have passed since the last launch returned and no fit app is running; the next launch uploads everything again (about 450 MB).

### Choosing a GPU

The sampler runs in float64, so the GPU's float64 throughput sets the speed. A100-40GB is the default. On 2026-10-06 the served design (94,453 rows, 2 chains, 300 warmup and 3,600 draws) ran:

| GPU | fit | PSIS-LOO | billed |
|---|---|---|---|
| A100-40GB | 822 to 919 s (warmup 288 to 364, sampling 516 to 546) | 139 s, 106,764.6 ± 334 | $0.72 for the fit alone; $0.80 for a 1,188 s rerun against a $0.79 estimate |
| L4 (300 warmup, 180 draws) | warmup 518 s | | |
| RTX 2060 SUPER (thelio) | 6,578 s | 141 s | |

The A100 reproduced thelio's diagnostics and PSIS-LOO exactly (R-hat 1.00529, minimum ESS 469.07, held-out ELPD 13,139.0, PSIS-LOO 106,764.6 ± 334). PSIS-LOO gains nothing from the A100 (139 s against 141 s) but costs only about $0.09 inside the fit's container, so it stays there. Prices are in `ops/modal/app.py`, from [modal.com/pricing](https://modal.com/pricing).

### Setup

```sh
uv venv --python 3.12 /data1/apartments/venvs/modal && VIRTUAL_ENV=/data1/apartments/venvs/modal uv pip install modal==1.6.1
/data1/apartments/venvs/modal/bin/modal setup          # once; writes ~/.modal.toml
cp ops/systemd/apartments-modal-cleanup.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now apartments-modal-cleanup.timer
```

## Root-project fits

A full-length remote refit of the product-scope spline model ran in 55.4 minutes against about 56 locally, reproduced the local protocol hash, and was billed $0.38 ([September 23 record](../analysis/modal-remote-fitting-2026-09-23.md)). One Modal core samples at local speed and the disk sampler uses at most four, so Modal helps only to run several fits at once or to keep load off the local machine.

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
