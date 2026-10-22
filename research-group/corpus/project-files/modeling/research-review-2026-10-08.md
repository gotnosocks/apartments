# Research review while fits are paused

*Modeling, 2026-10-08. Sources: `docs/model/feature-tests.md` and `research-backlog.md`, `frontier/src/rentfrontier/features.py` (repo at c3fb679), and team memory. No fits were run. Results marked "inferred" are reasoning, not measurements.*

## 1. The main finding: our test can barely credit explanatory location features

Every explanatory location feature tested so far came back null, all with an SE of about 14 to 17 ELPD:

| Test | ΔELPD |
|---|---|
| subway lines | +14.7, +20.5 |
| transit minutes to midtown | −7.9 |
| jobs within 30 minutes | −12.6 |
| parks | −5.2 |
| quiet street | +7.9 |
| busy street | −9.9 |
| retail within 150 m | +11.1 |
| nearby places | −2.3 |
| garden side | +11.7 |
| HPD violations | +0.4 |
| rent stabilization | −1.1 |
| smooth location surface | +10.0 |

Meanwhile, every model-structure change (season, bedroom trends, noise scales, Student-t units) gained a lot.

**Why (inferred, but follows from the model's structure).**

- Each building has its own level, and the five neighbourhoods each get a shift (`hoods_v1`).
- A feature that is constant for a building, such as "near the L train", is already absorbed by that building's level once the building has a few listings.
- PSIS-LOO scores each listing with the rest of its building still in the fit. So a building-constant feature can only gain ELPD on buildings with few rows.
- That matches the one partial signal we have: the location surface tied overall, but scored +16.8 ± 8.7 on small buildings.

So the test asks "does this feature help predict a listing in a building we've already seen?" For a building-level fact, the answer is almost always no, even when the fact is the true cause of the building's premium.

This is the obstacle to your goal. The building levels and the neighbourhood shifts are exactly the "this part of the neighbourhood has a premium" terms. Under the current scoring, an explanatory feature that takes their place shows up as a tie, never as a win.

**Proposal A: score explanation, not just prediction.** Add two numbers to every location or building-level test.

1. **Explained share.** This is how much the building-level SD and the neighbourhood shifts shrink when the feature goes in. It comes from the posterior we already save, so it costs no extra fit.
2. **New-building ELPD.** Hold out whole buildings (grouped 5-fold), which is the situation of pricing a listing in a building we've never seen. This costs 5 fits per test, so I'd use it only for features that pass a cheap screen (B below). The protocol already exists in `building-transfer-validation.md`; it was deferred, not rejected.

A rule change follows from this, and it's your decision. Should a feature that ties on PSIS-LOO but explains a clear share of building or neighbourhood variance be served? v3 already set the precedent of serving on principle.

## 2. Proposal B: screen candidates for free before spending a fit

Regress the served fit's building levels (posterior means with their SDs) and the neighbourhood shifts on each candidate building-level feature. That gives a ranked list of which candidates could explain building premiums at all, with no Modal spend.

- It's only a screen. A hit still needs its full fit, and every screen gets logged in feature-tests so we don't pick the winners afterwards.
- It reads model output, not rent directly, and it never feeds a data rule.
- **Retro-screen.** Run it now on the nulls above. If lines or parks explain a real share of the building SD, they're "explanatory but invisible to LOO", not "worthless".

## 3. Thought experiments on the queued tests

| Test | Varies within a building? | Prior for a LOO gain | Note |
|---|---|---|---|
| plutoasof-v3 | across time | n/a, it's a base change | Runs first, as decided. |
| **permits v1/v2** | yes (unit, time) | **good** | Renovation is a large unit-level rent driver, and the test is creditable under LOO. |
| **noise** | yes (by year) | fair | The one location feature that changes over time within a building. |
| university calendar | yes (date) | fair | Mostly studios and 1BRs near NYU. Asks lead leases by about a month, so the windows should be on listing date, as built. |
| lines, parks, water | no | low | Judge by explained share instead. |
| **walk-up** | barely | **very low** | The base already has `log_floor × no elevator` (`features.py:176`). walk-up-v1 adds `log(floor/3)` for walk-ups, which is nearly collinear. I'd run it as a swap or drop it. |
| loc surface | no | low | Run last, as the "what's still unexplained" check. |

**Leak to fix before any walk-to places test:** the places map is today's snapshot, with no opening dates. The six walk-to singles and nearby-v1 read it. Subway lines use today's timetable, a smaller version of the same issue.

## 4. New explanatory hypotheses, ranked

1. **Light and view (unit level, creditable under LOO).** Is the unit's floor above the roofs around it (the footprints file has roof heights)? Is the window side open? This varies by floor and orientation within a building, so it can win LOO, and it's a physical reason for the floor premium the model now fits as a slope.
2. **Zoned elementary school × family-size units.** Use DOE zone maps by year (dated) and school results. Zone lines cut through blocks, which fits the finding that premiums follow buildings more than blocks. Expect the effect only for 2BR and up.
3. **Building quality and management.** Candidates are LL84 energy scores, the owner's portfolio size from HPD registrations, and how often the building's earlier ads mention a gym, roof deck or package room (earlier ads only, to stay leak-free). These target the 8% building-level variance directly.
4. **Pre-war architecture and floor plates.** Ceiling height and floor-through layouts can come from PLUTO era plus footprint depth (floor-through was null on its own; it may be worth re-testing combined with these).
5. **Pandemic shock by location** (backlog). The 2020–21 dip and recovery likely differed by neighbourhood and unit size. That's a time term rather than a location term, but it keeps "trendy" from absorbing it.

## 5. Order when fits resume (my default)

1. plutoasof-v3, the new base.
2. Free screens (B) on the served fit, run at no Modal cost: retro-screen the nulls, then screen hypotheses 1–3.
3. Permits v2, then noise. These are the highest-prior LOO tests.
4. The university calendar.
5. Whichever of light/view, schools or building quality screens best, as full fits plus the new-building check.
6. Lines, parks and water, judged by explained share.
7. The loc surface, as the unexplained-remainder check.
8. The 21 singles as filler, but only after the places map is dated.
9. Walk-up dropped, unless it runs as a swap.

## 6. Calibration check of the served fit (added later, no fits run; details in research-backlog, #534)

- **Held-out rows:** bias −0.6%, typical error 3.8%, and 95% intervals cover 94.9%, which is on target.
- **Weak spots:**
  - Apartments with only one listing (32.5k rows) have a typical error of 6.0%, 92% coverage, and tail misses about twice as large.
  - Coverage is also short for 5-bedroom units (89%), Greenwich Village (93%) and the most expensive fifth of listings (93%).
  - Intervals are too wide for walk-ups.
- **Refuted or deprioritized:**
  - Apartment premiums fading over time: refuted, since no fade rate improved held-out scores.
  - Missing square feet as a latent variable: deprioritized, because rows with and without square feet fit equally well.
  - Neighbour pooling for buildings: only worth trying for small buildings.
- **Added to the order in section 5, ahead of the feature tests:**
  - A noise scale by neighbourhood and by price or size, extending the bedroom noise scales (a model-structure change, creditable under LOO).
  - Heavier-tailed apartment premiums for new apartments.
- **Caveat on the proposed audit of single-listing rows that miss by more than 40%:** those rows are picked by residual. That's fine for diagnosing what goes wrong, but any cleaning rule that comes out of it must be a rent-blind text check run over every ad. That is the quarantine-v10 standard.

## 7. Neighbourhood label vs. proximity (Ben, 2026-10-08)

**Hypothesis.** A Chelsea building next to the West Village may get two separate effects:

- a smooth premium for being near a popular area;
- a step from carrying the "Chelsea" name rather than "West Village".

Today the model can't tell these apart. The building levels and the neighbourhood shifts absorb both.

**How to separate them: three designs, cleanest first.**

1. **Label varies within the same building, as a within-building test.** If ads for the same building name different neighbourhoods over time (for example a broker writing "West Village" for a Chelsea building on Jane Street, or a later StreetEasy boundary change), the rent difference between those ads is a pure label effect, because the building's own level holds location fixed. This needs a per-ad label: either a neighbourhood named in the ad text, or the area recorded at scrape time. Today's label comes from the building page (current), so the first step is a free data check of how often ads name another neighbourhood.
2. **A step at the boundary on top of a smooth surface (spatial regression discontinuity).** Fit a smooth location surface that is continuous across the borders (the loc bumps or an HSGP), plus a shift for each label. The proximity effect is the surface rising toward the border, and the label effect is the jump at the line.
   - **Confound:** most borders are big streets (14th St, 6th Ave, 7th Ave S, Park Ave S), and a busy avenue has its own effect. Control for street frontage (the loud-v1 terms), or compare buildings near the border but not on it.
   - **Power:** only buildings within a few blocks of a border identify the jump. I'll count them before fitting.
3. **Space × time version.** Let the surface and each label shift drift over time, as a separable space-time term or label × year. This tests whether a name's premium (say "West Village") grew faster than the places next to it.

**Expected scoring.** Like other location terms, this will mostly tie on PSIS-LOO, because building levels absorb it. Under the serve-on-ties rule, it gets judged on explained share: how much of the neighbourhood shifts and building SD it takes over. Either answer is useful. A large label step means "trendy" is a real, separate effect, and a small one means proximity explains the premium.

**Order.** Free data check first (per-ad labels and buildings near borders), then design 2 as one full fit after the noise-scale and permit tests. Design 1 only if the data check finds enough within-building label variation.

**Border check on the served fit (no fit run; details in the research backlog, #535).** Each building has exactly one label (its StreetEasy area), so design 1 isn't available, and the split can only show at borders. For each building I took its building premium plus its label premium, grouped by distance to the nearest building with a different label:

- **Chelsea → West Village:** about +12%, mostly a jump. West Village buildings right at the border sit about 6% below their label, so part of it is gradual.
- **Chelsea → Flatiron:** gradual. Chelsea buildings within about 150 m of Flatiron are already 4–5% pricier.
- **Flatiron → Gramercy Park:** the Gramercy label is worth −14%, but Gramercy buildings near Flatiron carry +7 to +9% building premiums that cancel most of it. That's proximity, currently absorbed one building at a time.
- **Greenwich Village → West Village:** nearly continuous.

**Test pair:**
- `nb5p3-locnolabel-v1` is the smooth surface (bumps 250 m apart) with no labels.
- `nb5p3-loc-v1` is the surface plus the labels.

A tie means the labels add nothing beyond location, so they get dropped for a simpler model. If the version with labels wins, the name itself moves prices. Queued right after v3.

## 8. Amendments adopted from the independent review ([review-2026-10-08.md](/mnt/project-files/research-review-fable/review-2026-10-08.md))

- **Power:** a building-level feature that explains 20% of building variance should gain only about +34 ELPD under PSIS-LOO, almost all of it from small buildings, while shrinking the building SD by about 8 posterior SDs. Explained share is confirmed as the right score.
- **The free screen holds out whole buildings** (grouped CV on the served fit's output). That gives the new-building answer at no Modal cost, so 5-fold fits are only for survivors.
- **Explained share gets a permutation null,** and the screen uses posterior draws or SD weights, not just posterior means.
- **"Descriptive share" is published on every run:** the variance carried by labels, building levels, the building walk and unit levels together. The tie-break rule on it goes to Ben.
- **Within-building label test:** use the neighbourhood the ad text claims. This complements the loc/locnolabel pair, since the StreetEasy label is fixed per building.
- **Still to scrutinize:**
  - Final ask vs first ask as the target (42% of ads cut their price).
  - Noise explained by market velocity, ahead of noise scales by neighbourhood.
  - Concession rows in 2020–21.
  - Lease-ups for single-listing rows.
  - Feature premiums × post-2020.
  - `first_listing_of_unit` drifting by year: it means "first time our data saw it", so it partly tracks year and building age.

## 9. Free checks on the served fit (no Modal spend; run on thelio when Ben says so)

Run these in order. Report each one against its prediction to the Fable review thread, and record it in the research backlog.

1. **Walk steps vs permits.** Regress the served building-walk's fitted steps on the dated permit filings (#437/#478). Prediction: jumps line up with permits, which supports the permit fit and later dropping the walk.
2. **Bedroom curves outside 2020–22.** Are the fitted bedroom-time curves flat outside the pandemic years? If yes, a feature × post-2020 term is the explanatory replacement.
3. **Residual by year × building class** (elevator/doorman vs walk-up). Any structure makes class_time a competitor to area_time.
4. **Variance shares** of the neighbourhood group (keyed separately from "features") and the unit term. Add a "descriptive share" (labels + building + building over time + unit), reported overall and per neighbourhood.
5. **`first_listing_of_unit`:** its coefficient, and whether its residual drifts by year. The flag means "first time our data saw it", so it partly tracks year and building age.
6. **Single-listing residual tails** split by months since the building's first row, and by era. Tests lease-ups against genuinely heavy tails.
7. **Noise by what is unknown:** residual SD by sqft unknown × floor unknown × description missing × single listing.
8. **Line effects:** for units listed once whose line (4C, 7C) has other units with history, regress the residual on the line's mean unit effect from those other units.
9. **Top floor and relative floor:** residual by floor/numfloors bin and by top floor. A step would justify one fit, and it's creditable under LOO.
10. **Moran's I** of residuals for buildings with 5 or fewer rows, by distance band. This decides whether small-building spatial pooling is worth a fit.
11. **When Data's final_ask lands:** overshoot by year and bedroom group, meaning mean log(initial/final) and the share of ads that cut.

**Screen notes:**
- The grouped-CV regression of building levels is a screen, not a new-building ELPD.
- Weight it by draws or 1/(SD² + residual) so small buildings count.

## 10. Follow-up free checks after the noise result (#545)

12. **Is the neighbourhood noise really about comparables?** Split residual SD within neighbourhood by rows per building (1–5, 6–20, 21+) and by class (C/D/R/S). If the GV and WV multipliers fall below 1.03 inside those cells, neighbourhood noise scales aren't needed.
13. **What are the 5-bedroom ads?** Run a rent-blind text check over 5BR ads ("entire floor", "townhouse", "combined", "duplex") to see whether the ×1.32 is a product category or noise.
14. **Ledger note:** the global ×1.037 means the served noise scales are under-dispersed out of sample, likely because unit effects absorb in-sample scatter. Every other multiplier sits on top of that.

**Noise design to fit when runs resume (replaces the price-tier idea).** Use discrete groups keyed on facts known at fit time: bedroom group × {unit has one training row or more} × {building has ≤5 rows or more}. That's 16 scales, each with a reason, against the 68 year scales. Test it in place of yearnoise, not alongside it. If a price tier is still wanted, key it on size deviation from the bedroom median, never on the fitted level, which would be circular.

**Site:** report the posterior predictive median and intervals, never the mean. With a unit ν near 2 the mean barely exists, so this removes the need for the #540 clip.

## 11. Free-check results (thelio, #570 and #573, no Modal)
- **Line term:** single-listing residuals follow same-line peers, slope 0.64 (SE 0.05) with 2+ peers, 0.72 with 4+. Earlier line_effects test gained +151 to +176 but failed R-hat. Needs a Gibbs line block (code PR, no fit); fit order item 2.
- **Noise:** excess is small buildings, not neighbourhood. 1–5 row buildings ×1.33–1.37 everywhere; 21+ rows 0.99–1.08; classes R/other 1.2–1.4. Missing floor raises SD most (22.9% vs 15.5% single-listing; 11.0% vs 7.9% repeat). Neighbourhood noise scales not needed.
- **Walk:** slow drift in data-rich buildings, not lease-up or small-building noise. Yearly-knot walk is an elegance test. Permits barely move it (+0.06% per A1 filing).
- **Location surface re-score (explained-share rule):** R² 0.131 vs null 0.041 (p = 0.005); 19.5% of building variance; WV label 12.1% → 8.0%, GV 8.1% → 2.8%. No held-out gain (−1.2 ± 1.5; small buildings −1.0 ± 0.7). Qualifies under "serve on ties" if a fit confirms the share interval excludes 0.
- **Bedroom curves:** 3BR+ discount builds from 2015 (−4.4% by 2017), peaks −6.4% in 2020, −3.9% in 2026; 2BR about half.
- **Nulls:** year × class (χ²/df 2.3, cells ~1%), relative/top floor, 5BR phrases (no mean shift, wider tails). Moran's I weak positive to 500 m. Single-listing tails widest in a building's first year (6.7% off by >40%).
- **Descriptive share:** 15.7% overall (Chelsea 10.8, Flatiron 15.0, GV 16.2, Gramercy 17.4, WV 18.4).
- **Decision (Ben, 20:58Z):** wait for East Village and NoMad, then one v3 base on all neighbourhoods; every test rebased on it.

## 12. Round 6 with the independent review (after §11)
- **Reading:** most of the GV label is proximity (8.1 → 2.8 under the surface); a West Village step of about 8% remains. Serve locnolabel if the pair ties. The pair runs on the all-neighbourhood v3 base, because East Village and NoMad double the border sample.
- **Noise design is now log-linear:** log σ = a_bedroom + b·single_listing + c·small_building + d·floor_unknown + e·building_first_year, with 8 numbers. It replaces yearnoise and the bedroom scales. Predicted: b, c and d near log(1.3), and the year scales near 1.
- **Walk:** test building_trend as well as the yearly-knot walk.
- **Free checks handed to thelio:** (1) explain the surface with explanatory candidates under grouped CV, where the out-of-fold R² is the explanatory location score; (2) large-unit completions within 1 km against the 3BR+ curve, built from the dated PLUTO releases; (3) the WV step against class, rows, historic district, waterfront and the surface residual.
- **For Data, later:** a rent-blind count of "months free / net effective" in first-year ads (concessions at lease-up).
- **Results (thelio, backlog PR #577):**
  - (1) Named location features explain the surface: out-of-fold R² 0.54 with 400 m spatial-block folds (0.76 with building folds leaks through neighbours). Ranked by R² lost when dropped: subway lines 0.16, parks 0.08, retail 0.04, amenities 0.04. Noise, trees, frontage and PLUTO add almost nothing. Labels explain 14.1% of the surface but only 0.2% of the residual. If locnolabel wins, test lines + parks + retail without labels next.
  - (2) Large-unit supply does NOT explain the bedroom curves. The correlation is trend only; year-on-year it runs −0.06 to −0.42. Per listing, +0.09 ± 0.06 pp per log unit. Caveat: this used only lots that have listings; a full-borough PLUTO pull would close that gap.
  - (3) The West Village step is a name or area premium. Served: +11.5 ± 0.5 pp. After class, rows, historic district and waterfront: +10.5. After also adding the surface: +9.3 ± 0.7. It holds within every class, about 10 pp above Chelsea.
- **Gibbs line term (#576):** code and tests pass, including against NUTS, and it's in review. Brand-new units get no line effect in predictions yet.

## 13. Round 7 (independent review, on #577)
- Lines-v1 and parks-v1 are explanatory under the surface rule (R² lost when dropped: 0.16 and 0.08), though they were null under PSIS-LOO. The score was the problem, not the feature. Asked for the coefficient signs: if WV is transit-poor, its step is net of a transit penalty.
- WV step theories handed to thelio as free checks: (1) pre-1811 street geometry (angle, block length, through street); (2) low-rise context within 100 m; (3) step by year, where flat means structure and growing means fashion; (4) stabilized share at building level.
- 3BR+ curve: (5) the 30-year mortgage rate, with lag, on levels and year-on-year changes. (6) ACS share of households with children is held back.
- Scrape note: separating street geometry from the label needs other off-grid areas (SoHo, Tribeca, Brooklyn Heights) and on-grid old stock (East Village).
- **Round 7 results (#579):**
  - (0) Transit signs: N/Q/R/W +2.9 pp per SD, L +2.5. Lines net WV only −0.6 pp, so its step isn't hiding a big transit penalty.
  - (1) Off the 1811 grid: 90% of WV buildings, correlation with the label 0.87. Within WV, off-grid buildings are +4.2 ± 1.1 pp higher. The step stays at +11.6 (+9.7 with the surface). The prediction fails, and the two aren't separable today.
  - (2) Low-rise context: the sign flips by area. The WV step stays at +8.8 with the surface.
  - (3) WV minus Chelsea is about 0 in 2014–19, then +1.6 (2022) rising to +5.6 (2026), a trend of +0.48 pp a year. Other areas are flat. So it's partly fashion: the constant label under-predicts WV now, and the building walks carry the trend. Recommendation: move an area-time term up the queue. It's descriptive, so pair it with the claimed-neighbourhood ad flag as the explanatory test.
  - (4) Stabilized share: −10.9 ± 1.5 pp per unit share within WV and −8.9 ± 0.9 across areas. It doesn't explain the step, but it backs stabopen-v2 and explain-v1.
  - (5) Mortgage rate vs the 3BR+ curve: r = −0.31 in levels, the wrong sign; ≈ 0 on 12-month changes. Not supported.

## 14. Round 8 (independent review, on #579), handed to thelio
- A: surface regression split into 2014–19 and 2022–26. Choose between location features × post-2020 and area_time based on whether the coefficients shift (prediction: lines down, parks and retail up).
- B: re-score stab-v1 under explained share, no refit; compare within-building and between-building slopes.
- C: off-grid within WV vs avenue frontage.
- D/E: 3BR+ curve by class and area (sharer vs family market); studio curve; test one drifting per-bedroom slope.
- **Round 8 results (#582, merged):**
  - A: across 1,607 buildings in both periods, no location coefficient changed by more than 2 SE. WV went from −2.1 to +1.1, GV from −0.2 to +1.7, and off-grid within WV held (+9.3 → +8.1). WV moved as a whole, so area_time is the honest term; pair it with the claimed-neighbourhood flag as the test of the name. Resume order: area_time moves up next to the line term.
  - B: stab-v1 explains 1.2% of building variance (p = 0.001), between buildings only (−8 pp per unit share); within buildings +0.03 ± 0.22. A candidate, not a priority.
  - C: off-grid within WV survives frontage (+4.7 ± 1.1; frontage −0.04).
  - D: the 3BR+ discount is in elevator and condo buildings (the family market): −11 pp in 2020–24, −10 in 2025–26. Walk-ups are flat. The children series is the relevant ACS check.
  - E: one shared bedroom-time curve carries 85% of the variation (2BR miss 0.5 pp, 3BR+ 0.4, within the posterior SD). An elegance candidate, probably split by walk-up vs elevator.

## 15. Round 9 (independent review, on #582), handed to thelio
- A shift can't come from static features with stable prices; it needs a feature whose value changed in WV. Candidates: dated waterfront parks (Little Island 2021, Pier 57 2022, Gansevoort 2023), checked by drift in Hudson distance bands; Open Restaurants and Open Streets shed density; Google Trends attention (held).
- Composition first: drift by class and price quintile, and no-fee/source mix by year.
- ACS share of households with children vs the elevator 3BR+ curve.
- Agreed: the shared elevator large-unit curve replaces the bedroom curves as an elegance test; parks dating and the waterfront check go ahead of the loc pair.
- **Round 9 results (#584, merged):** WV drift is +2.5 ± 0.5 pp (Chelsea −0.9, GV −0.5).
  - (1) Parks: weak support. By street: west of Hudson St +4.2 ± 1.0, Hudson to 7th Ave S +2.7, east of 7th Ave S +1.0. Distance to the river gives no gradient (−4.6 ± 2.7 per km). Chelsea's west side shows no rise and the effect stops at the area line, so parks alone don't explain it. Hudson River Park isn't in the parks source at all, a data gap for Data.
  - (2) Composition: not it. Elevator +4.7, walk-ups +2.9, R −1.1. Reweighting doesn't change the drift. WV runs 2–6 pp above Chelsea in every price quintile. The no-fee decline is the same in GV and Gramercy, and every row comes from StreetEasy.
  - (3) Open Restaurants: data usable; no tracking (−0.05 ± 0.37 per SD pooled).
  - (4) ACS children: shared trend only (detrended r = 0.06), too noisy at this geography.
  - Conclusion: an area-wide WV shift, possibly stronger west of Hudson St. area_time stays next to the line term. Candidates left: Google Trends attention and the claimed-neighbourhood flag.

## 16. Round 10 (independent review), handed to thelio
- What changes exactly at the WV line? (1) Label vs geocode disagreements, with the claimed-neighbourhood fallback; (2) placebo lines (8th Ave, 23rd St, Bleecker, 7th Ave S), predicted to stay under 1 pp; (3) Google Trends attention as the covariate of area_time; (4) Inside Airbnb, testing whether the drift flattens after LL18 in 2023 (expected to fail).
- The parks-dating check is downgraded to a correctness fix. Checks 1 and 2 decide area_time's shape before it's fit.
- **Round 10 results (#585, merged):**
  - (1) The step and drift follow geography, not the label. 98 GV-labelled buildings inside the WV NTA price like WV (+9.6 vs WV +10.7 and GV +6.2) and drift +5.3 ± 2.4. Ads claiming "West Village" earn nothing within the same building (+0.4 ± 0.6 before 2021, −0.2 ± 1.0 after).
  - (2) Placebo lines are all within 2 SE: 8th Ave +0.2, W 23rd +0.4, Bleecker +1.0, W 4th −0.1. Hudson St +2.0 ± 1.2. Real borders: W 14th +3.2 ± 1.3, the WV/GV label border +1.6 ± 1.1. The test can rule out fake-line drifts of 2 pp or more.
  - (3) Google Trends is blocked (429 without auth). (4) Inside Airbnb history isn't public; on timing alone, the gap opens in 2022 and doesn't flatten after LL18.
  - **Design decision (my default):** define area_time on geographic areas (2020 NTAs), not StreetEasy labels. Also consider re-basing hoods_v1 itself on NTAs, since the 98 misassigned buildings are absorbed by building effects today. The claimed-neighbourhood flag is dropped as a lead.

## 17. Round 11 (independent review), handed to thelio
- Agreed: area_time is defined on 2020 NTAs, not surface cells (the step is sharp at the polygon). Hoods get re-based on NTAs (post-hoc re-score first). #6 and Airbnb are dropped.
- Shape before free curves: (a) a market beta per NTA, (b) one shared shape with per-NTA loadings (PCA). Free curves only if both fail.
- Attention: Wikipedia pageviews (no key) and a Trends retry.
- **Round 11 results (#587, merged):**
  - (1) NTA re-base: WV +11.1, GV −0.7 to +7.1, Flatiron −4 to +3.4 (79 cheap Chelsea-labelled buildings sit in the Flatiron NTA). Area share falls 1.6 pp (23.6 → 22.0), which misses the <1 pp prediction. The 98 buildings' effects go from +1.6 to −1.5, overshooting 0.
  - (2) Market beta: levels r 0.96, but it's two regimes. 2014–21 slope 0.01; 2022–26 slope 0.17, r 0.99. On changes r 0.54 (0.17 without 2022). No 2020–21 dip, so beta is wrong.
  - (3) PC1 carries 76%; WV loads 2.39 ± 0.23, and the other areas 0.5–0.9.
  - (4) Attention: Trends WV share 13.9% (2021) to 17.9% (2026), detrended r 0.56 (p 0.06); Wikipedia jumps only in 2025, r −0.15. Pooled r ≈ 0.
  - **Conclusion (closes the WV line for now):** area_time on 2020 NTAs as a per-area 2022 step or walk. No attention covariate. Remaining WV theories wait for the East Village and NoMad borders.

## 18. Round 12: WV line closed; next free work
- **WV closed:** a one-time 2022 repricing of the WV polygon that no dated feature we have explains. The served form is a per-NTA 2022 step; the walk is the elegance comparison (predicted to tie).
- **Handed to thelio:** label vs NTA discordance in every area (predicted: NTA wins everywhere, then NTA hoods become the planned served geography); the noise coverage-by-group table plus the log-linear noise code (no fit); line-term case counts (2+ peers / sparse line / new building) and the new-unit hierarchy.
- **Pre-registered before the EV and NoMad data lands:** the EV border shows no post-2020 step above 1 pp. NoMad (a broker label with no NTA) prices as its NTA plus the surface, with a label residual under 3 pp and no drift. If NoMad shows its own step, the WV result needs rereading.
- **Fit order on resume:** v3 all-area base → line term → log-linear noise → area_time (NTA 2022 step) → NTA hoods → elevator large-unit curve → locnolabel pair → permits → unical → other rebased tests → singles (after the places map is dated).
- **Round 12 results (#589, merged):**
  - (1) Label vs NTA: the prediction fails outside WV. The 98 GV-labelled buildings in the WV NTA follow the NTA (−1.0 ± 1.3). The 79 Chelsea-labelled buildings in the Flatiron NTA (W 26–29) are cheaper than both areas (−13.5 vs Flatiron, −6.1 vs Chelsea). The 18 Flatiron-labelled buildings in the Gramercy NTA price like Flatiron (+11 ± 5). NTA hoods are NOT queued; Midtown South needs the surface. Resume order: drop "NTA hoods". area_time still uses the WV NTA.
  - (2) Held-out coverage overall is 0.79 / 0.95 (80% / 95%). Single-listing rows: 0.62 / 0.87, median error 8.9%. 1BR with floor unknown 0.76; 2BR and 3+BR about 0.81. The miss is probably the variance of a new unit's effect, not σ, so judge the noise fit on new-unit held-out coverage as well as LOO. Log-linear noise code is written; the NUTS agreement test is running.
  - (3) Line coverage: 39% of single-listing units have 2+ peers, 59% are in a known building with no usable line, 1.5% are in a new building. Hierarchy: line posterior → building plus line prior → surface.

## 19. Round 13: why new-unit coverage is low (handed to thelio)
- Rule out first: does the held-out predictive integrate the unit effect at ν≈2 or as a Gaussian?
- First ask as a trial price: compare first-row vs later-row residual SD within repeat units. If it holds, the noise flag becomes "as-of first listing" (the dataset single flag leaks time), and coverage is measured on as-of first-listing rows. This is linked to decayed anchoring (#7) and final-ask noise (#10).
- Never-return products: rent-blind phrases (furnished, sublet, owner, condo…) and class.
- The loc pair becomes surface + WV step vs surface + labels (predicted tie; serve without labels).
- **Round 13 results (#591, merged; #590 log-linear noise code merged, no fit):**
  - (0) No code bug: the predictive integrates a Student-t unit prior (ν 1.84, scale 0.035) plus t noise (ν 2.74). The bands are what the model says.
  - (1) First asks: the prediction fails. First rows are 1.05× later rows (1.15× for 3+BR); single-listing units are at 9.2 vs 6.6–6.9. 47% of units list only once, and 80% of those rows are from 2023 or earlier, so it isn't censoring.
  - (2) Phrases flag 20% of singles with an SD ratio of 1.21×; the same share of repeat rows is flagged. Furnished +1.1 pp, utilities +0.2. Condo/other classes run 1.28× vs C/D.
  - (3) The noise flag is now as-of first listing. Held-out as-of first listings cover 0.76 / 0.93, but only 494 rows are truly new units (≈0.62 / 0.87). An honest number needs a time-split refit.
  - **Reading:** units that list once are a more dispersed population, not first asks. Levers: a wider or class-specific unit prior (condo and co-op lots), and a time-split new-unit evaluation.

## 20. Round 14: why once-listed units are wider (handed to thelio)
- (1) Missing or placeholder unit labels make ads single by construction. Predicted: over a third of singles, SD about 11 vs 7.5. Fix: a unit-label-missing noise term plus a fuzzy unit key from Data.
- (2) Bespoke stock: dispersion by line coverage, units per floor, pre-war and class. If it holds, the unit-prior scale becomes log-linear in building standardization covariates.
- (3) Seller type, if present.
- Conditional targets: on a time-split (last 12 months held out), truly new units go from 0.62 / 0.87 to ≥ 0.72 / 0.92.
- **Round 14 results (#593, merged):** all three predictions failed. Every row has a unit label (odd labels are not noisier). Line coverage gives 1.19×, units per floor 1.26×, class other vs D 1.40×; once-listed still adds 25–53% within every group. Owners are 12.95 vs 7.96 but only 1.6% of singles. The gap is about 1.35× everywhere.
- **My concern:** the comparison may be apples to oranges. Repeat-unit residuals are net of a fitted unit effect that saw the unit's own rows; singles' effects are shrunk to 0. Handed to thelio: the SD of repeat units' first-row residual with the unit effect added back, vs singles. If they match, the unit-prior scale is too narrow for unseen units, and there's no selection effect.
- **Round 15:** the comparison is made symmetric (leave-one-row-out) and judged on quantiles against the fitted t(1.84, 0.035). If the empirical quantiles are wider, the plan is ν_unit fixed at 4 with the scale free (predicted scale about 0.05, truly-new coverage about 0.72 / 0.92, LOO within ±15). A possible serving patch, a new-unit scale ×≈1.35, goes to Ben once confirmed.
- **Round 15 results (#595):** selection is real. With leave-one-row-out, repeat rows score 6.08–6.68 vs singles 9.11 (1.36–1.50×), and the gap holds by class and for units that are a small share of their building. The fitted unit prior is tight (0.0346 ± 0.0005, ν 1.84) and, if anything, too wide in the tails for repeat units (95% half-width 10.1 vs 16.2). ν_unit=4 dropped. The lever is the first-listing scale in the log-linear noise. It can only capture the mixture average, since whether a unit will list once isn't known at prediction.
- **Serving question for Ben:** site intervals for never-seen units are too narrow (80% band covers about 62%). Patch now with a documented multiplier, or wait for the noise fit.

## 21. Round 16 (handed to thelio)
- Signals for "won't come back": lister type (management vs brokerage) and building history (as-of once-listed share).
- Skew: do good deals not return (singles lower, heavy left tail)? If so, new-unit ranges should be wider AND lower.
- Fit on resume: a two-component unit-prior scale mixture (weight and second scale), with the weight a function of lister type if signal 1 holds.
- **Round 16 results (#597):** lister type is weak. Once-listed share: brokerage 43%, management 37%, other 40%. Singles vs repeat first rows: brokerage 9.75 / 7.36 (1.32×), management 8.13 / 6.39 (1.27×), other 1.46×. Building history orders weakly (1.11×). Skew: the median is +0.35 pp; both tails are heavier (below −20%: 5.9 vs 2.0%; above +20%: 7.1 vs 3.4%). The time split needs a refit.
- **Closing this line for now:** once-listed units are a symmetric, heavier-tailed population that nothing known at prediction identifies well. Fit on resume: log-linear noise (#590) with lister type added, compared with the two-component unit prior, judged on a time-split of truly new units. A site patch waits on Ben's card.

## 22. Round 17: fewer per-building parameters (handed to thelio)
- ×1.037 split by repeat vs singles; per-building slopes (how many are distinguishable, explained by type?); walk linearity by rows; the shared elevator large-unit curve pre-check.
- **Round 17 results (#598):**
  - (1) Noise multiplier split: global 1.051, repeat 1.016, singles 1.192. The under-dispersion is almost all singles; retire the global multiplier once the new-unit fix lands.
  - (2) Per-building slopes, % distinguishable (all / 20+ rows) and R² on type: bedrooms 20/43%, 0.02; size 9/20%, 0.06; second bath 9/20%, 0.02; floor 2/5%, 0.02. Drop the per-building floor slope; keep bedrooms (real and not explained by type).
  - (3) Walk linearity fails: a line carries 0.75 (5–19 rows) down to 0.39 (200+). building_trend can't replace the walk.
  - (4) The shared elevator/condo large-unit curve carries 0.755, but it is a 3BR+ curve (condo 2.10, elevator 1.33, 2BR 0.25–0.32). Walk-ups are flat.
  - **Fit additions on resume:** drop the per-building floor slope; replace the bedtime curves with a 3BR+ × elevator/condo time curve.
- **Round 18 (handed):** do data-rich walks co-move by class or size (2020–21 dip)? Is the per-building bedroom slope a stand-in for missing size? The flywheel rests after this.
- **Round 18 results (#599):**
  - (1) Walks: buildings with 200+ rows rose 7.6–8.7 pp above small ones in 2021 (the sign was opposite to the prediction; possibly advertised asks held with concessions). PC1 of the data-rich walks is 0.44, a slow 2015–25 divergence between buildings, not the pandemic. The walks stay.
  - (2) Bedroom-slope variance is 0.40–0.59× where size is known (small groups), so the slope is partly a stand-in for missing size. Candidate: bedroom-slope scale depends on size completeness.

## Flywheel resting (2026-10-09 ~01:30Z)
Free checks on the served fit are mined. Resume candidates, in order, after the v3 all-area base: line term → log-linear noise (first listing, lister type) vs two-component unit prior, on a time-split of truly new units → area_time (WV NTA 2022 step) → drop per-building floor slope → 3BR+ × elevator/condo curve → bedroom-slope scale by size completeness → locnolabel pair (surface + WV step vs labels) → permits → unical → singles (after the places map is dated). Retire the ×1.037 multiplier once the new-unit fix lands. Pending: Ben's card on patching site new-unit ranges.
- **Top free check when data work resumes:** concession text (months free, net effective) on 2020–22 ads by row band. Predicted: 200+-row buildings show at least 3× the small-building rate in 2021, and the 2021 walk gap closes to under 3 pp on net effective.
- **Data note (via the independent review):** ads with StreetEasy's months-free field filled are EXCLUDED from the data, and ad text stops mentioning concessions after 2020. So the 2021 large-building walk gap may be selection: held asks with the concession rows removed. Test: exclusion rate by row band in 2021 (predicted ≥3× for 200+-row buildings). If it holds, keeping concession rows as net-effective asks is a data decision for Ben, not a model term.
- **Concession result (Data item 1):** in 2021, buildings with 200+ rows conceded at 30.4% vs 15.1% for buildings with 1–19 rows (about 2×, and a standing property: 1.8× in 2020, 1.5× in 2022). That is worth about 1.5–2.5 pp of ask against a 7.6–8.7 pp gap, so concessions are minor. Open candidates: 2021 large-building cohort composition (bedroom and floor), and the share relisted lower within 6 months. first_listing_of_unit is already as-of.
