# family-bedroom-curve — One family-market bedroom curve in place of the three bedroom-group curves, gated by a free information-arithmetic loss estimate validated on lognoise

**kind:** free check then fit (model-term swap)

**what:** Modeling. Step 0 (about 4 h, free on thelio). (a) The class split of C's 2BR and 3BR+ minus 1BR gaps by year (PLUTO class families, features.py:1928-1933). Keep the walk-up exclusion only if class C's year SD is under 1.5 pp; otherwise use the all-rows rank-1 form. (b) The restriction arithmetic from the noise lens: predicted delta ELPD of about -0.5 x I x sum n delta^2 on the 68 log sigma, with I = 2nu/(nu+3), retro-checked on lognoise's observed -1,991 +- 89. Once validated, apply the same calculation to the bedroom curves' rank-1 misfit to predict the swap's loss. Step 1 (about 1 day of code): ModelConfig.bedroom_time_family, one quarterly random-walk curve g(t) with a HalfNormal(0.02) scale. Each row gets g(t) x L, with L = (studio 0, 1BR 0, 2BR 1, 3BR+ 2) x 1[class family not C], replacing the three curves (model.py _bedroom_time, gibbs.py:419-429, explain.py:99-100, kit.py). One fit: `m7-nocurves-floorslope-bednoise-dayfourier-familytime-yearnoise-sizeunkslope nb8-nostuy-v1`, plus the new-building score, only if the calibrated arithmetic predicts a loss no worse than about 2 clustered SE.

**weakness:** C carries three quarterly bedroom-group curves (about 201 global latents) describing what free checks found to be one drifting per-bedroom price in family stock. The SVD's first component carries 84.6%; the rank-1 misfit is 0.52/0.55 pp against posterior sds of 0.99/1.73; the studio curve is noise. The pooled 3BR+ curve misprices flat walk-up 3BR+ rows. And capacity-change predictions have no arithmetic: the team's removal misses were 6-22 SE (lognoise -1,991 vs a prediction of -30 or better; nofloorslope -314 vs -40..0).

**mechanism:** The price of an extra bedroom in elevator, condo and other non-walk-up stock fell from 2015, bottomed in 2020-24 and is easing; walk-ups (the sharer market) did not move. One curve x extra bedrooms x non-walk-up states that directly. The arithmetic makes the cost of the restriction computable from C's posterior before paying for a fit.

**evidence:**
- research-backlog.md:633-643 (check E): SVD 84.6 / 12.6 / 2.9%; fixed linear loadings misfit 1.01 / 0.52 / 0.55 against posterior sd 1.00 / 0.99 / 1.73.
- research-backlog.md:614-631 (check D): elevator/condo 3BR+ vs 1BR 2.8 -> -6.0 -> -10.8 -> -9.7 pp; walk-up -0.8 -> -1.6 -> -0.5 -> +1.2. :1373-1380: the shared curve carries 0.755.
- bigbed (3BR+ x elevator/condo as an add-on) gained +43 +- 18 against a predicted 0 to +40 (config/predictions.jsonl:4), using an elevator flag that is 43% unknown (features.py:3440).
- model.py:1547-1550: the curves add about 200 global columns, and the global solve grows with the square of its size.
- lognoise -1,991 +- 89 against a prediction of -30 or better (config/predictions.jsonl:1); inferred 0.48 x 193k x 0.15^2 is about 2,090, close to the observed loss.

**prediction:**
- psis_loo: +20 (80% -250 to +220) vs C; P(clears +2 SE) about 0.3; ties or wins with P about 0.55. Arithmetic retro-check: lognoise computed at -1,800 (-2,600 to -1,200) vs -1,991 observed; separable noise (21 scales) -60 (-150 to 0); market-velocity noise -1,000 (-1,600 to -400), killed with P about 0.9.
- new_building: -0.05 pp (80% -0.2 to +0.1); 80/95 coverage +-0.3.
- new_unit: n/a
- descriptive_share: +0.05 pp (80% -0.3 to +0.4); the curves count as market and time.
- other: The global block shrinks by 134 columns; fit time falls 5-15%. g(t): -3 to -8 pp per extra bedroom in 2020-24 vs 2010-14, with partial recovery by 2026. Class-C year SD 0.8 pp (0.5-1.4). Market velocity explains about 0.35 (0.1-0.6) of the within-bedroom year variance in log sigma.

**cost:** Modal about $2.1 (fit + $0.13 score), only if gated; the arithmetic and class split are $0 on thelio. Oxylabs $0; other $0. Modeling: about 4 h of free checks, about 1 day of code, one fit; about 2 days elapsed. Ben's go; gate, autoselect, PR.

**free_precheck:** The arithmetic is validated only if it reproduces lognoise within +-50%. Then fit the swap only if its calibrated predicted loss is within about 2 clustered SE (about -100). The class-C year SD picks the form. A noise-form fit (separable, 21 scales) is a separate later candidate, and only if its own calibrated loss is 100 or less.

**miss_criteria:** PSIS-LOO below -2 clustered SE vs C; the fitted non-walk-up curve falls by less than 3 pp per extra bedroom in 2020-24 vs 2010-14; the new-building miss worsens by more than 0.1 pp; fit time does not fall; or the arithmetic misses lognoise by more than +-50% (the tool is not validated).

**p_success:** 0.45

**expected_to_fail_reason:** About even odds. At 193k rows, PSIS-LOO has punished every capacity removal far beyond prediction. The studio curve, the second SVD component (12.6%) and residual walk-up drift may cost 100-300 nats. Checks D and E ran on the NB5 fit, before East Village (31% of rows) entered. The arithmetic may not carry over from noise scales to mean curves.

**worth_it_anyway:** A win or tie is served on elegance and speed, and puts the family-market finding into the model as one named curve. A loss, or the arithmetic alone, measures how much structure the three curves carry beyond rank 1. It also turns future removal pre-registrations into calculations instead of 'tie' calls (reader finding 10).

**rank_argument:** The cleanest parsimony swap with the evidence in hand: 134 latents out, one mechanism in. The free arithmetic addresses the team's worst prediction failures. It ranks last because it does not touch uncertainty and moves the new-building miss by 0.1 pp at most.

**depends_on:** Ben's go; the PLUTO as-of class column in nb8-nostuy-v1; nb-lpd-clustered's time-cell clustered SE for reading the result. Independent of walk-ar1.

**proposed_by:** ['parsimony']

**merged_from:** ['family-bedroom-curve', 'noise-arithmetic-gate']

**conflicts:** An editorial merge to meet the 11-candidate cap. Both are parsimony-lens restrictions, and the noise arithmetic here becomes the swap's missing kill rule (the original swap had none: 'one of the two forms runs'). Carrying the arithmetic from log sigma to mean curves is the editor's step, not a proposer's. The market-velocity noise fit stays dead, as its own lens predicted and as the outside view argued ('more noise structure explains nothing'). bigbed and pre-registration #9 are the alternatives this form beats, per the parsimony lens.
