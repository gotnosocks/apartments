# Keeping full-data fits on smaller GPUs

Written 2026-10-16 for the all-scraped fit (m7-...-unitnu4 on all-scraped-v1), which has 1,575,194 training rows, 67,735 buildings, 871,149 units and 170 features.

## Memory in the failed H100 run

I built the Gibbs design on a 10% building sample (168,516 rows, 6,786 buildings) on thelio and scaled each array up to the full data. The scaled total agrees with the 8.46 GB of captured constants in the H100 log.

| Array | Size at full data | GB |
|---|---|---|
| Global design `a`, dense float64 | 1,575,194 × 443 | 5.6 |
| Feature block `gram_feat` | 1,575,194 × 174 | 2.2 |
| Slots, buckets, indices and the rest | | 0.6 |

A row of `a` has 24 nonzero columns out of 443 on average (5.5%). Apart from the 170 features and 4 day-of-year terms, each column comes from the row's bedroom group and month through `gram_basis`, a 808 × 269 table.

On top of those constants, the first phase-2 warmup round asked for a 39.3 GB (36.6 GiB) working buffer. Reading the code, I estimate its contents fall into three groups, without a profile to confirm:

- rows × 443: `wa`, `a_t` and the per-bucket gathers of `a_t`, about 5.6 GB each
- units × 443: the unit sums `g` and `c·g`, about 3.1 GB each
- building cells × 443: `q_lg` for the current and the proposed scales, plus `v`, about 4.8 GB each. The full data has about 1.35 million building cells (buildings × compact walk width, with widths from 12 to 40).

Each compiled phase (phase 1, the three phase-2 rounds, sampling) embeds its own 8.5 GB copy of the design, and two copies were in memory when the run failed. Under the default 75% allocator cap the H100 offered about 60 GB against roughly 56 GB in use, and fragmentation left no free block big enough.

## Growth

All of the large terms grow linearly with the data and with the number of global columns. Rows and units account for most of it. Building cells grow with the number of buildings and with the length of each building's history, because a longer history widens its walk. Global columns grow with the months covered: at 202 months, 67 of the 443 columns are trend knots and 201 are bedroom-time knots.

## Changes, in order

The table gives GB at the full data size, and the multiple of the current data each card could hold with the allocator at 95% (38 GB usable on a 40 GB card, 76 GB on an 80 GB card).

| Step | Change | GB at 1× | 40 GB card | 80 GB card |
|---|---|---|---|---|
| 0 | MEM_FRACTION=0.95, already queued by Modeling | about 56 | no | up to about 1.3× |
| 1 | Pass the design into each jit as arguments, keeping one copy on the GPU | about 48 | no | about 1.6× |
| 2 | Run the building pass in chunks of buildings, building each chunk's rows of `a` from `gram_feat` and `gram_basis` | about 18 | about 2× | about 4× |
| 3 | Stream the solve, recomputing each chunk's `q_lg` and `v` during back-substitution | about 4 | about 10× | about 20× |

Step 1 changes no numbers. It also removes the minutes of constant folding per phase that the H100 log records.

Step 2 is the main change. Units nest in buildings, so each chunk of buildings carries its own units and rows. The chunk's `g`, `a_t`, `q_lg` and Schur contribution all come from its rows, and a `lax.scan` accumulates the 443 × 443 Schur matrix and its right-hand side across chunks. The largest working arrays then belong to one chunk at a time. The stored `q_lg` copies (about 9.6 GB) and `v` remain, and they grow with buildings. Since the arithmetic stays the same, the draws should match the current sampler up to summation order, and a fixed-seed comparison on the NB9 served fit can check that.

Step 3 drops the stored per-building blocks too, leaving memory proportional to rows × 174 (the features) plus chunk work space. The cost is a second pass over the rows on every block solve. Phase 2 runs 7 solves a step, so I expect a noticeable slowdown, and it needs timing before anyone relies on it. I would hold it until step 2 runs short.

Storing `gram_feat` in float32 and computing in float64 would halve the largest remaining constant. It alters the model's inputs slightly, so I would leave it aside unless step 3 falls short.

The large-fit launcher has A100-80GB, H100 and H200 functions. A 40 GB card would need its own large function in `ops/modal/app.py`.

## Price per fit

The card with the lower hourly price may not give the cheaper fit. The sampler runs in float64. By Nvidia's published figures an H100 has about 3.5 times the A100's float64 throughput and about 1.7 times the A100-80GB's memory bandwidth, at 1.33 times the large-container price ($5.86 against $4.41 an hour). If the H100 runs this sampler more than 1.33 times faster, it costs less per fit. No paired timing of this sampler exists yet. A single H100 run of the NB9 served fit, set against its A100-40GB time of 2,059 s, would answer it for about $3.

The two chains already run one at a time on a card (`chain_batch` 1). Running them in separate containers would halve wall time and leave memory per card unchanged.

## Recommendation

Do steps 1 and 2 next, in that order, as separate PRs, each with a fixed-seed equivalence test on the NB9 fit. Together they put the current full data on an A100-40GB with room for about twice the rows, and on an 80 GB card with room for about four times. Keep step 3 in reserve. Time the NB9 served fit once on an H100 before choosing the card for large fits.
