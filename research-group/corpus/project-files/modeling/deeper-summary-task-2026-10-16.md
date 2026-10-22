# A deeper version of the post-fit summary task

*Written 2026-10-16 for Ben. Sources: the repo at master `e28d63d` (read in a clean copy), the Modeling thread, `docs/model/listing-estimates.md`, `docs/model/modal.md`, `docs/site.md`, and a timing of the summary's own number-crunching functions on made-up arrays shaped like NB9's, run in a cloud container, not on thelio ([script](summary-timing-test-2026-10-16.py)). Nothing on thelio was run or changed. Where something is my judgment or an inference rather than a checked fact, it says so.*

Your task as written: *"Optimize the post fit summary to run faster. Optimize, remove code and features where possible. We do not need to maintain an exact match to previous work, but any optimized version should accomplish the same objectives. For fit outputs flowing to the app, decide if the app feature is adding value and optionally refactor to remove or feature gate that computation."*

## What the summary is today

After a fit lands on thelio, `ops/modal/summarize` runs `rentfrontier.summary` and then `rentfrontier.calibration`. After a serve, `ops/autoselect-publish.sh` runs the rent map, the estimate kit (for /estimate) and the site build. The summary itself:

1. **Loads every kept draw.** That is 1,000 joint draws of every model effect (2 chains, 4,500 draws kept every 9th), all converted to 64-bit (`explain.load_run`).
2. **Rebuilds the fit's inputs.** It reloads the dataset, reapplies the data rules and rebuilds the feature set from scratch (`features.build`), which the fit already did in its container.
3. **Works through blocks of 1,024 rows** (about 260 on NB9). For each block and each draw it:
   - computes every term of the model;
   - for rows in the fit, recomputes each row's leave-own-row-out likelihood with the unit level integrated on a 401-point grid (on the GPU), then reweights the draws (Pareto-smoothed importance sampling, PSIS). The LOO step in the fit's container already computed the same per-row likelihoods but kept only totals and each row's Pareto k (the docs record agreement to 2e-13);
   - splits the estimate into dollar parts against a reference apartment (the LMDI split);
   - takes a weighted mean, median and 95% interval of the estimate, of the in-sample fit and of every part;
   - computes where the ask falls in its predictive distribution (the PIT), then solves for the 80% and 95% likely-ask ranges by Newton steps on a mixture of 1,000 Student-t distributions per row, to 1e-7 in probability;
   - writes each row's model inputs as JSON.
4. **Writes at the end.** Every block's table is held in memory, joined, and written out with the market, building and coefficient tables, the term labels, copies of the row-dropping data rules, and provenance.

It refuses a dirty tree, a run that fails the gate, a changed dataset, data rule or feature source, unit-split runs, and designs it doesn't integrate. Those refusals are what make a bundle traceable, and they should stay.

**What the site reads from the bundle:**

| Output | Where it shows |
|---|---|
| Leave-own-row-out estimate (median, 95% interval), ask less estimate | listing pages, listing lists and their sorting, /best, building and unit pages |
| PIT, shown as below, typical or above | listing pages and lists; coverage on the research pages |
| Likely-ask ranges, 80% and 95% | listing pages ("asks for this apartment likely fall in …"), /estimate |
| Dollar parts of the estimate, each with a 95% interval, for every listing | the listing page's parts table; its plain "why" sentences, which name a part only when its interval leaves out zero; the story page's one worked example |
| In-sample fitted rent with interval | one line in the listing page's details; research pages |
| Model inputs (JSON) | the /estimate form's encoder check, /best, the "why" sentences |
| Pareto k, shown as "less reliable" | listing pages and lists |
| Market, building and coefficient tables; data-rule copies | the market chart, building pages, the model page, quarantined listings |

The site logs every request with its address, path, status and time (`src/apartments/site/web.py:727`), so which pages people actually open is on record in the site service's journal. I haven't read it.

## What it costs today

**Time.**
- On Sep 29 the served summary took 226 s on the RTX 2060 with a 2.9 GB peak, on about 52,600 rows and 1,200 draws (`docs/model/listing-estimates.md`). The likely-ask ranges didn't exist yet.
- NB9 (266,513 rows, 128,791 units) takes over an hour. Its first attempt was killed at the old 5 GB cap after 75 minutes, unfinished; under the new 8 GB cap it peaked near 7 GB. That's about five times the rows of September for more than sixteen times the time, with fewer draws.
- In the Modal container, several bundles hit the 1,200 s cap, which is why you moved the summary to thelio on Oct 14.

**Where the time goes (a test on made-up arrays, not a profile of the real run).** I timed the summary's own functions, extracted from the repo, on arrays shaped like one NB9 block: 1,000 draws, 1,024 rows, 24 terms (my guess at the count). It ran on one core of a 2.1 GHz cloud Xeon and is scaled to NB9's 261 blocks.

| Step | Seconds a block | Minutes for NB9 |
|---|---:|---:|
| Likely-ask ranges (Newton on the t-mixture) | 10.8 | 47 |
| Unit levels (JAX, 64-bit; on CPU here, on thelio's GPU in real runs, not timed there) | 9.0 | 39 |
| Mean and interval of every dollar part | 1.8 | 8 |
| PSIS reweighting | 1.2 | 5 |
| LMDI split | 1.1 | 5 |
| PIT | 0.3 | 1 |
| Estimate and in-sample intervals | 0.1 | 0.6 |
| Inputs JSON | 0.06 | 0.2 |

Leaving out the GPU step, the CPU steps come to about 67 minutes here, which matches the hour seen on thelio. The likely-ask ranges are the largest single cost. That needs confirming on the real run.

**Memory (inferred from the code, not measured).**
- All draws are held in 64-bit. The unit effects alone are 1,000 × 128,791 × 8 bytes, about 1.0 GB on NB9, and the building walk grows with buildings × knots.
- The 1.75M-row data has about five times the units and ten times the buildings (69k against 6,644). Modeling put its summary near 50 GB on thelio's 15 GB.
- The rest is the reloaded dataset and features, plus all output held until the end.

**Repeated work.**
- The LOO, summary, kit, rent map, explained-share and new-building steps each reload the dataset and rebuild the feature set. On NB9 that's about 3 minutes and 2.4 GB on thelio each time, from the pipeline task's measurements.
- On the 1.75M-row data, Modeling is profiling a sample feature build that took 966 s on 4% of the buildings.
- The summary recomputes the LOO step's per-row likelihoods.

**Downstream.** The site build for 214,931 listings took 1:42 and peaked at 5.0 GB (`docs/site.md`). It grows with rows, so I expect the 1.75M-row publish to run out of memory there even after the summary is fixed (inferred).

**For the run in flight.** The large Modal mode (#890) can build the summary inside its 192 GiB container. But you asked Modeling to download the fit to thelio and stop before the summary, so this run's bundle will be built on thelio by whatever comes out of this task.

## 1. What a top professional would do that you aren't asking for

By "top professional" I mean a computational statistician who builds the post-processing behind published Bayesian models, such as the people who write Stan's and ArviZ's tools, or a central bank's forecasting team. To them the summary is a short list of functions of the posterior (each listing's estimate, its range, its parts), each computed to the precision the draws support. Speed follows from computing exactly those, once. It isn't the goal.

1. **Say what each output means, who reads it, and how precise it must be, before touching code.** That makes "same objectives" testable: every number keeps its meaning and agrees with today's within Monte Carlo error, meaning how much it would move if the fit were rerun with fresh draws. The yardstick is today's code run twice with different seeds. The new version may differ from the old by no more than the old differs from itself, which turns "no exact match needed" into a precise rule rather than a licence.
2. **Measure first, and measure memory against data size.** Profile the real NB9 run. The target isn't a smaller peak but a flat one: peak memory set by the largest building, not by the number of rows. The next run is five times NB9, and thelio stays at 15 GB.
3. **Compute to the precision of the draws, not past it.**
   - 1,000 kept draws carry their own error, and the gate only promises about 400 effective draws on the worst building.
   - The likely-ask solver works to 1e-7 in probability. The draws are only good to about 0.005 to 0.008 at the 2.5% tail (from √(p(1−p)/n) with 1,000 to 400 effective draws). That's tens of thousands of times finer than the inputs support.
   - A professional picks the number of draws and each solver's stopping point from that error, records the error in the bundle, and shows ranges at that precision. The /estimate kit already works from 250 draws.
4. **Compute once.**
   - The fit's container already computes each row's leave-own-row-out likelihood for the LOO score, and the summary computes it again.
   - Six post-fit steps rebuild the feature set the fit already built.
   - Save the fit's prepared design and each row's likelihoods with the run. Where the LOO score, the bundle, calibration, the kit and the rent map share work, one pass over the draws produces them all.
5. **Work building by building.** Units sit inside buildings, and a row needs only its own building's and unit's draws. So process blocks of whole buildings, read only their draws from a store laid out for that (32-bit, read from disk as needed), and write results as each block finishes. The blocks are independent, so they can use all six cores or the GPU.
6. **Decide each site feature with evidence, and compute detail when someone asks for it.** For each output, ask three things: is it on a page people open (the request log), does the goal need it, and what does it cost (the profile)? Some detail shows only on one listing's page, like the parts table with an interval on every part. That could be computed when someone opens the page, from the kit the site already uses for /estimate, rather than for 1.75 million listings in advance.
7. **Make the site's numbers mean the goal's quantity.**
   - The goal defines a quality's worth as the rent difference between two apartments alike except for that quality.
   - The listing page's parts split the gap to a reference apartment (LMDI). They add up, but a part isn't that difference.
   - For one draw, the difference is R × (1 − e^(−part)), as cheap as the split. A professional would compute it wherever a page presents a part as a quality's worth, or label the part as a share of a split.
   - The summary is where the model becomes "what this is worth here", so this belongs in the task.

Deleting code follows from these. The candidates are branches for designs no current model uses, outputs the value review drops, and the repeated data preparation.

## 2. The rawest material, instead of what has been digested

- **The posterior draws themselves,** not the bundle or the site database: the run's 1,000 joint draws of every effect (`posterior.npz`), its record (`result.json`, `heldout.npz`), and the fit's own prepared design, which the fit builds but doesn't save today.
- **Each row's likelihood under each draw.** The LOO step computes it and throws it away, keeping only totals. Kept, it is the input for both the LOO score and the bundle's estimates.
- **The real run's own meters.** These are a profile of the NB9 summary (where time and memory go, line by line) and systemd's accounting of each step. Every bundle ever written under `/data1/apartments/frontier/summaries/` also has a `complete.json` recording its seconds, rows and draws, which gives a free scaling curve back to September.
- **The case it must handle:** the 1.75M-row run's downloaded draws, and nested samples of its buildings for scaling tests.
- **Evidence of use.** The main source is the site's request log (each request's path, status and time, in the site service's journal), with your devices told apart from playtest browsers. The templates and code that read each column show which page depends on which output. Playtest reports are secondary: they are agents' opinions, and playtests have been on hold since Oct 5.
- **The goal's own definitions.** The project goal defines worth as a counterfactual difference and asks for uncertainty about each factor and about the final ask. The evaluation framework asks for predictive medians and intervals, with coverage against nominal 80% and 95%.

## 3. Methods and tools they would use

- **Profiling.**
  - `py-spy record --native` samples a running job, NumPy and SciPy internals included, into a flame graph.
  - `memray` shows peak memory by the line that allocated it.
  - JAX's profiler covers the GPU step, and systemd's accounting gives each step's peak memory and CPU time.
  - Run on nested samples of the 1.75M-row data's buildings (1%, 4%, 16%) and fit how each step's time grows with rows. Any step growing faster than rows is a bug.
- **Monte Carlo error.** Use the error of means and quantiles (Vehtari et al. 2021; `arviz.mcse(..., method="quantile")`) and each row's effective number of draws after reweighting (1/Σw²). Choose draws and tolerances from these.
- **PSIS, done once.** Run Pareto-smoothed importance sampling (Vehtari et al. 2024) on the stored per-row likelihoods, with ArviZ's implementation as the independent check.
- **Cheaper likely-ask ranges.** There are two candidates:
  - posterior predictive simulation: one or a few noise draws per posterior draw, then a weighted quantile, at about the cost of one interval;
  - the current exact mixture, solved only to the Monte Carlo tolerance with a vectorized bracketed solver (SciPy's `optimize.elementwise.find_root`).

  Pick between them by measurement.
- **Blocked, streaming computation.**
  - Work in blocks of whole buildings.
  - Store draws as 32-bit arrays read straight from disk (NumPy memory maps or Zarr), ordered so each block's draws sit together.
  - Write output block by block with `pyarrow`'s `ParquetWriter`.
  - Run blocks in parallel across thelio's six cores (`multiprocessing`), or make each block one compiled JAX function on the GPU (`jit`, with `vmap` over rows). Use 32-bit wherever the Monte Carlo error is far larger than rounding.
- **One prepared design.** The fit saves its prepared arrays (feature matrix and indices) with a hash, and every post-fit step reads them instead of calling `features.build`. This is the data pipeline task's "build once, read many", applied after the fit.
- **Feature flags and detail on request.** The bundle carries a list of the optional outputs it holds, and the site build reads it so a page hides what a bundle lacks. Per-listing detail can come from the kit when a page asks for it.
- **Tests that don't depend on the code being right.**
  - Golden master with a statistical tolerance: the old code, run with two seeds.
  - Property tests: parts add up to the estimate, quantiles are in order, PITs lie between 0 and 1, and the refusals still refuse.
  - Simulation-based calibration (Talts et al. 2018): asks drawn from the run's own predictive distribution must come back with uniform PITs.
  - Brute-force references on sampled rows: a million-draw predictive for the ranges, and a finer grid for the unit integral.

## 4. What, other than you or me, would show the result is right

1. **Today's code, run twice.** Run the old summary with two seeds on NB9 to set the noise floor. Every column of the new bundle should agree with the old one within that floor: the share of rows differing by more than three combined Monte Carlo errors is no more than chance gives. Every larger difference is named and explained.
2. **Known answers.** Asks simulated from the run's own predictive distribution come back with uniform PITs, and the 80% and 95% ranges cover them at those rates. On a random sample of rows, brute-force references agree within Monte Carlo error.
3. **An independent implementation.** ArviZ's PSIS on the same likelihoods gives the same weights and Pareto k, and the bundle's k matches the LOO step's.
4. **Asks the fit never saw.** On the run's held-out rows, and on the later months of the latest time split, the ranges cover at today's rates and near nominal. Ads from the next top-up, scored the same way, are a dated forecast.
5. **The site.** Site databases built from the old and new bundles agree table by table, except for the listed features the review removed. The site's tests pass, and the request log shows no new errors or slow pages.
6. **The 1.75M-row run.** Its summary builds on thelio inside the 8 GB slice, and the site publishes from it.
7. **The meters.** Before-and-after times and memory come from systemd's accounting and the profiler, not estimates.

## 5. The rewritten task

> **Rebuild the post-fit summary as posterior post-processing: compute only what the site and the project goal need, once, to the precision the draws support, in memory that doesn't grow with the data.**
>
> The summary turns a finished fit's posterior draws into the site's numbers. On NB9 (266,513 rows) it takes over an hour on thelio and peaks near 7 GB. The 1.75M-row fit now running is about five times bigger, and Modeling estimated about 50 GB for its summary, against thelio's 15 GB. Faster and smaller should follow from the design below; they aren't separate goals. An exact match to past bundles isn't needed, but every number the site shows must keep its meaning and agree with today's within Monte Carlo error.
>
> The headline measure is wall time and peak memory from a downloaded fit to a published site, from systemd's accounting, on NB9 and on the 1.75M-row run. Aim for:
> - peak memory that doesn't grow with rows and fits the 8 GB GPU-job slice at any size;
> - time that grows no faster than rows.
>
> **Start from the raw material.**
> - The run's kept joint draws and its record.
> - Each row's likelihood under each draw, which the LOO step computes and discards today.
> - A profile of the real NB9 summary, and the time, rows and draws in every past bundle's `complete.json`.
> - The 1.75M-row run's downloaded draws.
> - For the value of each site feature: the site's own request log and the project goal.
>
> **Do this, in order.**
> 1. **Measure.**
>    - Profile the NB9 summary on thelio with py-spy and memray, under systemd's accounting.
>    - Time it on nested samples of the 1.75M-row run's buildings (1%, 4%, 16%), and find any step that grows faster than rows.
>    - A test on made-up arrays shaped like NB9's points at the likely-ask ranges as the largest cost, about 47 of 67 CPU minutes (`/mnt/project-files/modeling/deeper-summary-task-2026-10-16.md`). Confirm or overturn that on the real run.
> 2. **Write the contract.**
>    - Cover every output of the summary and of the steps after it (calibration, the kit, the rent map, the site build).
>    - For each, say what it means, which page or check reads it, and how precise it must be, as a Monte Carlo error.
>    - Run today's code twice on NB9 with different seeds. That spread is the noise floor every rewrite is held to.
> 3. **Decide each site feature with evidence.**
>    - For each output, set side by side how often its page is opened (the request log, with Ben's devices told apart from playtest browsers), whether the goal needs it, and its measured cost.
>    - Then keep it, compute it when a page asks for it (from the kit, as /estimate already does), put it behind a flag the site build reads, or remove it.
>    - Record each decision and its reason in the docs.
>    - Look first at the in-sample fitted rent, and at the interval on every dollar part of every listing.
> 4. **Make the numbers mean the goal's quantity.** The listing page splits an estimate into dollar parts against a reference apartment. The goal defines a quality's worth as the rent difference between two apartments alike except for that quality. Where a page presents a part as what a quality is worth, compute that difference (it costs the same per draw), or label the part as a share of the split.
> 5. **Compute to the precision of the draws.**
>    - Choose the number of draws and each solver's stopping point from the Monte Carlo error, and record that error in the bundle.
>    - The likely-ask ranges solve to 1e-7 in probability, while 1,000 draws are only good to about 0.005 there. Compare posterior predictive simulation with the exact mixture solved only to that tolerance.
> 6. **Compute once.**
>    - Keep each row's likelihood from the LOO step and reuse it, instead of computing it again.
>    - Save the fit's prepared design with the run, so no post-fit step rebuilds the feature set.
>    - Where the LOO score, the bundle, calibration, the kit and the rent map share work, do it in one pass over the draws.
> 7. **Work building by building.**
>    - Process blocks of whole buildings, reading only their draws from a 32-bit store on disk laid out for that.
>    - Write output as each block finishes.
>    - Run blocks across thelio's six cores or as one compiled JAX function on the GPU, whichever the profile favours.
>    - Where the summary runs (thelio, or the fit's container right after LOO) is a measured choice. This run's draws come to thelio, as Ben asked.
> 8. **Delete the rest.** Remove branches for designs no served or queued model uses, the outputs step 3 removed, and the repeated data preparation. The record keeps their results.
>
> **It's done when checks outside the code agree.**
> - Every column of the new NB9 bundle agrees with today's within the noise floor of today's code run with two seeds. Every larger difference is named and explained.
> - Asks simulated from the run's own predictive distribution come back with uniform PITs, and the 80% and 95% ranges cover them at those rates.
> - Brute-force references on a random sample of rows (a million-draw predictive, a finer unit grid) agree within Monte Carlo error.
> - ArviZ's PSIS gives the same weights and Pareto k as the new code.
> - On rows the fit never saw (the held-out rows, and the later months of the latest time split), the ranges cover at today's rates.
> - Site databases built from the old and new bundles agree table by table, except for the features step 3 removed, and the site's tests pass.
> - The 1.75M-row run's summary builds on thelio inside the 8 GB slice, and the site publishes from it.
> - Before-and-after times and memory come from systemd's accounting and the profiler, not estimates.
>
> **Keep the standing rules.**
> - The summary keeps its refusals: a dirty tree, a fit that fails the gate, and a dataset, data rule or feature source that differs from the run's record.
> - Free checks on thelio need no approval. Any Modal use keeps to the budget and the one-hour cap, unless Ben has said otherwise for that fit.
> - Modeling owns the 1.75M-row run and the fit queue, and Website owns the site build. Land the work in small reviewed PRs that keep a summary runnable at any time, and agree with each thread before changing a step it uses.
> - Run on Opus 5.5 at extra-high effort.
>
> This serves the project goal. The summary is where the posterior becomes what people read: what each quality is worth for this apartment, how sure the model is, and whether its ranges hold for asks it never saw.
