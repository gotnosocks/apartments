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

The goal is the best model structure *and* implementation. There is **one model definition**,
`model.build_model` (NumPyro) over the designs in `model.MODELS` (Ben, 2026-09-25: no duplicate
PyMC or NumPyro implementations). Samplers are the implementations. Each fit gets its own run
record, timed on its own hardware, and every sampler goes through the same runner and scorers:

    python -m rentfrontier.run --sampler gibbs|nuts --model <design> --split rows ...
    python -m rentfrontier.loo <run>; python -m rentfrontier.variance <run>

- **Custom Gibbs** (`gibbs.py`): the blocked Gibbs sampler with units integrated out. It needs
  every base term: trend, season, features, buildings and units.
- **NumPyro NUTS** (`nuts.py`): NumPyro's warmup, then the Gibbs sampler's bookkeeping
  (`collect.py`), on the GPU or the CPU. The building walk and unit drift are non-centred, and
  every other effect is centred (the data-rich levels diverged under NUTS when non-centred).

Where samplers overlap, their posteriors must agree. That is the independent convergence check
the project intent asks for. The dashboard's "Same model, different implementations" chart
shows it, and the frontier on each hardware class shows the best (design, sampler) pair at each
fit time.

**The ladder: start as simple as possible and build up** (`model.LADDER`). Each design adds one
term to the one below, except L2, which replaces L1's linear drift with a quarterly trend that
contains it. L0–L5 drop base terms, so only NUTS fits them. From m0q on, both samplers
fit every design.

| Design | Adds |
|---|---|
| L0-mean | intercept only (Student-t noise) |
| L1-drift | one shared linear drift per year |
| L2-trend | a shared market trend: random walk over quarterly knots (contains the drift) |
| L3-season | calendar season |
| L4-features | the listing features |
| L5-building | building levels |
| m0q | unit levels |
| m1q | each building's random walk over half-year knots |
| m5-nocurves | each building's premium per bedroom |
| m6-nocurves | each building's slopes on size and bathrooms |
| m7-nocurves | Student-t unit levels instead of normal |
| m8-nocurves | each unit's linear drift per year |

History, from the removed PyMC/NumPyro ladder (ladder.py, 3c26c4a–ac9e02b):
- Non-centring the data-rich effects made PyMC diverge at L2 and L3.
- nutpie needs one BLAS/numba thread per chain: about 1.8× faster per leapfrog step on L4.
- From L4 on, NUTS takes about 245 leapfrog steps per iteration with a diagonal mass matrix. The
  44 feature coefficients are correlated with each other and with the trend, so a dense or
  low-rank mass matrix is the NUTS variant to time next.
- Its records (lines `pymc` and `numpyro`, feature set `none` below L4) stay on the board as
  data.

## Current effort: the sub-15-minute frontier on thelio (from 2026-09-24)

Ben asked for a research effort on the part of the frontier that fits in under 10 minutes, with
variance decomposition as a measure of modeling quality and projection to search for more
efficient models. On 2026-09-25 he widened the window to **15 minutes per fit**. It runs
separately on each local hardware class (RTX 2060 SUPER and the CPU).

**Samplers: library over custom** (Ben, 2026-09-25: "I would prefer to use a library sampler
implementation over implementing our own").
- The custom Gibbs sampler (`gibbs.py`) is ours end to end: exact Gaussian block draws with units
  integrated out, its own Student-t augmentation, collapsed Metropolis scale updates and warmup
  adaptation. No library offers that combination in this stack:
  - NumPyro's `HMCGibbs` needs the conditional draws written by hand;
  - BlackJAX offers kernels (NUTS, elliptical slice, latent-Gaussian samplers), not a blocked
    Gibbs sampler;
  - PyMC has no conjugate Gaussian step;
  - NIMBLE and JAGS assign conjugate and block samplers automatically, but on the CPU outside this
    stack.
- The custom Gibbs sampler is **deprecated** (Ben, 2026-09-25: not to be used for any new work).
  - `run.py` defaults to `--sampler nuts` and refuses `--sampler gibbs` without
    `--reproduce-deprecated`, which exists only to reproduce a run record that cites it.
  - Its entries stay on the board and dashboard as history, labelled deprecated. They show the
    marks library samplers have to reach.
- **NUTS belongs on the CPU here.** On the RTX 2060, NumPyro NUTS took 23 s for L0-mean, 110 s for
  L1-drift and over 20 minutes for L2-trend (stopped), against 8 s, 9 s and 322 s for PyMC NUTS
  on the CPU. Every leapfrog step is many small float64 kernels, and the card runs float64 at
  about 1/32 rate. The NUTS ladder runs on the CPU, with and without the dense mass matrix.
- **NumPyro's CPU gradient is the cost, not the tree.** NumPyro NUTS on the CPU (4 × (1000 + 1000)):
  - L0-mean: 40 s, 6 leapfrog steps per draw;
  - L1-drift: 128 s, 15 steps;
  - L2-trend: 1,987 s, gate passed.

  Its trees are normal, but one chain-gradient over the 47,374 rows costs about 0.7 ms in JAX on
  the CPU, against about 0.08 ms in nutpie's numba-compiled gradient. PyMC/nutpie did L2 in 322 s.
- **Right-size the NUTS draw budget.** 1,000 + 1,000 draws per chain (PyMC's default) gave ESS
  4,767 on L2 against a gate of 400. The next pass uses 500 warmup + 250 draws per chain, all
  kept for PSIS (1,000 draws), with the dense mass matrix from L4 on.
- **NUTS-friendly coordinates** (`--coordinates`; Ben, 2026-09-25: "change the model to perform
  better with one of the libraries"). Each is an exact reparameterization of the same model, and
  each fixed the failure the one before it exposed:

  | Coordinate | What it samples | Failure it fixed |
  |---|---|---|
  | `trend_levels` | absolute quarterly market levels (intercept plus trend) | 500-step trees from the random-walk steps; levels relative to the intercept left an intercept ridge |
  | `season_zerosum` | the centred season (ZeroSumNormal) | season-scale funnel from the unseen raw mean |
  | `building_totals` | building effect plus mean features times beta, as a flat mean plus zero-sum deviations | market vs building ridge (Chelsea Tower), and building attributes (doorman, elevator) trading against building levels |
  | `unit_totals` | unit effect plus its within-building feature deviations times beta | apartment attributes (half baths, floor) trading against unit effects. Centring units on the building effect instead put the market ridge through all 22,000 units |
  | `unit_partial` | unit effects partially non-centred by row count, n / (n + 0.6) | unit-scale funnel from units listed once |
  | `walk_levels` | each building walk as levels inside the building's data range (relative to its anchor knot, the one with most rows), non-centred steps outside it | m1q step size 0.007–0.014: each level was a sum of half-year steps from 2009, tied to the building effect |
  | `slope_totals` | building and unit totals at their mean bedrooms, for per-building bedroom slopes (m5) | not yet run |

  - NumPyro NUTS on the CPU now passes L0–L5: 40 s, 128 s, 43 s, 68 s, 636 s and 909 s.
    Before the coordinates, L2 took 1,987 s and L3–L5 failed.
  - For designs with units the RTX 2060 wins: m0q took 752–947 s in float64 on the 2060, against
    2,300–2,600 s on the CPU.
  - With 500 draws per chain or fewer, m0q misses the traced-effect gate narrowly: R-hat
    1.013–1.027 on a few buildings, some with a single unit.
  - **With more draws it passes.** At 4 × (300 + 1,000): 1,137 s, R-hat 1.002, ESS 1,517,
    PSIS-LOO 40,606 (Gibbs: 40,604). That is the first library-sampler fit of a design with unit
    effects that passes the gate. Trimmed to fit the window:

    | Budget | Fit time | Max R-hat | Min ESS | PSIS-LOO |
    |---|---:|---:|---:|---:|
    | 4 × (300 + 1,000) | 1,137 s | 1.002 | 1,517 | 40,606.0 |
    | 4 × (300 + 600) | 952 s | 1.005 | 898 | 40,608.2 |
    | 4 × (300 + 450) | 885 s | 1.009 | 677 | 40,603.8 |
    | **4 × (250 + 550)** | **888 s** | **1.005** | **894** | **40,607.5** |

    With 250–300 warmup iterations, warmup takes 598–642 s of each fit (673–787 s with 400–500),
    so trimming draws saves little. 4 × (250 + 550) fits inside 15 minutes with a comfortable
    gate margin.
  - Float32 does not work: a chain's step size collapsed.
  - Across samplers and devices, m0q's PSIS-LOO agrees. Against the deprecated Gibbs m0q
    (ac9e02b, RTX 2060) on identical rows, NUTS minus Gibbs is +3.1 ± 4.0 for 4 × (250 + 550) and
    +1.6 ± 3.7 for 4 × (300 + 1,000).
  - m1q (the building walk) did not finish within 60 minutes on the 2060. With `walk_levels`
    (fad9e4f, 4 × (250 + 550)) its step sizes grew to 0.029, 0.029, 0.030 and 0.016, but the
    250 warmup iterations still took 1,243 s (5 s each, as before). The fit was stopped at
    33 minutes under the 30-minute cap, so it has no record.
  - Warmup, not the starting point, is the cost. Starting chains within ±0.5 instead of
    NumPyro's ±2 left m0q unchanged (3e80efb: 874 s, warmup 585 s against 598 s, PSIS-LOO
    40,606.8). Each warmup iteration costs about 5 times a sampling iteration (m0q: 2.4 s
    against 0.5 s). NumPyro's first 75 warmup iterations adapt only the step size, with an
    identity mass matrix. Warmup is now logged in five segments (`warmup_segments`).
  - **The SVI warm start cuts m0q to 592 s** (7229ef0, 4 × (250 + 550), `--svi-steps 2000`),
    and it still passes (R-hat 1.006, ESS 817). Before sampling, 2,000 steps of NumPyro SVI
    fit a mean-field normal guide (46 s). Each chain starts at a draw from it, with its
    variances as the initial mass matrix. Warmup drops from 598 s to 252 s. PSIS-LOO is
    40,602.1, −5.3 ± 3.5 against the 888 s fit on identical rows (Monte Carlo noise: it is
    the same model).
  - A shorter warmup does not pay: 4 × (150 + 550) with the warm start took 746 s. Warmup was
    142 s, but its one mass-matrix window left step sizes of 0.022–0.027, and sampling took
    541 s against 277 s (it passes: R-hat 1.006, ESS 596; PSIS-LOO 40,607.0).
  - The first two warmup segments ran at 58–67 leapfrog steps per iteration with step sizes
    0.07–0.13. The third, after NumPyro's first mass-matrix window, ran at 258 with 0.014–0.045.
    NumPyro regularizes windowed estimates as Stan does, adding 1e-3 × 5 / (n + 5) to every
    variance. After a 25-draw window no coordinate's metric sd is below 0.013, while the
    tightest posterior sds are a few thousandths.
  - Keeping the SVI metric fixed (adapting only the step size; 15db8f8) is fast but fails the
    gate. m0q took 452 s: warmup 115 s at 50–71 leapfrog steps per iteration, final step sizes
    0.084–0.095. But R-hat was 1.039 on season_scale and the minimum ESS 75 on a building,
    along directions a mean-field guide misses: the season-scale funnel, and building totals
    against their units' totals. A low-rank guide (rank 20, 2,000 steps) did not converge: its
    loss ended about 1,100 above the mean-field guide's, and its metric ran at 472 leapfrog
    steps per iteration. Both options were removed.
  - The sampler line stops here (Ben, 2026-09-25; see "Misspecification first" below). The
    NUTS coordinates and the SVI warm start stay; no further sampler work.
  - Every timed fit is capped at 30 minutes (Ben, 2026-09-25). Past the 15-minute window a fit
    has already shown it is outside, and its warmup log gives the diagnostics.
- New sampler work uses library samplers on `model.build_model`, with library options only:
  - NumPyro NUTS (`--sampler nuts`), with a diagonal or a structured dense mass matrix;
  - BlackJAX's NUTS and many-chain adaptation;
  - nutpie's Rust NUTS on the JAX log density.

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
  - Clean serial re-times at ac9e02b, all on the 2060:
    - m0q, 4 × (500 + 2000): 253 s, passes (350 s when measured alongside other jobs).
    - m1q with the solo walk-scale update, 4 × (300 + 1500): 702 s, passes (709 s before). Its
      cost is the solo update's extra block solves, not contention.
    - m0q gains nothing measurable over m0: PSIS-LOO +10.5 ± 11.1.
  - Round 2, description flags, 2 × (300 + 3000):
    - m0q + desc: 309 s, passes; PSIS-LOO about +174 over m0q.
    - m5-nocurves + desc: 1,125 s, passes.
    - m6-nocurves + desc: 1,245 s, **fails** (all-effects R-hat 9.76 on fslope, bedroom_slope and
      building; ESS 52 on the size coefficient). The per-building size slopes and the global size
      coefficient move together, and the slope scales mix slowly.
    - m7-nocurves + desc: 1,298 s, **fails** (fslope_scale[2] ESS 194).
    - m8-nocurves + desc: 1,573 s, **fails** (unit_drift_scale R-hat 1.085, ESS 52).
  - Fitting the 15-minute window by trimming draws (settings only):
    - m5-nocurves at 2 × (300 + 2300) passes: 823 s with base features, 895 s with desc.
    - m1q + desc at 4 × (300 + 1100): 883 s, fails (R-hat 1.015, ESS 379).
  - Exact block speedups: per-slot accumulation (−34–37% for walk designs) and a structured
    `a′Wa` with inverted building factors (a further −22–38%).
  - Walk designs need the solo collapsed walk_scale update. Without it walk_scale mixes 3.5×
    slower per draw, and cheap scaling moves or a covariance-shaped joint proposal don't close
    the gap. With it, an iteration costs about 3 block solves (~145 ms per chain), and four chains
    don't batch on this card. So a walk design that passes the gate needs about 15–17 min.
  - A short-warmup adaptation bug (steps sized from drift, ν frozen) is fixed.
- **Step 3. Native fits.** Fit the best candidates on each local class within 15 minutes with the
  step 1 settings, then score PSIS-LOO and the variance decomposition. These points form that
  class's sub-15-minute frontier.
- **Step 4. Structure search within 15 minutes** (Ben, 2026-09-25: explore feature space and model
  shapes to keep improving the frontier under the 15-minute limit). See the next section.

## Misspecification first (Ben, 2026-09-25)

Ben: "I believe the heuristic guidance that if a model is hard to sample then it is probably
misspecified. Can we direct our efforts toward feature engineering modeling decisions rather than
computational tweaks?" So a sampling problem is read as a diagnostic of the model or the data, and
the fix goes into the model, the features or the data, not the sampler.

**What the sampling problems point at.**
- **Heavy tails everywhere.** The residual Student-t has ν ≈ 1.9–2.6 in every design (m0q 2.6, m1q
  1.9, m8 2.2), and m8's unit effects are t with ν ≈ 2. At ν = 2 the variance is infinite: the
  model is defending against gross outliers at the row and unit level. Most of the worst rows are
  not keyword-flaggable product types: desc-v1 already flags furnished, income-restricted,
  rent-stabilized, shared, short-term, outdoor and duplex listings. In m5-nocurves + desc
  (e343847), the worst 1% of rows (473) carry 11% of the LOO deficit. They include:
  - implausible attributes, such as a "Full Floor" labelled as a studio at $28,681;
  - asks far from the same unit's other listings, such as a 1-bedroom at $2,395 against a unit
    median of $5,824, which suggests one unit ID covering different apartments. 715 rows are more
    than 1.5 times off their unit's median, with mean LOO 0.15 against 1.07;
  - other units: SRO-like rooms at 225 W 23rd St (the Chelsea Hotel, $999–1,610) and
    luxury extremes.
  Half of the worst rows are units listed once, against 24% of all rows.
- **Weakly identified terms.** The building walk has about one row per occupied half-year knot
  (median 1.2) and a median of 7 empty knots before a building's first listing. The unit scale
  makes a funnel from the units listed once (47% of all units; 51% of the units in the training rows). These are candidates for simpler,
  better-identified shapes: building drift, neighbourhood-level time terms, yearly knots, and
  column (line) effects that let a unit listed once borrow from its line.

**Results.**
- **Bedroom labels change within units.** 12.3% of the 11,713 units listed more than once
  change bedroom count between listings. 86% of those change by one, and 87% keep one square
  footage: the same apartment advertised as a studio or a junior one-bedroom, a one-bedroom or
  a flex two.
- **Unit-consistent bedrooms: +791 ± 73 PSIS-LOO on m0q** (`unitbeds-v1`, d80a714, the 592 s
  NUTS configuration; 631 s, passes). The bedroom levels use the unit's own count, the lower
  median of its listings. `bedrooms_vs_unit` carries a listing's relabel, fitted at
  +0.099 ± 0.003 per bedroom, against 0.23–0.26 for a real bedroom between units. The gain is
  on identical rows against m0q base-v1 (7229ef0), and +615 ± 79 against m0q with the
  description flags (desc-v1). Held-out ΔELPD improves by about 150. ν barely moves
  (2.59 → 2.62), so relabels were not what made the tails heavy.
- **Unit square feet: +653 ± 53 more** (`unitattrs-v1`, 403d94c; 626 s, passes). Each unit's
  size is the median of the sizes its listings state, used for every listing, so size is unknown
  on 52% of rows instead of 65%. Together with unit bedrooms: **+1,445 ± 91 over m0q base-v1**.
  ν stays at 2.6.
- **Unit label flags: +234 ± 29 more** (`unitlabels-v1`, 8914d43; 609 s, passes). Penthouse,
  garden and lower-level units, from the unit's StreetEasy label. Penthouses ask 12% more than
  other units of the same building, year and bedrooms. Total: **+1,679 ± 95 over m0q base-v1**.
- Within-unit price jumps (240 rows more than 2× off the unit's other listings, trend-adjusted)
  are mostly real changes: renovations, combined apartments, market moves. Almost none are
  furnished or short-term. A renovation mention appearing within a unit comes with only about
  +3% on the ask, which desc-v1's `renovated` flag already prices.
- Other attributes also vary within units: square feet (9% of multi-row units; stated on 35% of
  rows, 48% if filled from the unit's other listings), laundry (12%, in-building against
  in-unit) and doorman (7%; it varies across listings in 116 of 1,129 buildings).

**Order.**
1. **Data quality** (backlog "Data quality"). Audit rows by rules that do not use a model's
   residuals: within-unit consistency, attribute plausibility (price per square foot, bedrooms
   against square feet and text), unit and building identity (104 slugs on 41 lots). Decide per
   finding: correct, exclude, or add a feature. **Scoring (Ben, 2026-09-25): shared rows.** Every
   model compared, the baseline included, is refit and scored on the rows both versions keep,
   and the excluded count is reported next to the score.
2. **Features for distinct products.** SRO or hotel rooms, full floors and lofts, townhouse
   floors, penthouses, and the attributes the text states but the listing fields miss.
3. **Model shape.** Simpler time and unit terms (above), judged by PSIS-LOO and by whether the
   tails lighten (ν rising) and the geometry eases.

## Structure search under 15 minutes (from 2026-09-25)

**Goal.** Raise the most accurate gate-passing fit within 15 minutes on each thelio hardware class,
with library samplers only.
- The deprecated Gibbs sampler left a mark on the RTX 2060: m5-nocurves + desc, +9,922 PSIS-LOO
  over m0 in 895 s.
- The library path first has to reach comparable designs within the window (C.1). Then every
  candidate either buys time back or spends it better.

**Method.**
1. Screen cheaply before fitting.
   - Projection (`rentfrontier.projection`, seconds per structure) of the m8 + desc reference onto
     each candidate ranks structures the way their native PSIS-LOO does.
   - The variance decomposition shows where unexplained variation sits: features about 50%,
     building about 30%, unit 2–3%, residual 2–4%.
   - A candidate goes to a native fit only if projection says it beats the current mark.
2. Estimate its fit time before fitting.
   - NUTS cost is tree depth × gradient cost. The depth depends on the coordinates (see the NUTS
     findings above).
   - The gradient cost grows with rows × terms, plus the per-building and per-unit arrays.
3. Fit the shortlist natively, one at a time, within 15 minutes on each class. Right-size the draw
   budget to the gate (ESS > 400) and score PSIS-LOO and the variance decomposition.
4. Keep what moves the frontier; record what doesn't, in this plan and on the board.

**A. Feature space.** New features are new feature-set ids (`features.py`; `base-v2`, and so on).
They enter the design matrix, so NUTS fits them like any other design.

1. **Building covariates in the building mean.**
   - The data: stories, residential units and zip from archived building pages
     (`data/model/building-covariates-20260923`, 1,072 of 1,129 buildings); the archive's year
     built is a placeholder, so skip it.
   - A building-level column in the row predictor is exactly a regression in the building mean.
   - For NUTS, write it in the building mean: building ~ N(γ·z, τ), the same hierarchical
     centering as `unit_totals`. That avoids the collinearity with the building levels that the
     earlier PyMC screen hit.
   - Expect the gain on buildings with few rows, which carry most of the high-k PSIS rows.
   - **First result: MapPLUTO on m0q** (`pluto-v1`: era, floors, units, area per unit, building
     class, landmark, historic district, floor-area ratio, flood zone, recent alteration). NUTS on
     the 2060, the same coordinates and budget with and without it.
     - PSIS-LOO: −7.5 ± 17.0 (no measurable change).
     - Variance decomposition: features 52% → 74%, anonymous building effect 32% → 10%. Unit
       (3.4%) and residual (4.2%) are unchanged.
     - The building attributes explain about two thirds of the building-level variation, which the
       building effects were already capturing. So accuracy is equal and the description is much
       more interpretable.
2. **Location.** Buildings have latitude and longitude. Try a low-rank spatial basis over building
   locations, as building-level columns, so neighbouring buildings share information (west vs
   east Chelsea, the avenues, the High Line).
3. **Floor.** The label-derived floor and the expanded-floor sidecar (T3.2) next to the advertised
   floor label.
4. **Size and layout.**
   - A nonlinear size deviation: splines on log square feet relative to the bedroom median.
   - Bedrooms × size.
   - Bathrooms per bedroom.
5. **Description flags.**
   - desc-v1 adds about +200 but 21 columns, and on m1q it cost 1.6× the fit time.
   - Ablate the flags to find a short set that keeps most of the gain for fewer columns.
   - Later, richer text features (embeddings or topics), which need new tooling.
6. **Pruning.** Drop base-v1 columns that carry nothing (some view and window flags), to buy time
   for columns that do.
7. **External and neighbourhood data, widely** (Ben, 2026-09-25: explore and test widely from all
   sources, not just StreetEasy). Details in the next section.

**A′. External and neighbourhood data.** The listings describe the apartment. What surrounds it
comes from other sources, most of them public NYC and NYS data.

*Join and provenance.*
- **Building registry first.** Map every building to its BBL (tax lot) and BIN (building) with the
  NYC Planning GeoSearch geocoder: the address from the building slug, checked against the archived
  coordinates. Keep the registry versioned. Every external feature joins through BBL, BIN or
  coordinates.
- **Snapshots with provenance.** Each source is a dated snapshot under
  `/data1/apartments/external/<source>/<date>/`, recording the URL, query, retrieval time and
  sha256. A feature set records the snapshots it uses; run records already carry the feature
  sources.
- **As-of values.** Time-varying sources give each listing the values known by its listing date.
  That covers 311, crime, violations, permits and new stations; the 7-train extension to Hudson
  Yards opened in 2015. No future information.

*Sources and candidate features.* Building-level unless noted.

| Area | Source | Features |
|---|---|---|
| Building | MapPLUTO (DCP) | year built (replaces StreetEasy's placeholder), floors, units, lot and building area, building class, landmark or historic district, zoning |
| Condition | HPD violations and complaints; DOB permits | open violations per unit, as-of; recent alteration permits (renovation proxy) |
| Regulation | DOF rent-stabilization counts | share of stabilized units in the building |
| Energy | Local Law 84 benchmarking | Energy Star score |
| Street | LION street centerline (DCP); DOT traffic counts; street tree census | frontage street width and lanes, avenue vs side street, one-way, traffic volume, tree density on the block |
| Noise | 311 service requests | noise complaints near the building per year, by type (traffic, construction, nightlife), as-of |
| Transit | MTA subway entrances (GTFS); Citi Bike; PATH | distance to the nearest entrance, lines within 400/800 m, the 2015 Hudson Yards 7 extension |
| Schools | DOE school locations, zones and School Quality Reports | zoned elementary school and its ratings, schools nearby |
| Everyday | NYS Ag & Markets retail food stores; DOHMH restaurant inspections; OpenStreetMap | grocery and pharmacy distance, restaurant density |
| Health | NYS DOH facility locations | distance to the nearest hospital |
| Open space | NYC Parks properties | distance to a park, the High Line, Hudson River Park, the waterfront |
| Safety | NYPD complaint data | incidents near the building per year, as-of |
| Risk | FEMA and NYC flood hazard maps | flood zone |

*Unit orientation* (street vs courtyard, and the street's size).
- StreetEasy's view and exposure fields are sparse (base-v1 has `view_street`, `view_courtyard`
  and window directions).
- Add description flags ("courtyard-facing", "quiet rear", "faces the street").
- Infer orientation geometrically: the unit's window directions against the bearing of the
  building's frontage street (LION and building footprints). A street-facing unit then gets that
  street's width and traffic.
- Height against the neighbours (MapPLUTO heights) as a light and view proxy.

*Testing.*
- Add each source group as its own feature set, alone and then combined.
- Put building-level features in the building mean (the NUTS-friendly form).
- Screen by projection, then fit the best combinations natively within 15 minutes.
- The gain should show up mainly on buildings with few rows and on units listed once.
- Also watch the variance decomposition. Named neighbourhood features that take over building-level
  variance make the description more interpretable, even at equal PSIS-LOO.
- Census demographics (ACS) are deprioritized.
  - Ben's concern is the lag. Tracts only have 5-year estimates, published about a year after
    their window closes, so an as-of value is centred 3–4 years before the listing.
  - A period-matched window (centred on the listing year) exists only through about 2021.
  - With about 20 tracts under our 1,129 buildings, a static tract value adds little beyond the
    building levels. The within-tract change over time that could add something is blurred by the
    averaging and by tract-level sampling error.
  - Resident demographics also raise fair-housing concerns in a rent model.
  - If tried at all: period-matched windows, screened by projection, after the sources dated to the
    day (311, permits, violations, crime, transit).

**B. Model shapes.** Parameterization and shape switches in `model.ModelConfig`.

1. **Walk knot spacing.** Half-year to yearly knots halve the per-building walk parameters
   (about 38,000 steps), the largest array in walk designs. Measure the PSIS-LOO cost against the time saved;
   the saved time can go into slopes or features.
2. **Bedroom curves.** These are the market curve per bedroom group, dropped in the nocurves
   designs to save about 200 global columns. Yearly knots would cost 51 columns instead,
   and could win back part of the curves' gain at a fraction of the cost.
3. **Trend knot spacing.** Quarterly costs nothing measurable against monthly; test half-year.
4. **Per-building slopes.**
   - The bedroom slope pays (+2,200 over m1q).
   - The size and bath slopes (m6) did not mix under the deprecated Gibbs sampler.
   - Try them under NUTS, or a single size slope.
5. **Unit effects.**
   - Student-t units (+1,200) and unit drift (+360) did not mix under the deprecated Gibbs sampler
     (21–26 minutes).
   - Candidates under NUTS: as they are, with a fixed unit ν, or drift only for units with a long
     history.
6. **Noise.**
   - Heteroskedastic noise by bedroom group or by price basis. The earlier building-level residual
     scale was suggestive at +45 ± 29.
   - Fixed ν, as a speed option.
7. **Pooling structure.** A neighbourhood or spatial level between market and building, which
   pairs with A.1–A.2.
8. **Column ("line") effects** (Ben, 2026-09-25). A level between building and unit for units that
   stack vertically ("4C", "7C", "12C"), so a unit listed once borrows from its line's history. It
   also carries the unit-orientation features (A′). The plan is in the
   [research backlog](model/research-backlog.md), under "Column ("line") effects".

**C. Implementations within 15 minutes.**
1. **NUTS in NUTS-friendly coordinates on the CPU.**
   - Exact reparameterizations: trend levels, zero-sum season, units centred within buildings.
   - If NUTS reaches m0q/m1q/m5 within 15 minutes, it can fit any shape `build_model` expresses
     without sampler code. That includes the t-unit, drift and slope shapes the deprecated Gibbs
     sampler could not mix.
2. **Per-design draw budgets and chain counts** sized to the gate on each hardware class.
3. **Library samplers only** (Ben, 2026-09-25): the custom Gibbs sampler is deprecated. Other
   libraries (BlackJAX NUTS, nutpie) run on the same model if NumPyro's NUTS falls short.

**Order.** By expected PSIS-LOO gain per second of fit time:
1. C.1: NUTS on m0q, m1q and m5 in the new coordinates. Every later step needs a library fit that
   reaches these designs within 15 minutes. m0q passes in 888 s on the 2060. m1q's building walk
   is next, with yearly knots (B.1) if quarterly knots stay too slow.
2. A.1 and A.2 (building covariates and location) on the best NUTS design. In parallel, since it
   needs no fits: the building registry (A′) and the first sources: MapPLUTO, subway entrances,
   LION street width and 311 noise;
3. B.1 (yearly walk knots), reinvesting the saved time in B.2 (yearly bedroom curves) or A.5;
4. the t-unit and drift shapes under NUTS (B.5);
5. A.5 (flag ablation), A.6 (pruning), B.6 (noise) and A.3–A.4.

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

0. **Clean the data so the model can be less defensive** (Ben, 2026-09-25). Find and fix, or
   document and exclude, the rows the heavy tails protect against. Then test whether lighter tails
   (larger ν, Gaussian noise) win on the cleaned data, which would also speed up the samplers. The
   plan is in the [research backlog](model/research-backlog.md), under "Data quality".

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

The dashboard and board are generated from the run records; see them for the live frontier.

**Within 15 minutes on thelio (2026-09-25).** Gate-passing fits only, custom Gibbs on the RTX 2060:

| Design | Settings | Fit time | PSIS-LOO ΔELPD vs m0 |
|---|---|---:|---:|
| m0q | 4 × (500 + 2000) | 253 s | +10 |
| m0q + desc | 2 × (300 + 3000) | 309 s | +184 |
| m1q | 4 × (300 + 1500) | 702 s | +7,489 |
| m5-nocurves | 2 × (300 + 2300) | 823 s | +9,708 |
| m5-nocurves + desc | 2 × (300 + 2300) | 895 s | +9,922 |

- m5-nocurves + desc is the most accurate fit inside the window. Its ESS of 406 barely clears
  the gate of 400, and at 895 s it is just under the 15-minute limit.
- Library NUTS (NumPyro) in the NUTS-friendly coordinates passes L0–L5 on the CPU (40–909 s) and
  m0q on the RTX 2060 in 888 s (PSIS-LOO 40,607.5, equal to the deprecated Gibbs m0q). m1q
  and m5 do not yet fit within the window on NUTS.

The table below is the Modal H100/H200 frontier, recorded when this plan was written.

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
