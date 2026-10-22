from pathlib import Path

from common import HERE, data_js, page

FOLLOW = (HERE / "followups.html").read_text() if (HERE / "followups.html").exists() else ""

BODY = """
<main>
<header class="top">
  <div class="kicker">Short paper · Revision 2, 22 October 2026</div>
  <h1>Asking-rent differentials for floor, amenities and parks: a Bayesian hedonic model of 1.9 million New York rental ads</h1>
  <p class="byline">Apartments project · Revised after three referee reports; changes listed at the end</p>
</header>

<section class="col">
<div class="card">
<h3>Abstract</h3>
<p style="margin:0">We estimate asking-rent differentials for apartment qualities in Manhattan and Brooklyn from 1,896,486
StreetEasy rental listings, 2010 to 2026, in 67,977 buildings. The model combines a weekly market walk, a reduced-rank
Gaussian-process rent surface for each of two zones, a partially pooled level for every building, unit and building
attributes, and a Gaussian-process floor curve. Adding the floor curve improves the held-out log score on 189,649
held-out ads, each the latest ad of a unit listed more than once, by 2,945 (SE 171, clustered by building and week) and lowers RMSE on log rent from 0.1172 to 0.1154, with 90.4% coverage of 90% predictive
intervals. In elevator buildings asking rents rise with floor and rise faster with height, to about +4% at floor 10,
+7% at floor 20 and +13% to +14% around floor 40 relative to floor 1 of the same building; in walk-ups they fall
slightly. Identified from within-building contrasts with building means included (Mundlak), in-unit laundry carries
about +6%, a dishwasher about +2% and 10% more floor area about +2.3%. A simulation audit shows that without the
building means these unit estimates are biased upward by 0.1 to 0.7 points, and that posterior intervals for
coefficients cover their truth only 69 to 81% of the time, so we report coefficients to the nearest half point.
Distances to parks, water and transit do not improve forecasts for buildings withheld from fitting; frontage on a
park is the one block-scale feature with a forecast gain, which is not yet established.</p>
</div>
</section>

<section class="col">
<h2>1. Introduction</h2>
<p>Hedonic models price a good as a bundle of qualities (Rosen, 1974). The coefficients are equilibrium price
differentials, not willingness to pay, which requires further structure (Epple, 1987; Kuminoff et al., 2013). For
rental housing the bundle has three layers that are hard to separate: the unit, the building and the place. A doorman
building on a park has larger, better-equipped units, so a regression that pools the layers credits the unit with
value that belongs to the building or the block.</p>
<p>We estimate the difference in asking rent between two listings that are alike in everything the model measures
except one quality. Unit qualities are identified within buildings, because every building has its own level.
Building qualities are compared between buildings at the same point on a smooth rent surface; we present these as
conditional differences, not as values. Location is the surface itself, and we ask whether measured features of the
city improve forecasts of it.</p>
<p>The contributions are: (i) a model fitted to 1.7 million rows in about twenty minutes on one GPU, with 68,000
building effects and two reduced-rank Gaussian-process surfaces; (ii) a floor curve that depends on whether the
building has an elevator, adding to the literature on vertical rent gradients in office and residential towers
(Liu, Rosenthal and Strange, 2018; Danton and Himbert, 2018); (iii) a simulation audit of the bias that random
building effects put on unit coefficients and of the coverage of coefficient intervals; and (iv) evidence that smooth
distance features add nothing to forecasts for unseen buildings once a rent surface is present.</p>
</section>

<section class="col">
<h2>2. Data</h2>
<p>The data are rental listings collected from StreetEasy between July 2010 and October 2026. The unit of observation
is an ad; the target is its latest net-effective ask on the log scale, the last asking rent after advertised
concessions. The last ask is the price after any cuts, so it partly reflects time on market. Furnished and
short-term listings are excluded. Each building is matched to a tax lot (BBL) in MapPLUTO for year built, alterations,
floor count and footprint. Manhattan has 21,994 buildings and 1,115,906 ads; Brooklyn and a small part of Queens
(Ridgewood and Glendale) have 45,983 buildings and 780,580 ads.</p>
<p>Listings are a flow, not the stock. They over-represent units that turn over often and market-rate units, and
StreetEasy's coverage of Brooklyn grows over the period. Rent stabilization is taken from the ad's wording, which
under-reports it; asks for stabilized units mix legal and preferential rents. Our results describe the listed
market and are not reweighted to the housing stock.</p>
<p>Unit fields come from the listing: bedrooms, full and half baths, stated size (44.9% of training rows; another
18.8% filled from the same unit's or line's other ads), laundry (in unit 29.0%, in building 36.8%), dishwasher
(54.8%), floor and unit label. Building fields come from listings and city data: doorman (full, part, virtual),
elevator, condo, gym, retail, height, year built, alterations, and frontage on a through truck route.</p>
<p>The <i>latest split</i> holds out 189,649 ads: for units listed at least twice, 10% of their latest ads, drawn at
random. Held-out ads span 2014 to October 2026, like the training ads; each shares its unit with at least one
training ad, and the median gap back to that unit's previous ad is 733 days. This tests prediction of a known unit's
next ask, not a forecast: the market walk is interpolated through weeks that contain training ads. Some features
also read other ads of the same unit or building, held-out and later ones included: size filled from the unit's or
line's other ads (15.7% and 7.0% of held-out ads), building shares for elevator, doorman and gym, and the Mundlak
means. No rent enters any feature, but these fills can borrow information from the future; a refit with features
built from training ads only is among the follow-ups.
A second split holds out 6,798 whole buildings and their 184,437 ads (the <i>building split</i>), the only one
that can test a building-level feature.</p>
</section>

<section class="col">
<h2>3. Model</h2>
<p>For ad <i>i</i> in building <i>b</i> in zone <i>z</i>,</p>
<div class="eq">y_i  = L(t_i) + S(d_i) + x_i'β + f_g(i)(log floor_i) + η_b + ε_i,    ε_i ~ t_ν(0, σ_k(i))
η_b  = F_z(s_b) + w_b'γ + u_b,                                       u_b ~ N(0, b_z²)
F_z  ~ GP(0, a_z² k_SE(·,·; ℓ_z))   (Hilbert-space basis, rotated box per zone)
f_g  ~ GP(0, c_g² k_SE(·,·; λ_g)),  f_g(0) = 0,   g ∈ {elevator, walk-up}</div>
<p>L is a weekly random walk with drift and normal shocks; S has two annual harmonics. The vector x holds cumulative
bedroom steps, bath steps by bedroom count, log size relative to the median stated size for the bedroom count (with
imputed and unknown flags), laundry, dishwasher and floor flags (penthouse, garden, lower level, top floor, floor
unknown). The building level η<sub>b</sub> is centred on the zone surface F<sub>z</sub> plus building attributes
w<sub>b</sub>. σ varies by bedroom group and ν is estimated. In the Mundlak variant, w<sub>b</sub> also includes
the building's mean of each unit column (Mundlak, 1978; Bell and Jones, 2015). All coefficients are constant over
the sixteen years, and the surface is static; Section 7 discusses both.</p>
<p>The zones, Manhattan and Brooklyn plus Queens, are split at the river. Each surface uses a reduced-rank
Hilbert-space approximation (Solin and Särkkä, 2020; Riutort-Mayol et al., 2023) with the lengthscale fixed at
1 km, on a box rotated to the zone's footprint (the 0.1 to 99.9% quantile box, widened by a factor of 1.5). Manhattan
has 5 × 17 = 85 basis functions and Brooklyn plus Queens 10 × 11 = 110; both resolve lengthscales down to about
0.9 to 1.0 km, so the surface cannot represent block-scale variation by construction. The floor curves are exact GPs on log floor, pinned to zero at floor 1 and capped at floor 47 (elevator)
and 6 (walk-up). Coefficients take Normal(0, 0.5) priors; amplitudes and building spreads HalfNormal(0.3); the floor
amplitude squared an inverse gamma with median amplitude 0.15. The fitted Manhattan amplitude, 0.92 (90% 0.77 to 1.09), lies
in the prior's far tail (prior probability of exceeding it 0.002), so prior and data are in tension there; a fit with
a wider prior is among the follow-ups.</p>
<p>We sample with a blocked Gibbs sampler. Writing the Student-t error as a scale mixture of normals makes every
location and level term conditionally Gaussian. Each sweep draws the global block (coefficients, the walk's weekly
levels and the surface coefficients) jointly with the 68,000 building levels integrated out, then each zone's
building spread, the building levels, ν and σ with the mixing scales integrated out, the walk and surface
amplitudes, and the floor-curve hyperparameters (the lengthscale with the amplitude integrated out). Every step
leaves the posterior unchanged. We run four chains of 300 warmup and 1,000 kept sweeps, thinned by five. The fit
takes 19 minutes on one A100. Because the sampler is Gibbs, HMC diagnostics such as divergences and E-BFMI do not
apply; convergence is judged by R-hat and ESS.</p>
</section>

<section class="col">
<h2>4. Evaluation protocol</h2>
<p>Each candidate term is a separate full fit with predictions written before launch; misses are recorded. A fit must
pass a convergence gate (rank-normalised R-hat ≤ 1.01 and bulk ESS ≥ 400 on every traced quantity; Vehtari et al.,
2021). Fits are compared by the paired held-out log predictive density (elpd) on shared rows, with standard errors
clustered by building, and for the headline comparison also by listing week; a gain should exceed about 2 SE. Building-level features must also beat a within-zone
permutation null on their share of explained held-out building residuals. Separately we refit the model to rents
simulated from a fixed truth and score coverage of that truth, in the spirit of Cook et al. (2006) and Talts et al.
(2018). Many fits have been compared on the latest split, so gains near 2 SE there should be read as provisional.</p>
</section>

<section class="col">
<h2>5. Results</h2>
<h3>5.1 Fit and forecast</h3>
<p>The model passes the gate: max R-hat 1.0097 and min ESS 590, both on the outer zone's surface amplitude, which is
the slowest quantity in every fit of this family; the floor-curve hyperparameters have R-hat at most 1.0013.</p>
<div class="tw"><table>
<thead><tr><th>Model (each row adds to the one above)</th><th class="n">Δ elpd (SE)</th><th class="n">RMSE</th><th>Gate</th></tr></thead>
<tbody>
<tr><td>Zones, building levels, building attributes</td><td class="n">reference</td><td class="n">0.1244</td><td>pass</td></tr>
<tr><td>+ size, laundry, dishwasher, truck route</td><td class="n">+9,818 (≈162)</td><td class="n">0.1173</td><td>pass</td></tr>
<tr><td>+ year built, alteration, retail, gym</td><td class="n">+20 (19)</td><td class="n">0.1172</td><td>pass</td></tr>
<tr><td><b>+ floor curve and floor flags</b></td><td class="n"><b>+2,945 (171)</b></td><td class="n"><b>0.1154</b></td><td>pass</td></tr>
</tbody>
<caption>Table 1. Held-out scores on the latest split (189,649 ads). The second row's gain is derived from two reported comparisons that share the gym fit (gym vs the first row +9,807, SE 162; gym vs the second row −11, SE 3). The gym fit itself failed the gate on the outer surface amplitude (R-hat 1.0149) and is not shown; because the bridge runs through it, a direct paired score of row 2 against row 1 is among the follow-ups. The floor row's SE is clustered by building and by listing week (Cameron, Gelbach and Miller, 2011); by row it is 83 and by building alone 172. The other rows' SEs are as reported in the project notes and have not been re-clustered. The third row's gain is under 2 SE; its terms are carried as controls, not as established effects.</caption>
</table></div>
<p>The floor gain is largest on elevator floors 3 to 19 (+1,972), top floors (+911) and penthouses (+706), where the
previous model's median error of +10.5% falls to −0.3%. These bands were chosen after the fit and overlap, and they sum
to more than the total because elevator ads with no stated floor lose 202 (SE 17) and the walk-up bands gain little.
Predictive intervals are well calibrated overall on the latest split, but not everywhere: coverage of 90% intervals
is 78.8% for penthouses and 86 to 88% on elevator floor 1, floors 40 and up, and top floors. On the building split,
where a new building's level is drawn from its zone's prior, RMSE rises to 0.182 and 90% intervals cover 92.7%, which
is conservative. The floor fit on that split missed the gate by a hair (R-hat 1.0105 on the outer amplitude).</p>

<h3>5.2 Floor</h3>
<p>Figure 1 shows the two curves. In elevator buildings each doubling of the floor adds more than the one before above
floor 2: 0.3 points from 2 to 4, 1.6 from 4 to 8, 2.6 from 8 to 16 and 4.8 from 16 to 32. The curve is not perfectly
smooth: nine pairs of neighbouring floors dip by up to 0.6 points, floors 41 and 42 sit below floor 40, and all floors
from 47 up share one value 3.4 points above floor 46. That step is largely the cap: the 9,105 ads in that group have
a median floor of 52 (quartiles 49 and 58, maximum 104), and the curve's slope over floors 43 to 46 accounts for about
2.2 of the 3.4 points. Eight of the nine dips are under 0.15 points and not clearly real (posterior probability of a
dip 0.54 to 0.71); the ninth, 40 to 41, is 0.5 points (probability 0.92) because floor 40 sits high. We read the
shape below floor 40 and treat the top as unresolved. A penthouse adds about 8% above its floor's value and the top floor of an elevator building about 2%.
Walk-ups decline by about 0.2 points per floor, to about −1% at floor 5. Adding the curve moves the elevator premium
from 6.8% to 3.6% and leaves building effects almost unchanged (correlation 0.998). The floor differential bundles
whatever travels with height in the same building, such as light, views, quiet and layout.</p>
</section>
<figure>
  <div class="frame">
    <div class="legend"><span><i class="sw a"></i>Elevator buildings, median and 90% interval</span><span><i class="sw b"></i>Walk-ups</span></div>
    <div id="floor"></div>
  </div>
  <figcaption><b>Figure 1.</b> Asking-rent differential over floor 1 of the same building. Floors 47 and above share one value. Intervals are posterior intervals and are too narrow (Section 6).</figcaption>
</figure>

<section class="col">
<h3>5.3 Unit qualities</h3>
<p>We lead with the Mundlak estimates for unit qualities, because the simulation audit (Section 6) finds them
unbiased where the random-effects estimates are not. Rounded to the nearest half point: in-unit laundry carries
+5.5% to +6% against unstated laundry (random effects: +6.5%), laundry in the building +1.5%, a dishwasher +2%, and a
private garden or outdoor space +2% (random effects +3%). Size has an elasticity of 0.24 (random effects 0.25), so a
unit 10% larger than typical for its bedroom count asks about 2.3% more. A unit with no stated size asks about 4%
less. The Mundlak fit has not yet been scored on held-out ads.</p>
<p>Within-building contrasts remove building and block confounding but not unit-level quality. Laundry and
dishwashers probably travel with renovation, which varies unit by unit, so these differentials are upper bounds on
what the appliance alone adds. A within-unit design using repeat listings of the same unit (Ambrose, Coulson and
Yoshida, 2015) is among the follow-ups.</p>
</section>
<figure>
  <div class="frame">
    <div class="legend"><span><i class="sw a"></i>With building means (Mundlak), preferred</span><span><i class="sw b"></i>Random building effects</span></div>
    <div id="unit"></div>
  </div>
  <figcaption><b>Figure 2.</b> Unit-level differentials, 100(e<sup>β</sup>−1), posterior median and 90% interval.</figcaption>
</figure>

<section class="col">
<h3>5.4 Building qualities</h3>
<p>Between buildings at the same point on the surface, the conditional differences are about +15% for a full-time
doorman, +10% for a condo building, +8% for a part-time doorman, +7% for a gym, +4% for construction since 2010 or
before 1900 and +3.5% for an elevator; ground-floor retail is about −2% and frontage on a through truck route about
−4%. Ads stating rent stabilization ask about 2.5% less and income-restricted ads about 10% less. With building means
included these shrink by 16% (gym) to 56% (retail), and by 81% for building height, because the means absorb part of
what distinguishes such buildings (Figure 3). These are descriptive conditional differences with no exogenous source
of variation. Condo units in particular are rented by individual owners and differ from rental buildings in ways
the model does not measure.</p>
</section>
<figure>
  <div class="frame">
    <div class="legend"><span><i class="sw a"></i>Random building effects</span><span><i class="sw b"></i>With building means (Mundlak)</span></div>
    <div id="bld"></div>
  </div>
  <figcaption><b>Figure 3.</b> Building-level differentials and ad flags, 100(e<sup>β</sup>−1), posterior median and 90% interval.</figcaption>
</figure>

<section class="col">
<h3>5.5 Location</h3>
<p>Of the variance of log rent across training ads (0.192), the surface carries 23% and the leftover building levels
8%. Separating whether a place's qualities are priced (capitalization) from whether naming them helps a forecast,
we address only the second here. A flexible surface will absorb any smooth amenity, so the test is whether a named
feature predicts the rent of a building the model has not seen.</p>
<p>Six smooth distances (nearest station, routes served, any park, parks of 30 acres or more, shoreline, a noise
index) take 7.6% of the surface's variance. Their coefficients are stable between the two splits and between single
and joint fits; the largest is −2.1 points per log km from a park of 30+ acres. On the building split they change
the held-out log score by +26 (SE 116), and at held-out buildings their contribution correlates −0.97 with the
change in the surface (run building-zones-location-b0-buildings-35131df8-dense-w1000). The surface already holds
these gradients at its own scale.</p>
<div class="tw"><table>
<thead><tr><th>Step feature (added to the six distances)</th><th class="n">Differential, 90% interval</th><th class="n">Δ elpd, building split (SE)</th><th class="n">On flagged ads</th></tr></thead>
<tbody>
<tr><td>Faces a park of ≥ 5 acres (within 40 m)</td><td class="n">+3.5% (2.6, 4.3)</td><td class="n">+187 (80)</td><td class="n">+52 (67)</td></tr>
<tr><td>Within 150 m of shoreline</td><td class="n">+5.4% (3.5, 7.4)</td><td class="n">−229 (130)</td><td class="n">−175 (102)</td></tr>
<tr><td>Within 30 m of an elevated track</td><td class="n">−2.4% (−3.5, −1.5)</td><td class="n">−41 (51)</td><td class="n">−7 (32)</td></tr>
<tr><td>Mid-block on an avenue</td><td class="n">−1.8% (−2.5, −1.3)</td><td class="n">+86 (89)</td><td class="n">+63 (59)</td></tr>
</tbody>
<caption>Table 2. Four step features, each fitted separately and compared with the six-distance model on the building split (6,798 held-out buildings, 184,437 ads). "On flagged ads" is the gain on held-out ads where the feature is 1.</caption>
</table></div>
<p>Park frontage is the best of the four, but the evidence is weaker than its 2.3 SE suggests. Most of the gain falls
on ads that do not face a park (+135, SE 45), through shifts in the smooth distance coefficients; on park-facing ads
the gain is +52 (SE 67), although their mean error falls from 4.3 to 1.6 points. It fails the permutation test (0.30%
explained share against a null 95th percentile of 0.46%), the 40 m threshold was chosen after a check at 30, 40 and
60 m, and it is one of four features tried on one split. A fake-rent test shows the model recovers a planted step of
this size (3.46 planted, 3.54 returned, 90% 2.75 to 4.27) without moving the surface. We report it as not
established; a fit with park frontage alone on the building split is under way.</p>
</section>

<section class="col">
<h2>6. Simulation audit</h2>
<p>We simulated rents from the fitted model under three scenarios and refit each: a realistic truth (the fitted
medians, with the walk-up curve set to rise 0.4 points per flight, the elevator top-floor flag set to 3.9% and the
lower-level flag to zero), a null (floor curves and features set to zero) and a planted building-height effect. All
three pass the gate. Coverage of 90% intervals over 119 scalar terms was 80.7%, 75.6% and 73.9%, and 69% in a fourth
recovery for park frontage. Each figure comes from one simulated dataset, and the terms are dependent, so these are
indications, not calibrated estimates.</p>
<p>The misses repeat across runs in the same direction. In points of log rent ×100, the size elasticity comes back
0.6 to 0.7 high, in-unit laundry 0.4, laundry in the building 0.2 and the dishwasher 0.1 to 0.2. The null run's
elevator curve, whose truth is zero, comes back 0.1 to 0.4 points above zero with 66% coverage. For size, in-unit
laundry and dishwasher the bias follows the column's correlation with the true building level (+0.24, +0.22, +0.21),
the bias of random effects correlated with regressors; laundry in the building has no such correlation and we read
its bias as a spillover from in-unit laundry, since both are measured against unstated laundry. Adding building means
reduces every unit bias to 0.03 points or less, but shrinks building attributes toward zero (condo 6.6 against a truth
of 10.0) and worsens recovery of the surface. The surface recovers well (slope 0.99, coverage 94 to 99%, which is high
because the truth is smoother than the prior), and building levels cover at 90%.</p>
<p>The truth was drawn from the random-effects fit, which favours its split of variance between building attributes
and levels. Replicates with other seeds and with a truth drawn from the Mundlak fit are among the follow-ups.</p>
</section>

<section class="col">
<h2>7. Discussion and limitations</h2>
<p><b>Asking rents and the listed market.</b> We model asks, not contract rents, from a selected flow of listings. A
comparison with contract rents from the NYC Housing and Vacancy Survey, and reweighting to the stock, are the most
important next steps.</p>
<p><b>Interpretation.</b> All coefficients are conditional differences. The floor differential bundles light, views
and layout; appliance differentials likely include renovation; building differentials compare buildings, not
treatments. Boundary and natural-experiment designs (Black, 1999; Bayer, Ferreira and McMillan, 2007) would be needed
for capitalization claims about location.</p>
<p><b>Constant coefficients.</b> Implicit prices are held fixed over 2010 to 2026, across COVID-19 and the 2019 rent law
(HSTPA). Both plausibly changed the value of outdoor space, laundry and stabilized units (on regulation, see Glaeser
and Luttmer, 2003; Autor, Palmer and Pathak, 2014; Diamond, McQuade and Qian, 2019). The surface is also static. A fit
with period-specific coefficients is among the follow-ups.</p>
<p><b>Uncertainty.</b> Coefficient intervals are too narrow: the audit's biases exceed their half-widths, and repeat
ads of the same unit are treated as independent. We round coefficients to the nearest half point and treat the
intervals as lower bounds. Standard errors of elpd differences are clustered by building only; weekly shocks shared
across buildings are not accounted for.</p>
<p><b>Protocol gaps.</b> In-sample PSIS-LOO
(Vehtari et al., 2017) is not reported here. We have not benchmarked against a flexible learner. The data
omit the Bronx, Staten Island and most of Queens.</p>
</section>

FOLLOWUPS

<section class="col">
<h2>8. Conclusion</h2>
<p>A hedonic model with a level for every building and a smooth surface for each zone prices unit qualities from
within-building contrasts at city scale on one GPU. Floor is the largest such differential after size, and its sign
depends on the elevator. The model's weak points are measured rather than assumed: unit coefficients carry a small
upward bias that building means remove at a cost to building terms, and coefficient intervals understate uncertainty.
Location remains described rather than explained.</p>
</section>

<section class="col">
<h2>References</h2>
<ol class="refs">
<li>Ambrose, B. W., Coulson, N. E. and Yoshida, J. (2015). The repeat rent index. <i>Review of Economics and Statistics</i> 97(5), 939–950.</li>
<li>Autor, D. H., Palmer, C. J. and Pathak, P. A. (2014). Housing market spillovers: evidence from the end of rent control in Cambridge, Massachusetts. <i>Journal of Political Economy</i> 122(3), 661–717.</li>
<li>Bayer, P., Ferreira, F. and McMillan, R. (2007). A unified framework for measuring preferences for schools and neighborhoods. <i>Journal of Political Economy</i> 115(4), 588–638.</li>
<li>Bell, A. and Jones, K. (2015). Explaining fixed effects: random effects modeling of time-series cross-sectional and panel data. <i>Political Science Research and Methods</i> 3(1), 133–153.</li>
<li>Black, S. E. (1999). Do better schools matter? Parental valuation of elementary education. <i>Quarterly Journal of Economics</i> 114(2), 577–599.</li>
<li>Cameron, A. C., Gelbach, J. B. and Miller, D. L. (2011). Robust inference with multiway clustering. <i>Journal of Business &amp; Economic Statistics</i> 29(2), 238–249.</li>
<li>Cook, S. R., Gelman, A. and Rubin, D. B. (2006). Validation of software for Bayesian models using posterior quantiles. <i>Journal of Computational and Graphical Statistics</i> 15(3), 675–692.</li>
<li>Danton, J. and Himbert, A. (2018). Residential vertical rent curves. <i>Journal of Urban Economics</i> 107, 89–100.</li>
<li>Diamond, R., McQuade, T. and Qian, F. (2019). The effects of rent control expansion on tenants, landlords, and inequality: evidence from San Francisco. <i>American Economic Review</i> 109(9), 3365–3394.</li>
<li>Epple, D. (1987). Hedonic prices and implicit markets: estimating demand and supply functions for differentiated products. <i>Journal of Political Economy</i> 95(1), 59–80.</li>
<li>Glaeser, E. L. and Luttmer, E. F. P. (2003). The misallocation of housing under rent control. <i>American Economic Review</i> 93(4), 1027–1046.</li>
<li>Kuminoff, N. V., Smith, V. K. and Timmins, C. (2013). The new economics of equilibrium sorting and policy evaluation using housing markets. <i>Journal of Economic Literature</i> 51(4), 1007–1062.</li>
<li>Liu, C. H., Rosenthal, S. S. and Strange, W. C. (2018). The vertical city: rent gradients, spatial structure, and agglomeration economies. <i>Journal of Urban Economics</i> 106, 101–122.</li>
<li>Mundlak, Y. (1978). On the pooling of time series and cross section data. <i>Econometrica</i> 46(1), 69–85.</li>
<li>Riutort-Mayol, G., Bürkner, P.-C., Andersen, M. R., Solin, A. and Vehtari, A. (2023). Practical Hilbert space approximate Bayesian Gaussian processes for probabilistic programming. <i>Statistics and Computing</i> 33, 17.</li>
<li>Rosen, S. (1974). Hedonic prices and implicit markets: product differentiation in pure competition. <i>Journal of Political Economy</i> 82(1), 34–55.</li>
<li>Solin, A. and Särkkä, S. (2020). Hilbert space methods for reduced-rank Gaussian process regression. <i>Statistics and Computing</i> 30, 419–446.</li>
<li>Talts, S., Betancourt, M., Simpson, D., Vehtari, A. and Gelman, A. (2018). Validating Bayesian inference algorithms with simulation-based calibration. arXiv:1804.06788.</li>
<li>Vehtari, A., Gelman, A. and Gabry, J. (2017). Practical Bayesian model evaluation using leave-one-out cross-validation and WAIC. <i>Statistics and Computing</i> 27, 1413–1432.</li>
<li>Vehtari, A., Gelman, A., Simpson, D., Carpenter, B. and Bürkner, P.-C. (2021). Rank-normalization, folding, and localization: an improved R-hat for assessing convergence of MCMC. <i>Bayesian Analysis</i> 16(2), 667–718.</li>
</ol>
</section>

<section class="col">
<h2>Changes in revision 2</h2>
<ul>
<li>"Worth" replaced by asking-rent differentials; building terms framed as descriptive. Sample selection, time on market and self-reported stabilization added to Section 2.</li>
<li>Abstract no longer states interval widths; coefficients are rounded to half points throughout the text. Unit qualities lead with the Mundlak estimates.</li>
<li>Table 1 relabelled: the gym fit, which failed the gate, is no longer a row; the year-built step is marked as under 2 SE; the predecessor RMSE corrected to 0.1172.</li>
<li>Floor section reports the overlapping post-hoc bands, the unknown-floor loss, local dips, the cap jump and the subgroups with low coverage. The building-split base fit's gate miss is reported.</li>
<li>Park frontage removed from the abstract's claims and reported as not established, with the split of its gain between park-facing and other ads. "Large park" (≥ 5 acres) and parks of 30+ acres now named separately; the feature count fixed.</li>
<li>Mundlak shrinkage range corrected (16% to 56%, 81% for height); the simulated truth's modifications, the null run's floor-curve bias and the in-building laundry exception described; size bias units stated.</li>
<li>The sampler is now described correctly as blocked Gibbs (revision 1 wrongly said ChEES-HMC); the prior-tail amplitude noted. Added literature on vertical rent curves, hedonic identification, sorting, repeat rents, rent regulation and boundary designs.</li>
<li>Section "Follow-up experiments" added; it is updated as fits finish.</li>
</ul>
</section>
<footer>Runs: building-zones-floor-b0-latest-6b5a5b4a-dense-w1000 (base); building-zones-mundlak-b0-latest-a6d25054-dense-w1000 (Mundlak); building-split and simulation runs as named in the project's results notes of 21 and 22 October 2026. Revision 1 is kept as paper-v1.html in the project's conference folder.</footer>
</main>
"""

FOLLOW_DEFAULT = """
<section class="col">
<h2>7a. Follow-up experiments</h2>
<p>Requested by the referees and approved on 22 October; results are added here as each fit finishes.</p>
<div class="tw"><table>
<thead><tr><th>Experiment</th><th>Question</th><th>Status</th></tr></thead>
<tbody>
<tr><td>Floor + park frontage, latest split</td><td>Candidate base model</td><td><span class="pill open">queued</span></td></tr>
<tr><td>Floor + park frontage alone, building split, with permutation test</td><td>Is the gain the park's own, without the distance terms?</td><td><span class="pill open">queued</span></td></tr>
<tr><td>Wider surface-amplitude prior</td><td>Prior sensitivity</td><td><span class="pill open">queued</span></td></tr>
<tr><td>Unit or line effect for repeat ads</td><td>Within-unit identification; interval width</td><td><span class="pill open">queued</span></td></tr>
<tr><td>Period-specific coefficients (before 2020-03, 2020-03 to 2021, 2022 on)</td><td>Did implicit prices move?</td><td><span class="pill open">queued</span></td></tr>
<tr><td>Two more fake-rent replicates, one with a Mundlak truth</td><td>Calibration with replication</td><td><span class="pill open">queued</span></td></tr>
<tr><td>Held-out score of the Mundlak fit; two-way clustered SEs; 80/95% coverage; a direct score of row 2 against row 1</td><td>Free checks on saved draws</td><td><span class="pill open">running</span></td></tr>
</tbody></table></div>
</section>
"""

INIT = """
floorChart('floor',ELEV,WALK);
forest('unit',UNIT.map(r=>({label:r.label,f:r.m,m:r.f})),{unit:'%',xlabel:'Differential, % of ask'});
forest('bld',BLD,{unit:'%',xlabel:'Differential, % of ask'});
"""

html = page(
    "Floors, Dishwashers and Parks",
    "Short conference paper on the floor model of NYC asking rents",
    BODY.replace("FOLLOWUPS", FOLLOW or FOLLOW_DEFAULT),
    data_js() + INIT,
)
(HERE / "paper.html").write_text(html)
print(len(html))
