# Research direction: calibrated inference at city scale

**2026-10-17 — proposal only; no fits or GPU jobs run.**

## Recommendation

Build a **library-first, GPU-native inference system for an interpretable hierarchical rent model**, with two complementary research tracks:

1. **Reference inference:** NumPyro and BlackJAX MCMC, first on the existing model, then with building-local Gaussian effects integrated out. Benchmark ordinary NUTS against fixed-work, accelerator-friendly samplers rather than assuming NUTS or our custom Gibbs sampler must win.
2. **Beyond-memory inference:** structured stochastic variational inference using building minibatches. Treat its uncertainty as an approximation to test, not as an established posterior. Retain a full-data, streaming blocked sampler when exact-target inference is required.

The enabling investment is a **building-partitioned numerical dataset and chunked posterior storage**, not a bigger GPU alone. It supports all three engines, removes the local RAM bottleneck, and keeps the inference method replaceable.

I would not commit to maintaining the current sampler indefinitely, nor promise that a replacement will fit all-scraped in 20 minutes. I would fund a short, staged comparison with explicit failure criteria. The target is **a validated full fit within about an hour, for a few dollars**, including the work needed to report useful uncertainty. Whether that target is attainable is the first research question.

### Why this direction serves the rewritten goal

The objective is evidence about **what apartment qualities are worth**, not another increment in in-sample predictive density. Cheap, reliable inference buys:

- repeated recovery of known feature worths in simulated data;
- separate full fits for each model-term test and sensitivity analysis;
- dated forecasts for genuinely new advertisements;
- uncertainty on joint apartment comparisons, not just coefficient standard errors;
- natural-experiment analyses and comparisons with independent paid-rent records.

The latest asking rent remains the model target. Signed lease rents are an external comparison, not interchangeable labels. No sampler makes an observational amenity coefficient causal, and more rows do not repair weak identification or biased coverage of the city.

---

## 1. What the existing system tells us

I inspected `docs/research-plan.md`, `docs/thelio-jobs.md`, the model and inference code under `frontier/src/rentfrontier/`, the recent computational and mixing proposals, and the data layout. I read Parquet footers, small JSON records, and the posterior archive's directory—not the large datasets or posterior arrays into memory.

### Scale: distinguish three different datasets

| Artifact | Measured size / count | Meaning |
|---|---:|---|
| Existing all-scraped fit | **1,575,187 training rows**, 175,067 held-out rows | Rows actually used after the fit's rules |
| Its modeled population | **67,735 buildings; 871,143 units** | Model identities, not necessarily verified physical apartments |
| Current pipeline rows, `rows-c3fa81d0f768b96b.parquet` | **1,746,778 rows; 82.6 MB** compressed | A newer export; not the same snapshot as that fit |
| Current ads, `ads-eaae0c38cca9d94a.parquet` | **2,140,923 ads; 122.4 MB** | Includes ads outside the modeled row set |
| Raw records, `records-11f851377371710e.parquet` | **2,180,406 records; 3.40 GB** compressed | Repeated collected records, not independent rent observations |

The raw records' uncompressed Parquet row-group size totals **15.26 GB**, already around thelio's entire RAM before Python objects or working arrays. The current rows' corresponding total is only **297 MB**. The distinction matters: **the raw archive needs out-of-core processing now; the numerical rent likelihood probably does not yet need out-of-core GPU execution.**

The existing all-scraped `observations.jsonl` is 3.07 GB in decimal units. Its manifest contains 1,751,152 pre-rule rows. These counts differ legitimately from the newer pipeline export; any benchmark must freeze one manifest rather than mix them.

### Current computation

The model is a hierarchical additive model of log asking rent: measured attributes, market trend and season, bedroom-specific time curves, building levels and walks/slopes, unit effects, and Student-t residuals. Unit effects are also Student-t in the measured fit.

The custom JAX Gibbs sampler exploits conditional Gaussian structure through Student-t mixture weights. It eliminates units, performs batched building-block factorizations, and solves a dense global Gaussian system. It already has compact walk representations, row chunks, chain batching, and segmented draw collection. The proposal should build on those lessons, not rediscover them.

NumPyro NUTS already samples the same model. The stack already locks **JAX 0.11.2, NumPyro 0.22.0, BlackJAX 1.6.2, and ArviZ 1.3.0**. Library adoption is therefore mostly about using existing dependencies differently.

### The all-scraped run is not a viable iteration loop

From its `result.json` and `modal/modal.json`:

| Stage | Time |
|---|---:|
| Preparation | 912 s |
| Warmup | 900 s |
| Sampling | 15,533 s |
| PSIS-LOO | 1,631 s |
| Variance analysis | 631 s |
| Total container wall time | **20,472 s = 5.69 hours** |

It ran fp64 on an A100-SXM4-40GB. At the repository's approximately $4.01/hour large-container rate, the implied compute cost is **about $22.8**, not a verified invoice. It failed convergence: the Carlyle's building effect had ESS **11.7**, while `building_scale` had ESS **280**. The settings used two chains with `chain_batch=1`, so this run did **not** measure simultaneous many-chain throughput.

The repository documents an historical exemption allowing this large run. **I do not carry that exemption forward:** this proposal follows the rewritten statement's approximately one-hour fit cap and $10/day budget.

### A more specific memory diagnosis

For this configuration, the code implies **443 Gaussian global coefficients**:

`1 intercept + 170 features + 67 trend coefficients + 4 season coefficients + 3 × 67 bedroom-time coefficients`.

The anchored zero knots are not free parameters; one-bedroom is the reference time curve. Including approximately 80 scale/tail parameters gives about **520 gradient coordinates** after local Gaussian marginalization—not millions, but also not the 515 Gaussian coefficients estimated in the earlier proposal.

Useful memory arithmetic, in decimal GB:

- Dense fp64 global row design: **5.58 GB**. The 170 actual feature columns alone: **2.14 GB**. Time bases should remain indices and interpolation weights.
- A building-local/global cross-array with 20 local coordinates: `67,735 × 20 × 443 × 8` = **4.80 GB per chain**. The current compact solver retains arrays of this kind. Twenty is illustrative, not a measured average width.
- The corresponding local square matrices: **0.217 GB per chain**.
- Residual and unit mixture weights together: only **19.6 MB per chain**, before other state and autodiff workspaces.
- Every-building traces at two chains × 4,500 draws in fp32: **2.44 GB**.
- A 1,000-draw × training-row fp64 log-likelihood table: **12.60 GB**.

The saved `posterior.npz` is **13.44 GB** compressed, 14.72 GB uncompressed. Its walk draws alone account for 9.48 GB uncompressed, unit draws 3.48 GB. This is a storage/access problem as much as a sampling problem.

**Conclusion:** avoid large cross-intermediates and full draw-by-row arrays before buying capacity or treating the number of ads as the fundamental obstacle.

---

## 2. Scientific model: preserve interpretability, not the existing design

I would retain an interpretable additive/panel model as the research vehicle, but not regard the present collection of terms as mandatory.

- Use photos, floor plans and text to estimate **named physical qualities**, with evidence and measurement error: room dimensions, layout, light, exposure, condition, outdoor space, and so forth. Frozen embeddings can help extraction; a rent-trained embedding coordinate is not an explanation of worth.
- Separate within-apartment changes, comparisons among apartments in a building, and between-building associations. A within/between decomposition can expose which variation identifies each quality. Time-invariant amenities generally cannot be identified from within-unit changes alone.
- Use measured accessibility, noise, parks and other city features as the main location explanation. A modest residual spatial field can diagnose what remains unexplained; it must not become a neighborhood-label replacement that receives credit for explaining location.
- Use actual, evidenced change dates for natural experiments. For example, documented transit-service changes can support an accessibility study, with pre-trend, concurrent-change and spillover checks. They do not automatically establish causality.
- Treat unresolved identity and attribute conflicts explicitly. Poor mixing may signal erroneous records, genuine heterogeneity, competing explanations, or weak identification—not necessarily bad data to discard.

Gaussian versus heavy-tailed unit effects, walk versus stationary dynamics, and centered versus raw random slopes are **statistical choices**, not free computational optimizations. Each receives its own full fit if tested. Exact coordinate changes and analytical integration do not change the model; changing priors during a reparameterization does.

The first engine comparison should nevertheless keep one frozen existing model and dataset. Otherwise a faster answer could merely be an answer to a different question.

---

## 3. Reference track: library samplers, with structure only where it pays

### Step A: benchmark a genuinely off-the-shelf baseline first

Use the existing NumPyro model/log density with:

1. **NumPyro NUTS**, including its existing improved coordinates and a dense metric only for the manageable global block.
2. **BlackJAX fixed-work Metropolis-adjusted microcanonical HMC** (`adjusted_mclmc`), and, if useful, **ChEES-HMC**. MEADS/generalized HMC is a further candidate, not a reason to run an exhaustive sampler tournament.

BlackJAX's installed source explicitly describes `adjusted_mclmc` as Metropolis-corrected, unlike unadjusted MCLMC. This correction matters for posterior uncertainty. Its static-work variant is intended for parallelized execution.

Why these are worth testing:

- GPU work can batch over observations, buildings and chains.
- Fixed-work trajectories avoid NUTS's variable tree lengths and the longest-chain penalty under vectorization.
- Ensemble adaptation can share useful geometric information during warmup.

But all chains still need to reach the target. Stop adaptation for the retained phase; do not add ESS across unconverged short chains. Use multiple dispersed initialization groups and, when appropriate, nested R-hat **in addition to**, not instead of, established diagnostics.

Start with **4 chains**, then measure 8 or 16 only if memory and throughput justify them. Two hundred chains are not a sensible default for this model. Static features may be shared, but weights, gradients, states, and much intermediate arithmetic are chain-specific. `vmap` does not make them free.

The old RTX 2060 results are evidence about that hardware and parameterization, not proof that generic HMC must fail on an H100. Conversely, a million-row likelihood does not prove one chain underutilizes an H100.

**Decision:** if a generic library sampler meets the hour/cost/calibration targets, stop here. Do not build a special marginal likelihood simply because one is possible.

### Step B: integrate local Gaussian effects out of each building

If generic sampling loses, my preferred structural improvement is a **building-marginal density**, differentiated by JAX and sampled by library kernels.

For building `b`, write:

```
y_b = X_b g + Z_b a_b + U_b u_b + e_b

e_i | w_i ~ Normal(0, sigma_i² / w_i)
w_i       ~ Gamma(nu/2, nu/2)

u_j | v_j ~ Normal(0, tau² / v_j)
v_j       ~ Gamma(2, 2)                 # Student-t unit df = 4

a_b       ~ Normal(0, Lambda_b(theta))
```

Here `g` contains interpretable feature/time coefficients, `a_b` building-local Gaussian terms, and `theta` scales and tail parameters. Conditional on the weights, integrate `u_b` and `a_b` out:

```
y_b | g, theta, w, v ~ Normal(X_b g, C_b)
C_b = D_b + U_b V_b U_b' + Z_b Lambda_b Z_b'
```

Do not form the row-by-row covariance. Unit elimination uses small per-unit reductions; building elimination uses small Cholesky factors and the Woodbury/determinant identities. Batch buildings with similar active dimensions, retaining the current compact-walk lesson. Use triangular solves and stable square-root formulations rather than explicit matrix inverses.

This density needs only the local matrix and residual for the current `g`. **It need not materialize every building's local-by-global cross-array**, a major distinction from eliminating the global Gaussian block as well.

One valid transition schedule is:

1. Apply a library MCMC kernel to `(g, theta)` conditional on current `w, v`, targeting the building-marginal density, including the weight priors and all scale-dependent normalization terms.
2. Draw `(a_b, u_b)` jointly from their Gaussian conditional, independently across buildings.
3. Update `w, v` from their Gamma conditionals given the reconstructed effects.

These compose an exact-target Markov transition, subject to ordinary numerical accuracy. A conditional MCMC transition need not be an independent draw to be valid.

**Important limitations:**

- The *gradient block* has about 520 dimensions, but the augmented chain still has **roughly 2.45 million weights**. Marginalizing Gaussian effects has not integrated out the heavy-tail mixture. Slow weight/scale coupling and genuine multimodality can remain.
- Gamma weight updates are not valid using residuals from effects that have been integrated out and not reconstructed.
- Changing the weights changes the conditional target. BlackJAX's cached log density and gradient must be refreshed before the next trajectory.
- If later adding partially collapsed noise/tail updates, prove the transition ordering; swapping conditionals informally can change the stationary distribution.
- This trades one Gaussian block solve for potentially many marginal gradients. Better geometry is a hypothesis, not a speed guarantee.

**Library boundary:** NumPyro's experimental `Gibbs`/`CustomGibbs` or `HMCGibbs` can drive HMC/NUTS plus custom conditionals. `HMCGibbs` requires a NumPyro model, not merely a potential-function argument. A marginal wrapper model can supply the density. BlackJAX makes kernel substitution easier but requires an explicit composition loop. Neither library automatically discovers the nested Gaussian elimination.

The custom responsibility should be **one tested marginalization/conditional-draw layer and its data adapter**, not another homegrown adaptation, HMC, or convergence library.

### What not to optimize first

Do not immediately integrate out `g` as well. It reduces the gradient dimension further, but introduces global cross-products, Schur complements and their derivatives. Measure whether global geometry, local marginal cost, or weight coupling is actually limiting progress first.

Do not make stochastic log-determinants part of an allegedly exact likelihood. A noisy unbiased log determinant is not an unbiased nonnegative likelihood estimator. Likewise, a few truncated conjugate-gradient iterations do not automatically yield an exact Gaussian draw.

---

## 4. Beyond-memory track: structured variational inference

**This is the most promising algorithmic departure for datasets much larger than memory.** Unlike full-data MCMC, it can make useful progress after reading only a small fraction of the buildings.

Use NumPyro SVI with an Optax-compatible optimizer and a structured guide of the form

```
q(g, theta) × product_b q(local_b | g, theta, data_b)
```

The global block should have meaningful covariance—dense or low-rank at this size. Local guides should retain important building/unit/time dependencies through sparse Gaussian structure or conditional parameterizations. A mean-field normal over all millions of effects is a baseline, not the proposed final approximation.

Sample **whole buildings**, keeping their unit histories together. Uniformly sampled buildings permit the usual scaled sum of building contributions; unequal sampling requires explicit inclusion-probability corrections. Count each local prior once and each global prior once. Sampling ads independently while losing their shared latent context is not the same estimator.

For datasets beyond RAM:

- stream building partitions from Parquet through Arrow batches;
- keep global variational parameters on the GPU;
- use an amortized local guide, or a partitioned local-parameter/optimizer-state store loaded with each batch;
- keep batch shapes stable through size buckets and masked padding.

Amortization makes state size largely independent of the number of buildings, but introduces approximation error. A disk-backed local-state store avoids amortization but needs careful optimizer handling. **Neither capability comes automatically from calling `SVI.run`**; the data/guide adapter is project code.

### Role and admission criteria

Initially use SVI for initialization and an explicitly labeled approximate research comparison. Do not silently replace the standing full-fit-per-term policy with cheap VI screening.

A VI fit could eventually count as a full-data fit after its own convergence, data-coverage and calibration protocol is accepted. It is not MCMC: R-hat and ESS are not appropriate certificates. Compare its scientific contrasts, covariance, tails and predictive intervals with the reference, across batch sizes and repeated optimizer starts.

In particular, test rare amenities, small buildings, changes within apartments, and multimodal conflicting-price examples. A low loss or nearly identical predictive error can coexist with badly understated uncertainty about feature worth.

If structured VI passes those tests, it offers a defensible scalable engine. If it does not, retain it as an initializer or approximate exploratory result. High-dimensional importance reweighting is not a guaranteed repair.

---

## 5. A memory hierarchy that all engines can use

### A. Prepare once, without constructing a city-sized pandas object graph

Replace the JSONL-to-list-of-dicts fitting path with immutable, content-addressed numerical shards prepared from the pipeline's rows. The existing loader can construct all flattened JSON records and a DataFrame together; that is avoidable.

Use DuckDB with bounded memory and spill for joins/sorts, Arrow record batches for reading, and Parquet for persistent partitions. Store:

- rows sorted by building and unit, preserving histories;
- integer identities and group boundaries;
- only actual feature columns, with appropriate sparse or categorical representations;
- dates and interpolation indices/weights rather than expanded time bases;
- provenance, knowledge/effective-time cutoffs, training-only encoders, data rules and hashes.

Cache keys must include feature/model preparation and split definitions, not just the raw data hash. Photos, floor plans and text remain content-addressed raw evidence outside the hot numerical working set. Extraction can stream on cheaper GPUs; embeddings do not justify deleting source evidence.

### B. GPU-resident data: the immediate target

Keep compact numeric data on one GPU if they fit, and chunk the building computations. JAX checkpointing/rematerialization can reduce reverse-mode tape storage, at a recomputation cost.

**Chunked arithmetic is not out-of-core I/O.** A `lax.scan` over a GPU-resident dataset or a rematerialized function does not cause Parquet files to be streamed from disk.

Profile segmented reductions, active-width padding, repeated matrix products, held-out prediction work inside each sweep, compilation and host/device synchronization. Do not infer runtime from peak FLOPS: the present solver moves large cross-arrays, and small factorizations/atomics often behave unlike large matrix multiplication.

### C. Larger than GPU, smaller than host RAM

Use pinned-host buffers and explicit prefetch/double buffering, or shard independent buildings across GPUs while sharing global parameters. For a building-marginal gradient, sum the local scalar densities and global gradient vectors across devices.

Compare **data parallelism** with **chain parallelism**; choose based on the measured bottleneck. Multi-GPU execution may meet the hour cap while increasing dollar cost. It is not the first purchase under $10/day.

### D. Larger than system RAM: two honest choices

1. **Minibatch structured SVI**, above: genuinely sublinear work per optimizer step.
2. **Exact full-data streaming**, accepting that each transition must revisit the data.

A useful exact fallback is a two-pass joint Gaussian block draw conditional on scales and weights:

- First pass: eliminate each building's local effects, accumulating its contribution to the small global precision and right-hand side. Discard or spill the local factors instead of retaining a city-sized cross-array.
- Draw the global coefficients from that Gaussian.
- Second pass: reconstruct each building/unit conditional draw, update mixture weights, and accumulate sufficient statistics for hyperparameters.
- Update hyperparameters with a library kernel conditional on those statistics. Keep the previous and next weight generations separate until the sweep completes.

This is a different transition schedule from the current heavily collapsed sampler. It preserves the target but may mix more slowly. Its advantage is a small, bounded number of full passes rather than dozens of disk scans per HMC trajectory. It still needs a custom structured Gaussian conditional, not a custom general-purpose sampler.

For the robust model, the weights change: **one cached `X'X` is not a sufficient statistic for all future iterations**. More generally, exact full-data gradients can be streamed and summed over chunks, but integrating disk I/O into a compiled library trajectory requires a real dataflow adapter; it is not an off-the-shelf minibatch switch.

A bandwidth lower bound is

`time per transition >= full passes × bytes read / sustained end-to-end bandwidth`.

For illustration, one 100 GB pass is at least 4 seconds at 25 GB/s host-to-device, or 33 seconds at 3 GB/s disk throughput—before decompression, computation or synchronization. Twenty such passes cost at least 80 seconds or 11 minutes. Measure the actual storage and interconnect; never use HBM bandwidth to price an NVMe workload.

### E. Posterior and scoring must also be out-of-core

Replace monolithic compressed NPZ access with **chunked Zarr or equivalent arrays**, partitioned by effect and building, plus small global draw tables.

- Preserve joint draw identities for dollar contrasts. Marginal means and variances cannot reconstruct the uncertainty of a comparison.
- Keep scientific contrasts, scales and global trajectories densely enough for diagnostics. Store full local draws on disk in chunks where needed; reserve cheap summaries for browsing.
- Draw unobserved walk bridges on demand from their correct conditional when possible. For robust local effects, global draws plus an RNG seed are **not** sufficient to recreate a Gaussian conditional without the corresponding weights/state. Save those checkpoints, save the relevant joint draws, or run a validated local conditional sampler.
- Compute rank-normalized split R-hat, bulk/tail ESS and MCSE by reading all retained times for a bounded group of buildings. Running means and variances alone do not reproduce these diagnostics.
- Evaluate LOO one row/unit block at a time across retained draws, then discard that block's likelihood table. The current implementation already chunks device work but still allocates a full host draw-by-row table.
- Apply the existing integrated-unit scoring definition consistently. Do not change the predictive target just because the fitting representation is marginalized. Preserve all rows of a unit when its integration requires them.
- Ordinary PSIS can operate on all retained weights for a bounded row block. A top-weights-only online approximation needs separate validation; it is not automatically identical to library PSIS.

Full PSIS remains a useful model check, but should not consume the budget needed for prospective and external validation. Report preparation, sampling, diagnostics, scoring and publication costs separately and end-to-end.

---

## 6. Other algorithms: their place in the research

| Method | Library / implementation | Recommendation |
|---|---|---|
| NUTS | NumPyro; nutpie on reduced CPU reference cases | Baseline and independent correctness check; not presumed GPU winner |
| Adjusted microcanonical HMC, ChEES-HMC, MEADS | BlackJAX | Prioritized accelerator candidates; judge geometry and mixing, not raw draw counts |
| Pathfinder / multipathfinder | BlackJAX | Initialization and geometry estimates; not an automatic replacement for posterior sampling |
| Tempered SMC | BlackJAX | Useful if substantive multimodality persists; parallel particles, but particle state, resampling and repeated full likelihoods can be expensive |
| Sequential/data-tempered SMC | BlackJAX partial-posterior machinery | Later candidate for dated updates; finite-particle degeneracy and rejuvenation still require checking, and old observations cannot simply disappear |
| SGHMC / SGLD | BlackJAX SG-MCMC kernels | Secondary experiment after SVI; stochastic-gradient and finite-step bias need calibration. More samples do not remove discretization bias at a fixed step size |
| Energy-conserving subsampling HMC | NumPyro `HMCECS` | Consider only with good control variates and estimator checks. An unbiased log likelihood does not establish exact pseudo-marginal inference; ordinary minibatched NUTS is invalid |
| Sparse Laplace / INLA / TMB | R-INLA, TMB; GPU research implementations | Credible challenger on a simpler model, especially sparse Gaussian dynamics. Hyperparameter count, non-Gaussian unit effects, approximation error and GPU maturity need assessment—not a blanket rejection |
| Matrix-free Gaussian draws | JAX CG / Lineax plus a correctly randomized solve | Later for genuinely large crossed spatial effects. A solver is not a complete sampling library; conditioning, tolerance and covariance must be tested |
| Sparse variational spatial field | GPyTorch SVGP or a NumPyro finite-basis field | Useful if residual geography requires it; distinguish approximation from a changed finite-basis prior, and do not let geography substitute for measured explanations |

I would **not** prioritize consensus fits by neighborhood. Combining subposteriors can lose shared uncertainty and dependence, while independent area models weaken the project's citywide explanations. Parallel building work conditional on common globals is a cleaner partition.

---

## 7. Hardware: choose dollars per validated answer

The repository's configured total container rates are approximately:

| Hardware | GPU memory | Configured hourly cost | First role |
|---|---:|---:|---|
| A100-40GB | 40 GB | $2.39 standard | Cheapest serious fp64 baseline |
| A100-80GB | 80 GB | $2.78 standard | Capacity headroom; particularly attractive if memory limits chains |
| H100 | 80 GB | $4.24 standard | Test whether bandwidth/compute gains justify its premium |
| H200 | 141 GB | $6.45 in the current large-container configuration | Only after identifying a capacity or bandwidth benefit |

These are repository estimates, not newly verified provider quotes. Host CPU/RAM reservations matter: the large-container configuration adds roughly $1.90/hour versus $0.29/hour standard. Avoid reserving 192 GiB merely to accommodate an eager loader.

B200-class hardware is worth a later benchmark, but it is not currently configured in the launcher. Newer hardware, tensor-core headline throughput and large memory do not establish better ordinary fp64 performance per dollar. Verify the actual device, arithmetic path, available memory and price before recommending it.

Use fp64 first for marginal log determinants, global reductions and acceptance calculations. Mixed precision can later save memory and use faster arithmetic, but must be checked on log-density **differences**, gradients, Hamiltonian errors and posterior contrasts—not just similar fitted rents. The existing fp32 NUTS failure is a warning, not proof that every mixed-precision design fails.

Use thelio for bounded preparation, code tests, tiny deterministic algebra checks and report rendering. Do not make a full-city fit depend on its 15 GB RAM or its consumer GPU's weak fp64 rate.

---

## 8. A staged experiment, not an open-ended rewrite

### What every engine must report

Use the same frozen model, feature values, split, price target and priors. Record cold and cached timings, compilation/warmup/sampling separately, peak host/device memory, bytes read/transferred, total cost, and failure/timeouts.

The main performance measure is **cost and elapsed time to adequate MCSE for prespecified worth contrasts**, subject to convergence and calibration—not samples/second or the best average ESS. Include `building_scale`, rare-feature contrasts, representative slow buildings, and building levels at their observed dates rather than checking only an extrapolated walk intercept.

### Proposed stages and spend ceilings

The following are budget allocations, **not runtime predictions**. Paid stages stop at their ceilings and wait for the next day's accrual if needed. Every individual fit stays within about one hour; no use of the historical large-fit exemption.

| Stage | Work | Spend ceiling | Decision |
|---|---|---:|---|
| 0. Contract and algebra | Freeze inputs; audit dimensions/memory; tiny dense marginal and conditional tests | No paid GPU allocation | Correct likelihood, gradients, priors and conditional covariance before performance work |
| 1. Library baseline and profile | Existing NumPyro NUTS versus BlackJAX adjusted microcanonical HMC on NB9; brief all-scraped kernel/memory measurements on A100 and H100 | $4 | If a generic engine meets the target, avoid the special marginal layer |
| 2. Structured reference | Building-marginal engine on NB9, using the winning library kernel; compare with a trustworthy same-data reference | $8 | Continue only if accuracy agrees and measured cost-to-precision materially improves |
| 3. Full-scale confirmation | One all-scraped fit with the selected engine; bounded streaming preparation/scoring | $5 | Adequate uncertainty and diagnostics within the hour, or explicitly record failure |
| 4. Approximation and beyond-memory pilot | Structured SVI against reference; tiny SBC pilot; force host/disk streaming with small memory limits | $8 | Separate inference bias from throughput and verify bounded-memory behavior |

**Total initial ceiling: $25 spread over at least three budget days**, longer if existing work uses the balance. Reallocate unused stage money rather than spending it automatically. A failed convergence test is investigated, not retried with a lucky seed. Small sampler/algebra benchmarks are implementation research, not replacements for full model-term fits.

A sensible engineering success threshold for stage 2 is **at least 2× better cost-to-precision** on the monitored difficult quantities, with no worse calibration. It is a decision threshold, not a prediction. If local marginalization fails to earn that gain, retain the simpler engine and pursue structured VI or a statistically justified simpler model.

The initial SBC pilot does not establish calibration. After measuring its cost, budget a larger batch—roughly 100 or more independent small/medium synthetic datasets, with full-scale recovery cases as affordable. Do not claim that 100 all-scraped fits cost the same as 100 tiny fits.

### Validation before treating results as established

1. **Algebra and transition correctness.** Compare the marginal density with a dense multivariate normal on tiny fixtures, including all scale-dependent constants; compare gradients and conditional covariance. Test reconstruction and composed transitions against an independent sampler.
2. **Same-model posterior agreement.** Compare prespecified means, interval widths, covariance and joint dollar contrasts within combined Monte Carlo error. Paired LOO agreement alone is insufficient: different coefficient posteriors can predict nearly identically. Account for multiple comparisons rather than demanding every one of hundreds of coordinates fall inside a naive fixed threshold.
3. **SBC under a declared generative model.** Draw parameters from the same proper priors used for fitting, simulate, fit, and inspect rank/coverage behavior. A narrowed prior is a useful separate test only if simulation and fitting use it consistently; it does not validate the entire original prior domain. Report finite-replicate uncertainty.
4. **Scientific recovery and misspecification.** Separately fix known amenity worths and simulate correlated amenities, missing-not-at-random features, measurement error, price conflicts and market shifts. Assess recovery of the actual contrasts. This is not interchangeable with prior-predictive SBC.
5. **Outside-model agreement.** Publish dated forecasts using only available evidence; compare market reactions on held-out ads and independent paid-rent records; run a prespecified natural-experiment analysis. Define how an active listing's not-yet-known latest ask becomes scoreable, without silently replacing it by first ask. If market reactions are later trained into the model, they cease to be independent validation for that fit.

For SVI or any approximate method, require the same substantive recovery and external checks plus sensitivity to approximation settings. Until that evidence exists, label its intervals approximate and do not serve them as established worth estimates.

---

## 9. First concrete outputs

The first research cycle should deliver:

1. An immutable, building-partitioned numerical snapshot with a bounded-memory loader.
2. A small benchmark report: generic library kernels versus building marginalization, on identical models and inputs, with actual cost-to-precision and memory.
3. A chunked posterior/diagnostic interface that does not require loading a 13 GB NPZ or a full draw-by-row matrix.
4. A calibration report distinguishing exact-target MCMC, approximation error, measurement error and identification limits.
5. One interpretable worth study with a prespecified external check—not just a faster leaderboard entry.

**Bottom line:** use large GPUs for batched local computation and library MCMC now; develop structured minibatch inference for truly large data; keep exact streaming as the fallback. Spend the resulting speed on stronger evidence about apartment qualities, rather than preserving today's random-effect machinery or maximizing predictive score alone.

---

## Sources and implementation references

### Repository evidence

Paths below are relative to the repository unless absolute:

- Adopted statement: `/data1/apartments/tmp/pi-research-2026-10-17/project-statement.md`.
- `docs/research-plan.md`; `docs/thelio-jobs.md`; `docs/model/modal.md`.
- `docs/model/mixing-review-2026-10-17.md`; `docs/model/compute-direction-2026-10-17.md`; `docs/model/gpu-inference-direction-2026-10-17.md`. The recommendation shares the last proposal's local-marginalization idea but does not adopt its unmeasured gradient/chain speed estimates or treat the remaining weights as integrated out.
- `frontier/src/rentfrontier/model.py`: `TIME_GROUPS`, `prepare`, `build_model`, `linear_predictor`.
- `frontier/src/rentfrontier/gibbs.py`: `build_design`, `_compact_parts`, `_compact_solve`, `make_step`.
- `frontier/src/rentfrontier/nuts.py`; `collect.py`; `loo.py`; `data.py`; `frontier/tests/test_gibbs.py`; `frontier/uv.lock`.
- `docs/data/fit-ready-rows.md`; `docs/data/pipeline.md`; `docs/data/point-in-time.md`; `docs/model/rolling-rent-validation.md`.
- `ops/modal/cap.py`; `ops/modal/app.py` for configured prices and resources.
- Measured run: `/data1/apartments/frontier/runs/m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise-sizeunkslope-slopemin3-unitnu4-all-scraped-v1-rows-e694a775-a40/` (`result.json`, `modal/modal.json`, ZIP directory of `posterior.npz`).
- Footer-only metadata reads: `/data1/apartments/pipeline/datasets/{rows-c3fa81d0f768b96b,ads-eaae0c38cca9d94a,records-11f851377371710e}.parquet`.

### Off-the-shelf methods

APIs were checked against the installed pinned source, not inferred solely from current online documentation:

- [NumPyro MCMC, Gibbs composition and HMCECS](https://num.pyro.ai/en/stable/mcmc.html).
- [BlackJAX adjusted microcanonical kernel](https://blackjax-devs.github.io/blackjax/autoapi/blackjax/mcmc/adjusted_mclmc/index.html); installed `adaptation/chees_adaptation.py`, `adaptation/meads_adaptation.py`, and package exports for SMC, Pathfinder and SGHMC.
- [Hoffman et al., *Stochastic Variational Inference* (2013)](https://www.jmlr.org/papers/v14/hoffman13a.html).
- [JAX gradient checkpointing](https://docs.jax.dev/en/latest/gradient-checkpointing.html).
- [GPyTorch stochastic variational GP regression](https://docs.gpytorch.ai/en/stable/examples/04_Variational_and_Approximate_GPs/SVGP_Regression_CUDA.html).

This session changed no repository or data files and launched no model fits, GPU work, or Modal jobs. The proposal is the sole authored deliverable.
