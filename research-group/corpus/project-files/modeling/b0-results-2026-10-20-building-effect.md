# Building-effect fit: results (did not converge)

*Fit 2026-10-20. This is the whitened three-zone 1 km model (#1171) plus a descriptive building effect. Each of 73,433 buildings gets an unexplained level, η_k ~ N(F(s_k), s_zone), with a HalfNormal(0.3) spread per zone. The ads see η_k. The model is in PR #1173, and #1174 turned off ChEES's trajectory-length floor. The data are the all-data v36 dense set, rebuilt with the bath fix from PR #1172, which recodes 97 listings. Nothing on the served model or the site changed.*

## Bath fix (PR #1172)

**The rule.** It recodes full baths when a listing codes 3+ full baths, no half bath, and at least bedrooms + 2 full baths, and when at least half the other ads for the same unit or line code fewer. The new count is the most common one among those ads. Listings where another ad codes more bedrooms are skipped.

**How it scores:**
- Against the reading pass: precision 1.00 (60 of 60), recall 0.45.
- Against Ben's hand review:
  - It fixes 180 Riverside 25A (to 2 baths), 722 Marcy and 952 Bedford.
  - It misses 160 Riverside 7A, 70 W 68th and 486 9th Ave 4RN.

**What the hand review settled:**
- 180 Riverside 25A is 1 bed with 2 full baths, matching its A stack.
- 90 4th Pl #1 is 2 beds plus a den with 3 full baths, so its error is the bedroom count.

**Half baths counted as full** (The Rectory, 370 Butler) aren't recoded yet. About 5% of 3+ bath listings show the pattern, but the evidence for a rule isn't clear-cut.

**Effect on the model.** In the 5% local check, the fix moved the 1-bed, 3+ bath coefficient from −0.19 to −0.08. So the typos were biasing it.

## Run

- **First launch:** ran out of GPU memory after 2 minutes, before sampling. ChEES kept a covariance over all 74k coordinates. Cost about $0.10.
- **Second launch:** run `building-zones-b0-latest-70e1b061-dense-w1500`. Wall time 10.8 min (warmup 4.1, sampling 4.7), cost about $0.2.

## Convergence: fails badly

- Max R-hat is 6.57 (the studio→1 bed step), and the lowest ESS is 8. Every quantity fails.
- The step size was 0.021, but ChEES adapted a trajectory of only 3 leapfrog steps (2.3 on average). The whitened-zones fit used 64.
- No divergences while sampling; 620 in warmup.
- The 16 chains agree to 3 decimals but barely move. For example, the 1-bed step's chain medians all fall between +22.0% and +22.3%.

## Stuck values (not estimates)

- **Surface amplitudes:** about 0.001 in all three zones.
- **Building share:** 1.00. The buildings took all the location variation.
- **Building spread:** Manhattan 0.296, Brooklyn + Queens 0.251, NJ 0.232.
- **σ:** 0.107–0.146.
- **ν:** 6.1.

These may simply be the chains' starting values, since 3-step trajectories barely move. A surface amplitude near zero contradicts every earlier fit, which found a converged zone gap of about +32%. So these values say nothing about the model yet.

## Confirmed: the stuck values were the starting point (free check, 2026-10-20)

- **Starting values:** the chains started with amplitude 0.1 and the waves near 0. Warmup drained the amplitude to 0.001, and the waves never moved. σ and ν did move (σ 0.3 → 0.11, ν 10 → 6).
- **The posterior wants the surface:** holding the stuck building levels fixed and putting in the whitened-zones waves and amplitudes raises the log density by about +11,200. The best waves given those levels raise it by about +15,450 to +16,000.
- **Building share:** at those best waves, the surface carries about 44% of the building-level variance, so the buildings' share would be well under 1.
- ~~Proposed fix: start chains from the whitened-zones draws.~~ Withdrawn.

**5% CPU NUTS check** (88,631 rows, one chain per start, 127 leapfrog steps per draw):
- Both starts reach the same posterior, including the Modal start of amplitude 0.1 with the waves at 0.
- Amplitudes come out at 0.80, 0.36 and 0.44, with building shares of 0.58, 0.39 and 0.62 and building spreads of 0.22, 0.14 and 0.15. ν is 3.9.

So the problem is trajectory length. ChEES tuned its moves to suit the 73k building levels (3 steps), and without the length floor the slow directions never moved.

**Proposed fix (needs Ben's go):** a fixed floor of 32 leapfrog steps (cap 64), with warmup shortened to 1000/400 to fit under the 1-hour cap (about 52 min). Predictions:
- R-hat < 1.05 and ESS > 100;
- amplitudes 0.4–2;
- a building share of 0.3–0.7;
- building spread 0.18–0.26 for Manhattan and 0.11–0.18 elsewhere.

If it fails, the next candidate is sampling the amplitude non-centred against the waves.

## Original next steps

1. Compare the stuck values with the initial values.
2. On a 5% CPU NUTS run, check whether the amplitude leaves 0 when started at 1, and whether the log density favours amplitude 1–6 over 0.001.
3. Check whether the 5% ChEES check, which has run 3+ hours with no output, is hung.
4. Propose one fix with predictions. Candidates are a fixed minimum trajectory length, initializing from the whitened-zones posterior, or a structural change if the posterior really prefers no surface.

## ChEES 5% check on whitened zones (finished 2026-10-20)

This was production ChEES warmup on the 88,631-row sample: 16 chains, 1500 warmup draws, the length floor on, cap 1000. It took 6.8 CPU-hours.
- **Adapted step:** 0.0192, against 0.046 for NUTS.
- **Steps per draw by tenth of warmup:** 12, 9, 8, 7, 7, then about 500 for the rest. Once the diagonal mass matrix took effect, the floor jumped to the cap.
- **Divergences:** 348, mostly early.

**What it means.** On whitened zones there is a slow direction that ChEES's own criterion misses by about 50×. On Modal, the cap of 64 clipped that floor, which may explain part of the whitened fit's R-hat of 1.14. For the building fit, an average of 32 steps is well short of the roughly 127 that NUTS used or the roughly 500 the floor wanted. So R-hat < 1.05 and the amplitude range are now at risk. The run is still the cheapest test of whether trajectory length is the bottleneck. If it fails, the next fix is structural: sample the amplitude non-centred against the waves, rather than paying for longer trajectories.
