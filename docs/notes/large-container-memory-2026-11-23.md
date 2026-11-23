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

Run `drift-building-phase-unitkn-ablate-b0-onefit-fe4930e7-mem-probe`, 04:25 ET: exit 0,
608 s wall (fit stage 543 s: design prep about 345 s, first sweep 138 s, 40 sweeps 40 s),
$1.09 at the large rate, not $0.65: I priced the stage and the prep too low.

| Prediction | Outcome |
|---|---|
| 1. `memory_peak_bytes` filled in | Right: 15,881,175,040 bytes. gVisor has no `memory.peak`, so this is the fit process's `ru_maxrss`. |
| 2. Peak 20–80 GiB, central 40 | Wrong, low: **14.8 GiB**. Same as the served NB9 design's 15 GB on a sixth of the rows; the drift design is leaner than I assumed. |
| 3. Under 64 GiB, so a smaller reservation pays | Right, and by more: see below. |

A full fit holds more than the probe only in its kept draws and held-out predictions
(`trace`, `kept`, `pred_loc`, `pred_unit_sd` in `drift.run`). The full `u5-of-a` run's
`posterior.npz`, which holds all of them, is 236 MB. So a full fit peaks within 1 GiB of the
probe, about 16 GiB, and I did not wait on a full fit's own record.

Change (this PR): `ops/modal-fit --large --lean` reserves 48 GiB (`app.LEAN_MEMORY_MIB`), three
times the measured peak, for a baseline's fit (every drift model in `cap.BASELINES`) with no
scoring in the container: no `--score`, the default for fits. A container then lists at $5.30 an hour on
an H200 in place of $6.45, which saves about $2.6 of a two-container onefit fit's $14.46 (18%).
The probe measured `rentfrontier.run` alone, so in-container LOO, held-out scoring, post
steps, the summary bundle and `--publish-only` keep 192 GiB until their peaks are measured.
The launch pre-check still reserves at the large price, and the ledger settles
at the lean one.
