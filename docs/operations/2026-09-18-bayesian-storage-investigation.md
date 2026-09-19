# Bayesian trace memory investigation

The longer source refit was killed by the kernel after sampling, before result
extraction produced a posterior checkpoint. The immutable failure review is
`data/model/chelsea-bayesian-source-long-memory-failure-20260918`: it binds the
protocol, last progress, partial-fit hashes, sampling log and two kernel OOM
records. There is no posterior to recover or interpret.

Nutpie's [official storage documentation](https://pymc-devs.github.io/nutpie/sampling-options.html)
describes experimental disk-backed Zarr traces with lazy loading. The installed
versions are PyMC 6.2.0, nutpie 0.16.11, Zarr 3.4.0, obstore 0.11.1 and xarray
2026.7.0. They were preserved with `uv run --frozen --no-sync`.

A two-chain toy PyMC model with two Normal coefficients and a HalfNormal noise
scale was sampled through both storage paths with identical seed, 80 warmup and
100 retained draws. Both posterior variables and 16 common per-draw statistics
matched exactly. This is a small storage-parity check, not full-model validation
or evidence of adequate posterior convergence.

The disk result is not a drop-in replacement in this installed version:

- Warmup groups remain despite `save_warmup=False`.
- Transformed variables and optional diagnostic arrays remain present.
- Explicit chain/draw coordinates are absent; named feature labels are present.
- Event diagnostics use different dimensions from Arrow's per-draw layout.
- Direct NetCDF export fails because root sampler metadata includes a dictionary
  that HDF5 cannot store as an attribute.

The sandbox stalled in asynchronous Zarr opening. A bounded 90-second repeat
confirmed the stack; host execution completed sampling/opening and reached the
export incompatibility. This environment issue is separate from the original
full-fit memory exhaustion.

Artifact `data/model/chelsea-bayesian-storage-pilot-20260918` preserves the exact
pilot script, output, review and publisher. The next implementation needs a
versioned adapter, strict coordinate/variable checks, metadata normalization,
chunked export, durable interrupted-state handling and a representative peak-memory
check. All retained posterior draws must be preserved. Existing accepted fit
archives and frozen samplers remain unchanged. The source and floor full fits
have not been restarted.

## Adapter implementation and measured export

`models.bayesian_disk_sampling` now preserves the raw Zarr trace separately,
checks a model-derived variable/coordinate contract and exports only retained
posterior draws plus the 16 per-draw statistics used by analysis. Raw warmup,
transformed variables and event diagnostics remain archived. Export converts
metadata to JSON text, preserves Boolean diagnostics, validates finite posterior
values and writes arrays in blocks capped at 8 MiB. It never thins draws.

A completion manifest binds every raw trace file to the experiment protocol.
Completed raw sampling can resume export without recompilation or resampling.
Incomplete sampling is preserved and rejected for automatic restart in place.
The exported posterior checkpoint allows report recovery without another fit.

The actual two-chain PyMC adapter pilot reproduced both posterior variables and
all 16 statistics exactly, including named coordinates. Recovery was tested with
both compilation and sampling replaced by functions that fail if called.
Artifact: `chelsea-disk-adapter-parity-20260918-v2`. This repeats parity and
recovery after disabling posterior array caching for report reads.

A separate synthetic trace used the long run's **4 × 6,000 × 22,158** unit shape:
4,254,336,000 logical posterior bytes. Export and exhaustive rereading verified
every value. Peak process RSS was **249,495,552 bytes (238 MiB)**; the largest
array block was 5,672,448 bytes. Creation, export and exhaustive check took 94.36
seconds. This verifies export memory behavior, not full-model sampler or report
memory. Artifact: `chelsea-disk-export-memory-20260918`.

`models.bayesian_disk_experiment` runs the unchanged v3 or v4 mathematical model
with a separately versioned execution/storage contract. It archives the original
model code alongside the disk runner/adapter/verifier and reuses the original
convergence rules. Report and source-comparison readers explicitly verify the
storage metadata and posterior/trace bindings. A storage change does not authorize
a likelihood, prior or feature change.

The actual 52,704-row graph also completed a 2-chain, 20-warmup/20-retained
integration run (`chelsea-disk-full-graph-smoke-20260918`). Its full checkpoint
and reports exist; maximum R-hat 3.10 and low BFMI correctly make it diagnostic-only.
These intentionally short chains supply no price conclusions. The later one-line
change disables caching when reopening the exported posterior; the v2 adapter
pilot verifies that final code. Export logic is unchanged from the memory proof.

The unchanged long source fit has now started under
`chelsea-bayesian-source-shared-disk-long-20260918`. Full-run sampling/export/report
memory and convergence remain to be assessed. Floor sampling and main-model
promotion remain pending; neither happens automatically.

Validation at this checkpoint: **1,530 passed, 3 skipped, 9 warnings** in the full
suite (289.09 seconds). The final cache-setting adjustment separately passed all
24 storage/runner tests and the actual v2 parity/recovery pilot. The source-only
comparator accepts the explicitly verified storage change while rejecting changes
to shared mathematical implementation or unrecognized storage policies.

The floor disk protocol is prepared in
`data/model/chelsea-floor-disk-readiness-20260918`, including the exact launch
command and source/model/graph/code bindings. It has not been launched.

## Diagnostic read-layout benchmark

The running long fit completed raw sampling and exported a 4.1 GiB posterior with
a durable checkpoint. Its diagnostics remain live but read inefficiently: the
NetCDF `unit_z` chunks have shape `(1, 32, 22158)`, while diagnostics select 512
units at a time. Each such slice decompresses chunks spanning every unit. The
installed ArviZ summary calculates several diagnostics separately, adding reads.
At 00:16 UTC the live process had read about 205 GB through its file interfaces
while resident memory remained under 1 GiB. This is a throughput problem, not
another observed memory failure; no process was stopped or restarted.

A separate synthetic benchmark uses the actual unit-axis width, four chains and
64 draws per chain (45,379,584 logical bytes). Keeping the same bounded write
slabs but storing `(1, 32, 512)` chunks preserves **every value exactly**. Two
parameter-slice read passes, with layout order reversed, take 7.66/7.65 seconds
for the current layout versus 0.177/0.177 seconds for the proposed layout:
**43.2× faster for those reads**. File sizes remain about 43.8 MB; measured write
times are 1.44 versus 1.15 seconds. Peak process RSS is 97.6 MB.

Artifact: `data/model/chelsea-posterior-chunk-benchmark-20260918`, including the
frozen script, file hashes, exact shape/seed and repeated timings. This is a
storage benchmark, not total-fit timing or a posterior convergence result. No
implementation used by the running fit was changed. After that process exits,
separate HDF5 storage chunk dimensions from bounded source-read slab dimensions,
then verify exact export/recovery parity before the next full run. The model,
priors, observations and every retained draw must remain unchanged by this fix.
