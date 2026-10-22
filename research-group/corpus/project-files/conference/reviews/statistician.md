# Statistician review (reviewer subagent, 2026-10-22)

**Recommendation: major revision.** The design is careful and the floor result holds up, but several uncertainty and location claims go further than the authors' own runs support, and some numbers differ from the notes.

## Main weaknesses and fixes

1. **Coefficient intervals are not justified.** The paper prints intervals 0.1 points wide and then says they are too narrow. The null simulation, not reported, shows the same problem in the floor curve: true value 0, estimate +0.1 to +0.4 points, 66% coverage. Repeat ads of the same unit are treated as independent, which narrows intervals further. Fix: add a unit or line effect, or cluster draws by unit. Lead with Mundlak (unbiased in the simulation) for unit terms. Drop "within ±0.5 points" and the second decimal place everywhere, abstract included.
2. **The simulation audit is weak as a calibration check.** Each scenario has one dataset whose truth is a posterior median. That truth is smoother than the prior, which explains the surface's 94–99% over-coverage, and it is tilted toward random effects. Coverage across 119 dependent terms in one dataset has no Monte Carlo error. Fix: run several replicates per scenario, with truths drawn from the prior and from the Mundlak fit, and report per-term coverage with Monte Carlo standard errors.
3. **The negative result on location is confounded.** The basis size, boundary factor and smallest resolvable lengthscale of the reduced-rank surface are not given. "Features that vary faster than the surface help" may only reflect basis resolution. The surface is also static across 16 years of gentrification. Fix: report the approximation settings, refit with a finer basis or a block-level effect, and add a space-time term or zone-specific trends.
4. **The park-frontage claim is overstated.** The +187 gain (2.3 SE) comes mostly from ads not facing a park: +135 (SE 45) there against +52 (SE 67) on park-facing ads, because the smooth distance terms shifted. The feature also fails its permutation null, and four or more features were tried on this split. Fix: say the result is not established and adjust for the number of features tried.
5. **Convergence and validation are under-reported.** The outer-zone surface amplitude is the bottleneck in every fit (R-hat 1.0097). Divergences, E-BFMI and tree depth are not reported. Per-building standard errors on the latest split ignore weekly shocks shared across buildings. The Manhattan surface amplitude (0.92) sits about 3 prior SDs into a HalfNormal(0.3), so a prior-sensitivity check is needed. Fix: report the full HMC diagnostics, cluster standard errors two ways by week and building, and run a prior-sensitivity fit.

## Mismatches with the notes

- Under Mundlak, building terms "shrink by a sixth to a half". The notes show 25% (doorman) to 56% (retail), and 81% for log height.
- The building-split base fit fails the gate (R-hat 1.0105). The paper does not say so.
- The paper says floor hyperparameters have R-hat ≤ 1.001; the note gives 1.0013.
- Table 1's predecessor RMSE is 0.1173; the note gives 0.1172.
- Elevator ads with an unknown floor lose 202 elpd (12 SE). This is omitted, and the note calls the floor bands post hoc, while the paper says the gain falls "where theory says".
- The "realistic" truth is not simply the fitted medians: the walk-up curve was changed and the top-floor flag set to 3.92% against 1.75% fitted.
- In-building laundry is biased +0.22 to +0.26 with correlation −0.01, which contradicts "each bias follows its correlation".
- The Mundlak fit's held-out score was never computed, yet it defines half of every reported range.
- The abstract says "seven named location features"; Table 2 has ten.

## Strengths

- Predictions are written before each fit and misses are recorded, with paired, building-clustered held-out elpd and a split that holds out whole buildings.
- The authors measure and report bias in their own estimator, including a Mundlak comparison on both simulated and real data.
