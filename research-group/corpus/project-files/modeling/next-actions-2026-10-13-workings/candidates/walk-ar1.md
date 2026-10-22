# walk-ar1 — Mean-reverting (AR(1)) building walk nesting C, gated by free walk-origin diagnostics; a building scale by PLUTO size is the alternative single fit

**kind:** free check then fit (model term)

**what:** Modeling thread. Step 0, free on thelio (2-3 h, partly from nb-lpd-clustered step 0): first-knot rescore and 80/95 coverage by listing-year band x row bin on C, areatime and nofloorslope. SD of the posterior-mean entry premium by entry cohort (6+-row buildings). A nugget-corrected variogram of buildings' yearly premia at lags of 1-10 years, with a building block bootstrap. Cross-sectional SD of level + walk by knot against sqrt(bs^2 + ws^2 k). A regression of each building's mean^2 + variance on centred log_unitsres and class. Step 1 (2-3 days of code): ModelConfig.walk_ar1, with w_k = rho w_{k-1} + e_k and w_0 = 0, so rho = 1 recovers C. Half-life prior log-uniform over 0.5-50 years, with mass at rho = 1. gibbs.py builds the gap-based tridiagonal AR(1) precision (rho^gap) in compact_walk (:284-296), an OU bridge in fill_walk (:327-341), and a rho step. newbuilding.building_variance uses ws^2(1 - rho^(2k))/(1 - rho^2). One fit: `m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise-sizeunkslope-ar1walk nb8-nostuy-v1`, rows split, plus the new-building score. If step 0 shows a flat year gradient but a unitsres gradient (5- vs 200-unit sd ratio of 1.15 or more at t >= 3), the single fit is instead `-bscaleunits`: log bs_b = log bs + gamma log_unitsres_b + delta unitsres_unknown_b, about 1 day of code.

**weakness:** C's walk is pinned at 0 in 2010 (model.py:135-138), and the score keeps that origin (newbuilding.py:95-104). So the prior implies building dispersion growing from about 12% to about 21% over 2010-26 (reader finding 1). New-building coverage is 90.7/98.1, with predicted variance about 1.8x actual in 21+-row buildings. The held-out-lots refit is just as wide (91.2/98.1), so the model is the cause, not the score. A late entrant's static premium is split between level and walk, so 'building' (10.2%) vs 'building over time' (5.6%), and every explained-share target, depend on entry date. Separately, 1-5-row buildings are too narrow (77.8/92.3).

**mechanism:** Building premia drift (management turnover, renovation cycles) but revert. A stationary AR(1) bounds dispersion at bs^2 + ws^2/(1 - rho^2), turns the level into the long-run premium, and gives an unseen building the same spread in any year. Its half-life is one renter-readable number in place of an assumption that drift never stops. rho = 1 recovers C, so the data choose and PSIS-LOO has little room to lose. The bscale branch instead widens small buildings and narrows large ones, if dispersion tracks observable size.

**evidence:**
- newbuilding.py:74-104: walk variance ws^2*(knot - origin), origin at the panel start; model.py:155-162: 'a building first listed in 2020 has a level reached through ten years of prior-only walk steps'.
- gibbs.py:241-296: compact RW1 precision over touched knots; gibbs.py:344-363 refuses anchored, t, masked and zero-sum walks (NUTS only); anchored NUTS runs failed every-element R-hat at 1.21-1.32 (research-plan.md:742-790).
- Fitted half-year steps have RMS 0.36-1.59% against a prior sd of 2.8-3.1%, a slow drift (research-backlog.md:306-322). 200+-row buildings were 7.6-8.7 pp above small ones in 2021 and converged by 2026, but PC1 of data-rich walks (0.44) is a slow 2015-25 divergence.
- Coarsening loses: yearly knots -776.5 +- 34.7 (research-plan.md:1611-1622); linear trend -2,636 +- 152 (:695-700).
- Bins: 1-5 rows 77.8/92.3; 21-100 rows 91.9/98.5; 101+ rows 91.1/98.3 (newbuilding-2026-10-13.md:26-29). NB5-era scale multipliers: 1-5 rows 1.33-1.37, 21+ rows 0.99-1.08; class R 1.22-1.35 (research-backlog.md:255-269).
- Only 2.3% of rows are from 2010-13, so nearly every building enters at knot 8 or later (size-predictability-2026-10-12.md:134-137).
- Slope priors may add comparable width: scales of 0.099 (bedrooms), 0.161 (second bath) and 0.270 (log size) (research-backlog.md:1326-1332).

**prediction:**
- psis_loo: +40 (80% -80 to +300) vs C on shared rows; paired SE about 40-50. P(clears +2 clustered SE) about 0.3; P(< -2 SE) about 0.12. bscale branch: +30 (-20 to +150).
- new_building: Miss 0.0 pp (80% -0.15 to +0.1). 80/95 coverage 90.7/98.1 -> 87.0/97.0 (84-90 / 96-98); 21+-row bins about 91.5 -> 87.5 at 80%; the 1-5-row bin narrows from 77.8/92.3 to about 74/91 (71-78 / 88.5-92.5). New-building lpd +0.03 nats/row (0.00-0.05); the year gradient falls by 3 pp or more. bscale branch: 1-5 bin -> 82/94.5 (79-85 / 93-96); overall 89.5/97.8.
- new_unit: n/a: unit terms are unchanged (67/89 +- 1 pp).
- descriptive_share: Total -0.2 pp (80% -1.1 to +0.7), inside the noise floor. The split moves: building over time 5.6 -> 3.5-3.8 (2.0-5.2); building 10.2 -> 12.0 (10.5-13.5).
- other: Free checks: year gradient +5 pp. Entry-cohort premium SD flat within +-2 pp (12-14%), against the random walk's implied ~19% for 2020 entrants. Variogram gamma(8y)/gamma(2y) 2.6 (1.9-3.6), against 4 for a random walk. Fit: rho 0.90 per half-year (0.80-0.97), a half-life of about 3-5 years (1.6-15). Explained shares of screened families x1.0-1.3 on the cleaner level.

**cost:** Modal about $2.1-2.2 (+$2 if the gate needs more draws). Oxylabs $0; other $0. Modeling: 2-3 h of free checks, 2-3 days of gibbs.py/model.py/newbuilding.py code and NumPyro reference tests (the bscale branch about 1 day), one fit and a reviewed PR; about 4 days elapsed. Ben's release of held runs; gate, autoselect, PR.

**free_precheck:** Kill the AR(1) fit if the coverage gap between 2014-16 and 2024-26 rows is under 2-3 pp and the first-knot rescore moves overall 80% coverage by under 2 pp. Also kill it if gamma(8y)/gamma(2y) is 3.3 or more while the entry-cohort SD rises by at least 60% of the random walk's implied amount (or the cross-sectional SD grows at least 70% as fast as implied). Then fit the bscale branch only if its precheck passes: ratio of 1.15 or more at t >= 3, and no 1-5-bin signed error of 3% or more. If the over-width tracks bedroom/bath instead, the correlated-slope prior is the next candidate.

**miss_criteria:** A precheck kill counts as a miss of the mean-reversion hypothesis. Fit misses: rho median at 0.98 or above, or its 80% interval reaching 0.995 (half-life of 10+ years); overall 80% coverage falling by under 1.5 pp; PSIS-LOO below -2 clustered SE; the miss moving by more than 0.1 pp; a gate failure on rho or walk_scale after one more-draws retry.

**p_success:** 0.38

**expected_to_fail_reason:** Slightly likelier to fail than to pass. Data-rich walks show a slow 2015-25 divergence (PC1 0.44), so rho may sit near 1. The independent slope priors (+0.039 for 3BR, +0.088 for 4BR+, +0.026 for a second bath) and the single building scale may carry as much excess width as the walk. walk_scale is the slowest-mixing scale, and rho may worsen it under the every-element R-hat gate. It also narrows the already-narrow 1-5-row bin.

**worth_it_anyway:** The free checks alone settle reader finding 1 and tell Modeling whether to fix the walk, the slopes or the building scale. Even at rho near 1, we learn how persistent a building premium is. The level also becomes a long-run premium, which cleans the descriptive split and every explained-share target.

**rank_argument:** It is the only single term aimed at the over-width on 89% of rows, with a bounded downside (it nests C) and a free kill. Coarser walks lost heavily, and anchored or t walks need NUTS and failed the gate, so a change of prior is the only way to keep the walk's PSIS-LOO value. It ranks below time-split because its precheck may kill it and the code takes 2-3 days.

**depends_on:** nb-lpd-clustered (step 0 and the lpd judge). Ben releasing held runs. Autoselect ignores new-building coverage, so a coverage-only win is Ben's call. Follow-ups noted here, not part of this fit: a second fit with rho fixed at the variogram half-life if rho fails the gate; the other branch (bscale or AR(1)) on top if both mechanisms show; a Student-t building level after bscale.

**proposed_by:** ['parsimony', 'uncertainty', 'outside view']

**merged_from:** ['ar1-walk', 'walk-ar1', 'walk-anchored-at-entry', 'bscale-units']

**conflicts:** Form: the outside view proposed anchoring each walk at the building's first knot (cheapest, about 5.4k fewer latents; PSIS-LOO -10, -150 to +120). The uncertainty lens argues that anchoring leaves row-weighted width about unchanged if the level scale absorbs entry dispersion, and that it leaves post-entry growth untouched. Parsimony and uncertainty both chose AR(1), which nests C. I kept AR(1), with anchoring as the fallback if rho mixes badly. PSIS-LOO: +60 (parsimony), +40 (uncertainty), -10 (outside view); kept +40 with the -80 lower end. Half-life: 5 years (parsimony) vs 3.3 (uncertainty). bscale-units (uncertainty lens) is folded in as the alternative branch chosen by the same free diagnostics, as the uncertainty and outside-view decision rules prescribe; this is an editorial merge to meet the cap.
