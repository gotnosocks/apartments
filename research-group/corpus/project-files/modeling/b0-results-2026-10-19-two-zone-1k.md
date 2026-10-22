# Two-zone location fit at 1 km: results (did not converge)

*Fit 2026-10-19. This is the two-zone model (#1159) with only the length-scale changed, to a fixed 1 km in both zones (PR #1164, merged as 8c51149b). The basis shrank to match: Manhattan 5 × 17 = 85 waves (from 340), Brooklyn + Queens 10 × 11 = 110 (from 440). Angles and boxes are unchanged, and no buildings are clipped. Nothing on the served model or the site changed.*

## Run

- Run `two-zone-1k-b0-latest-8c51149b-dense-w1500`, fit-only, on an A100-40GB.
- 16 chains, 1,500 warmup steps and 500 draws.
- 27 min and $1.07.
- No divergences while sampling; 294 in warmup.
- Acceptance 0.78, with 32.5 leapfrog steps on average.

## Convergence: fails

| Quantity | R-hat | ESS |
|---|---|---|
| Season cos2 (worst) | 2.31 | — |
| 1 bed with 4+ baths | — | 11 |
| Bed, bath and season terms | 1.9–2.3 | — |
| g | 1.77 | 17 |
| τ | 1.49 | 34 |
| Manhattan amplitude | 1.30 | 62 |
| σ, groups 1–3 | 1.13–1.18 | — |
| ν | 1.14 | 81 |
| Brooklyn + Queens amplitude | 1.10 | 180 |
| **Zone gap** | **1.024** | **505** |
| **σ, group 0** | **1.016** | **841** |

The step size was 0.0026. The 500 m fit took 0.0016, and the converged fit without location took 0.25. Removing the fast waves didn't fix the stall.

## Values (posterior medians; only the zone gap and σ[0] are trustworthy)

- **Zone gap:** Manhattan +32.3% (32.2 to 32.4) above Brooklyn + Queens, the same as the 500 m fit.
- **Amplitudes:** Manhattan 1.15, Brooklyn + Queens 2.12.
- **Surface sd across buildings:** Manhattan 0.185, Brooklyn + Queens 0.172.
- **σ by group:** 0.178, 0.193, 0.181, 0.194. ν 7.35. τ 0.0062. Trend +3.6% a year.
- **Bedroom steps:** studio→1 +28.1%, 1→2 +13.7%, 2→3 +17.1%, 3→4 +40.2%, 4→5 +12.1%.
- **One extra bath:** studio +68%, 1 bed +38%, 2 bed +45%, 3 bed +30%. The 4 and 5 bed steps change sign between chains.

## Map

`/data1/apartments/frontier/runs/two-zone-1k-b0-latest-8c51149b-dense-w1500/surface_map.png` on thelio.
- **High:** Tribeca (up to +0.70), the West Village, Chelsea and the Upper West Side.
- **Low:** Harlem, East Harlem and eastern Brooklyn (down to −0.61).
- **Above the Brooklyn + Queens mean:** brownstone Brooklyn and Long Island City.

The flat 0.02 posterior sd understates the uncertainty, because the chains stalled.

## Why it stalls (free checks on thelio, no fits)

**Method.** Hold the scales at their medians, build the Gaussian precision of everything else in the sampler's coordinates on all 1.71M rows, and scale it by the true posterior sds. The stable step size is about 2/√λ_max.

| Setup | λ_max | Predicted step | Observed step |
|---|---|---|---|
| 1 km, as run | 805,000 | 0.0022 | 0.0026 |
| No surface | 12.3 | 0.57 | 0.25 |

The stiff directions are all combinations of waves: 53 eigenvalues above 1,000 in the Brooklyn + Queens block and 40 in Manhattan. The stiffest lies on low Brooklyn + Queens waves. The data pin each coefficient tightly (a median of 77,000 to 211,000 times the prior precision), and on the data some wave combinations are nearly interchangeable.

**Ruled out:**
- **Centring.** Without it, λ_max is unchanged (806,000).
- **Confounding with the ladder or season.** The largest ad-level correlation is 0.24, and no fixed effect correlates with a wave by more than 0.03 in the linearised posterior.
- **A funnel.** The data, not the prior, set every coefficient.

The fixed effects stall only because every trajectory is 32 steps of 0.0026. Their spread between chains equals their posterior sd, so each chain is still sitting where warmup left it.

## Predictions (PR #1164)

| Prediction | Result |
|---|---|
| R-hat ≤ 1.02, ESS ≥ 400, step ≥ 0.05 | Miss |
| Zone gap +22% to +35% | **Hit**, +32.3% |
| Manhattan amplitude 0.3–1.5 | Hit, 1.15 |
| Brooklyn + Queens amplitude 0.15–0.8 | Miss, 2.12 |
| Brooklyn + Queens sd ≤ 0.17 | Narrow miss, 0.172 |
| σ rising toward the fit without location | Partly; groups 0–2 rose 6–8%, group 3 rose 4% |
| ν 4–15 | Hit, 7.35 |
| τ 0.009–0.014 | Miss, 0.0062 |
| Wall time 12–35 min | Hit, 27 min |

## Proposed fix (not built; waiting on Ben)

Rotate the wave block with a fixed linear map, computed once from the data's Gram matrix and the prior at reference amplitudes. Sample z, with w = T z (the QR reparameterisation). The model and priors are unchanged; only the sampler's coordinates change.

In the same linear check, λ_max falls from 805,000 to 12.8, so the predicted step returns to 0.56. That holds for amplitudes from 0.7 to 1.4 times the median.

Diagnostic scripts are on thelio in `/data1/apartments/tmp/tz-diag`.
