# Current-model sampler reassessment

**The fastest configuration is not established yet.** The previous two-chain
50-warmup/50-draw M1-versus-T4 comparison is execution evidence only. It is too
short and mixes hardware; its elapsed-time ratio must not select a backend.

The current workload has 52,863 observations, 22,189 units, 1,131 buildings and
23,462 unconstrained parameters. It uses the exact PyMC floor-increment model,
shared Student-t residual scale and unchanged priors. The comparison target is
four chains with 4,000 warmup and 6,000 retained draws each, target acceptance
0.93 and diagonal mass matrices. No surrogate model is used.

Hardware: Ryzen 5 3600X (six physical cores), RTX 2060 SUPER (8 GiB), driver
595.91.07. The isolated `.venv-sampler-benchmark` retains PyMC 6.2.0, PyTensor
3.2.3, nutpie 0.16.11 and NumPy 2.4.6, and adds JAX/JAXlib 0.11.1, CUDA 13 wheels,
NumPyro 0.22.0 and BlackJAX 1.6.2. Production dependencies are unchanged.

## Compatibility and execution findings

- Full-model Numba CPU versus JAX GPU float64 log-density/gradient parity passes
  at three parameter points. Maximum absolute differences are 3.49e-10 in log
  density and 7.75e-10 across the gradient. Artifact:
  `data/model/chelsea-gpu-full-model-preflight-20260918`.
- Warm kernel medians in that preflight are 2.15 ms CPU versus 21.93 ms GPU.
  CPU separately evaluates log density and gradient; GPU uses a fused autodiff
  function with resident inputs and explicit synchronization. These are kernel
  diagnostics, **not a matched sampling benchmark or an ESS/sec comparison**.
- The current nutpie/Numba run reports all four chains finished 4,000+6,000
  iterations, with zero reported divergences, in 1,150–1,184 seconds per chain.
  Its synchronous Zarr reader then stalled in the sandbox. The same archive
  opens immediately on the host and validates four-by-6,000 retained shapes,
  coordinates and warmup exclusion. Recovery preserves existing draws; this
  reader delay must not be charged to sampling throughput. Independent bounded
  export and unchanged-inventory checks subsequently passed for all 24,000
  retained draws. The stalled reader was interrupted only after that recovery
  succeeded; the verified checkpoint was installed under its exclusive lock.
  The unchanged command completed diagnostics/reporting on the host. All
  parameter, derived-contribution and joint-floor diagnostic gates pass.
- An eight-minute interior retained window (02:44:24–02:52:24 UTC) contains
  **17,757 draws across four chains in 480.066 seconds: 36.99 aggregate draws/sec,
  or 9.25 per chain**. Each chain contributes 4,425–4,450 retained draws to this
  window. Startup, warmup and final export are excluded; ordinary raw trace
  writes are included. This is a useful long-window raw-throughput baseline,
  not ESS/sec or evidence that nutpie is fastest. The counters and calculation
  are archived in `data/model/chelsea-nutpie-steady-throughput-20260918`.
- The timestamped callbacks also bracket the **shared retained wall interval
  at 600.08–705.71 seconds**: earliest chain warmup completion to last chain
  sampling completion. This includes overlapping warmup in slower chains and
  raw trace writes. It excludes initial compilation and final export. Unlike
  per-chain runtime sums, this is a denominator for pooled four-chain ESS.
  The minimum bulk ESS/sec across parameters is **1.28–1.51**; across derived
  unit/bathroom contributions **1.76–2.07**; across joint floor contrasts
  **2.54–2.99**. These ranges reflect callback timing resolution, not statistical
  confidence intervals. All parameter rates, bulk/tail diagnostics, callback
  evidence and fit bindings are archived in
  `data/model/chelsea-nutpie-wall-efficiency-20260919`. Reproduction script:
  `docs/analysis/scripts/measure_current_cpu_efficiency.py`.
- The first production NumPyro/GPU attempt exhausted GPU memory before a usable
  warmup completed. NumPyro 0.22 allocates `num_samples` collection slots during
  `warmup(collect_warmup=False)`. The original trace allocation was too large for
  this card. Its failed protocol/log remain preserved.
- The revised runner allocates one unused warmup slot, retains samples in
  500-draw batches, and writes each batch to host memory-mapped files. The exact
  adapted chain state and RNG continue between batches. There is no thinning,
  new warmup or discarded retained draw. A lifecycle test verifies all draws
  and sampler statistics match the unbatched continuation, including a final
  partial batch. These tiny tests establish correctness, not performance.
- GPU warmup completed in **2,839.77 seconds including initialization/JIT**.
  All **6,000 retained draws per chain** finished at 04:50:07 UTC on September 19:
  **1,919.65 seconds** retained compute including first-loop JIT, plus **8.30 seconds**
  transfers/storage, or **1,927.94 seconds** together. This is **12.45 aggregate
  raw draws/sec**. All retained iterations used 127 leapfrog steps; no divergences
  were recorded. ESS and convergence checks remain necessary before choosing a
  backend; raw throughput alone is insufficient.
- PyMC 6.2 then failed during posterior conversion: its scan postprocessor calls
  `jnp.swapaxes` on the default GPU before moving arrays to the requested CPU.
  The attempted 3.97-GiB allocation failed. This occurred **after every retained
  sample/statistic leaf was flushed**, so the production chains were not rerun.
  The original terminal log is preserved as `postprocessing-failure.log` in the
  benchmark directory.
- `models/recover_numpyro_trace.py` reconstructs the archived spill pytree using
  the exact model's value-variable ordering and JAX dictionary ordering. It checks
  all leaf shapes, positive retained step counts, finite values, and potential
  energy at the first/middle/final retained positions in all four chains. Maximum
  potential-energy discrepancy is **7.28e-12**. It applies PyMC's exact constrained
  transform on CPU in 64-draw batches and verifies every output write by reading
  it back. All 24,000 draws were recovered; raw file hashes are unchanged.
  Conversion/transform compilation/write time was **133.06 seconds**, separately
  from sampling; installation was **13.13 seconds**. Neither includes all recovery
  preparation or human investigation time. No successful end-to-end PyMC-call
  timing is claimed for this run.
  Recovery artifact: `data/model/chelsea-numpyro-cpu-conversion-recovery-20260919`.
  Its posterior SHA is `bb8bbaa29166d3a0863976c541535c4b7a7e701453dc55407186595d1fc7d16a`.
  Tiny correctness tests reproduce native PyMC posterior variables, coordinates
  and every sampler statistic; they are not speed benchmarks.

## Timing and decision rules

`models/numpyro_sampling_benchmark.py` reports warmup including initialization/JIT,
retained sampling including its loop JIT, transfer/storage, PyMC postprocessing,
and posterior writing separately. The retained loop is reused across batches.
The frozen protocol records data/code hashes, float64, devices, chain scheduling,
priors, seed, versions and batch size. GPU chains are vectorized; JAX CPU chains
require four declared CPU devices. A completed sample file is explicitly marked
as awaiting diagnostics; it does not automatically become the selected model.

Compare common parameters and derived building/unit contributions using bulk and
tail ESS/sec, R-hat, divergences, tree-depth saturation and energy diagnostics.
Report both retained-only and warmup-inclusive ESS rates plus complete user-facing
wall time. Avoid treating adaptation recipes from different samplers as identical
or treating a single run as a precise speed ranking. The CPU raw progress log
only approximates the warmup boundary; label that uncertainty if using it.

Active revised GPU artifact:
`data/model/chelsea-numpyro-gpu-batched-benchmark-20260918`.
Raw production GPU timing is now measured as above; convergence and ESS/sec
diagnostics are running on the recovered complete posterior. No winner yet.

The follow-up `models.sampler_efficiency` command requires a completed, hash-bound
benchmark posterior and its original source/design/code. It applies the same
parameter, unit/bathroom contribution and joint-floor diagnostic gates used by
the CPU fit. It rejects incomplete inputs, preserves all chains/draws and adds
NumPyro's tree-depth saturation flag in a read-only view. Rate tables distinguish
retained compute, retained compute plus storage, warmup plus retained sampling,
and, for successful original calls, the PyMC call plus posterior writing. A
verified postprocessing recovery omits that unavailable end-to-end denominator.
A compute-only GPU rate must not be
compared without qualification to CPU sampling that includes durable trace writes.

```sh
UV_CACHE_DIR=/tmp/apartments-uv-cache OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  uv run --frozen --no-sync python -m models.sampler_efficiency \
  --benchmark data/model/chelsea-numpyro-gpu-batched-benchmark-20260918 \
  --dataset data/model/chelsea-reviewed-current-analysis-20260918 \
  --output data/model/chelsea-numpyro-gpu-efficiency-20260918
```

Eleven focused tests cover rate denominators, normalization and refusal to infer
timings from incomplete or unbracketed chains. Applying the timing helper to
verified CPU counters produces per-chain retained-duration intervals of
619–679, 645–705, 632–692 and 610–670 seconds. These are intervals because progress
callbacks straddle the warmup boundary. They are **not** a single wall-clock
denominator for pooled ESS. Evidence is preserved in
`data/model/chelsea-nutpie-retained-time-brackets-20260918`.

After diagnostics finish, `models.compare_sampler_efficiency` joins identical
named parameters and contribution contrasts, verifies matching data, priors,
graph code and sampling settings, and refuses failed diagnostic gates. It reports
CPU/GPU bulk and tail rate ratios with the CPU wall-timing bounds, separating
coefficient, building and unit parameter families. It also reports the minimum
ESS/sec in each diagnostic family; the slowest parameter need not be the same
one across samplers. Its 13 tests cover alignment, timing bounds, artifact
bindings, posterior modification, mismatched models and failed diagnostics.

Official API references: [nutpie PyMC compilation](https://pymc-devs.github.io/nutpie/pymc-usage.html),
[PyMC NumPyro sampling](https://www.pymc.io/projects/docs/en/stable/api/generated/pymc.sampling.jax.sample_numpyro_nuts.html),
and [JAX installation](https://docs.jax.dev/en/latest/installation.html).
The installed package source was checked for the exact versions above.
