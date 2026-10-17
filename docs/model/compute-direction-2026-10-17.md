# Computational direction for the all-scraped data (proposal, 2026-10-17)

This is a proposal. It launches nothing on Modal. Every fit below waits for Ben's go, and then
runs under the usual rules: one fit at a time on the $10/day balance, each about an hour or less,
with predictions written before it starts.

I read the adopted goal through its summary in the project instructions, the served model
(`frontier/src/rentfrontier/model.py`), the Gibbs sampler (`gibbs.py`), the all-scraped fit's
record and Modeling's mixing review of the same day (`docs/model/mixing-review-2026-10-17.md`).
The full goal file under `/mnt/project-files` isn't readable from thelio.

## The all-scraped fit in numbers

The fit `...-unitnu4-all-scraped-v1-rows-e694a775-a40` ran on an A100-SXM4-40GB over 1,575,187
rows, 67,735 buildings and 871,143 units, with 2 chains.

| stage | seconds | share of 20,472 s wall |
|---|---|---|
| prepare (CPU, inside the container) | 912 | 4% |
| warmup | 900 | 4% |
| sampling, 4,500 sweeps a chain | 15,533 | 76% |
| PSIS-LOO | 1,631 | 8% |
| the rest (image, copy, summary) | about 1,500 | 7% |

A sweep took 3.45 s, ten times the NB9 sweep for six times the rows. The fit failed the gate at
the Carlyle (ESS 11.7). Among the scalars, building_scale mixed slowest at ESS 280.

To pass the gate inside the hour, a fit gets about 2,400 s of sampling once prepare, warmup and
LOO shrink (below). building_scale then needs 400 ESS in 2,400 s, or 0.167 a second, against
0.018 now: a factor of about 9 in ESS per second. The mixing review's P1 and P2a predict 2.4x of
that from better steps and a collapsed solo. I look for the rest in the cost of a sweep and in
running more chains at once. The slow buildings themselves are a data problem (the review's P6),
which no sampler fixes, so the Data improvements queue stays on the critical path.

At $10 a day the balance pays for about four A100-hours. A fit spread over 8 GPUs costs 8 times as
much an hour, so it helps the hour cap and does nothing for dollars. I therefore aim for one GPU
per fit and treat multi-GPU as the route for data beyond one card.

## Proposal

I propose keeping the exact model and its exact conditional structure, while rebuilding the
sampler's inner work around operations a GPU runs well, and borrowing library code wherever it
exists. Alongside, I propose benchmarking off-the-shelf many-chain HMC against it on equal dollars,
so the choice of engine rests on a measurement.

### A. Measure where a sweep's 3.45 s goes

The arithmetic in a sweep is small for an A100. A pass over 1.58M rows with about a hundred
float64 columns reads about 1.3 GB, or about 1 ms at the card's memory bandwidth. The 67,735
building blocks of about 35 walk knots or fewer need about a GFLOP to factor. The dense global
system has on the order of a thousand rows. So a sweep should be able to run in tens of
milliseconds, and the 3.45 s comes from somewhere other than the arithmetic. Likely places:

- float64 scatter-adds in `jax.ops.segment_sum`, which serialize on atomics;
- padding in the bucketed building Cholesky;
- the 10 serial Metropolis steps of the noise update, each a pass over the rows;
- many small kernels, each paying its launch cost.

I'd run a 200-sweep profiling fit on NB9 and on all-scraped with `jax.profiler` and Nsight Systems
on an A100, at about $0.40 for NB9 and $1.20 for all-scraped, and record time by kernel. Each fix after that is a sampler change
with the same posterior, judged by ESS per second and a paired PSIS-LOO within 2 SE. Candidate
fixes, in the order the profile suggests:

- replace scatter-adds over sorted rows with segmented reductions over contiguous ranges (the rows
  are already sorted by unit and building), or with a one-hot matmul per bucket;
- fuse the noise steps into one kernel per pass with `jax.lax.scan`;
- size the buckets from the measured cost.

### B. Take the fixed costs out of the hour

- **Prepare** (912 s on the container's CPU). The design arrays depend only on the data's hash
  and the design config. I'd cache them on the Modal Volume under that key, so only the first fit
  of a dataset pays. Every later fit on the same data then saves about 15 minutes, a quarter of the
  hour cap.
- **LOO** (1,631 s). The kept draws are already thinned. I'd compute the pointwise log likelihood
  on the GPU in row chunks with streaming accumulators for PSIS (the largest weights per row and
  the running sums), so the cost falls toward one pass over rows per kept draw.
- **Warmup** (900 s). Pathfinder (BlackJAX) gives starting points near the typical set from an
  optimizer run, which can shorten the first warmup phase. I'd test it only if warmup still takes
  more than 10% of the hour after A.

### C. Many chains on one card

With 2 chains the card spends most of a sweep waiting on memory. With 16 or 32 chains under
`vmap`, each pass over the rows serves all chains, and matrix-vector products become
matrix-matrix products. On thelio's RTX 2060, Modeling found four chains didn't batch, but that card
runs float64 at about 1/32 of its float32 rate. The A100 and H100 run float64 at half the float32
rate, and the A100-80GB, H100, H200 and B200 hold many chains' state. More chains also help with the
goal's standard of evidence:

- Nested R-hat (Margossian and others) checks convergence across many short chains.
- Buildings with two clusters of prices (P6) show up as chains disagreeing, which a pair of
  chains can miss.
- ESS adds across chains, so 32 chains of 300 kept sweeps give the gate's 400 ESS for a quantity
  with IACT 24, after a shorter warmup per chain.

I'd measure sweep time against chain count (2, 8, 32) on NB9 and all-scraped in the profiling
fits of A.

### D. Matrix-free Gaussian draws

The sampler draws all Gaussian latents jointly by Cholesky, with units integrated out and building
blocks eliminated. That trick needs every unit nested in one building and every local term nested
in its building, so the sampler refuses line effects that cross buildings and any spatial field.
The goal asks for location as a map of value explained by measurable things, which calls for
effects crossing buildings: a smooth field over the street graph, subway catchments, school zones
and blocks.

A Gaussian draw can also come from one linear solve: draw a perturbed right-hand side
b + L z, then solve Q x = b + L z, where Q is the posterior precision. Conjugate gradients (CG)
solves it with nothing but products Q v, each a pass or two over the rows. Published work
supports this route:

- Papaspiliopoulos, Roberts and Zanella (Biometrika 2020) study Gibbs samplers for crossed random
  effects, and with Stumpf-Fetizon (2023) draw them by CG at a cost linear in the data.
- Nishimura and Suchard (JASA 2023) precondition CG with the prior for large Bayesian regressions,
  on GPUs.

For this model, the existing building-block Cholesky becomes the preconditioner. With only nested
terms, CG then converges in a handful of iterations. With crossed terms, the iteration count
measures how far the crossing pulls away from the nested structure. `lineax` and
`jax.scipy.sparse.linalg.cg` supply the solver. The draw is exact up to the solve's tolerance, and
a test against the Cholesky draw on NB9 checks it. The collapsed scale updates need log
determinants as well, which CG doesn't give. I'd keep the Cholesky for the nested part's
determinant and use stochastic Lanczos quadrature only for the crossed part, testing its error on
simulated data.

This changes no posterior while the terms stay nested, so a fit with the CG draw tests as a sampler
change. Its payoff comes in the model terms it lets the modeling threads test, starting with the
street-graph field from the 2026-09-29 note.

### E. Data beyond one card

The rows fit easily for now: 1.58M rows take a few GB on a 40 GB card. The data outgrow a card
once each ad carries its photos, floor plan and text as embeddings, as the goal asks. 1.58M ads
with 20 photos and a 768-number embedding each come to about 100 GB in float32. The draws outgrow
it sooner: the kept posterior of the all-scraped fit already fills 13 GB on disk.

Each step of a sweep reads the rows only to reduce them to per-unit, per-building or global sums.
The sweep therefore streams. I'd plan for it in two steps.

1. **Sharding by building across GPUs.** Buildings are independent given the global terms. Each
   GPU holds the rows of a set of buildings, eliminates those buildings' blocks and sends its
   share of the dense global system to the others with one all-reduce per solve. JAX's
   `shard_map` handles this on Modal's 8-GPU containers. This mostly helps the hour cap, at N times
   the hourly price.
2. **Streaming from host memory.** For data larger than all the GPUs, the rows stay in host memory
   or on local NVMe in chunks, and each pass copies chunk k+1 to the card while it computes on
   chunk k. A pass over 100 GB at PCIe 4's 25 GB/s takes about 4 s, so a streamed sweep needs few
   passes. I'd arrange the sweep for it: the lam draw and the w update read each row once, and
   the Gaussian draws use the sums. High-dimensional embedding features enter through their
   streamed cross-products X'WX, whose size depends on the number of columns and not the rows.

Diagnostics stream the same way. Online ESS and R-hat by batch means, and the streaming PSIS
accumulators of B, remove the need to keep every draw of every latent.

### F. Off-the-shelf many-chain HMC, as the benchmark

The NumPyro model in `model.py` already runs under NUTS. BlackJAX adds GPU-oriented samplers built
for many parallel chains: ChEES and MEADS adaptation for HMC, and adjusted microcanonical Langevin
(MCLMC). Their gradient is one fused pass over the rows for all chains, which suits a GPU better
than NUTS's tree of small steps, the reason NUTS lost on thelio's card.

This posterior is hard for HMC, though. The t likelihood and t units give the posterior
heavy tails, and the posterior has about 3.3 million dimensions, so each draw needs hundreds of
gradient steps (about 245 with NUTS at L4 on the old ladder). I'd still run one benchmark on NB9:
BlackJAX adjusted MCLMC with 128 chains on an H100, for an hour, scored on the slowest quantities'
ESS per dollar and on paired PSIS-LOO against the Gibbs control. If it wins, the project drops a
custom sampler. If it loses, the record shows by how much.

### Not recommended

- **Stochastic-gradient MCMC and minibatches.** A unit has 1.8 rows on average and a building 23,
  so a minibatch carries almost nothing about most latents, and SG-MCMC's bias goes into the
  uncertainty the goal asks us to report.
- **Variational inference for the final posterior.** Mean-field and low-rank families understate
  the spread of hierarchical effects. I'd use Pathfinder only to start chains.
- **INLA.** It handles latent Gaussian models with a t likelihood, but it scales with the number of
  hyperparameters, and this model has about 150 (79 group scales and 68 noise groups). R-INLA also runs on the CPU.
- **Splitting the city into separately fitted areas and combining them** (consensus Monte Carlo).
  The global terms are tight, so a combination of their subposteriors would come out close, but the
  areas share the trend, the noise model and every scale, and a bad combination would show up only
  as a slightly wrong interval everywhere. I'd hold it in reserve in case E fails.

## Tests and predictions

Each item runs as its own Modal fit. Items A to D change the sampler and leave the posterior
unchanged, so they pass when paired PSIS-LOO agrees within 2 SE with the control, and they win on
ESS per second of the slowest quantity. The control is the served model's next refit on
latest-ask-v9. Medians with 80% intervals:

| test | data | cost | prediction |
|---|---|---|---|
| A. profiling, 200 sweeps, chains 2, 8, 32 | NB9, all-scraped | about $0.40 and $1.20 | over half of a sweep goes to scatter-adds and the noise steps (40% to 80%); 32 chains take 4x (2.5x to 8x) a 2-chain sweep |
| B. design cache and streamed LOO | NB9 | about $2 | prepare under 60 s on a cache hit; LOO under 25% of its current time (10% to 40%) |
| C. 16 chains with A's fixes, P1 and P2a | NB9 | about $2 | slowest-scalar ESS per second 4x (2.5x to 7x) the control's |
| D. CG draw, nested terms only | NB9 | about $2 | CG converges in 3 (2 to 6) iterations to 1e-8; ESS per second within 20% of C |
| C on all-scraped, after P6's data fixes | all-scraped | about $4 on an H100 | passes the gate inside the hour; building_scale ESS 600 (400 to 1,000) |
| F. BlackJAX adjusted MCLMC, 128 chains | NB9 | about $4 on an H100 | slowest-scalar ESS per dollar 0.4x (0.1x to 1.5x) of C's |

A prediction misses when the result falls outside its interval. I'd record misses as misses.

Simulated data come before any of these is served. The goal counts a result as established only
when it recovers known answers from simulated data. For each sampler change I'd draw a synthetic
dataset from the served fit's posterior median, with NB9's rows, buildings and units, refit it,
and check that the 80% and 95% intervals cover the known effects at those rates. These refits
replace the reference-sampler agreement tests on small models, which cover only small data.

## Order and cost

1. A, at about $1.60 for both datasets. Its profile decides which fixes in A and C to make first.
2. B and the fixes from A, as code changes with tests on thelio, then one NB9 fit (about $2).
3. C, then C on all-scraped once Data improvements has worked through the P6 buildings.
4. D after C, since its payoff comes with crossed terms.
5. F in parallel with D, as the only fit not built on the custom sampler.
6. E when the data first exceed a card, which I expect with the photo embeddings.

Items 1 to 5 come to about $16, or a day and a half of the balance.

Ben's decisions:

- a go for the A profiling fits;
- whether F's benchmark is worth $4 of the balance.
