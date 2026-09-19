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
  The unchanged command now continues diagnostics/reporting on the host.
- An eight-minute interior retained window (02:44:24–02:52:24 UTC) contains
  **17,757 draws across four chains in 480.066 seconds: 36.99 aggregate draws/sec,
  or 9.25 per chain**. Each chain contributes 4,425–4,450 retained draws to this
  window. Startup, warmup and final export are excluded; ordinary raw trace
  writes are included. This is a useful long-window raw-throughput baseline,
  not ESS/sec or evidence that nutpie is fastest. The counters and calculation
  are archived in `data/model/chelsea-nutpie-steady-throughput-20260918`.
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
No production GPU speed or convergence result is claimed in this checkpoint.

Official API references: [nutpie PyMC compilation](https://pymc-devs.github.io/nutpie/pymc-usage.html),
[PyMC NumPyro sampling](https://www.pymc.io/projects/docs/en/stable/api/generated/pymc.sampling.jax.sample_numpyro_nuts.html),
and [JAX installation](https://docs.jax.dev/en/latest/installation.html).
The installed package source was checked for the exact versions above.
