# Remote PyMC fitting on Modal

September 22–23, 2026. This covers the content-addressed remote fit workflow, a full-length remote refit of the product-scope spline model, and CPU/GPU sampler measurements. The local checkout stays primary; Modal is a scratch worker plus a cache Volume.

**Result.** A full-length remote refit of the product-scope spline model reproduced the local protocol exactly (protocol SHA-256 `336d9d096f40…`), ran in 55.4 minutes (local: about 56), was billed $0.38, and downloaded in full (4.39 GB) in 141 s. Coefficients and floor contrasts agree with the local fit within Monte Carlo error. The remote chains narrowly missed the R-hat gate (1.0103 on `alpha`, against 1.01), which the local run passed at 1.0036. That is run-to-run variation at 6,000 draws per chain, not a remote-execution difference.

**Recommendation.** Keep nutpie/Numba on CPU for this model. Use Modal to run several fits concurrently, which also avoids loading the 15 GB local machine, at about $0.32 per worker hour for 4 cores and 16 GiB. GPU sampling was slower for this model (see below), and float32 sampling failed.

## Workflow

```sh
# From any checkout; --code-root chooses whose src/models/config and uv.lock are sent.
uv run --locked --extra model --extra modal python -m models.modal_remote_fit run --detach \
  --code-root /home/ben/code/apartments \
  --dataset /home/ben/code/apartments/data/model/chelsea-product-scope-analysis-20260921 \
  --output /home/ben/code/apartments/data/model/modal-runs/<name> -- --seed 20260924
uv run --locked --extra model --extra modal python -m models.modal_remote_fit list
uv run --locked --extra model --extra modal python -m models.modal_remote_fit fetch --run-id <id> --output <dir>
uv run --locked --extra model --extra modal python -m models.modal_remote_fit complete --output <dir>
uv run --locked --extra model --extra modal python -m models.modal_remote_fit clean --run-id <id>
```

- **Upload.** Code (`git ls-files` of `src`, `models`, `config`, `pyproject.toml`, `uv.lock`, including uncommitted edits) and every file under `--dataset`/`--input` go to Volume `apartments-fit-work` as SHA-256-named blobs. Only blobs the Volume lacks are sent. `--add-code` adds new files from another checkout without touching the code root.
- **Worker.** The image is built from the code root's `uv.lock` (`uv sync --extra model`), plus build tools. `--gpu` or `--jax` adds a pinned JAX/NumPyro/BlackJAX layer that is not in the lock. The worker rebuilds the dataset **at its original absolute path**, because protocols record `source_directory`. It then runs the unchanged runner with single-threaded BLAS (`OPENBLAS_NUM_THREADS=1` etc.; see below) and copies selected products to the Volume.
- **Download.** By default everything returned except `fit/posterior.nc` and `fit/prior.nc` (about 50 MB for a full fit). Each file is checked against the worker's inventory and every bundle's `complete.json` before `<dir>.partial` is renamed. A `remote-omitted.json` marker lists the files left remote, so `_verified_bundle`, `BayesianAnalysis` and promotion refuse the directory until `complete` fetches and verifies them. `--full` downloads everything at once. `trace/` and `report-cache/` stay remote unless `--keep-auxiliary` is given.
- **Detach.** Use `--detach` for anything long. An attached client that disconnects (for example the local machine rebooting) stops the Modal app.
- **Cleanup.** `clean --run-id` deletes a run's remote copy; `clean --unreferenced-blobs` prunes blobs no remaining run needs. Fetches record local copies on the Volume (`local-copies.json`), and `clean` refuses a run that was never downloaded, or whose posterior exists only remotely, unless `--discard-remote-draws` is given.

Who needs the draws: the main page (`BayesianAnalysis`), source-review regeneration, `bayesian_feature_checks*.load_draws`, and anything that calls `_verified_bundle` on `fit/`, such as main-analysis selection and promotion. Screens and summary-based comparisons do not (confirmed with the model-improvement session). Fetch the complete bundle only for promotion candidates.

## Transfer and reproducibility

| Measurement | Result |
|---|---|
| Cold upload, code + 276 MB dataset | 281 blobs, 290.7 MB in 12 s |
| Unchanged resubmit | 0 bytes |
| One edited source file | 10.8 KB |
| Switching code root to another checkout | 27 files, 410 KB |
| Worker dataset rebuild from the Volume | 43 s (about 7 MB/s) |
| Smoke fit download (62 files) | 116 MB in 25 s |
| Worker image build (first time, cached afterwards) | 17 s |

A 100 + 100 draw smoke fit reproduced the local product-scope protocol exactly except for `draws`, `tune` and `seed`. The 30 archived implementation hashes and `source_directory` were identical, and `time-design.json`, `time-design.npz`, `feature-design.json`, `graph-configuration.json` and `compression.json` were byte-identical to the local fit's. One Modal core sampled at 2.34 ms per gradient, against 2.15 ms locally.

**BLAS threading.** `verify_design` rejects both the local and the remote fit (`time-design.json`) unless BLAS is single-threaded **before Python starts**. An in-process `threadpool_limits(1)` alone was not enough in a standalone script. The worker sets the environment variables for every runner. Local checks should too.

## Full-length remote refit

Run `20260923T051342Z-spline-full`: `models.bayesian_floor_spline_experiment` on
`chelsea-product-scope-analysis-20260921`, 4 chains × (4,000 warmup + 6,000 draws), seed 20260924, 4 Modal cores and
16 GiB. Local copy: `data/model/modal-runs/spline-full-20260923` (complete bundle, including `posterior.nc`).
Reference: the local fit `chelsea-bayesian-product-scope-spline-disk-20260921`.

| Phase | Remote | Local reference |
|---|---|---|
| Upload | 0 bytes (all blobs cached) | — |
| Dataset rebuild on worker | 6 s | — |
| Runner (compile, sampling, export, reports) | 55.4 min | about 56 min |
| Persist to Volume | 8 s | — |
| Download, complete bundle | 4.39 GB in 141 s (31 MB/s) | — |
| Billed | $0.38 (worker estimate $0.29) | — |

- **Identity.** The protocol SHA-256 equals the local fit's, and all 30 hashed Python files are excluded from ruff formatting in `ruff.toml`. Design reconstruction (`verify_design`, single-threaded BLAS) passes.
- **Agreement.** Across 47 coefficients, posterior medians differ from the local fit by at most 0.083 posterior SD (median 0.013). Across 55 floor contrasts, at most 0.072 SD. Draws are not bit-identical: floating-point differences between machines send chains down different paths from the same seed.
- **Diagnostics.** Floor-contrast and derived-contribution gates pass. The parameter gate fails narrowly: max R-hat 1.0103 on `alpha` and 1.0100 on `beta[elevator.unknown]` (2 parameters above 1.01), minimum bulk ESS 635; the local run had R-hat 1.0036 and minimum bulk ESS 894. No divergences, no tree-depth saturation, minimum BFMI 0.44. Status is therefore `diagnostic_only_do_not_interpret_intervals`, and `BayesianAnalysis` correctly refuses to load it. The slow-mixing intercept makes 6,000 draws per chain marginal for the 1.01 gate. That is a model/protocol question for the model-improvement work, not a Modal defect.
- **Still open.** Loading a converged Modal-produced bundle in `BayesianAnalysis`. It needs a run that passes the gates, for example another seed or more draws.

## Sampler and hardware measurements

Gradient probe (`models/sampler_hardware_probe.py`; `data/model/modal-runs/probe*-2026092*`). Seconds per logp+gradient, per chain, float64:

| Hardware | 1 chain | 16 chains | 64 chains | 256 chains | $/hour |
|---|---|---|---|---|---|
| Modal CPU core, Numba | 2.6 ms | — | — | — | 0.047 per core |
| L4 | ~29 ms | 0.095 ms | 0.074 ms | 0.087 ms | 0.80 |
| A100-80GB | ~38 ms | 0.062 ms | 0.029 ms | 0.025 ms | 2.50 |
| H100 | ~31 ms | 0.040 ms | 0.015 ms | 0.010 ms | 3.95 |

- JAX float64 on GPU matches Numba to 6e-14 relative in log density and 2e-13 in gradient.
- float32 differs from float64 by 5e-7 relative in log density and 7e-4 in scaled gradient, and is 2–3× faster on the L4.
- On a 16-core CPU container, aggregate Numba throughput stopped growing at about two chains' worth (4 processes: 2× slowdown each; 16: 12.8×). That is likely memory bandwidth on a shared host. The 4-core fits showed no such slowdown.
- The ~30 ms single-chain GPU cost comes from JAX autodiff of this graph. nutpie's JAX backend with PyTensor-built gradients ran at about 4 ms per step per chain on the L4 (30-draw canary).

Sampling trials (`models/jax_sampling_trial.py`; L4, NumPyro, 4 vectorized chains, 300 warmup + 100 draws):

| | float64 | float32 |
|---|---|---|
| Leapfrog steps per iteration | 511 on every iteration | 1,023 on every iteration (maximum) |
| Divergences | 0 | 0 |
| Max R-hat | 1.11 | infinite |
| Bulk ESS, median / minimum | 922 / 38 | 4 / 4 |
| Sampling time | 637 s | 247 s |

NumPyro's window adaptation needs 6–10× more gradients per draw than nutpie (about 50–90). So a full-length NumPyro fit would take about 4.4 h on the L4, against about 22 min of CPU sampling. float32 chains did not move at all. The PyMC developers' June 2026 advice is nutpie, including its JAX backend for GPUs; it evaluates chains one at a time, which is exactly the slow single-chain case here. Follow-ups are in the [research backlog](../model/research-backlog.md#remote-fit-execution).

## Costs and lessons

Billed from 2026-09-22 to the time of writing: $14.53, of which about $10 was lost to failed GPU trials. Modal bills whole container lifetime, about 20% above the worker's own timer. Rates checked with `modal billing rates`: CPU $0.0473/core-h, memory $0.008/GiB-h, L4 $0.80/h, A100-80GB $2.50/h, H100 $3.95/h, Volumes $0.09/GiB-month with 1 TiB free.

- About $10 was lost to GPU trials that sampled and then crashed in untested summary code. Trials now save results after each stage. Launches go through a local toy-model test and a cheap canary first.
- A GPU container that runs CPU diagnostics keeps billing for the idle GPU. Split sampling and diagnostics before running long GPU jobs.
- Explicit ephemeral disk must be at least 512 GiB and is billed as memory at 1 GiB per 20 GiB of disk. The default disk is free and was enough; a ramdisk would add about 40% to a fit's cost.
- PyMC's `get_jaxified_logp(negative_logp=False)` returns the **negative** log density, and PyMC 6.2's `pm.sample(nuts_sampler_kwargs=...)` passes kwargs to NumPyro's kernel, not `sample_jax_nuts`. Call `pymc.sampling.jax.sample_jax_nuts` directly.
- Concurrent submissions can race on uploading the same new blob. Blob uploads therefore overwrite, which is safe because names are content hashes.
