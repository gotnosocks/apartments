# Building zones with building features, 1 km surface: results

Run `building-zones-attrs-b0-latest-9bd8c1a3-dense-w650`, fitted October 20, 2026, 8:48 to 8:57 PM ET on a Modal A100. Fit stage 535 s, about $0.37. Fit-only (no PSIS-LOO, no held-out scoring). Model change and predictions: PR #1182.

Visual explainer: https://claude.ai/artifact/G3KAZmnBb2gzPVMn6WnbSC

## Setup

- Data: the bath-fixed NYC rows, Manhattan and Brooklyn + Queens (1.71 million training ads, 67,977 buildings). New Jersey is out, since it has no footprints or condo data.
- Model: the building-zones model (weekly market walk, season, unit steps, zone level plus a 1 km HSGP surface per zone, a level for each building, Student-t noise). Each building's level is now centred on its map plus x'γ, with these columns:
  - log roof height from the building footprints, centred at 78 ft, plus a height-unknown flag
  - elevator, plus an elevator-unknown flag
  - condo
  - doorman: full time, part time, virtual
- Sampler: blocked Gibbs, 4 chains, 150 warmup and 650 kept sweeps.

## Feature premiums

Posterior median with 90% interval, as percent on asking rent for the same unit at the same spot.

| Feature | Premium | 90% interval | R-hat | ESS |
|---|---|---|---|---|
| Full-time doorman | +19.6% | 18.7 to 20.6 | 1.001 | 1,773 |
| Condo | +14.8% | 14.3 to 15.3 | 1.000 | 1,993 |
| Part-time doorman | +12.0% | 11.1 to 12.9 | 0.999 | 2,396 |
| Elevator | +9.1% | 8.7 to 9.4 | 1.000 | 2,364 |
| Virtual doorman | +4.4% | 4.1 to 4.7 | 1.000 | 1,903 |
| Elevator unknown | +1.7% | 1.1 to 2.3 | 1.002 | 1,486 |
| Roof height unknown | +0.2% | -0.5 to +1.0 | 0.999 | 2,493 |
| Roof height, per e-fold | -0.7% | -1.1 to -0.4 | 1.000 | 2,047 |

The four chains' medians agree to within 0.2 points on every premium.

## What changed against the last run (no features, `building-zones-gibbs-b0-latest-f1cd5984-dense-w650`)

- **Building spread.**
  - Realised sd of the building levels, weighted by ads, fell from 0.229 to 0.181 in Manhattan and from 0.149 to 0.126 in Brooklyn + Queens. That is about 38% and 28% of the building-to-building variance moving into the features.
  - Building share of location variance fell from 0.56 to 0.49 (Manhattan) and from 0.40 to 0.36 (Brooklyn + Queens).
  - Manhattan buildings more than 0.25 from their expected level: 21%, down from 28%.
- **Feature premium per building, weighted by ads.** The median is +13% in Manhattan and +5% in Brooklyn + Queens. About a third of Manhattan's ads and 40% of Brooklyn + Queens ads sit in buildings with no feature premium.
- **Map.**
  - Amplitudes fell from 1.10 to 1.03 (Manhattan) and from 0.48 to 0.38 (Brooklyn + Queens).
  - With each zone's overall shift taken out (Manhattan -0.05, Brooklyn + Queens +0.03), the map fell by 0.13 to 0.17 on the log scale where the feature-rich towers stand, and rose about 0.1 in East Harlem and the East Village. The largest drops sit on waterfront edges where the map's 90% interval is 0.2 to 0.3 wide.
  - In Manhattan, ads in cells whose map fell more than 0.1 sit in buildings whose features add +32% on average. Ads in cells whose map rose get +10%.
- **Zone gap.** Manhattan's map averages 30.1% above Brooklyn + Queens (29.6 to 30.6), down from 37.3%.
- **Unit steps** barely move: the 2 bed second bath is +23.5% (last run +22.9%), and the half bath is +14.3%.
- **Noise:** ν 3.83; σ 0.086 to 0.103 by bedroom band.

## Convergence

The run misses the repo's strict gate on the same sparse step as the last run: beta[bed=2:full>=4], with R-hat 1.021 and ESS 325. τ has R-hat 1.015 and ESS 654. Map chain medians differ by at most 0.18 of a cell's 90% interval. 18 buildings have chain medians that differ by more than a quarter of their 90% interval, all with 17 ads or fewer.

## Predictions

| | Prediction | Result | Score |
|---|---|---|---|
| A1 | Convergence in the usual range | max R-hat 1.021, min ESS 325 | hit |
| A2 | Time and cost | 535 s, $0.37 | hit |
| A3 | Roof height +4% to +11% per e-fold | -0.7% | miss |
| A4 | Elevator | +9.1% | hit |
| A5 | Condo +2% to +7% | +14.8% | miss |
| A6 | Doorman levels | +19.6%, +12.0%, +4.4%, all above range | miss |
| A7 | Building spread falls | 0.228 Manhattan, 0.141 Brooklyn + Queens | hit |
| A8 | Building share falls | 0.494, 0.363 | hit |
| A9 | 2 bed second bath | +23.5%, at the top edge | hit |
| A10 | Zone gap falls below 37.3% | +30.1% | hit |
| A11 | ν and noise scales hold | ν 3.83 | hit |

I expected the map to absorb part of the earlier no-map fit's premiums (`building-attrs-b0-latest-041e6aa9-dense-w1500`: elevator +12.2%, condo +5.9%, doorman +6.7% / +9.4% / -1.8%). Instead condo and doorman came out larger. I have not checked why. That fit's noise model was much heavier (ν 6.85, σ 0.165 to 0.26), so its coefficients are not directly comparable. Roof height turns slightly negative once elevator and doorman are in; tall buildings' premium is carried by those two.

## Open questions

- Why condo and doorman rose against the no-map fit.
- Whether the doorman "not stated" group mixes buildings without doormen with ads that leave it out.
- The 500 m surface run with the same features and data (`building-zones-attrs-500m`) is running; its report will compare against this one.
