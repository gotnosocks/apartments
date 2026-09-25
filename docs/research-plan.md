# Research plan: the PSIS-LOO × fit-time frontier

Living plan for the modeling work. Ben set its objective on 2026-09-24: optimize the Pareto frontier of
PSIS-LOO accuracy and fit time. The [board](model/leaderboard/leaderboard.md) and the
[dashboard](dashboard.md) (http://thelio.tail3983e0.ts.net:8500) apply the rules below. The goals, data
contract and pitfalls in [the 2026-09-24 brief](brief-2026-09-24.md) and the
[project intent](project-intent.md) still apply. This plan replaces the brief's evaluation contract
(§4) and first tasks (§5).

## Objective

Push the frontier of **PSIS-LOO ΔELPD** against **fit time on thelio**. That means more accurate
descriptions of every listing for the same fit time, or the same accuracy sooner. Product decisions,
such as the app's selected model, the summary reader and West Village, stay Ben's and are on hold
for this phase.

## The score

- **Definition.** For every row of the row split's 47,374 training rows (seed 20260922; fixed and
  shared by every row-split fit), the expected log predictive density of its log rent given all the
  other training rows: elpd_loo = Σᵢ log p(yᵢ | y₋ᵢ). It is estimated by Pareto-smoothed importance
  sampling over the fit's saved joint draws (`python -m rentfrontier.loo <run>`). No refit is needed.
- **Why this score.** Ben analyzes listings whose own unit is in the fit, so the test is each
  in-fit listing predicted from all the others. Unlike the 10% held-out split, it covers every
  training row, including the 47% of units listed once. It is a proper scoring rule: it rewards
  describing the whole distribution of asks, and it penalizes fitting a row by its own ask.
- **Unit effects are integrated exactly.** For every draw, each row's unit level (and drift, in
  designs with unit drift) is integrated by quadrature given the unit's other rows. PSIS then only
  reweights the remaining parameters. A unit listed once gets its exact prior predictive. Tests:
  exact LOO on a conjugate hierarchical model, and SciPy quadrature for Student-t units with drift.
- **Pairing.** ΔELPD is paired row by row against the baseline `m0-base/base-v1/gibbs@5cc0809`.
  Its uncertainty combines the paired standard error with both runs' Monte Carlo errors.
- **Reliability.** Pareto k is reported per row, against the threshold min(1 − 1/log₁₀ S, 0.7):
  0.60 at the 320 draws the recorded runs kept. Designs without a building walk have about 0.4%
  of rows over it; walk designs have 2–4%. These are rows alone in their building's half-year:
  that single ask pins the building's walk at that knot. They carry about 40% of the Monte Carlo
  variance (MCSE ≈ 8–10 per run at 320 draws).
- **Validation.** Each row-split fit also scores its 5,264 held-out rows, which it never saw. The
  board keeps that held-out ΔELPD (against the promoted PyMC model) as an independent check, and the
  dashboard plots it against PSIS-LOO. For m8, the mean held-out log density is 1.228 and the PSIS
  mean over training rows of multi-row units is 1.236.

## The fit-time axis

- Fit time is the scored (row-split) fit's sampler wall time, including JIT compilation, on the
  hardware recorded with the run. Unit-split fits are optional and are not counted.
- **One frontier per hardware class** (Ben, 2026-09-24: the frontier on different hardware is
  expected to differ a lot). A fit time only competes with fit times on the same hardware. The
  class is where the fit actually ran (the JAX device, not just the host's GPU): Modal H100,
  Modal H200, thelio RTX 2060 SUPER, thelio CPU (Ryzen 5 3600X), Modal CPU for PyMC screens.
- The target hardware is **thelio**: the RTX 2060 SUPER (8 GB, slow float64) or the CPU. Every
  recorded frontier run so far used a Modal H100 or H200. Those points stay on the board as
  context, labeled by hardware, but their thelio times are unmeasured. m8 is not refit locally
  (Ben, 2026-09-24).
- **One timed job at a time** (Ben, 2026-09-24: "I'm okay with waiting longer to do these things
  serially in favor of getting good data"). Every heavy job on thelio holds
  `/data1/apartments/tmp/heavy.lock`: fits, LOO and variance scoring, and reviewers' tests. The
  fit queue runs from a fixed-commit worktree. From commit 3c26c4a, each run record carries a
  `contention` block: the mean number of cores other processes kept busy during the fit, and any
  other GPU compute processes. A timing is clean below 0.5 other cores, and the dashboard's Timing
  column shows it. Thelio fits from before this rule whose times may include contention were
  moved to `/data1/apartments/frontier/runs-archive/contended-2026-09-24/` and are being re-timed.

## Rules

- **Gate.** Split R-hat < 1.01 and bulk ESS > 400 on scalars and traced effects. Frontier-line runs
  also need R-hat < 1.05 over every element of every group effect (1.1 when recomputed from older
  runs' kept draws). No divergences under NUTS. Named additive dollar contributions are required.
- **Eligible.** Passes the gate, is interpretable, and has a PSIS-LOO score.
- **Best.** The top PSIS-LOO ΔELPD defines a tie band of two combined SE. The best is the fastest
  entry inside that band.
- **Frontier.** Eligible entries that no other eligible entry beats on both PSIS-LOO ΔELPD and fit
  time.
- Screen-grade PyMC runs stay visible and are never best or on the frontier. PyMC screens that
  saved no draws have no PSIS-LOO score yet.

## Protocol for a candidate

1. Write the design as a self-contained, committed configuration (model plus features) in
   `rentfrontier`. No `_vN` copies or code-hash protocols.
2. Run one row-split fit on thelio from a clean commit (`python -m rentfrontier.run --split rows …`),
   launched with `systemd-run --user` and a `MemoryMax`, with TMPDIR and outputs under `/data1`.
   Check `free -g` first. The run records its commit and hardware.
3. Score it with `python -m rentfrontier.loo <run>` (about 30–80 s on the GPU).
4. The dashboard picks it up within 10 minutes. Regenerate the board in the PR that lands the
   design.
5. Run the unit split only for entries that reach the frontier (secondary evidence).
6. One unit of work per PR, reviewed by a reviewer who isn't the author. Squash-merge after an
   `archive/pr-N` tag.

Compared with the previous protocol (a row-split and a unit-split fit for every design), this
halves the compute per candidate.

## Two axes: structure and implementation (Ben, 2026-09-24)

The goal is the best model structure *and* implementation. Every structure can be fit by more
than one exact sampler, and each gets its own run record, timed on its own hardware:

- **Custom Gibbs** (`rentfrontier.run`, JAX): the blocked Gibbs sampler with units integrated out.
- **PyMC** (NUTS via nutpie, CPU) and **NumPyro** (NUTS, JAX on the GPU or the CPU), through the
  model ladder (`rentfrontier.ladder`) and, for the Gibbs designs, `model.build_model`, which is a
  NumPyro model of every design.

Where implementations overlap, their posteriors must agree. That is the independent convergence
check the project intent asks for, and it runs again whenever a sampler changes. The frontier on
each hardware class then shows the best (structure, implementation) pair at each fit time.

**The ladder: start as simple as possible and build up.** Each rung adds one term to the one
below. Priors mirror `model.build_model`, so L6 is m0q and L7 is m1q. A test checks, for every
rung, that the PyMC and NumPyro models give the same joint log density and that the scoring
terms are the model's mean.

Parameterization follows the Gibbs line's NUTS reference. Trend steps, season, building and unit
effects are centred, since each is informed by many rows. Only the building walk is non-centred,
because most building half-years have no rows. The first ladder (3c26c4a) had every group effect
non-centred, and PyMC diverged at the scales: 1 divergence on L2 (344 s) and 6 on L3 (525 s). Those
records stay on the board as the evidence.

| Rung | Adds |
|---|---|
| L0-mean | intercept only (Student-t noise) |
| L1-drift | one shared linear drift per year |
| L2-trend | a shared market trend: random walk over quarterly knots (contains the drift) |
| L3-season | calendar season |
| L4-features | the base-v1 listing features |
| L5-building | building levels |
| L6-units | unit effects (= m0q) |
| L7-walk | each building's random walk over half-year knots (= m1q) |

Each rung gets PSIS-LOO (L6 with the unit effect integrated, as in the Gibbs line), a held-out
score, a variance decomposition and a fit time. The first rung agrees across backends: PyMC and
NumPyro give the same PSIS-LOO (−31,786.1) at L0.

## Current effort: the sub-10-minute frontier on thelio (from 2026-09-24)

Ben asked for a research effort on the part of the frontier that fits in under 10 minutes, with
variance decomposition as a measure of modeling quality and projection to search for more
efficient models. It runs separately on each local hardware class (RTX 2060 SUPER and the CPU).

- **Starting point.** On the H100, only m0 (83 s) is under 10 minutes; m1-walk (6–12 min) failed
  the gate and m5-nocurves took 13 min. On thelio, m0 with 8 chains × (100 + 100) took 241 s on
  the 2060 (2 chains at a time; 8 at once ran out of GPU memory) and 410 s on the CPU, without
  converging (R-hat 1.54 on sigma; the joint collapsed update's acceptance fell to 3% in
  the short warmup). The 2060 runs float64 at about 1/32 rate.
- **Quality measures.** PSIS-LOO ΔELPD (primary); the variance decomposition
  (`rentfrontier.variance`: shares of features, market and time, building level, building over
  time, building slopes, unit effects and residual); the held-out check.
- **Step 1. Sampler cost per hardware.** Profile m0 and m1 on each local class (JIT, warmup,
  per-iteration cost by Gibbs block) and search chains, chain batching, warmup length and draws
  for the cheapest setting that passes the gate. The target is effective draws per second, not
  iterations.
- **Step 2. Projection search.** Use m8 + desc as the reference (its saved draws). Project its
  predictions onto cheaper design families (the structure of m0, m1, m5 without curves, with or
  without the description flags, per-building slopes; Student-t units are not in the prototype)
  and measure the in-sample log density each projection loses. That is a proxy: it ranks
  structures as their native PSIS-LOO does but inflates the losses. The terms that keep the
  most accuracy per second of expected fit time define the candidates.
- **Findings so far (RTX 2060).**
  - m0q passes the gate (PSIS-LOO +10.3 vs m0; the quarterly trend costs nothing). Its 350 s and
    m1q's times were measured alongside other jobs and are being re-timed serially.
  - Exact block speedups: per-slot accumulation (−34–37% for walk designs) and a structured
    `a′Wa` with inverted building factors (a further −22–38%).
  - Walk designs need the solo collapsed walk_scale update. Without it walk_scale mixes 3.5×
    slower per draw, and cheap scaling moves or a covariance-shaped joint proposal don't close
    the gap. With it, an iteration costs about 3 block solves (~145 ms per chain), and four chains
    don't batch on this card. So a walk design that passes the gate needs about 15–17 min.
  - A short-warmup adaptation bug (steps sized from drift, ν frozen) is fixed.
- **Step 3. Native fits.** Fit the best candidates on each local class within 10 minutes with the
  step 1 settings, then score PSIS-LOO and the variance decomposition. These points form that
  class's sub-10-minute frontier.

## Work tracks, in order

### T1. Make the score resolve design differences

1. **Save more draws.** New runs should keep 1,000–2,000 joint draws (a smaller `--keep-every`),
   or write per-row log densities on the device. This lowers MCSE by roughly 2–2.5× and makes the
   k estimates stable. Storage is about 0.4–1 GB per run on `/data1`.
2. **Treat the lone-row walk knots.** For rows alone in their building's half-year, integrate the
   affected walk knots locally, or refit exactly without those rows (they are about 2–4% of rows).
   This removes most of the remaining high-k rows.
3. **Score the promoted PyMC model.** Rerun its row-split screen locally with draws saved (about 3 h
   of CPU NUTS) and add the PyMC-side integrated LOO. It then returns as a comparison point with its
   6.2 h production fit.
4. ~~Close the tdrift sampler-agreement xfail.~~ Done (PR #17 review). It passes against the
   non-centred reference, and the xfail is removed. The margin is thin: Gibbs ESS on
   unit_drift_scale is about 80–200 in the test.

### T2. The fit-time axis on thelio

1. Measure thelio fit times for the cheap frontier designs (m0, m1, m5-nocurves, m5-quarterly) on
   the RTX 2060 and on the CPU. This gives the local baseline for the time axis.
2. Profile a local fit: JIT compilation, warmup and sampling, and the per-iteration cost of each
   Gibbs block (unit integration, building Cholesky, Schur solve).
3. **Right-size the draw budget.** 16 chains × 2,000 draws reach bulk ESS of about 2,600 against a
   gate of 400. Size chains and draws to the gate plus the PSIS draw needs of T1.1, not the old
   defaults.
4. Use float32 only where it is exact enough (not the Schur solve), and batch chains to fit the
   2060's memory.

### T3. The accuracy axis

1. **Walk regularization for sparse building periods.** The high-k finding says lone rows pin walk
   knots. Try knot pooling or a stronger walk prior where a building-period has few rows.
2. **m9 candidates** from the frontier hand-off: floor features (the expanded-floor sidecar) and a
   free first walk knot (the 2010 +4% bias).
3. **Features** from the PyMC line, re-evaluated under PSIS-LOO: description flags (≈0 on held-out
   rows before), as-of attribute flags, and the `size_missing` slope.

### T4. Product (on hold, Ben's decisions)

The summary reader (branch `app/summary-reader`), any change to `config/main-analysis.json`, and
West Village once its crawl completes.

## Current state

The dashboard and board are generated from the run records; see them for the live frontier. The
table below was recorded when this plan was written.

| Frontier entry | PSIS-LOO ΔELPD vs m0 | k over threshold | Held-out ΔELPD vs promoted | Fit time | Hardware |
|---|---:|---:|---:|---:|---|
| `m0-base/base-v1/gibbs@5cc0809` | +0.0 ± 0.0 | 0.4% | -827.1 ± 49.7 | 83 s | NVIDIA H100 80GB HBM3 |
| `m5-nocurves/base-v1/gibbs@33e8bad` | +9,766.5 ± 160.0 | 3.0% | +255.7 ± 36.9 | 13 min | NVIDIA H100 80GB HBM3 |
| `m5-quarterly/base-v1/gibbs@4226f40` | +9,870.6 ± 160.8 | 2.9% | +271.5 ± 36.5 | 20 min | NVIDIA H200 |
| `m7-tunits/base-v1/gibbs@d62fc51` | +12,770.9 ± 182.7 | 3.8% | +569.5 ± 44.0 | 44 min | NVIDIA H100 80GB HBM3 |
| `m7-tunits/desc-v1/gibbs@d62fc51` | +12,941.1 ± 183.5 | 3.8% | +549.1 ± 44.4 | 46 min | NVIDIA H100 80GB HBM3 |
| `m8-drift/base-v1/gibbs@b7c196f` | +13,125.5 ± 183.3 | 4.1% | +623.5 ± 44.4 | 54 min | NVIDIA H100 80GB HBM3 |
| `m8-drift/desc-v1/gibbs@b7c196f` (best) | +13,279.3 ± 184.1 | 4.0% | +601.7 ± 44.9 | 56 min | NVIDIA H100 80GB HBM3 |

- m8 + desc is both the top score and the best: no faster entry is within two combined SE of it
  (m8 base trails by 153.8 ± 38.9).
- Description flags (desc-v1) add about +150 to +180 on PSIS-LOO for m7 and m8, against ≈0 on the
  held-out rows. The held-out rows come only from repeat-listed units; PSIS-LOO also covers units
  listed once, where the listing's own description carries more information.
- PSIS-LOO and held-out ΔELPD rank the 28 scored entries almost identically (Spearman 0.94).
- All scores come from the recorded H100/H200 runs; no frontier point has a thelio fit time yet (T2.1).
