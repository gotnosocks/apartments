# Building zones with building features, 500 m surface: results

Run `building-zones-attrs-500m-b0-latest-9bd8c1a3-dense-w650`, fitted October 20, 2026, 8:58 to 9:08 PM ET on a Modal A100. Fit stage 576 s, $0.39. Fit-only. It has the same data, features and sampler settings as the 1 km fit (`building-zones-attrs-b0-latest-9bd8c1a3-dense-w650`). Only the surface lengthscale changed, from 1 km to 500 m.

Visual explainer: https://claude.ai/artifact/EqoGvZmqsixkJj7K3r2dyc
1 km report: [building-zones-attrs-1km-results-2026-10-21.md](building-zones-attrs-1km-results-2026-10-21.md)

## Summary

At 500 m the map adds a little detail in Manhattan and almost none outside it. The feature premiums and the predictions hold still. The finer map's intervals are about 1.7 times as wide, and both map amplitudes fall below the repo's convergence gate.

## Feature premiums, 500 m against 1 km

| Feature | 500 m | 1 km |
|---|---|---|
| Full-time doorman | +20.0% | +19.6% |
| Condo | +14.7% | +14.8% |
| Part-time doorman | +12.4% | +12.0% |
| Elevator | +8.9% | +9.1% |
| Virtual doorman | +4.5% | +4.4% |
| Elevator unknown | +1.8% | +1.7% |
| Roof height unknown | +0.6% | +0.2% |
| Roof height, per e-fold | -0.8% | -0.7% |

Every premium is within 0.41 points of its 1 km value, with R-hat at or below 1.003 and ESS above 1,500.

## Map and buildings

- **Map shape.**
  - The middle 90% of cells runs from -27% to +88% in Manhattan and from -36% to +17% in Brooklyn + Queens.
  - The peaks are +181% on the Hudson Square and West SoHo blocks and +69% in DUMBO. The lowest cells are -33% in East Harlem and -42% around Brownsville and Ocean Hill.
- **Against 1 km.**
  - The zones' overall levels match to within 0.006.
  - Among cells whose 500 m interval is narrower than 0.15, 10% of Manhattan cells move by more than 0.1, against 2% in Brooklyn + Queens.
  - The largest rises are about +0.2 in SoHo and NoHo. The largest drops, 0.15 to 0.19, are in parts of the West Village, the East Village and the Lower East Side.
- **Map certainty.**
  - The median 90% width is 0.107 against 0.060 in Manhattan, and 0.042 against 0.026 in Brooklyn + Queens.
  - The chain medians agree everywhere. The largest gap is 0.17 of a cell's interval.
- **Variance split, weighted by ads.**
  - The map's spread over buildings is 0.188 in Manhattan (0.183 at 1 km) and 0.167 in Brooklyn + Queens at both scales.
  - The leftover building sd is 0.176 in Manhattan (0.181 at 1 km) and 0.125 in Brooklyn + Queens (0.126).
  - The building share is 0.468 in Manhattan (0.494 at 1 km) and 0.361 in Brooklyn + Queens (0.363).
- **Building levels** differ from the 1 km fit by a typical 0.054 in Manhattan and 0.022 in Brooklyn + Queens. 14 buildings have disagreeing chains, all with 17 ads or fewer.
- **Map and building trade off.**
  - At 796 Sixth Avenue the map adds 59% (39% at 1 km), and the building's own level moves from +6% to -7%. The prediction moves by $1.
  - The two held-out examples get the same predictions to the dollar.
- **SoHo walk-ups** sit further under the finer map. For example, 26 Thompson St's map goes from +98% to +110%, and its own level from -49% to -52%.
- **Zone gap:** +29.9% (+30.1% at 1 km).
- **Noise:** ν 3.83; σ unchanged.

## Convergence

The run misses the gate on four quantities:
- amp[outer]: R-hat 1.024, ESS 303
- amp[manhattan]: R-hat 1.022, ESS 256
- beta[bed=2:full>=4]: R-hat 1.021, ESS 324
- τ: R-hat 1.014, ESS 679

The amplitude scales the waves' spectral weights, and those depend on the lengthscale. Its value is therefore not comparable across scales: it fell from 1.03 to 0.34 in Manhattan and from 0.38 to 0.18 in Brooklyn + Queens, while the map's spread grew slightly.

## Predictions

| | Prediction | Result | Score |
|---|---|---|---|
| B1 | Converges in the usual range, amplitudes slowest | max R-hat 1.024, min ESS 256, both amplitudes | hit |
| B2 | Runs 14 to 30 minutes | 9.6 min | miss |
| B3 | Building spread a little lower than 1 km | 0.220 (-0.008), 0.139 (-0.002) | hit |
| B4 | Building share falls in both zones | Manhattan -0.026, Brooklyn + Queens -0.002 | half |
| B5 | Amplitudes | 0.34, 0.18; I misread what the amplitude measures | miss |
| B6 | Feature premiums within half a point of 1 km | all within 0.41 | hit |
| B7 | Zone gap near 1 km's | +29.9% | hit |
| B8 | ν and noise scales hold | ν 3.83 | hit |

Without a held-out score, the fit gives no evidence that 500 m predicts better than 1 km. Since the predictions hardly change, a PSIS-LOO or held-out comparison would be the way to choose between them.
