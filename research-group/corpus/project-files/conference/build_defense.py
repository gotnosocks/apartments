from common import HERE, data_js, page

BODY = """
<main>
<header class="top">
  <div class="kicker">Base model and defense case · 22 October 2026</div>
  <h1>The floor model of New York asking rents</h1>
  <p class="byline">Apartments project. Built from fits already run; no new fit, nothing served.</p>
</header>

<section class="col">
<p class="lede">I would present <b>the floor model</b> as the base: a Bayesian hedonic model of 1.9 million StreetEasy
rental ads in Manhattan and Brooklyn, with a city-wide market walk, a smooth rent surface for each borough zone,
a partially pooled level for each of 67,977 buildings, unit and building attributes, and a floor curve for elevator
and walk-up buildings. It is the model I can defend line by line. Park frontage is the one location feature I would
put next to it, labelled as provisional.</p>

<div class="facts">
  <div><b>+2,945</b><span>held-out log score over the previous model (SE 171, by building and week), 189,649 held-out ads (each unit's latest)</span></div>
  <div><b>11.5%</b><span>held-out RMSE on log rent; 90% intervals cover 90.4%</span></div>
  <div><b>1.0097</b><span>worst R-hat; least ESS 590 (four chains)</span></div>
  <div><b>$0.73</b><span>Modal cost of the fit, 19 minutes on one A100</span></div>
</div>
</section>

<section class="col">
<h2>The claim</h2>
<p>For a renter comparing two apartments that differ in one measured quality, the model gives the difference in
asking rent with a posterior median and a 90% interval. The numbers are strongest for qualities that vary
<i>within</i> a building (floor, size, laundry, dishwasher, outdoor space), because there the building's own level is held fixed.
They are weaker for qualities that vary only <i>between</i> buildings (doorman, condo, year built), because those
compete with the building level and the location surface for the same variance. They are weakest for location
itself: the surface predicts well, but named features of the city explain little of it so far.</p>
</section>

<section class="col">
<h2>The model</h2>
<div class="eq">log rent_i = L(week_i) + S(day_i)                     market walk + 2 yearly harmonics
           + x_i·β                                    bedrooms, baths, size, laundry, dishwasher, flags
           + f_g(floor_i) + flags_i                   GP floor curve, g ∈ {elevator, walk-up}
           + η_b(i) + ε_i                             building level, Student-t error

η_b      = F_z(s_b) + w_b·γ + u_b,   u_b ~ N(0, b_z)   map + building attributes + leftover
F_z      ~ GP(0, a_z² · SE kernel), HSGP basis          z ∈ {Manhattan, Brooklyn + Queens}
ε_i      ~ Student-t(ν, 0, σ_bedroom group)</div>
<ul>
<li><b>Target.</b> Each listing's latest net-effective ask (concessions netted out), on the log scale. Furnished and short-term ads are excluded.</li>
<li><b>Data.</b> 1,896,486 ads from July 2010 to October 2026 in 67,977 buildings, each joined to MapPLUTO by BBL. Training uses 1,706,837 ads; 10% of the latest ads of units listed more than once (189,649) are held out.</li>
<li><b>Zones.</b> Manhattan and Brooklyn + Queens (the Queens rows are Ridgewood and Glendale), split at the river, each with its own rotated box, amplitude and building spread. No borough dummy.</li>
<li><b>Floor.</b> Two exact Gaussian processes on log floor, pinned to zero at floor 1, capped at floor 47 (elevator) and 6 (walk-up). Penthouse, garden, lower level, top floor and floor-unknown flags sit on top.</li>
<li><b>Priors.</b> Normal(0, 0.5) on coefficients, HalfNormal(0.3) on the building spreads and map amplitudes, an inverse gamma on the floor amplitude squared (median 0.15).</li>
<li><b>Sampler.</b> Blocked Gibbs: the Student-t is written as a scale mixture so the location terms are conditionally Gaussian, and the global block is drawn with the building levels integrated out; 4 chains, 300 warmup, 1,000 sweeps keeping every 5th. Fit-only, under the project's 1-hour cap.</li>
</ul>
</section>

<section class="col">
<h2>How it got here</h2>
<p>Each step was a separate full fit, with written predictions before launch, and kept only if it beat the
previous model on held-out ads with paired log scores and building-clustered standard errors.</p>
<div class="tw"><table>
<thead><tr><th>Step</th><th class="n">Held-out elpd vs previous</th><th class="n">RMSE (log)</th><th>Kept</th></tr></thead>
<tbody>
<tr><td>B0: market walk, season, bedrooms, baths, flags; no location</td><td class="n">baseline</td><td class="n">median abs. error 20.3%</td><td><span class="pill keep">base</span></td></tr>
<tr><td>Two-zone map + building levels + building attributes (1 km)</td><td class="n">not paired</td><td class="n">0.1244</td><td><span class="pill keep">kept</span></td></tr>
<tr><td>+ unit size, laundry, dishwasher, truck route</td><td class="n">+9,818 (SE ≈160)</td><td class="n">0.1173</td><td><span class="pill keep">kept</span></td></tr>
<tr><td>+ gym</td><td class="n">−11 (SE 3)</td><td class="n">0.1173</td><td><span class="pill keep">kept, neutral</span></td></tr>
<tr><td>+ year built, alteration, retail</td><td class="n">+32 (SE 18)</td><td class="n">0.1173</td><td><span class="pill keep">kept, neutral</span></td></tr>
<tr><td><b>+ floor curves and flags (the base)</b></td><td class="n"><b>+2,945 (SE 171)</b></td><td class="n"><b>0.1154</b></td><td><span class="pill keep">base</span></td></tr>
</tbody>
<caption>Held-out set: 189,649 ads, each the latest ad of a unit listed more than once, drawn at random across 2014 to 2026 (latest split). Every held-out ad's unit also has training ads, so this split tests a known unit's next ask, not a forecast. Some size fills and building shares read held-out ads; a training-only rebuild is queued. B0 trained on the same rows but scored only coverage and absolute error; the B0-to-map step was not scored as a paired log score.</caption>
</table></div>
</section>

<figure>
  <div class="frame">
    <div class="legend"><span><i class="sw a"></i>Elevator buildings, median and 90% band</span><span><i class="sw b"></i>Walk-ups</span></div>
    <div id="floor"></div>
  </div>
  <figcaption><b>Floor is worth more the higher you go, but only with an elevator.</b> Premium over floor 1 in the same building, posterior median and 90% interval. Elevator: +1.2% at floor 2, +3.8% at 10, +6.7% at 20, +13.8% at 40. Walk-ups fall about 0.2 points a floor, to −0.9% at floor 5. Penthouses add +8.3% on top of the curve.</figcaption>
</figure>

<section class="col">
<h2>What it says</h2>
<p>Premiums below are 100·(e<sup>β</sup> − 1), posterior median and 90% interval. Teal is the base model. Amber is the
same model with each building's average unit features added (Mundlak), which removes the bias that
building-level random effects put on unit features. Where the two disagree, the truth is most likely between them,
and I report the pair as the range I'd defend.</p>
</section>
<figure>
  <div class="frame">
    <div class="legend"><span><i class="sw a"></i>Base (floor) model</span><span><i class="sw b"></i>With building averages (Mundlak)</span></div>
    <div id="unit"></div>
  </div>
  <figcaption><b>Unit features.</b> Within-building comparisons. Size enters as an elasticity: a unit 10% larger than its bedroom count's median asks about 2.4% more (elasticity 0.252, 90% 0.251 to 0.253; Mundlak 0.242).</figcaption>
</figure>
<figure>
  <div class="frame">
    <div class="legend"><span><i class="sw a"></i>Base (floor) model</span><span><i class="sw b"></i>With building averages (Mundlak)</span></div>
    <div id="bld"></div>
  </div>
  <figcaption><b>Building features.</b> Between-building comparisons at the same point on the map. These shrink by a sixth to a half once building averages enter, so the definition of "alike" matters here.</figcaption>
</figure>

<section class="col">
<h3>Where the variance sits</h3>
<p>Across training ads, the log rent variance is 0.192. Using posterior medians, the map carries 0.0436 (23%),
the leftover building levels 0.0159 (8%), and the residual 0.0146 (8%). The remaining 62% is bedrooms, baths, size,
floor, the market walk and their covariances. The descriptive share (map plus building levels) is 31%.</p>
<div class="stack" role="img" aria-label="Variance shares">
  <div style="flex:62;background:var(--muted)">unit, time, covariance 62%</div>
  <div style="flex:23;background:var(--accent)">map 23%</div>
  <div style="flex:8;background:var(--alt)">bldg 8%</div>
  <div style="flex:8;background:var(--bad)">resid 8%</div>
</div>
<p class="muted" style="font-family:var(--sans);font-size:13.5px">Source: variance split of the combined location fit against the floor fit, latest split, posterior medians.</p>
</section>

<section class="col">
<h2>The evidence it holds up</h2>
<div class="tw"><table>
<thead><tr><th>Check</th><th>Result</th><th>Verdict</th></tr></thead>
<tbody>
<tr><td>Convergence gate (R-hat ≤ 1.01, ESS ≥ 400)</td><td>max R-hat 1.0097, min ESS 590, both on the outer map amplitude; floor hyperparameters R-hat ≤ 1.001</td><td><span class="pill keep">pass</span></td></tr>
<tr><td>Held-out latest ads of repeat units</td><td>+2,945 elpd (17 SE, clustered by building and week); RMSE 0.1172 → 0.1154; 90% coverage 90.4%; median error −0.8%</td><td><span class="pill keep">pass</span></td></tr>
<tr><td>Where the gain comes from</td><td>elevator floors 3 to 19 (+1,972), top floors (+911), penthouses (+706; their median error falls from +10.5% to −0.3%)</td><td><span class="pill keep">pass</span></td></tr>
<tr><td>Unseen buildings (6,798 held out whole, 184,437 ads)</td><td>RMSE 0.182, 90% coverage 92.7%; a new building's level comes from its zone's prior</td><td><span class="pill keep">calibrated</span></td></tr>
<tr><td>Fake-rent recovery, 3 scenarios</td><td>floor curves 72 to 90% coverage; map 94 to 99%; building levels 90%; planted height term does not leak into the curve</td><td><span class="pill open">partial</span></td></tr>
<tr><td>Fake-rent recovery, unit features</td><td>size, laundry, dishwasher come back 0.1 to 0.7 points high in every scenario; building averages remove it (bias ≤ 0.03)</td><td><span class="pill open">known bias</span></td></tr>
<tr><td>Coefficient interval coverage in simulation</td><td>69% to 81% of scalar terms inside their 90% intervals</td><td><span class="pill drop">too narrow</span></td></tr>
<tr><td>Predictions written before the fit</td><td>17 of 23 hit; misses recorded (floor 10 lower than expected, walk-up curve flat)</td><td><span class="pill keep">recorded</span></td></tr>
</tbody></table></div>
</section>

<section class="col">
<h2>Location: what passed and what didn't</h2>
<p>The project's rule is to move variance from the map into things you can measure. Every candidate below was
fit as its own model and scored on <b>buildings the model never saw</b>, which is the only split that can test a
building-level feature, since in the latest split each building's own fitted level absorbs it.</p>
<div class="tw"><table>
<thead><tr><th>Feature</th><th class="n">Premium (90%)</th><th class="n">Unseen buildings, elpd</th><th>Decision</th></tr></thead>
<tbody>
<tr><td>Faces a park of 5+ acres (within 40 m)</td><td class="n">+3.5% (2.6 to 4.3)</td><td class="n">+187 (SE 80)</td><td><span class="pill open">provisional</span></td></tr>
<tr><td>Distances: station, routes, parks, big parks, water, noise</td><td class="n">big park −2.1 per log km</td><td class="n">+26 (SE 116)</td><td><span class="pill drop">names, not forecasts</span></td></tr>
<tr><td>Within 150 m of the shoreline</td><td class="n">+5.4% (3.5 to 7.4)</td><td class="n">−229 (SE 130)</td><td><span class="pill drop">dropped</span></td></tr>
<tr><td>Within 30 m of an elevated track</td><td class="n">−2.4% (−3.5 to −1.5)</td><td class="n">−41 (SE 51)</td><td><span class="pill drop">unconfirmed</span></td></tr>
<tr><td>Mid-block on an avenue</td><td class="n">−1.8% (−2.5 to −1.3)</td><td class="n">+86 (SE 89)</td><td><span class="pill drop">dropped</span></td></tr>
<tr><td>Street width bands, corner lot</td><td class="n">−2.1 to −2.8% wide street</td><td class="n">not scored</td><td><span class="pill drop">dropped</span></td></tr>
</tbody>
<caption>Park frontage was fit on top of the six distances. Its gain is 2.3 SE and it was recovered in a fake-rent test (planted 3.46, returned 3.54, 90% 2.75 to 4.27, with no leak into the map). It still misses the framework's explained-share test against a within-zone shuffle (0.30% against a null 95th percentile of 0.46%), so I present it as provisional.</caption>
</table></div>
<p>The six distances are the clearest negative result. They take 7.6% of the map's variance, their coefficients
are stable across splits, yet they forecast unseen buildings no better: the map they replace correlates −0.97 with
their contribution. At the 1 km scale the map already knows where the parks and the water are. A feature has to
vary faster than the map to add a forecast, which is why park frontage, a first-row effect, is the one that helps.</p>
</section>

<section class="col">
<h2>Why this model and not another</h2>
<ul>
<li><b>Not the Mundlak model as the base.</b> On simulated rents it fixes the unit-feature bias, but it cuts building features by 20 to 85% (condo 9.99 → 6.62 against a truth of 9.99) and worsens the map's recovery (level coverage 88% → 52% in Manhattan). It also changes what "alike" means for a building quality. I use it as a robustness bound instead.</li>
<li><b>Not floor plus all the location distances.</b> They don't help a new building's forecast and they reassign map variance with names that may stand for neighbourhoods.</li>
<li><b>Not floor plus park frontage as one fit.</b> That would be my choice, but no single fit has that exact design on the latest split. It is one fit (about 20 minutes, $0.80) when the fit hold lifts.</li>
</ul>
</section>

<section class="col">
<h2>Questions I expect, and my answers</h2>
<dl class="qa">
<dt>These are asking rents. Renters pay something else.</dt>
<dd>Yes. The target is the latest net-effective ask, which nets out advertised concessions but not negotiation. The
claims are about asks. Checking them against independent records of rents paid is the next data step in the
project goal, and I would say so on the first slide.</dd>
<dt>A hedonic coefficient isn't a causal effect.</dt>
<dd>Agreed. "Worth" here means the difference between two ads alike in everything the model measures. Unmeasured
quality, such as a renovation or light, can load onto a feature it travels with. The within-building comparisons
(floor, size, laundry) are the most robust, because they hold the building and the block fixed. Natural
experiments are the planned route to causal claims.</dd>
<dt>Random building effects correlated with the regressors bias the coefficients.</dt>
<dd>We measured it. On simulated rents with a known truth the bias is 0.1 to 0.7 points; adding building averages
removes it. On real data the building-average model moves size from 0.252 to 0.242, in-unit laundry from 6.3% to
5.7% and dishwasher from 2.0% to 1.85%. I quote both.</dd>
<dt>Your intervals look implausibly tight.</dt>
<dd>For coefficients they are too tight: in the recovery tests 69 to 81% of terms fell inside their 90% intervals,
with misses of under half a point on terms whose intervals are 0.1 to 0.2 points wide. The intervals reflect sampling
uncertainty given the model, not model uncertainty. The predictive intervals are calibrated: 90.4% coverage on new
ads and 92.7% on unseen buildings.</dd>
<dt>With 68,000 building effects and a GP map, how do you know you aren't overfitting?</dt>
<dd>Partial pooling, held-out scores on each repeat unit's latest ad and on buildings never seen, and fake-rent recovery of the map
(slope 0.99) and building levels (slope 0.78 to 0.89, shrinking for sparse buildings as expected).</dd>
<dt>Many fits were compared on the same held-out set.</dt>
<dd>Fair. Predictions were written before each fit and misses recorded, but adaptive reuse of the latest split is a
real risk for small gains. The floor gain is 17 SE even with two-way clustering, far beyond that. Gains near 2 SE, like park frontage, are why the
unseen-buildings split and simulations exist.</dd>
<dt>Why not gradient boosting?</dt>
<dd>The goal is the value of each quality, with uncertainty, not the best forecast. I have not run a boosted-tree
benchmark, so I would not claim the model forecasts better than one.</dd>
</dl>
</section>

<section class="col">
<h2>Known weaknesses</h2>
<ul>
<li>Coefficient intervals are too narrow, as above.</li>
<li>Elevator units with no stated floor get one +4.0% flag that fits them slightly worse (−202 elpd on 15,272 ads).</li>
<li>Floors 47 and up share one column; the model prices floors 40+ 3.3% too high.</li>
<li>Held-out coverage is 0.799, 0.904 and 0.955 at 80%, 90% and 95% on the held-out latest ads. Coverage on a time-split refit for new units, which the framework also asks for, has not been computed.</li>
<li>In-sample PSIS-LOO was not run (fit-only default). Comparisons use held-out log scores, which are the stricter test.</li>
<li>No Bronx, Staten Island or most of Queens.</li>
</ul>
</section>

<footer>
Sources: docs/notes/building-zones-floor-2026-10-21.md (PR #1197), building-zones-mundlak-real and -sim, simulated-recovery-results, building-holdout-location, building-zones-parkfront and simulated-recovery-parkfront, building-zones-waterfront, -elevated, -avenue, -front, building-zones-unit, -gym, -age, b0-baseline (all 2026-10-18 to 2026-10-22). Fit: building-zones-floor-b0-latest-6b5a5b4a-dense-w1000.
</footer>
</main>
"""

INIT = """
floorChart('floor',ELEV,WALK);
forest('unit',UNIT,{unit:'%',xlabel:'Premium, % of rent',aria:'Unit feature premiums'});
forest('bld',BLD,{unit:'%',xlabel:'Premium, % of rent',aria:'Building feature premiums'});
"""

html = page(
    "Floor Model Defense",
    "Base model and defense case for NYC asking rents",
    BODY,
    data_js() + INIT,
)
(HERE / "defense.html").write_text(html)
print(len(html))
