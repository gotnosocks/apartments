# Whitened three-zone location fit: results (nearly converged)

*Fit 2026-10-19/20. This is the 1 km two-zone model (#1164) with two changes:*
- *The wave coefficients are sampled in rotated ("whitened") coordinates, w = T z. T is one fixed matrix, the Cholesky factor of the data-weighted Gram matrix of every wave plus the prior precision, computed jointly across zones at reference σ 0.19, ν 7 and amplitude 1. The model and priors are unchanged.*
- *A third zone for NJ (Jersey City and Hoboken), at 1 km.*

*The data are the all-data v36 dense set, 1,969,084 rows (`b0-30b3edae310c2fae-alldata-v36-dense`). PR #1171, merged as ff932360. Nothing on the served model or the site changed.*

## Boxes at 1 km

| Zone | Rotation | Waves |
|---|---|---|
| Manhattan | 25.5° | 5 × 17 = 85 |
| Brooklyn + Queens | 39° | 10 × 11 = 110 |
| NJ | 12.5° (3.35 × 7.09 km, 5,456 buildings) | 3 × 7 = 21 |

Unrotated boxes would need 334 waves instead of 216. Whitening each zone separately only lifted the predicted step bound to 0.026, because the surface centring ties the zones' lowest waves together. So the zones are whitened jointly.

## Checks before the fit

| Check | Result |
|---|---|
| Linear step bound, full data | 0.558 whitened, against 0.0022 unwhitened; flat for amplitudes 0.7–1.4 |
| 5% CPU NUTS | whitened 0.0495 (127 steps), the same as no surface (0.049); unwhitened 0.0062 at the 255-step cap |
| Prior predictive | 93% of rents in $1k–$30k |

## Run

- Run `whitened-zones-b0-latest-ff932360-dense-w1500`, fit-only.
- Modal preempted the container once and restarted it on the same input. It was not a seed retry.
- 23 min wall time, about $0.92.
- Step size 0.0070, 33 leapfrog steps, acceptance 0.80.
- No divergences while sampling; 399 in warmup.

## Convergence: fails the gate, narrowly

- **Worst:** R-hat 1.14 (1 bed with 4+ baths, 44 rows); lowest ESS 60 (1 bed with 3+ baths, 215 rows).
- **Compared with earlier fits:** the 1 km fit without whitening reached R-hat 2.31 at step 0.0026, and the converged fit without location adapted 0.19.
- **No longer a problem:** the surface coefficients.
- **Unconverged:** the two sparse bath cells, the season (sin1 1.12), the Manhattan amplitude (1.12), the drift g (1.10) and the Brooklyn + Queens amplitude (1.04).
- **Trustworthy** (R-hat ≤ 1.02, ESS ≥ 400): the zone levels and gaps, ν, every σ, τ, the NJ amplitude, every bedroom step, and every bath cell except the two sparse ones.

The step size came in well below the check's prediction. ~~The likely reason is a mis-scaled T.~~ That guess was ruled out (2026-10-20): T rebuilt at the fitted σ, ν and amplitudes gives the same linear bound (0.559 against 0.558). The small step is set during warmup, where there were 399 divergences, so something nonlinear is responsible. The suspects are:
- the mostly mistyped sparse bath cells;
- the heavy tails (ν 7.2, against 21 without location);
- the season trading off against the walk.

## Zones (median [95%])

| | Manhattan | Brooklyn + Queens | NJ |
|---|---|---|---|
| Amplitude | 6.26 [5.92, 6.60] (untrusted) | 3.84 [3.54, 4.14] (untrusted) | 1.34 [1.12, 1.62] |
| Surface sd across buildings | 0.188 | 0.172 | 0.095 |
| Level against Brooklyn + Queens | **+32.2%** [32.1, 32.3] | — | **+0.9%** [0.7, 1.1] |

## Noise and walk

- **σ by group:** 0.177, 0.190, 0.180 and 0.193.
- **ν:** 7.24 [7.17, 7.32].
- **τ:** 0.0064 [0.0058, 0.0070], against 0.0116 in the fit without location.
- **COVID:** the trough came in the week of 2021-01-11, at −22.4% [−22.8, −22.0]. The largest shock was 2.5 τ, in the week of 2021-07-19. 9 of the 10 largest shocks fall in COVID.
- **Untrusted:** g is +3.4% a year [+1.3, +5.9], and the season peaks in early July with 5.1% from peak to trough.

## Ladder (intervals within about ±0.6 points)

- **Bedrooms:** studio→1 +27.9%, 1→2 +13.6%, 2→3 +17.1%, 3→4 +40.1%, 4→5 +12.1%.
- **Second full bath:** studio +68%, 1 bed +37%, 2 bed +43%, 3 bed +29%.
- **4 beds:** a third bath adds +52%, and dropping from 2 baths to 1 costs −21%.
- **Flags:** rent stabilized −6.8%, income restricted −12.3%, shared space −5.2%.

## Predictions (PR #1171): 4 hits, 4 misses

| Prediction | Result |
|---|---|
| R-hat ≤ 1.02, ESS ≥ 400, step ≥ 0.1 | Miss: 1.14, 60, 0.0070 |
| Manhattan over B+Q +22% to +35% | **Hit**, +32.2% |
| NJ over B+Q +5% to +30% | Miss, +0.9% |
| Amplitudes M 0.3–1.5, B+Q 0.15–1.0, NJ 0.05–0.8 | Miss: 6.26, 3.84, 1.34 |
| Surface sd M 0.10–0.20, B+Q 0.10–0.17, NJ 0.04–0.15 | Narrow miss (B+Q 0.172) |
| σ in 0.165–0.30, ν in 4–15 | Hit |
| τ 0.009–0.014 | Miss, 0.0064 |
| Wall time 15–45 min | Hit, 23 min |

## Map

The map is at `/data1/apartments/frontier/runs/whitened-zones-b0-latest-ff932360-dense-w1500/surface_map.png` on thelio. The per-building surface is in `/data1/apartments/tmp/tz-diag/wzfit/surface.parquet`.

## Proposed next steps (waiting on Ben)

1. **Fix the sparse bath cells.** They are mostly typos (checked 2026-10-20):
   - Of the 215 rows with 1 bed and 3+ baths, 150 are typos, 29 are correct and 25 have the wrong bedroom count.
   - Of the 44 rows with 1 bed and 4+ baths, 39 are typos and none are correct.
   - 160 Riverside Blvd alone contributes 37 rows from one feed error.
   - The proposed rule (not merged) recodes baths when every other ad for the same unit says 1 bed with at most 2 full baths. It catches 83 listings, 82 of which a reading pass marked as typos.
   - The evidence is on thelio in `/data1/apartments/tmp/tz-diag/bath/`.
2. **Rebuilding T at the fitted values changes nothing,** so no fit is needed for it.
3. **Free 5% CPU NUTS checks.** Run one with the bath cells corrected and one with ν fixed near 20, to see which suspect holds the step down.
3. **Later:** amplitudes this large at 1 km mean the data want rougher surfaces than the prior expects. That favours a building effect, or a finer scale once sampling is solved.
