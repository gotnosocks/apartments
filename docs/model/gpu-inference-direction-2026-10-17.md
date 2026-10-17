# GPU inference for the all-scraped data (2026-10-17)

This is a proposal for fitting the rent model on the all-scraped data, and on larger datasets after
it, with off-the-shelf inference libraries on Modal's GPUs. I wrote it for Ben on 2026-10-17 with
the goal adopted on 2026-10-15 in mind. I worked from the model's structure and set the current
Gibbs sampler aside. The case for keeping Gibbs is in `compute-direction-2026-10-17.md`. When a
figure is my own estimate, I say so. Each estimate also appears as a written prediction under
Experiments, so I can record misses.

## Recommendation

I propose integrating each building's local effects out of the model exactly, then sampling the
remaining global parameters with a library sampler from BlackJAX or NumPyro.

- When I write each Student-t term as a normal with a Gamma-distributed weight, the model becomes
  linear and Gaussian given about 600 global parameters and the weights. Buildings are then
  independent of one another. For each building I can compute the likelihood with its walk, slopes,
  level and units integrated out, at the cost of a Cholesky factor of at most about 40 by 40.
- A library sampler (NUTS, MAMS or ChEES-HMC) then moves through about 600 dimensions instead of
  the 3.6 million latent values in the full model. After each of its steps I draw the building
  effects and the weights exactly from their conditional distributions.
- The per-building work batches well on a GPU. I'd split buildings into chunks to bound memory and
  across cards for speed, since each gradient needs only a sum of about 600 numbers across cards.

I predict a full all-scraped fit in 10 to 40 minutes on an H100, for $1 to $4, against 5.7 hours
and about $23 for the Gibbs fit on Oct 16. I derived these figures from operation counts. The
first paid experiment (E2, about $4) measures the time per gradient, and E3 times a whole fit on
NB9. Gibbs stays served until the new sampler matches the served NB9 fit and passes
simulation-based calibration.

## Cost of the last all-scraped fit

The Oct 16 fit (`m7-...-unitnu4-all-scraped-v1-rows-e694a775-a40`) ran Gibbs in fp64 on an
A100-SXM4-40GB in Modal's large container, at $4.01 an hour.

| stage | seconds | share of wall time |
|---|---|---|
| prepare | 912 | 4% |
| warmup, 300 sweeps | 900 | 4% |
| sampling, 2 chains of 4,500 sweeps | 15,533 | 76% |
| PSIS-LOO | 1,631 | 8% |
| variance shares | 630 | 3% |
| other | 866 | 4% |
| wall | 20,472 | 100% |

At the large-container rate in `ops/modal/cap.py`, the fit cost about $22.80 by my arithmetic. Each
sweep took 3.45 s. The fit failed the gate at the Carlyle (ESS 11.7, R-hat 1.093), one of 9
buildings with conflicting price clusters (P6 in `mixing-review-2026-10-17.md`). Among the
scalars, building_scale mixed slowest, with an integrated autocorrelation time of 32 sweeps. To
clear ESS 400 it needs about 6,400 sweeps per chain. So a faster Gibbs sweep would cut the cost
only in proportion to its speedup. Larger savings need a sampler with better mixing on the scales.

Prepare, PSIS-LOO and the variance shares took 53 minutes together. In a 20-minute fit they would
dominate, so I propose moving them as well.

## Computation for the adopted goal

The goal asks for results confirmed outside the model. Each kind of confirmation adds its own
computing load:

- **Known answers.** Simulation-based calibration (SBC) runs the sampler on 100 or more simulated
  datasets, plus a few recovery fits at full scale. At $23 a fit, ten recovery fits would cost
  $230, which the $10 a day budget accrues in 23 days.
- **Dated forecasts.** Forecasts for ads not yet posted need refits as data arrive, ideally weekly.
  A refit warm-started from the last posterior can skip most of its warmup.
- **The market's reaction.** The rent model leaves out time on market and price cuts. To keep the
  test independent, I'd fit the reaction as a second-stage model on the rent model's posterior
  draws, so I need those draws stored compactly or cheap to regenerate.
- **Location as a map.** A smooth location field, as a Hilbert-space Gaussian process (HSGP) with
  1,000 to 4,000 basis functions, adds that many global parameters. Measured features then compete
  with the field for the variation held by building effects.
- **Natural experiments.** Difference-in-differences terms around station and park openings add a
  few global coefficients each, or a space-time field.
- **Photos and floor plans.** Image embeddings come from a separate batch job and enter the rent
  model as a few dozen feature columns.

For all of these I need fits costing a few dollars, room for a larger global block and compact
posterior storage.

## Data size and memory

I measured the all-scraped data on thelio (`observations.jsonl`, 3.07 GB):

- It holds 1,751,152 rows in 67,773 buildings. Of these rows, 1,575,187 are training rows and
  about 175,000 are held out.
- Rows per building have a median of 7, a 99th percentile of 289 and a maximum of 3,226. Of the
  buildings, 11,147 have a single row.
- Each building's data spans a median of 14 half-year walk knots, and at most 34.
- By `unit_id` the data hold 842,400 units. The fit counted 871,143 under its own unit definition.
- The global design has 515 columns: an intercept, 170 feature columns, 68 trend knots, 4 season
  terms and 272 bedroom-by-time knots. The knot columns hold interpolation weights, so each row has
  at most 2 nonzero trend weights and 2 nonzero bedroom-by-time weights.

By my arithmetic the global design takes about 3.2 GB dense in fp32. Stored as the 171 dense
feature columns plus knot indices and weights, it takes about 1.1 GB. I haven't measured how
sparse the feature columns are, so a sparse layout may shrink it further. At ten times the rows,
the compact layout would take about 11 GB and still fit on a 40 GB card. So the rent data stays
within a single card's memory for every dataset now planned.
The workloads larger than memory lie elsewhere:

- **Posterior draws.** The Oct 16 `posterior.npz` takes 13.4 GB. I'd keep the global draws, a
  thinned set of building-effect draws and per-building running summaries, under 3 GB in all.
- **Photos.** At an estimated 13 photos per ad (I haven't counted), the data hold about 20 million
  images. Stored as files they would take terabytes, so I'd stream them through the embedding
  model: fetch, embed, keep the vector and drop the image. Fetching them needs its own plan with
  Data collection.
- **Simulation replicates and predictive checks.** Each replicate runs independently, so they spread
  across cards and containers.

For exact MCMC, out-of-core streaming has a steep price. A gradient reading 1.5 GB over PCIe at
about 25 GB/s takes 0.06 s, while NUTS needs dozens of gradients per iteration. So I'd keep the
model's data resident in GPU memory, across several cards if it ever outgrows one. I'd stream
from host memory or disk only in passes made once per iteration or once per fit: exact draws of
building effects, LOO, predictions and posterior summaries. Subsampling MCMC (HMCECS in NumPyro) and
stochastic-gradient MCMC trade exactness for memory, so I'd hold them in reserve.

## Proposed sampler

### The model in conditionally Gaussian form

In the all-scraped fit, each row's log rent comes from a sum of global terms and building terms,
plus a unit effect and a residual. The global terms cover features, trend, season and bedrooms by
time. The building terms cover the level, the half-year walk, the bedroom slope and the feature
slopes. The unit effect is Student-t with nu fixed at 4, while
the residual is Student-t with nu estimated. I'd write both as scale mixtures:

```
residual:  e_i | w_i ~ Normal(0, sigma_g(i)^2 / w_i),  w_i ~ Gamma(nu / 2, nu / 2)
unit:      u_j | v_j ~ Normal(0, s_u^2 / v_j),         v_j ~ Gamma(2, 2)
```

I group the remaining parameters in two blocks:

- `theta`, about 90 hyperparameters: the 68 noise sds by bedroom group and year, about 20 scales
  and correlations, and nu.
- `G`, 515 global coefficients: the intercept, 170 feature coefficients, 68 trend knots, 4 season
  terms and 272 bedroom-by-time knots.

Given `theta`, `G` and the weights, building k's rows follow a linear Gaussian model:

```
y_k = X_k G + Z_k a_k + U_k u_k + e_k
a_k ~ Normal(0, Lambda_k(theta))    level, walk knots and slopes
u_k ~ Normal(0, V_k)                one effect per unit
e_k ~ Normal(0, D_k)                diagonal, from sigma and w
```

Buildings share only `theta` and `G`, so given those they're conditionally independent.

### The per-building marginal

For each building I integrate `a_k` and `u_k` out, giving `y_k ~ Normal(X_k G, C_k)` with
`C_k = D_k + U_k V_k U_k' + Z_k Lambda_k Z_k'`. I'd evaluate its log density without forming
`C_k`:

1. Fold each unit's effect into the noise with the Sherman-Morrison formula. Each unit adds a rank-1
   term, so the work comes down to segment sums over each unit's rows.
2. Fold the building block in with the Woodbury identity. `Z_k` has `p_k` columns: the level, the
   knots spanned by the data and the slopes. On all-scraped, `p_k` comes to about 20 at the median
   and about 40 at most. The work comes down to segment sums for `Z_k' A_k^-1 Z_k` and a
   `p_k` by `p_k` Cholesky factor.
3. Fold knots outside the data range in analytically. Knots after a building's last data knot drop
   out of the likelihood. Steps before its first data knot add up to a single Gaussian offset,
   which joins the level.

By my count a full evaluation takes 10^9 to 10^10 floating-point operations, most of them in
segment sums over 1.6 million rows and 67,735 small Cholesky factors. Memory traffic and kernel
launches should limit it more than arithmetic. I'd group buildings into buckets by `p_k` (8, 16,
24 and 40) so the batched Cholesky wastes little on padding. JAX differentiates through the batched
Cholesky, so a gradient costs a small multiple of an evaluation.

The NumPyro `build_model` stays the model's only definition. The marginal acts as a transformation
inside the sampler. In E1 I'd test it against `build_model`'s log joint on small datasets.
BlackJAX includes an adjoint-differentiated Laplace marginal (`laplace_hmc`), but it forms a dense
Hessian over the whole latent vector, which rules it out at 3.6 million dimensions. So the
structured marginal needs a few hundred lines of project code on JAX's batched linear algebra, with
library samplers around it.

### Sampling the global block with library samplers

In each iteration I'd make these draws:

1. Update `theta` (without nu) and `G` together with a library gradient-based kernel on
   `p(theta, G | w, v, y)`, with the building effects integrated out.
2. Draw each building's `a_k` and `u_k` exactly from their Gaussian conditional. The library kernel
   returns only the new position, so this step factors each building's block once more there.
3. Draw nu from its conditional given the residuals, with `w` integrated out. Its density is
   one-dimensional, so I can evaluate it on a grid of a thousand values in parallel over rows. The
   grid has to follow the posterior, since on Oct 16 the posterior sd of log nu came to 0.0034. I'd
   use the gridded density as the proposal of an independence Metropolis step, which keeps the
   draw exact. Then draw `w` and `v` from their Gamma conditionals.

Because step 3 draws `w` right after nu, the partially collapsed sampler stays valid. In the mixing
review (P1), the Gibbs sampler's random-walk step for nu came to 13 to 15 times nu's posterior sd.
The exact draw removes that step.

NumPyro's `HMCGibbs` can host this pattern, with NUTS on the gradient sites and a function of my
own for the exact draws. Its inner kernel conditions on the Gibbs sites, so the model I pass it has
to be the marginal itself, with `w`, `v` and nu as Gibbs sites. My Gibbs function would draw
`a_k` and `u_k` on the side. BlackJAX offers more choice of kernel:

- MAMS, the Metropolis-adjusted microcanonical Hamiltonian Monte Carlo of Robnik, Cohn-Gordon and
  Seljak, needed up to 7 times fewer gradients than NUTS in its authors' benchmarks. BlackJAX calls
  it `adjusted_mclmc`.
- ChEES-HMC tunes a single trajectory length across many chains. MEADS adapts its step size,
  damping and mass matrix across chains and has no trajectory length to tune.
- With about 600 dimensions, a dense mass matrix becomes affordable. NUTS on the early L4 model
  took about 245 leapfrog steps per iteration with a diagonal mass matrix, and the research plan
  traces that to correlations among the feature coefficients and the trend. BlackJAX also has a
  low-rank metric adaptation.

### Many chains on a single card

At 1.6 million rows I expect a single chain to leave most of an H100 idle. If I run chains as a
batch dimension with `jax.vmap`, they fill the card, so 8 to 32 chains should cost little more
wall time than 1 (a prediction for E2). Samplers with a fixed trajectory length suit this best.
Under `vmap`, NUTS keeps every chain running until the longest tree finishes, while MAMS and
ChEES-HMC move all chains in lockstep. With many chains, warmup becomes the main cost, since every
chain pays for it. ChEES and MEADS adapt across chains, which shortens warmup. Nested R-hat, from
Margossian and coauthors in Bayesian Analysis (2024) and available in ArviZ 1.3, gives a
convergence check suited to many short chains. I'd choose the chain count by dollars per minimum
ESS, measured in E2 and E3.

### Streaming and several cards

Because buildings are independent given `theta` and `G`, the marginal log density adds up over
buildings. I'd store rows sorted by building and evaluate the sum in chunks with `lax.scan` and
`jax.checkpoint`, so the gradient's memory grows with the chunk instead of the dataset. Across
cards, I'd shard buildings with `jax.sharding` and add the per-card results with a `psum` of about
600 numbers per gradient. Modal offers up to 8 H100s in a container, about 640 GB of GPU memory.
At 1.6 million rows I expect a single card to suffice. The multi-card path matters for later
datasets, such as full ad histories or other boroughs, and for batches of SBC replicates.

### Storage and the passes around the sampler

- **Posterior storage.** I'd keep the global draws, a few hundred thinned draws of the building
  effects, per-building running means and variances, and the level at each building's median data
  knot for the P4 check. These come to under 3 GB, against 13.4 GB.
- **Prepare.** I'd build the building-sorted arrays once per dataset on a CPU container, or on
  thelio in a memory-capped scope, and cache them on a Modal volume. Starting from prepared arrays,
  the GPU container skips the 912 s of preparation, which moves to a CPU job costing cents.
- **PSIS-LOO.** I'd compute the pointwise log-likelihoods and the Pareto smoothing on the GPU in
  row chunks. I estimate a few minutes, against 1,631 s.
- **Variance shares.** I'd compute these on the GPU in chunks from the stored draws.

Without the large container, the fit runs at the standard container price in `cap.py`: $2.39 an
hour for an A100-40GB and $4.24 for an H100, against $4.01 and $5.86 in the large container. The
standard container's 24 GiB of host memory holds prepared arrays of about 2 GB easily. `app.py`
offers the H200 only in the large container, at $6.45 an hour.

## Other approaches and their roles

| approach | library | role | reason it stays secondary |
|---|---|---|---|
| joint NUTS or MAMS over all 3.6 million latent values | BlackJAX, NumPyro | fully generic baseline in E3 | funnels between scales and building effects. NUTS on the much smaller m1q, with the walk, didn't finish in 60 minutes on thelio |
| SVI with building minibatches | NumPyro, optax | cheap screening of candidate terms | approximate, with overconfident intervals. Using it to choose tests would change the rule giving every test its own full fit |
| R-INLA on a Modal CPU | R-INLA | independent cross-check on a reduced model | handles a handful of hyperparameters, against about 90 here |
| DALIA, GPU INLA (arXiv 2507.06938) | research code | watch | young code built for spatio-temporal Gaussian processes |
| SMC with tempering | BlackJAX | multimodal posteriors | after the P6 data fixes, I don't expect multimodality |
| perturb-then-optimize with stochastic log-determinants | lineax, matfree | fine-grained spatial fields | noisy log-determinants would bias exact MCMC |
| data-tempered SMC or warm-started refits | BlackJAX `partial_posteriors_smc` | weekly refits for dated forecasts | later, once the main sampler works |

## Choosing a GPU

| GPU | Modal list price per hour | standard container in `cap.py` | memory (GB) | bandwidth (TB/s) | fp64 (TFLOPS) |
|---|---|---|---|---|---|
| L4 | $0.80 | $1.09 | 24 | 0.3 | weak |
| L40S | $1.95 | not in `app.py` | 48 | 0.86 | weak |
| A100-40GB | $2.10 | $2.39 | 40 | 1.56 | 19.5 |
| A100-80GB | $2.50 | $2.78 | 80 | 2.04 | 19.5 |
| H100 | $3.95 | $4.24 | 80 | 3.35 | 67 |
| H200 | $4.54 | large container only, $6.45 | 141 | 4.8 | 67 |
| B200 | $6.25 | not in `app.py` | about 180 | 8.0 | about 40 |

The list prices come from Modal's pricing page and cover the GPU alone. I took bandwidth and fp64
figures from vendor spec sheets and haven't checked them against Modal's exact parts. For
memory-bound work, the B200 and H200 give the most bandwidth per dollar, followed by the H100 and
A100. The H100 gives the most fp64 arithmetic per dollar. At 1.6 million rows I expect kernel
launches to limit speed, in which case the cheapest card with fast fp64 gives the lowest cost: the
A100-40GB at $2.39.

The L4 and L40S run fp64 at a small fraction of their fp32 rate. They become useful only if mixed
precision works, with per-building terms in fp32 and the sums over buildings and the HMC energy in
fp64. NUTS in pure fp32 failed on thelio (a chain's step size collapsed), so I'd compare mixed
precision with fp64 on identical inputs before trusting it. E2 measures dollars per gradient on
each card.

## Experiments

Each experiment comes with predictions written before it runs, a cost and a criterion. E0 and E1
are free and run on thelio under the standing approval for free checks. The paid ones wait for Ben,
then run one at a time within the $10 a day limiter and the 1-hour cap. Model changes built on the
new sampler go through the evaluation framework as before.

### E0. Prepared arrays and structure (free, thelio)

In a `MemoryMax=3G` scope, I'd build building-sorted arrays for all-scraped: the sparse design,
unit and building segment indices, knot spans and size buckets.

- Prediction: the largest `p_k` comes to at most 40.
- Prediction: the arrays take under 1.5 GB with fp32 values and int32 indices.
- Prediction: at least half the buildings need `p_k` of 16 or less.

### E1. Exactness of the marginal (free, thelio CPU)

On datasets of about 2,000 rows simulated from `build_model`, with JAX on the CPU, I'd check these
predictions:

- The marginal log density matches a dense multivariate normal to a relative error under 1e-10 in
  fp64.
- Gradients match central finite differences to a relative error under 1e-6.
- Exact draws of building effects match the dense Gaussian conditional's mean and covariance over
  10^5 draws.
- `build_model`'s log joint, integrated analytically, matches the marginal.

Then I'd run the whole sampler on a 20,000-row slice of NB9 on the CPU and compare it with a long
Gibbs run on the same slice, under the agreement criterion in E3.

### E2. GPU microbenchmarks (Modal, about $4)

I'd time a gradient of the marginal and an exact draw of the building effects on all-scraped data,
on the L4, L40S, A100-40GB, H100 and H200, for 1, 8 and 32 chains, in fp64 and mixed precision.
Each benchmark runs a few minutes. The L40S needs an entry in `app.py` first, and the H200 runs in
the large container.

- Prediction: a gradient in fp64 with 1 chain takes 5 to 20 ms on an H100.
- Prediction: 32 chains on an H100 take less than 4 times the wall time of 1 chain.
- Prediction: the A100-40GB or the H100 in fp64 gives the lowest dollars per chain-gradient.
- Prediction: mixed precision keeps the absolute error in the log density under 0.01.

### E3. Agreement on NB9, and the joint baseline (Modal, $3 to $6)

On an H100, I'd fit the served NB9 model on its own rows (`5dbdc4f1`) with the new sampler, once
with MAMS on 16 chains and once with NUTS. I'd also run joint MAMS over all latent dimensions,
stopped at 30 minutes. The new sampler agrees with the served Gibbs fit when:

- The paired pointwise elpd difference falls within 2 combined MCSE.
- Each global parameter's posterior median falls within 3 MCSE or 0.1 posterior sd.
- Each variance share falls within 1 percentage point.
- The every-building gate passes, with the P4 level check added.

Predictions:

- The new sampler agrees with Gibbs under both kernels.
- Its fit stage takes under 10 minutes, against 2,071 s for Gibbs.
- Its minimum ESS per dollar comes to at least 5 times that of Gibbs.
- Joint MAMS falls short of ESS 400 on building_scale within 30 minutes, or costs at least 5 times
  more per minimum ESS than the marginalized sampler.

### E4. Simulation-based calibration and known answers (Modal, $3 to $5)

- **SBC.** I'd simulate 100 datasets of about 50,000 rows in 2,000 buildings from the model's
  priors, with the scale priors narrowed around the NB9 posterior so the data look realistic. The
  fits use the same narrowed priors, which keeps SBC valid as a test of the inference code. The
  replicates run as a batch on one or two cards. Prediction: the rank histograms of about 20
  monitored quantities (hyperparameters, a sample of feature coefficients and building levels) pass
  a uniformity test at the 1% level, after allowing for the number of tests.
- **Known answers.** I'd run 3 recovery fits at NB9 scale on data simulated from the NB9 posterior
  medians, with feature worths set to known values. Prediction: the 90% intervals cover the true
  feature coefficients 85 to 95% of the time, and the variance shares come back within 2 points.
  This delivers the goal's fake-data recovery test for the current model.

### E5. All-scraped fit (Modal, $1 to $4)

I'd run it after E3 and E4 pass, and after Data improvements resolves the P6 buildings. I'd use the
standard container, since the predicted time falls within the 1-hour cap. If E3 points to a longer
run, the large container's exemption from the cap applies, at $5.86 an hour on an H100.

- Prediction: the fit stage takes 10 to 40 minutes on an H100.
- Prediction: with LOO and variance shares on the GPU, the run costs $1 to $4. I'd record anything
  above 60 minutes or $6 as a miss.
- Prediction: the gate passes everywhere except at buildings with unresolved price conflicts.

### Later

- A sharding test on 2 and 8 H100s with a simulated 15-million-row dataset. Prediction: 8 cards
  give at least 5 times the throughput of 1.
- Out-of-core passes for predictions and LOO, with the data on disk.
- An SVI calibration, ranking past candidate tests by SVI and by full-fit paired LOO. I'd ask about
  using SVI to screen only after measuring their agreement.
- Warm-started weekly refits for dated forecasts.
- An HSGP location field in the global block, as the first model change built on the new sampler.
- Integrated PSIS-LOO, which integrates each row's own unit effect and weight out of its pointwise
  likelihood, to cut the 32,430 rows with Pareto k above 0.67. Because it changes the score's
  definition, it would need its own decision.

## Risks and signals

- **The global block mixes slowly.** If `theta` and `G` correlate strongly, NUTS and MAMS slow down.
  In E3 this would appear as low ESS per gradient on the scales. I'd then draw `G` exactly given
  `theta` as a Gaussian block and sample `theta` alone. To integrate `G` out, every gradient needs
  the Schur complement of `G`, a 515 by 515 sum over buildings. By my estimate that adds 10^11 to
  10^12 operations per gradient, several times the marginal's own cost, so I'd switch only on
  evidence from E3.
- **The noise scales mix slowly given the weights.** The sampler moves `sigma_g` and `unit_scale`
  with `w` and `v` held fixed, as Gibbs does. Their autocorrelation times may then stay near the
  Gibbs values of 7 to 12 sweeps, which would put the E3 prediction of 5 times the ESS per dollar
  at risk. I'd then add a joint rescaling move for each scale and its weights, like the rescale
  moves in the Gibbs sampler.
- **The weights mix slowly at conflicting buildings.** If a few building levels show low ESS while
  the scalars mix well, the likely cause is the same kind of price conflict as in P6. I'd fix the
  data first, as for any sampler.
- **Mixed precision fails.** E2 measures the energy error directly. On a failure I'd stay in fp64
  on an A100 or H100.
- **Kernel launches dominate even with many chains.** If E2 measures a flat time per gradient
  across cards, I'd choose the cheapest card with fast fp64, then fuse kernels and enlarge the
  buckets.
- **Library limits.** `HMCGibbs` might adapt poorly while the exact-draw sites change. BlackJAX also
  changes its API between releases. I'd fix library versions in the frontier lockfile, and if
  needed write the outer loop in BlackJAX directly.
- **Agreement fails on NB9.** I'd trace the cause with E1's exactness tests and a per-quantity
  comparison before changing anything else, with Gibbs served meanwhile.

## Changes to current work if adopted

- No more all-scraped Gibbs fits.
- The Gibbs tuning proposals P1 (the nu step) and P2 (a solo update for building_scale) stop. The
  new sampler draws nu exactly and moves building_scale jointly with the other scales.
- P3 (the AR walk), P4 (the level check), P5 (centered slopes) and P6 (price conflicts) continue,
  since they concern the model, the gate and the data. All of them carry over to the new sampler.
- The served model stays on Gibbs until E3 and E4 pass. After that, I'd switch samplers through a
  reviewed PR and refit the served model with the new sampler.

## Decisions for Ben

1. Adopt this direction: reopen the sampler line, and replace Gibbs once the new sampler matches the
   served NB9 fit (E3) and passes SBC (E4). I recommend yes.
2. Approve Modal spend for E2 to E5, about $11 to $19 in all, run one at a time within the $10 a
   day limiter. I won't launch anything on Modal before you say. I recommend yes.

E0 and E1 cost nothing, so I'd start them while waiting.
