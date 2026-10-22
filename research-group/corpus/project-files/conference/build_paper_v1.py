from common import HERE, data_js, page

BODY = """
<main>
<header class="top">
  <div class="kicker">Short paper · Draft of 22 October 2026</div>
  <h1>What a floor, a dishwasher and a park are worth: a Bayesian hedonic model of 1.9 million New York rental ads</h1>
  <p class="byline">Apartments project</p>
</header>

<section class="col">
<div class="card">
<h3>Abstract</h3>
<p style="margin:0">We estimate the asking-rent value of apartment qualities in Manhattan and Brooklyn from 1,896,486
StreetEasy rental listings, 2010 to 2026, in 67,977 buildings. The model combines a weekly market walk, a
Gaussian-process rent surface for each of two zones, a partially pooled level for every building, unit and building
attributes, and a Gaussian-process floor curve. Adding the floor curve improves the held-out log score on the newest
189,649 ads by 2,945 (SE 83) and lowers RMSE from 11.7% to 11.5%, with calibrated 90% predictive intervals (90.4%
coverage). In elevator buildings rent rises with floor and rises faster with height: +3.8% at floor 10, +6.7% at 20
and +13.8% at 40 over floor 1 (90% intervals within ±0.5 points); in walk-ups it falls slightly. A unit 10% larger
than typical for its bedroom count asks 2.3 to 2.4% more; in-unit laundry is worth 5.7 to 6.3% and a dishwasher 1.8
to 2.0%, where each range spans a random-effects and a Mundlak estimate. Simulations with known truth show the
random-effects estimates of unit features are biased upward by 0.1 to 0.7 points and that posterior intervals for
coefficients cover their truth only 69 to 81% of the time. Of seven named location features tested on buildings
withheld from fitting, only frontage on a large park (+3.5%, 90% 2.6 to 4.3) improves forecasts; distances to parks,
water and transit relabel the rent surface without improving forecasts for unseen buildings.</p>
</div>
</section>

<section class="col">
<h2>1. Introduction</h2>
<p>Hedonic models price a good as a bundle of qualities (Rosen, 1974). For rental housing the bundle has three
layers that are hard to separate: the unit, the building it sits in, and the place the building sits. A doorman
building on a park in a desirable neighbourhood has larger, better-equipped units, so a regression that pools these
layers will credit the unit with value that belongs to the building or the block.</p>
<p>We take worth to mean the difference in asking rent between two apartments that are alike except for one
quality. Our design makes that comparison explicit at each layer. Unit qualities are identified within buildings,
because every building has its own level. Building qualities are identified between buildings at the same point on a
smooth rent surface. Location is the surface itself, and we test whether measurable features of the city can
explain it.</p>
<p>The contributions are: (i) a model that runs on 1.7 million training rows in about twenty minutes on one GPU, with
68,000 building effects and two reduced-rank Gaussian-process surfaces; (ii) a floor curve that is the largest
predictive gain after unit size; (iii) a simulation audit that quantifies the bias random building effects impose on
unit features and the undercoverage of coefficient intervals; and (iv) a negative result on location: smooth distance
features recover stable coefficients but add nothing to forecasts for buildings the model has not seen.</p>
</section>

<section class="col">
<h2>2. Data</h2>
<p>The data are rental listings scraped from StreetEasy between July 2010 and October 2026. The unit of
observation is an ad; the target is the ad's latest net-effective ask, that is, the last asking rent after
advertised concessions, on the log scale. Furnished and short-term listings are excluded. Each building is matched to
a tax lot (BBL) in MapPLUTO, which supplies year built, alterations, floor count and footprint; the registry is
extended by geocoding so that every row has a location. Manhattan has 21,994 buildings and 1,115,906 ads; Brooklyn
and a small part of Queens (Ridgewood and Glendale) have 45,983 buildings and 780,580 ads.</p>
<p>Unit fields come from the listing: bedrooms, full and half baths, stated size (44.9% of training rows; a further
18.8% filled from the same unit's or the same line's other ads), laundry (in unit 29.0%, in building 36.8%),
dishwasher (54.8%), floor and unit label. Building fields come from listings and city data: doorman (full, part,
virtual), elevator, condo, gym, retail, height, year built, alterations, and frontage on a through truck route.
Rent stabilization, income restriction and shared space are taken as stated in the ad.</p>
<p>We hold out the newest 189,649 ads (the <i>latest split</i>). Every held-out ad's building also has training
ads, so this split tests prediction of new ads in known buildings. A second split holds out 6,798 whole buildings
and their 184,437 ads (the <i>building split</i>) and is the only one that can test a building-level feature.</p>
</section>

<section class="col">
<h2>3. Model</h2>
<p>For ad <i>i</i> in building <i>b</i> in zone <i>z</i>,</p>
<div class="eq">y_i  = L(t_i) + S(d_i) + x_i'β + f_g(i)(log floor_i) + η_b + ε_i,    ε_i ~ t_ν(0, σ_k(i))
η_b  = F_z(s_b) + w_b'γ + u_b,                                       u_b ~ N(0, b_z²)
F_z  ~ GP(0, a_z² k_SE(·,·; ℓ_z))   (Hilbert-space basis, rotated box per zone)
f_g  ~ GP(0, c_g² k_SE(·,·; λ_g)),  f_g(0) = 0,   g ∈ {elevator, walk-up}</div>
<p>L is a weekly random walk with drift and normal shocks; S has two annual harmonics. The vector x holds
cumulative bedroom steps, bath steps by bedroom count, log size relative to the median stated size for the bedroom
count (with imputed and unknown flags), laundry, dishwasher and floor flags (penthouse, garden, lower level, top
floor, floor unknown). The building level η<sub>b</sub> is centred on the zone surface F<sub>z</sub> plus building
attributes w<sub>b</sub>. The residual scale σ varies by bedroom group and ν is estimated.</p>
<p>The two zones, Manhattan and Brooklyn plus Queens, are split at the river. Each surface uses a reduced-rank
Hilbert-space approximation (Solin and Särkkä, 2020; Riutort-Mayol et al., 2023) on a box rotated to the zone's
footprint. The floor curves are exact GPs on log floor, pinned to zero at floor 1 and capped at floor 47 (elevator)
and 6 (walk-up), roughly the 99th percentile of each. Coefficients take Normal(0, 0.5) priors; amplitudes and
building spreads take HalfNormal(0.3); the floor amplitude squared takes an inverse gamma with median amplitude
0.15.</p>
<p>We sample with NumPyro (Phan et al., 2019) using ChEES-adapted HMC (Hoffman et al., 2021): four chains, 300
warmup and 1,000 sweeps, keeping every fifth. The surface coefficients are sampled in coordinates whitened by
their approximate posterior precision, which raised the stable step size by two orders of magnitude; the floor
lengthscale is drawn with the amplitude integrated out. The fit takes 19 minutes on one A100 and costs $0.73.</p>
</section>

<section class="col">
<h2>4. Evaluation protocol</h2>
<p>Each candidate term is a separate full fit. Before launch we write predictions for its coefficients, cost and
scores, and we record misses as misses. A fit must pass a convergence gate (rank-normalised R-hat ≤ 1.01 and bulk
ESS ≥ 400 on every traced quantity; Vehtari et al., 2021). Fits are compared by the paired held-out log predictive
density (elpd) on shared rows, with standard errors from per-building sums; we require a gain of about 2 SE.
Building-level features must also beat a within-zone permutation null on their share of explained held-out building
residuals. We report predictive medians and intervals. Separately, we fit the model to rents simulated from a known
truth and score coverage of the truth, in the spirit of simulation-based calibration (Cook et al., 2006; Talts et
al., 2018), though with a fixed truth rather than draws from the prior.</p>
</section>

<section class="col">
<h2>5. Results</h2>
<h3>5.1 Fit and forecast</h3>
<p>The model passes the gate (max R-hat 1.0097, min ESS 590, both on the outer zone's surface amplitude; all floor
hyperparameters R-hat ≤ 1.001). Table 1 shows the path to it.</p>
<div class="tw"><table>
<thead><tr><th>Model</th><th class="n">Δ elpd vs previous (SE)</th><th class="n">RMSE</th><th class="n">90% cov.</th></tr></thead>
<tbody>
<tr><td>Zones + building levels + building attributes</td><td class="n">n/a</td><td class="n">0.1244</td><td class="n"></td></tr>
<tr><td>+ size, laundry, dishwasher, truck route</td><td class="n">+9,818 (≈160)</td><td class="n">0.1173</td><td class="n"></td></tr>
<tr><td>+ gym</td><td class="n">−11 (3)</td><td class="n">0.1173</td><td class="n">88.2%</td></tr>
<tr><td>+ year built, alteration, retail</td><td class="n">+32 (18)</td><td class="n">0.1173</td><td class="n">88.3%</td></tr>
<tr><td><b>+ floor curve and flags</b></td><td class="n"><b>+2,945 (83)</b></td><td class="n"><b>0.1154</b></td><td class="n"><b>90.4%</b></td></tr>
</tbody>
<caption>Table 1. Held-out scores on the latest split (189,649 ads). RMSE is on log rent. Coverage for the earlier rows was computed with fewer draws (68 against 400), which narrows sampled intervals; the floor fit's own comparison at 400 draws gives 90.4% for both it and its predecessor.</caption>
</table></div>
<p>The floor gain is concentrated where theory says it should be: elevator floors 3 to 19 (+1,972), top floors
(+911) and penthouses (+706), where the previous model's median error of +10.5% falls to −0.3%. On the building
split, a new building's level is drawn from its zone's prior; RMSE rises to 0.182 and 90% coverage is 92.7%. The
heavy tails are real: ν ≈ 4.1.</p>

<h3>5.2 Floor</h3>
<p>Figure 1 shows the two curves. In elevator buildings each doubling of the floor adds more than the last above
floor 2: 0.3 points from 2 to 4, 1.6 from 4 to 8, 2.6 from 8 to 16 and 4.8 from 16 to 32. A penthouse adds 8.3%
(90% 8.1 to 8.5) above its floor's value and the top floor of an elevator building 1.75%. Walk-ups decline by about
0.2 points per floor, to −0.9% at floor 5, consistent with a small discount for stairs. Adding the curve moves the
elevator premium from 6.8% to 3.6%, since elevator units sit higher, and leaves the building effects nearly unchanged
(correlation 0.998), so floor explains within-building variation that building terms cannot.</p>
</section>
<figure>
  <div class="frame">
    <div class="legend"><span><i class="sw a"></i>Elevator buildings, median and 90% interval</span><span><i class="sw b"></i>Walk-ups</span></div>
    <div id="floor"></div>
  </div>
  <figcaption><b>Figure 1.</b> Asking-rent premium over floor 1 of the same building. Floors 47 and above share one value.</figcaption>
</figure>

<section class="col">
<h3>5.3 Unit qualities</h3>
<p>Figure 2 reports unit premiums from the model (teal) and from a variant that adds each building's mean of the
unit columns to the building level (Mundlak, 1978; Bell and Jones, 2015), which identifies unit coefficients from
within-building contrasts only. Size has an elasticity of 0.252 (90% 0.251 to 0.253), 0.242 under Mundlak. In-unit
laundry is worth 6.3% (6.26 to 6.39) against unstated laundry, 5.7% under Mundlak; laundry in the building 1.7% and
1.4%; a dishwasher 2.0% and 1.85%; a private garden or outdoor space 2.9% and 2.3%. A unit with no stated size asks
4.0% less than one of typical size, which we read as a disclosure effect. Bedroom and bath steps barely move between
the two models.</p>
</section>
<figure>
  <div class="frame">
    <div class="legend"><span><i class="sw a"></i>Random building effects</span><span><i class="sw b"></i>With building means (Mundlak)</span></div>
    <div id="unit"></div>
  </div>
  <figcaption><b>Figure 2.</b> Unit-level premiums, 100(e<sup>β</sup>−1), posterior median and 90% interval.</figcaption>
</figure>

<section class="col">
<h3>5.4 Building qualities</h3>
<p>Between buildings at the same point on the surface, a full-time doorman is worth 15.0% (14.2 to 15.8), a condo
building 10.5%, a part-time doorman 8.4%, a gym 6.7%, construction since 2010 4.1%, construction before 1900 4.0% and
an elevator 3.6%. Ground-floor retail costs 1.9% and frontage on a through truck route 3.9%. Ads stating rent
stabilization ask 2.4% less, and income-restricted ads 10.4% less. Under Mundlak these building terms shrink by a
sixth to a half (condo to 6.2%, construction since 2010 to 2.0%), because the building means absorb part of what
distinguishes such buildings (Figure 3). The two numbers answer different questions: the first compares buildings
as they are, the second compares buildings with the same unit mix.</p>
</section>
<figure>
  <div class="frame">
    <div class="legend"><span><i class="sw a"></i>Random building effects</span><span><i class="sw b"></i>With building means (Mundlak)</span></div>
    <div id="bld"></div>
  </div>
  <figcaption><b>Figure 3.</b> Building-level premiums and ad flags, 100(e<sup>β</sup>−1), posterior median and 90% interval.</figcaption>
</figure>

<section class="col">
<h3>5.5 Location</h3>
<p>Of the variance of log rent across training ads (0.192), the surface carries 23% and the residual building levels
8%. We tested whether named features explain the surface (Table 2). Six smooth distances (nearest station, routes
served, any park, parks of 30+ acres, shoreline, a noise index) take 7.6% of the surface's variance with coefficients
that are stable across splits; the largest is −2.1 points per log km from a large park. On the building split they
improve the held-out log score by only 26 (SE 116), and their contribution correlates −0.97 with the change in the
surface: they relabel the surface rather than add to it.</p>
<div class="tw"><table>
<thead><tr><th>Feature (separate fit)</th><th class="n">Premium, 90% interval</th><th class="n">Δ elpd, building split (SE)</th></tr></thead>
<tbody>
<tr><td>Six smooth distances, jointly</td><td class="n">big park 4.7 pts, water 3.5 pts (p10–p90)</td><td class="n">+26 (116)</td></tr>
<tr><td>Faces a park of ≥ 5 acres (within 40 m)</td><td class="n">+3.5% (2.6, 4.3)</td><td class="n">+187 (80)</td></tr>
<tr><td>Within 150 m of shoreline</td><td class="n">+5.4% (3.5, 7.4)</td><td class="n">−229 (130)</td></tr>
<tr><td>Within 30 m of an elevated track</td><td class="n">−2.4% (−3.5, −1.5)</td><td class="n">−41 (51)</td></tr>
<tr><td>Mid-block on an avenue</td><td class="n">−1.8% (−2.5, −1.3)</td><td class="n">+86 (89)</td></tr>
</tbody>
<caption>Table 2. Location features. The four step features were each added to the six-distance model and compared with it on the building split (6,798 held-out buildings, 184,437 ads).</caption>
</table></div>
<p>Park frontage is the one exception. Held-out park-facing buildings were underpriced by 4.3 points by the model
without it and by 1.6 with it. On rents simulated with a planted 3.46-point step, the model returned 3.54 (2.75 to
4.27) and moved the surface and building levels at park-facing buildings by 0.1 point or less. It nonetheless falls
short of the permutation test (0.30% explained share against a null 95th percentile of 0.46%), so we treat it as
provisional. Waterfront looks strong in training but worsens forecasts for its 42 held-out buildings.</p>
</section>

<section class="col">
<h2>6. Simulation audit</h2>
<p>We simulated rents from the fitted model's medians under three scenarios (realistic, a null with zero floor and
feature effects, and a planted building-height effect) and refit. All three pass the gate. Coverage of 90% intervals
over 119 scalar terms was 80.7%, 75.6% and 73.9%; a fourth recovery for park frontage gave 69%. The misses repeat in
every run, in the same direction: size comes back 0.6 to 0.7 points high, in-unit laundry 0.4, dishwasher 0.1 to 0.2.
Each unit column's bias follows its correlation with the true building level (size +0.24, laundry +0.22, dishwasher
+0.21), the familiar bias of random effects correlated with regressors. Adding building means reduces every unit
bias to 0.03 points or less, but shrinks building attributes toward zero (condo 6.6 against a truth of 10.0) and
worsens recovery of the surface. The surface itself recovers well in every scenario (slope 0.99, coverage 94 to 99%)
and building levels cover at 90%, shrinking toward zero in buildings with few ads as they should.</p>
<p>The audit's caveat is that the truth was drawn from the fitted model, whose building levels were estimated
alongside its attributes, which favours the random-effects split of variance. A truth from a different model could
favour Mundlak's.</p>
</section>

<section class="col">
<h2>7. Discussion and limitations</h2>
<p><b>Asking rents.</b> We model asks net of advertised concessions, not rents paid. Validation against independent
records of contract rents is the most important next step.</p>
<p><b>Interpretation.</b> Coefficients are conditional differences, not causal effects. Within-building contrasts
(floor, size, laundry) remove building and block confounding but not unmeasured unit quality such as renovation or
light. We report the random-effects and Mundlak estimates as a range because neither is correct by construction.</p>
<p><b>Uncertainty.</b> Predictive intervals are calibrated, but coefficient intervals are too narrow: for the common unit
terms the audit's biases (0.1 to 0.7 points) exceed the intervals' half-widths (0.05 to 0.1), because the intervals
omit model uncertainty. We would not
publish the second decimal place.</p>
<p><b>Selection on one split.</b> Many fits were compared on the same latest split. Pre-registered predictions limit,
but do not remove, adaptive overfitting for gains near 2 SE. The floor gain (36 SE) is far outside that range.</p>
<p><b>Coverage of the city and of the protocol.</b> The data omit the Bronx, Staten Island and most of Queens. The
framework's 80% and 95% coverage on a time-split refit and in-sample PSIS-LOO (Vehtari et al., 2017) were not
computed for this fit. We have not benchmarked against a flexible learner and make no claim about relative accuracy.</p>
</section>

<section class="col">
<h2>8. Conclusion</h2>
<p>A hedonic model that gives every building its own level and every zone its own smooth surface can price unit
qualities from within-building contrasts, at city scale, on one GPU. Floor is the largest such quality after size,
and its value depends on the elevator. The model's weak points are measurable: unit coefficients carry a small upward
bias that a Mundlak term removes at a cost to building terms, and coefficient intervals understate uncertainty.
Location remains mostly described rather than explained. The features that help forecasts vary faster than the
surface, as park frontage does, which suggests looking at block-scale and view-scale qualities next.</p>
</section>

<section class="col">
<h2>References</h2>
<ol class="refs">
<li>Bell, A. and Jones, K. (2015). Explaining fixed effects: random effects modeling of time-series cross-sectional and panel data. <i>Political Science Research and Methods</i> 3(1), 133–153.</li>
<li>Cook, S. R., Gelman, A. and Rubin, D. B. (2006). Validation of software for Bayesian models using posterior quantiles. <i>Journal of Computational and Graphical Statistics</i> 15(3), 675–692.</li>
<li>Hoffman, M., Radul, A. and Sountsov, P. (2021). An adaptive MCMC scheme for setting trajectory lengths in Hamiltonian Monte Carlo. <i>AISTATS</i>.</li>
<li>Mundlak, Y. (1978). On the pooling of time series and cross section data. <i>Econometrica</i> 46(1), 69–85.</li>
<li>Phan, D., Pradhan, N. and Jankowiak, M. (2019). Composable effects for flexible and accelerated probabilistic programming in NumPyro. arXiv:1912.11554.</li>
<li>Riutort-Mayol, G., Bürkner, P.-C., Andersen, M. R., Solin, A. and Vehtari, A. (2023). Practical Hilbert space approximate Bayesian Gaussian processes for probabilistic programming. <i>Statistics and Computing</i> 33, 17.</li>
<li>Rosen, S. (1974). Hedonic prices and implicit markets: product differentiation in pure competition. <i>Journal of Political Economy</i> 82(1), 34–55.</li>
<li>Solin, A. and Särkkä, S. (2020). Hilbert space methods for reduced-rank Gaussian process regression. <i>Statistics and Computing</i> 30, 419–446.</li>
<li>Talts, S., Betancourt, M., Simpson, D., Vehtari, A. and Gelman, A. (2018). Validating Bayesian inference algorithms with simulation-based calibration. arXiv:1804.06788.</li>
<li>Vehtari, A., Gelman, A. and Gabry, J. (2017). Practical Bayesian model evaluation using leave-one-out cross-validation and WAIC. <i>Statistics and Computing</i> 27, 1413–1432.</li>
<li>Vehtari, A., Gelman, A., Simpson, D., Carpenter, B. and Bürkner, P.-C. (2021). Rank-normalization, folding, and localization: an improved R-hat for assessing convergence of MCMC. <i>Bayesian Analysis</i> 16(2), 667–718.</li>
</ol>
</section>
<footer>Run: building-zones-floor-b0-latest-6b5a5b4a-dense-w1000 (base); building-zones-mundlak-b0-latest-a6d25054-dense-w1000 (Mundlak); building-split and simulation runs as named in the project's results notes of 21–22 October 2026.</footer>
</main>
"""

INIT = """
floorChart('floor',ELEV,WALK);
forest('unit',UNIT,{unit:'%',xlabel:'Premium, % of rent'});
forest('bld',BLD,{unit:'%',xlabel:'Premium, % of rent'});
"""

html = page(
    "Floors, Dishwashers and Parks",
    "Short conference paper on the floor model of NYC asking rents",
    BODY,
    data_js() + INIT,
)
(HERE / "paper.html").write_text(html)
print(len(html))
