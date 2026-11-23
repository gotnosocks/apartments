# Large container memory (2026-11-23)

A large Modal container (`app.LARGE_CPU, LARGE_MEMORY_MIB` = 8 cores, 192 GiB) costs about
$1.90 an hour beside the H200's $4.54, and $1.53 of that is memory. No fit has recorded its
peak: under gVisor `memory.peak` is missing. Since #1540 `memory_peak_bytes` falls back to
the largest finished child's `ru_maxrss`.

## Probe

One short large fit at fe4930e7. Same model, dataset and split as the full onefit fit
(`u5-of`), with `2 20 20 1` (2 chains, 20 warmup, 20 draws), `--no-loo --no-heldout
--no-summary`, label `mem-probe`. The design, the GPU factors and the host copies are the
same size as in a full fit; only the sweeps are fewer. About 6 minutes, about $0.65. Not a
model test: its draws are not scored.

## Predictions (written before launch)

1. `memory_peak_bytes` is filled in (gVisor reports `ru_maxrss`). P ≈ 0.8.
2. Peak between 20 and 80 GiB, central 40 GiB: the served design took 15 GB on 266k rows,
   and this design's 1.76M rows are mostly sparse indices.
3. If the peak is under 64 GiB, a 96 GiB reservation keeps 50% headroom and saves about
   $0.75 a container-hour, about $1.7 a onefit fit. A full fit's own peak (through #1540)
   checks it before the change.

## Result

(after the probe lands)
