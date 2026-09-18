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
