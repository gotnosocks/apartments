# Running jobs on thelio

Fit time is one of the research objectives, so a fit's time must not depend on what else runs.
Until 2026-10-03 that was done with one global lock (`heavy.lock`): every fit, test, LOO, board
and site build ran one at a time. Light work such as a data PR's tests waited behind hour-long
fits. Now each job runs in one of two resource classes with `ops/job`, and light work runs beside
a fit on cores the fit never uses.

```sh
ops/job gpu   [-m MEM] -- command...   # anything that uses the GPU: fits, GPU LOO, summaries
ops/job light [-m MEM] -- command...   # everything else: tests, reviews, data and site builds
ops/job status                          # what is running in each class
```

The canonical copy is `/data1/apartments/serve/master/ops/job`, which follows master; call it by
that path from any worktree. The job runs in the foreground and its exit status is passed on, so
`timeout`, `&&` and systemd units wrap it as before. Long jobs still go in a `systemd-run --user`
unit so a session restart doesn't kill them.

## The machine

An AMD Ryzen 5 3600X: 6 cores, 12 threads, in two core complexes of 3 cores. Each complex has its
own 16 MB L3 cache: cores 0–2 are CPUs 0–2 and 6–8, cores 3–5 are CPUs 3–5 and 9–11. 15 GB of RAM
and 3 GB of swap, and an RTX 2060 Super with 8 GB. A Gibbs fit keeps the GPU busy and uses about
1.3 CPU cores and 4–5 GB of RAM.

## The classes

| | gpu | light |
|---|---|---|
| At once | one (the GPU lock) | three (slots); a fourth waits |
| CPUs | 0–2, 6–8 (first complex) | 3–5, 9–11 (second complex) |
| systemd slice | `apartments-gpu.slice`, CPU weight 1000, 7 GB | `apartments-light.slice`, CPU weight 20, 5 GB in total |
| Per job, default | MemoryMax 6G | MemoryMax 3G, nice 10, best-effort I/O 7 |
| GPU | yes | hidden (`CUDA_VISIBLE_DEVICES=`, `JAX_PLATFORMS=cpu`) |

Cores are assigned with CPU affinity (`taskset`), because the user systemd manager on thelio has
no cpuset controller (`AllowedCPUs=` needs root). Affinity only binds the jobs `ops/job` starts:
agent sessions, the crawler and the site server can still run on the fit's cores. They use little
CPU, and each run record measures them (below).

The GPU lock is `/data1/apartments/tmp/locks/gpu.lock`, a symlink to the old `heavy.lock`. A script
that still takes `heavy.lock` therefore queues with GPU jobs and never runs beside them, so
scripts can move over one at a time. A legacy job isn't pinned, though: it can share the light
cores, and its own time isn't fenced. Move fit queues to `ops/job gpu` first.

Light jobs don't take the GPU lock. That includes LOO and variance on the CPU
(`JAX_PLATFORMS=cpu`), the research-data build, site builds, board rebuilds and data builds.
LOO on the GPU is a gpu job.

## What a run records

`rentfrontier.run` adds to each run's `contention` block:

- `job_class`: `gpu` when started by `ops/job gpu`;
- `fit_cpus`: the CPUs the fit could use;
- `other_cores_on_fit_cpus`: the mean number of those CPUs busy with other processes;
- `light_cores`: the mean number of cores the light jobs used meanwhile.

`other_cores` keeps its old meaning: other work on the whole machine. A fit's time is clean when
`other_cores_on_fit_cpus` is below 0.5. For runs before this change, `fit_cpus` is all 12 CPUs, so
the two numbers are the same.

## Benchmark (2026-10-03)

The same short fit (m0q, 2 chains, 100 warmup and 600 draws, Gibbs on the 2060) was timed as a
gpu job alone, with a light job keeping all six light CPUs busy (five matrix-multiply threads and a
memory-copy thread), and with the same load on all twelve CPUs at normal priority, which is what
running a job beside a fit without `ops/job` looks like.

BENCHMARK_TABLE

## Setup

Once per machine, and again when the slice files change:

```sh
cp ops/systemd/apartments-gpu.slice ops/systemd/apartments-light.slice ~/.config/systemd/user/
systemctl --user daemon-reload
```

The research-data build (`apartments-dashboard-build.service`) runs in the light slice on the
light CPUs. After changing it, copy it to `~/.config/systemd/user/` and reload as above.
