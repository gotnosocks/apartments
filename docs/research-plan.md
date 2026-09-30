# Research plan: the PSIS-LOO × fit-time frontier

Living plan for the modeling work. Ben set its objective on 2026-09-24: optimize the Pareto frontier of
PSIS-LOO accuracy and fit time. The [board](model/leaderboard/leaderboard.md) and the
[dashboard](dashboard.md) (http://thelio.tail3983e0.ts.net:8500) apply the rules below. The goals, data
contract and pitfalls in [the 2026-09-24 brief](brief-2026-09-24.md) and the
[project intent](project-intent.md) still apply. This plan replaces the brief's evaluation contract
(§4) and first tasks (§5).

## Objective

Push the frontier of **PSIS-LOO ΔELPD** against **fit time on thelio**. That means more accurate
descriptions of every listing for the same fit time, or the same accuracy sooner. Product decisions stay
Ben's. On 2026-09-29 he chose the Gibbs `m5-nocurves` fit with the building facts
(`unitdescpluto-v3`) as the app's model: the most accurate gate-passing fit within the 30-minute
window (tied with the same design without them), and it names most of the differences between
buildings. On 2026-09-30 he switched the app to the same design refit without the quarantined
listings (`quarantine-v1`, a tie on shared rows), with the site saying which listings are
quarantined and why (earlier on 2026-09-29 `m5-nocurves` +
`unitdesc-v1`, and from 2026-09-26 the best NumPyro fit); it ships through the summary output to the
[listings site](site.md). West Village is on hold.

## Interpretability and elegance (Ben, 2026-09-29)

"One of the goals of the project is that the selected model is interpretable and elegant. There
should be a simple conceptual explanation for the role of each term in the model that makes sense
to a reasonable user. The model should reflect the qualities of an apartment and its surroundings
that a typical apartment renter thinks about when choosing a place to rent."

- **Rule.** A term can enter the selected model only with a one-sentence explanation a renter
  would accept (the glossary below). A term without one is a research tool, not a selection
  candidate. PSIS-LOO per fit time is still the frontier; this is a gate on what gets selected.
- **Features** should be qualities renters weigh: size and layout, light and views, floor,
  outdoor space, condition and renovation, amenities, the building, the block and
  neighbourhood, transit, noise, schools, groceries, parks.
- **Fewer, clearer terms.** Overlapping terms are hard to explain and, as the trend-plus-walk
  design showed, hard to sample.
- **Not model terms.** Sampling coordinates, warm starts and samplers change how a fit runs, not
  what the model says. Data rules are cleaning and must be explainable as such ("one apartment,
  one id").
- **Visualization (Ben, 2026-09-29).** "A lesser goal or element of the desire for descriptive,
  interpretable features that is perhaps better described as 'features that work well in a data
  visualization'", for example "a visualization geo-spatial-temporal model of rents stratified by
  number of bedrooms". "Again a lesser goal, but something to keep in mind." Terms that compose
  into a map (the market over time, the bedroom count, a smooth location surface) serve it;
  anonymous per-building effects do not. This is guidance for the research, not a selection rule.

**Glossary** (terms in the current designs, and what each means to a renter):

| Term | What it says about a listing |
|---|---|
| Market trend and season | What Chelsea rents are doing overall at that time, and in that month of the year. |
| Listing attributes (bedrooms, baths, size, floor, amenities, views, windows) | What the apartment offers, priced the same way everywhere (unless a design adds the per-building slopes below). |
| Price basis (`current_capture_ask`) | A data control, not a quality: 0.3% of rows record the price shown when the page was captured, not the listing's first advertised price (later prices can be cut). |
| Unit bedrooms and relabels (`unitbeds-v1`) | The apartment's real bedroom count; a "flex" or "junior" bedroom adds about a third to 40% of a real one (0.085–0.099 against 0.23–0.26 in log rent). |
| Unit size, floor and label flags (`unitattrs`, `unitfloor`, `unitlabels`) | The same apartment keeps its size across listings; when a listing states no floor, the unit label's floor is used (if the building is that tall); penthouses, garden and lower-level units are priced as such. |
| Description flags (`desc-v1`) | What the ad says: renovated, washer-dryer, outdoor space, no fee, furnished, and so on. |
| Building facts (`pluto-v1`, `unitdescpluto-v1`; `unitdescpluto-v2` without the flood-zone flag; `unitdescpluto-v3` also dating alterations by the latest) | What the city records about the building: when it was built, its height and number of apartments, the space per apartment, how densely the lot is built, its type (walk-up, elevator, condo, a small mixed-use building of a few apartments over a store or office, or other), landmark or historic-district status, flood zone and a recent alteration; an "unknown" flag where the city's record has no usable value. |
| Location (`unitdescplutoloc-v1`) | What buildings nearby rent for: a smooth premium over the map, shared by buildings a few blocks apart (for example the western blocks near the High Line). |
| Transit (`unitdescplutotransit-v2`) | The walk to the nearest subway station, and how many subway lines stop within a 10-minute walk, counting the stations open at the time of the listing. |
| Which way the apartment faces (`unitfacing-v2`) | Whether the apartment looks onto its building's street (an avenue, a wide street such as 14th, or a side street), onto the back, both front and back, or only to the sides, from its window directions, front/rear unit labels, ad text and street or courtyard views. |
| Building level | This building's premium beyond its apartments' features: its location, quality and management. |
| Building trend or walk | How that premium has moved over time, for example a renovation or a changing block: steadily (the trend) or along a path that can change direction at each knot, joined by straight lines (the walk). Sum-to-zero walks make it relative to the market, so "the market" and "this building" never overlap. |
| Bedroom slope (m5) | In some buildings the larger apartments carry an extra premium or discount. |
| Size and bathroom slopes (m6–m8) | In some buildings extra space or an extra bathroom is worth more or less than usual. |
| Bedroom-group market curves (m2, m4, m5–m8; not the nocurves designs) | Studios, 2- and 3+-bedroom apartments can follow their own market path over time. |
| Line (column) effects | Apartments stacked in the same column share a layout and exposure. |
| Unit level | This apartment's own premium beyond its listed features: layout, light, condition. |
| Unit drift (m8) | This apartment's ask moving steadily over time on its own. |
| Student-t unit levels (m7, m8) | A few apartments differ a lot from their building (a penthouse, an oddity) without pulling the others' estimates. |
| Heavy-tailed residuals (Student-t) | Some asks are unusual for reasons the data don't show. |

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
- **Eligible.** Passes the gate, is interpretable (every term in the glossary under
  "Interpretability and elegance"), and has a PSIS-LOO score.
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

## Current effort: the frontier within the fit window on thelio (from 2026-09-24)

Ben asked for a research effort on the part of the frontier that fits in under 10 minutes, with
variance decomposition as a measure of modeling quality and projection to search for more
efficient models. On 2026-09-25 he widened the window to 15 minutes per fit, and on 2026-09-29
to **30 minutes per fit**, with a hard stop at **35 minutes** ("to keep up the pace of
iteration"). It runs
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
- The custom Gibbs sampler was **deprecated** on 2026-09-25 (Ben: not for new work) and
  **reinstated on 2026-09-29**, together with the other options based on exact mathematical
  simplifications (Ben: "the custom sampler and other options based on mathematical
  simplifications are no longer deprecated").
  - `run.py --sampler gibbs` fits any design that `gibbs.build_design` has exact updates for.
    Designs with terms it lacks (market drift, building trends, coarse, Student-t or
    sum-to-zero walks, walk masks and anchors, line effects), or without every base term, are
    refused there.
  - Exact coordinates and collapsed updates are back in use next to library NUTS.
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
  - Across samplers and devices, m0q's PSIS-LOO agrees. Against the Gibbs m0q
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
  - Every timed fit is capped: at 30 minutes from 2026-09-25, and at 35 minutes from 2026-09-29
    (Ben). Past the window a fit has already shown it is outside, and its warmup log gives the
    diagnostics.
- Samplers for new work (from 2026-09-29, when Ben reinstated the custom Gibbs sampler), all on
  `model.build_model`:
  - the custom Gibbs sampler (`--sampler gibbs`), for the designs it has exact updates for;
  - NumPyro NUTS (`--sampler nuts`), with a diagonal or a structured dense mass matrix and the
    exact coordinates above;
  - BlackJAX's NUTS and many-chain adaptation, and nutpie's Rust NUTS on the JAX log density.

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
- **Step 3. Native fits.** Fit the best candidates on each local class within the window (30
  minutes from 2026-09-29) with the step 1 settings, then score PSIS-LOO and the variance
  decomposition. These points form that class's frontier within the window.
- **Step 4. Structure search within the window** (Ben, 2026-09-25: explore feature space and
  model shapes to keep improving the frontier under the 15-minute limit; 30 minutes from
  2026-09-29). See the next section.

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
- Floors from unit labels, unchecked (`unitfloor-v1`, abca5b7), gave 16 divergences and only
  +18 PSIS-LOO. In 121 buildings the label's number is not a floor ("24A" in a 4-storey
  building): 421 of the 3,445 filled floors exceed MapPLUTO's floor count + 1. `unitfloor-v2`
  fills a floor only where the building is tall enough (3,065 rows). Listed floors have the
  same problem on 474 rows, and one registry match looks wrong ("The Cortland", a new tower,
  has a 3-storey lot). Both go to the data audit.
- **Checked label floors: +28.7 ± 7.3** over `unitlabels-v1` (`unitfloor-v2`, 55f745f; 605 s,
  passes, no divergences). That is +1,708 ± 95 over m0q base-v1, the best feature set so far.
  Features now carry 55.9% of the variance (from 52%), buildings 28.9% (from 31.6%), units
  2.7% (from 3.5%).
- **One linear trend per building: +3,165 ± 93** (`m0q-btrend`, 55f745f, with `unitlabels-v1`;
  634 s, passes). That is 1,129 numbers, each centred on its building's mean month, against the
  walk's 34 steps per building. Trends are ±1.5% a year between the 5th and 95th percentiles
  (scale 0.012). Against m0q base-v1 the gain is +4,844 ± 130 PSIS-LOO within 11 minutes.
  The walk still does better: the Gibbs m1q (base-v1) is 2,636 ± 152 ahead, so part
  of each building's path is not linear. The next shape between the two is a coarse, smooth
  building-time term.
- With `unitfloor-v2` the trend gives 45,484.9 (0962ea7; 646 s, passes): +4,891 over the m0
  baseline, the best gate-passing library fit so far.
- **A walk with knots every 2 years, around the trend** (`m1-btrend-walk24`, 0962ea7, walk
  levels): 1,150 s, **fails**. building_trend_scale has R-hat 1.077 and ESS 35 because a walk
  already holds a trend: the two trade off, and the fitted trend scale fell to 0.005. PSIS-LOO
  is 48,748.2, which is +3,263 ± 88 over the trend alone and +666 ± 128 over the Gibbs
  half-year walk (m1q, base-v1). Held-out ΔELPD is +237.6, against −185.4. Next: the coarse
  walk alone, at 2- and 3-year knots.
- **The walk alone, knots every 3 years** (`m1-walk36`, 937c466): **771 s**, within the window.
  It narrowly misses the gate: walk_scale ESS is 368 against 400 (max R-hat 1.008), and there is 1 divergence.
  PSIS-LOO is 48,096.7: +2,612 over the linear trend, and level with the Gibbs
  half-year walk (m1q, 48,082.6) at a fifth of the knots. Building over time takes 1.1% of the
  variance, and the residual falls to 3.1%.
- **The walk alone, knots every 2 years** (`m1-walk24`, 937c466): **812 s**, fails on walk_scale
  (R-hat 1.019, ESS 200). PSIS-LOO is 48,742.7, the same as with the trend (48,748.2), so the
  trend added nothing. It is +646 over the 3-year walk and +660 over the Gibbs m1q.
- **Both Normal coarse walks fail on walk_scale;** their every-element R-hat is fine (1.012 and 1.018). The fitted 2-year steps have kurtosis 7.3:
  most buildings move little and a few jump, so one Normal scale compromises. Next: Student-t
  walk steps (`walk_t`, df estimated), `m1-twalk36` and `m1-twalk24`.
- **Student-t steps, df estimated** (`m1-twalk36`, e6718f5): 845 s, fails. The df is poorly
  identified by latent steps (walk_nu 2.64 ± 0.19, R-hat 1.06, ESS 80). PSIS-LOO is 48,211.5,
  +115 over the Normal 3-year walk, so heavy-tailed steps fit better. Next: df fixed at 3
  (`walk_nu_fixed`; `m1-t3walk36`, `m1-t3walk24`).
- **df fixed at 3** (9fa29ee). Both walks fit within 15 minutes, and both fail on walk_scale and on the every-element R-hat (see the correction below):
  - 3-year (`m1-t3walk36`): 817 s, walk_scale ESS 292, PSIS-LOO 48,201.5;
  - 2-year (`m1-t3walk24`): 859 s, walk_scale ESS 297 (and a traced building at R-hat 1.012),
    **PSIS-LOO 48,944.1**, the best yet: +201 over the Normal 2-year walk and about +8,350
    over the m0 baseline.
- **Why walk_scale mixes slowly:** at 2-year knots, 529 of 1,128 buildings have fewer than 2
  training rows per knot of their data range, a third of the walk levels (2,269 of 6,551).
  Those levels are mostly prior, and they make the scale's funnel: the walk is more flexible
  than the data support. Next: walks only where the data can carry one
  (`walk_min_rows_per_knot`; `m1-t3walk24-min2`, `m1-walk24-min2`). The other buildings follow
  the market trend at their building level.
- **Masking data-poor buildings did not fix it** (`m1-t3walk24-min2`, 345628a): 865 s,
  walk_scale ESS 346, and a building at R-hat 1.018. **The specification problem is where the
  walk is anchored.** Every building's walk is 0 at the panel's first month, so its building
  level, and the building prior, refer to its level in early 2010. A building first listed in
  2020 reaches that level through ten years of prior-only walk steps, and the building prior
  ties the walk scale to them. Next: each walk is anchored at 0 at its building's own anchor
  knot (`walk_anchor_data`; `m1-t3walk24-anchored`). The building level is then its level
  where it is observed.
- **Anchoring did not fix it either** (d1867e8): 934 s, walk_scale ESS 195, held-out ΔELPD
  +268.4, PSIS-LOO 48,992.6 (the best yet).
- **Correction (PR #25 review).** An earlier version of this entry blamed the coarse walks'
  failures on walk_scale ESS alone and called them slow mixing, not misspecification. The
  records say otherwise. Every Student-t walk run also fails the every-element check (R-hat <
  1.05 over every walk and building value):

  | Run | Every-element R-hat | Elements > 1.05 |
  |---|---:|---:|
  | m1-t3walk24-anchored (d1867e8) | 1.318 | 22 |
  | m1-t3walk24 (9fa29ee) | 1.615 | 12 |
  | m1-t3walk36 (9fa29ee) | 1.616 | 10 |
  | m1-twalk36 (e6718f5) | 2.133 | 8 |
  | m1-t3walk24-min2 (345628a) | 1.058 | 1 |

  m1-walk36 (937c466) also had 1 divergence. About half of the flagged elements are prior-only
  knots outside a building's data range, which is heavy-tail noise. The worst are chains that
  sit in different modes inside the data range, each traced to one or two odd rows:
  - 299 10th Ave: a lone 2011 row labelled `spac1`, a $5,300 "studio", where the other 29 rows
    ask $2,000–3,300;
  - 181 9th Ave: a 2022 `1h` at $1,650, against six others at $2,900–5,500;
  - 227 W 17th: five $30,000–35,000 lofts, with the 7th floor under three unit IDs (`7thfl`,
    `7th-fl`, `7th-floor`).

  The Normal walks do not split this way (every-element R-hat 1.012 and 1.018). With
  heavy-tailed steps, a walk can take up a single outlier as a building jump or leave it alone,
  and the chains find both. More draws will not fix that. It is a data and specification
  signal, which is Ben's principle. Next: unit identity (the same physical unit under several
  labels) and non-residential or implausible rows, as data-audit rules scored on shared rows.
- **Data rule `unit-labels-v1`: one unit id per physical unit.** 521 groups of units in one
  building have the same label written differently: "4-FLR" and "4FLR", "02" and "2",
  "UNIT4J" and "4J", and the three spellings of 227 W 17th's 7th floor. Merging them removes
  534 unit ids (22,144 → 21,610), and 641 fewer training units are listed once. Rows are
  unchanged, and the rule applies after the held-out split is drawn (the row split depends on
  unit ids), so it scores on identical rows. `run.py --data-rules` applies it, and the run
  record lists it for the scorers.
- **With the rule, the best passing library (NUTS) fit is 45,815.1** (`m0q-btrend`, `unitdesc-v1`,
  `--data-rules unit-labels-v1`, df5dacb; 745 s, passes). That is +188.6 ± 25.9 over the same
  design without the rule on identical rows, and **+5,221 over the m0 baseline**. (The
  Gibbs m5-nocurves + desc still passes at +9,921.7 on the same hardware.)
- With the rule, the anchored 2-year t walk (`m1-t3walk24-anchored`, `unitdesc-v1`) scores
  49,394.5, the best overall (+8,801 over the m0 baseline). It still fails, in 1,031 s, and
  the rule does not fix the split chains (PR #26 review).
  - The every-element maximum falls from 1.318 to 1.209, but the elements above 1.05 rise from
    22 to 36.
  - The worst is still 299 10th Ave's `spac1` row, which the rule does not touch. The feature
    set also changed (`unitfloor-v2` to `unitdesc-v1`).
  - 19 gate quantities fail: two traced buildings (R-hat 1.032; ESS 150), walk_scale (R-hat
    1.015, ESS 182) and sigma (R-hat 1.011), among others.
- **The Normal 3-year walk with the rule nearly passes** (`m1-walk36`, `unitdesc-v1`,
  `unit-labels-v1`, 4 × (250 + 650), df5dacb): **880 s**. walk_scale ESS is 401,
  every-element R-hat 1.014, no divergences. It fails only on the market trend point
  trend[144] (R-hat 1.0106 against 1.01). Held-out ΔELPD is +137.4. The Normal steps give no
  split chains. The trend point mixes slowly because a common shift of every building's walk
  at a time trades off against the market trend there: only the priors separate "market up"
  from "every building up". Two ways out: sum-to-zero walks across buildings (a model change:
  the market trend carries all common time variation), or a per-knot mean plus zero-sum split
  of the walks (an exact coordinate, as for the building totals). Ben's call.
  - **Ben (2026-09-26) chose the model change: sum-to-zero walks** (`walk_zero_sum`,
    `m1-walk36-zs`, 06580e6). The likelihood uses each knot's walk less its mean across
    buildings, i.e. zero-sum walk steps across buildings, so the market trend carries all
    common time variation. **It fixes the trend:** the worst market-trend R-hat drops from
    1.0106 to 1.0039, and no trend point is above 1.01. PSIS-LOO is unchanged (48,507.7,
    −2.8 ± 4.2 against the walk without the constraint).
  - The fit (902 s) still fails on walk_scale (R-hat 1.013, ESS 205; 401 and 368 in the
    earlier Normal 3-year walks, so near the gate anyway). Like line_scale, walk_scale is a
    centred scale over thousands of weakly informed effects and mixes slowly, which no model
    change is expected to fix. More draws or a sampling coordinate are back with Ben.
  - **In the 30-minute window it passes on more draws** (4 × (250 + 1300), ab2a7df,
    2026-09-29): 1,300 s, R-hat 1.0036 (trend[132]), walk_scale ESS 773, every-element R-hat
    1.007, no divergences. walk_scale needed draws, not a new coordinate. PSIS-LOO is 48,501.6
    (−6.1 ± 5.0 against the 650-draw fit, i.e. Monte Carlo noise): **+2,686.5 ± 79.4 over
    `m0q-btrend`** on identical rows and +7,908 over m0. Held-out ΔELPD is +138.7. It is the
    best passing library (NUTS) fit.
- **The reinstated Gibbs sampler: m5-nocurves with `unitdesc-v1` and `unit-labels-v1`**
  (ab2a7df, 2026-09-29, RTX 2060). The design has building walks and a bedroom premium per
  building, and the sampler integrates the units out.
  - At 2 × (300 + 3000) it failed only on sigma (R-hat 1.011, ESS 388) in 1,128 s. At
    2 × (300 + 3600) it **passes in 1,326 s**: R-hat 1.006, ESS 580 (sigma), every-element
    R-hat 1.010.
  - **PSIS-LOO 52,431.4, +11,837.5 ± 174.8 over m0**, the most accurate passing fit within 30
    minutes. On identical rows that is +6,616.3 ± 136.7 over `m0q-btrend`, +3,929.8 ± 111.1
    over the NUTS sum-to-zero walk, and +1,915.8 ± 93.4 over the Gibbs m5-nocurves + desc
    (desc-v1, no rule). Held-out ΔELPD is +520.1. 0.8% of rows have k > 0.7 (0.24% for
    `m0q-btrend`); 0.9% are over the threshold for its 1,200 draws (0.675).
  - Variance: market and time 8.4%, features 54.0%, building 29.3%, building over time 2.4%,
    building slopes 1.7%, unit 1.9%, residual 2.5%.
  - Its walks are not sum-to-zero; the Gibbs sampler refuses `walk_zero_sum`. So some common
    time variation can sit in "building over time" instead of the market, and only the priors
    separate the two, as in `m1-walk36` above. Its market-trend points pass the gate here.
  - The common part is negligible in this fit. Over the kept draws, the walks' mean across
    buildings has a posterior mean of at most 0.05% at any knot (log scale), and 95% of draws stay
    within 1.3% at every knot. That compares with a market trend spanning 59% and a spread of 18%
    across buildings at the last knot. The prior already puts it there: the mean of 1,129
    independent walks moves about √1,129 ≈ 34 times less than one walk, so the market trend
    takes nearly all common movement.
- **Line ("column") effects within buildings** (`m0q-btrend-lines`, `unitdesc-v1`,
  `unit-labels-v1`, 4224e62; Ben's backlog). Units stacked vertically share an effect, taken
  from the unit label (23C and 4C are line C; 1204 and 304 are line 04; 2ND, 4TH and 4THFL
  are the floor-through line), for lines with at least 2 training units: 2,871 lines holding
  12,996 units, including 4,987 of the 10,628 training units listed once. The fit took 810 s.
  - **PSIS-LOO +175.6 ± 23.9** over the same design without lines, on identical rows
    (45,990.7). Held-out ΔELPD is about unchanged (−170.6 against −173.4).
  - line_scale is 0.039, and unit_scale falls from 0.078 to 0.072.
  - It fails only on line_scale (R-hat 1.028, ESS 200). The every-element R-hat is 1.026 and
    there are no divergences. A line's effect trades off against its 2–4 units' effects, the
    same pattern as the walk scale. The fixes are the same two kinds: a model choice (lines
    with at least 3 units), or centring units on their line (as `unit_totals` centres them on
    their building). Ben's call.
  - **Ben (2026-09-26) chose the model change; it does not help** (`line_min_units=3`,
    `m0q-btrend-lines3`, 9486254; the code was reverted). In 791 s, line_scale still fails
    (R-hat 1.018, ESS 172), and PSIS-LOO is −24.2 ± 8.0 against lines of 2 or more units
    (+151.4 over no lines).
  - The chains show why: they agree on line_scale (means 0.0367–0.0375, within-chain sd
    0.0015), its autocorrelation is 0.70 at lag 1 and gone by lag 50, and its correlation with
    unit_scale is only −0.21 (−0.15 for 2-unit lines).
  - So a line does not trade off against its units, as this entry first said. line_scale is a
    hierarchical scale over about 2,000 centred line effects and mixes slowly, like
    walk_scale. That is the cost of centred effects, not a misspecification, and it is fixed
    by more draws or by a sampling coordinate (partial non-centring, as `unit_partial` does
    for units). Back to Ben.
- **Listed floors above a building's MapPLUTO height** (407 rows in 11 buildings) are mostly in
  new towers: 507 West Chelsea (listed up to 33, MapPLUTO 13), One Hudson Yards, Avalon West
  Chelsea, The Cortland and One High Line. The listings are right; the lot's floor count is
  stale or the registry matched the wrong lot. Using the listings' highest floor as the height
  in the label-floor check would add a floor to only 17 rows, so it was not pursued. The
  registry matches for new towers go to the data audit.
- For the data audit, from the PR #28 review:
  - some numbered "lines" merge different stacks: 270 units in about 135 numbered lines have
    a label floor more than 2 above their building's highest listed floor (The Caledonia's
    4907, 5007 and 5110 in a 24-floor building; The Tate; The Sierra; The Westminster), so
    their labels are probably unit numbers, not floor plus line;
  - 13 floor-through units appear under two spellings that `unit-labels-v1` does not merge
    ("5TH" and "5THFL", "4FL" and "4THFL", "2ND" and "2NDFL").
- For the data audit, from the PR #26 review:
  - `unit-labels-v1` may join renumbered units ("09" and "9", "08" and "8" at 228 8th Ave);
  - with the units split, the rule would join 77 held-out units (142 rows) to training units,
    so `run.py` refuses data rules on the units split.
- **Description flags on the unit features, with the building trend** (`m0q-btrend`,
  `unitdesc-v1`, acab950): 697 s, passes (R-hat 1.006, ESS 634). PSIS-LOO is 45,626.5:
  +141.6 ± 28.1 over `unitfloor-v2`, and **+5,033 over the m0 baseline**. It was the best
  gate-passing library fit until the unit-labels-v1 rule (below).
- Within-unit price jumps (240 rows more than 2× off the unit's other listings, trend-adjusted)
  are mostly real changes: renovations, combined apartments, market moves. Almost none are
  furnished or short-term. A renovation mention appearing within a unit comes with only about
  +3% on the ask, which desc-v1's `renovated` flag already prices.
- Other attributes also vary within units: square feet (9% of multi-row units; stated on 35% of
  rows, 48% if filled from the unit's other listings), laundry (12%, in-building against
  in-unit) and doorman (7%; it varies across listings in 116 of 1,129 buildings).
- **Data rule `quarantine-v1`: the divergence review (Ben, 2026-09-29).**
  - **Queue.** The served fit's leave-own-row-out estimates picked 664 candidate rows: asks more
    than 1.5× off the estimate, PIT outside [0.002, 0.998], or Pareto k above 0.7. Text detectors
    over all rows (commercial, location, SRO, income-restriction and short-stay wording) found
    the rest. Of the 143 rows quarantined, 45 came from the queue and 98 from the detectors.
  - **Rule.** As in the earlier scope review (`config/reviews/`), a large residual only puts a row
    in the queue. What excludes it is the ad's own words, or official data: MapPLUTO shows the
    registry lot has no apartments, or a unit label shows it is not an apartment.
  - **What is quarantined.** 143 rows in 55 buildings. Each has its reason and a quote from the ad
    (or the MapPLUTO record) in `config/reviews/chelsea-divergence-quarantine-20260929.jsonl`:
    - 10 non-residential offers: retail, offices, a recording studio, commercial condos and
      lofts, and a "full floor" at $28,681 in an office building with no apartments.
    - 36 ads that place the apartment elsewhere:
      - 8 on Park Slope's Seventh Avenue, geocoded to Manhattan's;
      - East 15th and East 19th Street ads filed as West;
      - ads that correct their own address;
      - AVA High Line, SoHo, Murray Hill and East Village ads filed at other addresses;
      - four at "the-amanda-i" that the ads place on West 22nd Street or in the East Village;
      - all 11 rows of the registry page "103-8-avenue". MapPLUTO records its lot, 111 Eighth
        Avenue, as an office building with no apartments, and some of its ads name other
        buildings.
    - 83 outside the product the model prices:
      - 68 SRO rooms with shared or communal baths, in six buildings;
      - 14 income-restricted apartments;
      - a room share.
    - 9 short-stay-only offers.
    - 1 ask net of a departing tenant's $2,200 monthly incentive.
    - 4 bedroom counts that the ad contradicts, for example a "studio" whose ad and other
      listings say two bedrooms.
  - **Kept.** Penthouses, lofts, townhouses and rent-stabilized units stay in. So do furnished
    and "short or long term" offers: the 305 kept rows that mention short-term stays have a median
    ask of 1.00× the estimate. Some rows stay in, unresolved:
    - Three studios at 225 W 23rd St ask $999–1,610, against $3,450–3,950 for studios of the same
      size there in the same months. They have no ad text that says why.
    - Two the-amanda-i ads name "22nd and 8th" (a block from the registry address) and, in
      template text, Williamsburg.
  - **How it applies.** The rule runs after the split. It drops the rows from the fit and the
    held-out set, so every other row keeps its split. Every reader that re-applies a run's rules
    refuses a rule file that differs from the run's hash. The board's paired scores (PSIS-LOO and held-out)
    leave out the quarantined rows for every entry, so all entries share one population.
  - **Cost of these rows in the served fit.** Its 139 quarantined training rows average −0.99
    PSIS-LOO per row, against +1.11 for all rows.
  - **Result: a tie.** The served design was refit with the rule (`m5-nocurves` +
    `unitdescpluto-v3` + `unit-labels-v1` + `quarantine-v1`, Gibbs 2 × (300 + 3600), fef2aa5,
    RTX 2060). It took 1,361 s and passes the gate (R-hat 1.0043, ESS 694).
    - On the rows both fits keep, PSIS-LOO is +8.9 ± 13.5 (47,235 rows) and held-out +2.7 ± 3.1
      (5,260 rows) over the served fit.
    - ν is 2.10 ± 0.04, against 2.06 ± 0.03: the tails barely lighten.
    - The 143 rows are errors or out-of-scope offers, 0.27% of the data. Dropping them leaves the
      scores on the other rows unchanged within error.
    - The rule's value is in what the model serves. Ben switched the app to this fit on
      2026-09-30 and asked that the site say which listings are quarantined. The site lists all
      143 at `/quarantined`, and on their building, unit and listing pages, with the review's
      reason and no estimate. The 20 building pages that had only quarantined rows, including
      the office lot at 103 Eighth Avenue and three Park Slope addresses, now redirect to that
      list.
    - A first draft of the file (131 rows, be61586) was also a tie: +3.6 ± 14.1 and +2.9 ± 2.4.
      That fit is archived under `runs-archive/quarantine-draft-2026-09-30`.

- **Data rule `quarantine-v2`: a second review over every listing (2026-09-30).** It keeps all
  143 rows of v1 and adds 15, each with its quote, in
  `config/reviews/chelsea-quarantine-v2-20260930.jsonl`:
  - six ads that locate the apartment on another street: four "335 West 29th" studios "located on
    35th st & 8th ave", a 220 West 24th ad "located on tree-lined west 21st street", and a 421
    West 21st ad "situated on west 22nd street";
  - nine bedroom counts the ad flatly contradicts, found by comparing the count the ad's first
    sentence states with the record, dropping hedged wording such as "convertible" or "1.5
    bedroom". For example, Verde Chelsea 5A is recorded as one bedroom, and its ad says "1,686
    square foot three-bedroom home".
  - **Result: a tie.** The served design was refit with `unit-labels-v1` + `quarantine-v2`
    (7ed6c55, 1,363 s, passes). Against the v1 fit (fef2aa5), on the rows both keep, PSIS-LOO is
    −6.3 ± 9.0 and held-out −1.3 ± 1.4; ν stays at 2.10. The 15 rows were not badly fit (+0.4 PSIS-LOO
    per row in the served fit): they are wrong data, not outliers.
  - Paired scores on the board now leave out every row either quarantine drops (158).

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

## Structure search within the fit window (15 minutes from 2026-09-25, 30 from 2026-09-29)

**Goal.** Raise the most accurate gate-passing fit within the window (30 minutes from 2026-09-29)
on each thelio hardware class, with the Gibbs sampler or NUTS (library samplers only from
2026-09-25 until 2026-09-29).
- The mark on the RTX 2060 (2026-09-29) is the Gibbs m5-nocurves with `unitdesc-v1` and
  `unit-labels-v1`: +11,838 PSIS-LOO over m0 in 1,326 s. The best NUTS fit is the sum-to-zero
  walk, +7,908 in 1,300 s.
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
3. Fit the shortlist natively, one at a time, within the window on each class. Right-size the draw
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
   - **On the app's design** (`unitdescpluto-v1` = `unitdesc-v1` plus the 22 building columns;
     Gibbs m5-nocurves, `unit-labels-v1`, 2 × (300 + 3600), c84f228, RTX 2060, 2026-09-29).
     - It passes in 1,369 s (44 s more than without the building facts): R-hat 1.006, ESS 665
       (sigma), every-element R-hat 1.010.
     - PSIS-LOO is 52,438.3, **+6.9 ± 18.5 against the same design without them** on identical
       rows (no measurable change) and +11,844 over m0. Held-out ΔELPD is +525.1 (+520.1 without).
     - The variance decomposition moves from anonymous to named terms: features 54.0% → 76.8%,
       building level 29.3% → 7.8%, building over time 2.4% → 1.0%. Market (8.4%), slopes (1.7% →
       1.6%), unit (1.9%) and residual (2.5%) are unchanged. building_scale falls from 0.257 to 0.159;
       walk_scale, unit_scale, sigma and ν do not move.
     - Effects (posterior mean, 95% interval):
       - space per apartment: +27% per log unit (+23 to +31);
       - condominium buildings (class R): +17% (+12 to +22) against elevator apartment buildings
         (D);
       - walk-ups (C): −7% (−11 to −3);
       - small mixed-use buildings (S: a few apartments over a store or office): −11% (−16 to
         −5); other classes: −11% (−17 to −5);
       - built 1990–2009 or 2010 on: +9% (+2 to +16, +2 to +18) against 1900–1929;
       - built 1960–1989: −9% (−15 to −3);
       - altered since 2000: +7% (+3 to +11);
       - historic district: +6% (−1 to +12);
       - landmark: +0% (−14 to +17).
     - The 2015 flood-zone flag gets +8% (+3 to +12). The 146 flagged buildings are the
       sample's western blocks: all west of Ninth Avenue, 90 of them between Ninth and Tenth
       (89 on the side streets, where the flag splits the buildings 89 to 70, and Chelsea
       Market), 14 on Tenth, 35 between Tenth and Eleventh and 7 on or west of Eleventh. So the
       flag most likely stands in for location there rather than flood risk (this fit cannot
       separate the two), which makes it a poor renter-facing term. A location term (below)
       should take it over.
   - **Without the flood-zone flag** (`unitdescpluto-v2`, 134737e, 2026-09-29; the candidate for
     the app, Ben 2026-09-29). It passes in 1,374 s: R-hat 1.006, ESS 602, every-element R-hat
     1.009. PSIS-LOO is 52,438.2: **−0.1 ± 7.2 against the building facts with the flag** and
     +6.8 ± 18.1 against the app's fit, on identical rows. Historic district takes up part of the
     western blocks' premium (+5.6% → +7.5%, +1 to +14), and built 1990 or later rises by about
     one point. The other facts barely move (under 0.5 posterior sd), and the building level
     stays at 7.9% of the variance.
   - **With alterations dated by the latest** (`unitdescpluto-v3`, faa8c78, 2026-09-29; the app
     candidate). `altered_since_2000` used `yearalter1` alone, so 44 buildings (950 rows) whose
     alteration in 2000 or later is recorded only in `yearalter2` got 0 (PR #52 review): 39
     altered before 2000 and again after, 5 with no `yearalter1` at all. v3 takes the later of
     the two recorded alterations, on v2 (no flood-zone flag). It passes in
     1,376 s: R-hat 1.006, ESS 585, every-element R-hat 1.009. PSIS-LOO is 52,439.6: +1.4 ± 6.8
     against v2 and +8.2 ± 18.3 against the app's fit. An alteration since 2000 is now +6.8%
     (+3 to +10, +6.4% in v2); no coefficient moves more than 0.2 posterior sd.
2. **Location.** Buildings have latitude and longitude. Try a low-rank spatial basis over building
   locations, as building-level columns, so neighbouring buildings share information (west vs
   east Chelsea, the avenues, the High Line).
   - **First result: a smooth surface on the building facts** (`unitdescplutoloc-v1` =
     `unitdescpluto-v1` plus 42 Gaussian bumps 250 m apart and wide over the registry
     coordinates, scaled to a prior sd of about 0.15 in log rent; prior correlation 0.78 at
     250 m, 0.37 at 500 m, about 0 at 1 km). Gibbs m5-nocurves, `unit-labels-v1`, 2 × (300 + 3600),
     10f6c70, RTX 2060, 2026-09-29.
     - It passes in 1,584 s (215 s more than without the surface): R-hat 1.006, ESS 623,
       every-element R-hat 1.009.
     - PSIS-LOO is 52,429.4, **−9.0 ± 8.0 against the building facts alone** on identical rows
       (no gain), −2.0 ± 19.2 against the app's fit. Held-out ΔELPD is +524.5.
     - The surface takes the flood-zone proxy's place: the flag falls from +7.6% (+3 to +12) to
       +3.2% (−3 to +10), 2.1 posterior sd of the earlier estimate, and historic district from
       +5.6% to +2.9%. Some other building facts shift by 0.5–0.9 sd: built 1990–2009 from +9.0%
       (+2 to +16) to +6.0% (−1 to +13), floors (log) from +6.5% to +8.2%, floor-area ratio
       (log) from −4.8% to −6.5%. The building level falls from 7.8% to 6.8% of the variance
       and building_scale from 0.159 to 0.154.
     - So the building facts plus each building's own level already carry the location signal,
       and the surface adds fit time without accuracy. It is not a frontier move on accuracy.
     - It is, though, the piece a map needs (the visualization goal above). Market, bedrooms and
       the surface give "what a typical N-bedroom rents for here, that month" at any point in
       Chelsea, not only at buildings with listings. The surface is identified relative to its
       own mean (its spread across buildings is 0.047 in log rent against a posterior sd of
       0.023; 37% of buildings have 90% intervals excluding 0), so the map shows where rents are
       above or below the Chelsea average. A true geo-temporal map also needs the
       surface to change over time (a space-time term), which is the next step on this line.
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

*Results so far* (each on the app's design, Gibbs m5-nocurves with `unit-labels-v1`, 2 × (300 +
3600), RTX 2060, paired on identical rows).
- Building facts (MapPLUTO): see A.1. They add no accuracy, but the building level's share of the
  variance falls from 29% to 8%.
- **Transit** (`unitdescplutotransit-v2`, 74ff297, 2026-09-29; MTA station stops snapshot
  20260929-8e7c364).
  - Per building: log minutes' walk to the nearest station stop (80 m/min, straight line) and
    log(1 + distinct daytime routes within 800 m). A stop counts only for listings in months that
    begin after it opened (34 St–Hudson Yards, 2015-09-13), which changes 1,049 rows in 35
    buildings.
  - It passes in 1,372 s. PSIS-LOO is **−0.0 ± 6.7 against the building facts alone** (52,438.3).
  - Effects are nil: a 2- to 8-minute walk changes rent by +0.1% (−4.1 to +4.3), and 4 against 14
    routes nearby by +0.2% (−3.9 to +4.7).
  - In Chelsea almost every building is a short walk from the subway: a median of 206 m and a 90th
    percentile of 515 m. What differences remain sit in the building levels.
  - The first version (`-v1`, f980477) used today's stations for every year. It scored the same
    (+1.1 ± 6.7, noise) and was replaced to keep the no-future-information rule. Its run is archived
    under `runs-archive/future-information-2026-09-29/`, off the board.
- **Building condition: HPD housing-code violations** (`unitdescplutohpd-v1`, 0544905;
  `unitdescplutohpd-v2`, 0fc2df7; 2026-09-30; HPD snapshot 20260930-cb289ad; both with
  `quarantine-v1`, against fef2aa5).
  - **Data.** 30,302 violations; 914 of the 1,129 registry buildings have at least one. The feature counts class B (hazardous)
    and class C (immediately hazardous) violations found in the building before the listing's
    month, per apartment and year. Apartments are MapPLUTO's residential units, or the units
    listed where a condominium lot records none. The window trails the listing, so no future
    information enters.
  - **v1, the past year.** Levels are none, a few, or many (a quarter or more per apartment).
    - About 15% of listings fall in "a few" and 5% in "many".
    - 1,359 s, passes. PSIS-LOO **+0.4 ± 6.6**, held-out +0.3 ± 0.2.
    - Effects: a few +0.1% (−0.3 to +0.4), many −0.1% (−0.6 to +0.4).
  - **v2, the past five years** (chronic condition). "Many" is 0.05 or more a year per
    apartment, about the top 15% of listings.
    - 1,358 s, passes. PSIS-LOO **−1.0 ± 6.7**, held-out −0.4 ± 0.5.
    - Effects: a few −0.1% (−0.6 to +0.4), many +0.3% (−0.4 to +0.9).
  - **Why it adds nothing.** Across buildings, violations do go with lower rents. About half the
    buildings have no class B or C violations since 2010, and their median premium is +2.4%.
    Buildings with any have a median of −1.3%, and the quarter with the most per apartment,
    about −2.5%. But the building facts and each building's own level already carry that. The
    building level's share of the variance stays at 7.7%, and a year with violations does not
    move a building's asks against its own path.
  - **Known limitations of these versions** (PR #67 review; a new version would fix them, but
    the result gives no reason to make one):
    - A building with its own BIN but no class B or C violations falls back to its lot's, taking
      the violations of other buildings on the lot (20 buildings, 535 rows; London Terrace's lot,
      for example).
    - On lots with several buildings, a building's violations are divided by the whole lot's
      apartments.
  - Recording condition in the site's building facts, as information rather than a model term,
    is a possible follow-up.

*Unit orientation* (street vs courtyard, and the street's size).
- StreetEasy's view and exposure fields are sparse (base-v1 has `view_street`, `view_courtyard`
  and window directions).
- Add description flags ("courtyard-facing", "quiet rear", "faces the street").
- Infer orientation geometrically: the unit's window directions against the bearing of the
  building's frontage street (LION and building footprints). A street-facing unit then gets that
  street's width and traffic.
- Height against the neighbours (MapPLUTO heights) as a light and view proxy.
- **First result: which way the apartment faces** (`unitfacing-v2` = `unitdescpluto-v3` plus the
  facing columns; Gibbs m5-nocurves, `unit-labels-v1`, 2 × (300 + 3600), 4519fb2, 2026-09-29;
  Ben's hypothesis, 2026-09-29: facing a wide, loud street such as 14th or an avenue is cheaper,
  facing a quiet side street dearer).
  - Frontage per building: the street of its address (avenue, wide crosstown street 14th, 23rd or
    34th, or side street) and the side of it the building stands on, from the basemap snapshot's
    centerlines. It is found for 1,121 of 1,129 buildings; the rest are rear buildings and named
    places. It agrees with house-number parity on all 901 crosstown buildings.
  - Facing per unit, pooled over its listings, uses four kinds of evidence: window exposures
    against the frontage, front/rear labels (2F/2R, only in buildings whose lettered labels are all
    F or R), ad text ("street-facing", "quiet rear", "floor-through", ...) and street or courtyard
    views.
    - Front: 1,717 rows on an avenue, 1,050 on a wide street, 2,547 on a side street.
    - Other classes: rear only 4,733; windows front and back 2,763; sides only 2,592 (side
      windows count only where the frontage is known).
    - Unknown (the reference): 37,236.
  - It passes in 1,365 s: R-hat 1.006, ESS 579, every-element R-hat 1.009. PSIS-LOO is 52,453.4,
    **+13.7 ± 9.1 against the building facts alone** (not a clear gain), and +11,860 over m0.
  - Effects are small, about a percent. Against rear-facing units:
    - front on a wide street −0.9% (−1.8 to +0.1), and −1.1% (−2.2 to +0.0) against front on a
      side street. That is the direction Ben expected, but both intervals reach zero;
    - front on an avenue +0.8% (−0.0 to +1.6): the other way. Avenue-facing units are often in
      taller buildings with light and views, which may explain it;
    - front on a side street +0.2% (−0.6 to +1.0);
    - windows front and back **+2.3%** (+1.5 to +3.2). The class counts floor-throughs, but also
      corner units with three or four exposures in towers;
    - sides only −0.3% (−1.0 to +0.5).
  - A first version (`-v1`, 18df498) missed Sixth Avenue: its centerlines are named Avenue of the
    Americas, and spelled-out avenues did not parse. It also counted side windows where the
    frontage was unknown. It scored +8.9 ± 7.9 with the same pattern (PR #58 review).
  - **Frontage is ambiguous for 39% of listings** (Ben, 2026-09-29, pointing to 130 West 15th, whose
    front desk is on 15th but which stands on 14th, and a Stonehenge building). The frontage above
    is the address street. By MapPLUTO, 178 buildings holding 20,451 listings have, or may have,
    more than one street front, or a different one:
    - corner lots: 120 buildings, 12,172 listings;
    - through lots: 22 buildings, 2,373 listings (The Tate, Chelsea Tower, the London Terrace
      complex on one lot, Walker Tower, Stonehenge Gardens);
    - other lots 150 ft or deeper, neither corner nor through: 22 buildings, 4,456 listings (The
      Sierra at 125 West 14th runs 206 ft, through to 15th; some avenue lots are deep without
      reaching another street);
    - MapPLUTO's lot address on a different street from the registry's (both addresses read): 61
      buildings, 10,164 listings.

    In these buildings a "rear" or "side" unit may face a second street, which dilutes the
    contrasts. The fix is each side's street from building footprints (below). The 25 buildings
    whose listed windows mostly face their assigned back are nearly all on the south side of their
    street (22 of 25): their back faces south, which looks like ads featuring south light rather
    than wrong frontages.
  - Why so small:
    - the evidence covers 29% of rows;
    - a unit's own level already carries its orientation when it has other listings;
    - noise may matter mostly on low floors (an interaction with floor is the natural next test);
    - frontage is ambiguous for 39% of listings (above).
  - **Next: every side's street, from building footprints.** NYC Building Footprints (joined by BIN)
    give each building's outline. Each side of the outline gets the street it faces (the nearest
    centerline beyond it) or none (a lot line or the rear). A unit's window directions then say
    which street it looks onto. Corner and through buildings get their real fronts.

*Testing.*
- Add each source group as its own feature set, alone and then combined.
- Put building-level features in the building mean (the NUTS-friendly form).
- Screen by projection, then fit the best combinations natively within the window.
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
   - The size and bath slopes (m6) did not mix under the Gibbs sampler.
   - Try them under NUTS, or a single size slope.
5. **Unit effects.**
   - Student-t units (+1,200) and unit drift (+360) did not mix under the Gibbs sampler
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

**C. Implementations within the window.**
1. **NUTS in NUTS-friendly coordinates on the CPU.**
   - Exact reparameterizations: trend levels, zero-sum season, units centred within buildings.
   - If NUTS reaches m0q/m1q/m5 within the window, it can fit any shape `build_model` expresses
     without sampler code. That includes the t-unit, drift and slope shapes the Gibbs
     sampler could not mix.
2. **Per-design draw budgets and chain counts** sized to the gate on each hardware class.
3. **Samplers** (Ben, 2026-09-29): the custom Gibbs sampler and exact simplifications
   (coordinates, collapsed updates) are in use again next to NumPyro NUTS. Other libraries
   (BlackJAX NUTS, nutpie) can run on the same model too.

**Order.** By expected PSIS-LOO gain per second of fit time:
1. C.1: NUTS on m0q, m1q and m5 in the new coordinates. Every later step needs a library fit that
   reaches these designs within the window. m0q passes in 888 s on the 2060. m1q's building walk
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

### T4. Product (Ben's decisions)

- Shipped on 2026-09-26: `rentfrontier.summary` (per-listing leave-own-row-out estimates, PR #34), the
  [listings site](site.md) (PR #35), and `config/main-analysis.json` selecting the summary of
  `m0q-btrend` + `unitdesc-v1` + `unit-labels-v1`. A new selection needs Ben's OK. It takes a summary,
  a publish, and an edit of the selection.
- Switched on 2026-09-29 (Ben): the selection names the summary of the Gibbs `m5-nocurves` +
  `unitdesc-v1` + `unit-labels-v1` fit (PSIS-LOO 52,431.4, 1,326 s on the RTX 2060).
- Switched again the same day (Ben: the building facts without the flood-zone flag, once they tie):
  the Gibbs `m5-nocurves` + `unitdescpluto-v3` + `unit-labels-v1` fit (PSIS-LOO 52,439.6, +8.2 ± 18.3
  against the previous selection; 1,376 s).
- On hold: West Village, once its crawl completes.

## Current state

The dashboard and board are generated from the run records; see them for the live frontier.

**Within 30 minutes on thelio (2026-09-29).** Gate-passing fits on the RTX 2060, by fit time,
PSIS-LOO on identical rows. "Rule" is the `unit-labels-v1` data rule. The Frontier column is the
board's, for this hardware. The board lists every run, including four more NUTS frontier fits (m0q
and m0q-btrend with unit features, 605–697 s, +1,716 to +5,033).

| Design | Sampler | Features | Settings | Fit time | PSIS-LOO ΔELPD vs m0 | Frontier |
|---|---|---|---|---:|---:|---|
| m0q | Gibbs | base-v1 | 4 × (500 + 2000) | 253 s | +10 | yes |
| m0q | Gibbs | desc-v1 | 2 × (300 + 3000) | 309 s | +184 | yes |
| m1q | Gibbs | base-v1 | 4 × (300 + 1500) | 702 s | +7,489 | yes |
| m0q-btrend | NUTS | unitdesc-v1 + rule | 4 × (250 + 550) | 745 s | +5,221 | beaten by Gibbs m1q |
| m5-nocurves | Gibbs | base-v1 | 2 × (300 + 2300) | 823 s | +9,708 | yes |
| m5-nocurves | Gibbs | desc-v1 | 2 × (300 + 2300) | 895 s | +9,922 | yes |
| m1-walk36-zs | NUTS | unitdesc-v1 + rule | 4 × (250 + 1300) | 1,300 s | +7,908 | beaten by Gibbs m5-nocurves |
| m5-nocurves | Gibbs | unitdesc-v1 + rule | 2 × (300 + 3600) | 1,326 s | +11,838 | yes (best) |

- m5-nocurves with `unitdesc-v1` and the rule is the most accurate passing fit within the window
  (details under "Misspecification first").
- From 702 s on, the Gibbs fits are ahead of NUTS. `m0q-btrend` at df5dacb and the sum-to-zero
  walk are beaten on both accuracy and time by Gibbs fits without the unit features. Below 702 s,
  NUTS `m0q-btrend` fits fill the gap between Gibbs m0q + desc and Gibbs m1q.
- NUTS m1q in `walk_levels` was stopped at 33 minutes (see the NUTS findings).
- Within the earlier 15-minute window (2026-09-25) the best was m5-nocurves + desc on Gibbs at
  895 s. The NUTS sum-to-zero walk needs the 30-minute window.
- Library NUTS (NumPyro) in the NUTS-friendly coordinates passes L0–L5 on the CPU (40–909 s) and
  m0q on the RTX 2060 in 888 s (PSIS-LOO 40,607.5, equal to the Gibbs m0q).

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
