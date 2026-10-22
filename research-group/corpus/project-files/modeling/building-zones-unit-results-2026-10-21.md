# Building zones with unit size, laundry, dishwasher and truck route: results

Run `building-zones-unit-b0-latest-a3aec3ff-dense-w650`, fitted October 21, 2026, 9:47 to 9:57 AM ET on Modal. Fit stage 9.9 min, about $0.41. Fit-only. Model change and predictions: PR #1190. Results note: PR #1191.

The base is the 1 km building-features model with the 2 bed bath cap (PR #1185) and no frontage columns. Every comparison below is against `building-zones-attrs-b0-latest-9bd8c1a3-dense-w650`.

Visual explainer: https://claude.ai/artifact/KFZg6XZxycCjW6GKrUhi3w
Data page: https://claude.ai/artifact/PvBs8AxoZmFCJZd58ynrig

## Summary

Unit size, laundry, dishwasher and truck route explain 15% of what the map, the building levels and the error carried together. Their combined variance fell from 0.0622 to 0.0530. Most of the drop came from the building levels. Size took over part of what the bath steps and the loft-district map had carried. The run passes the repo's strict convergence gate.

## New columns

- **Size:** log(size / median size for the bedroom count), centred. A unit-level column.
  - The size comes from the ad first, then from other listings of the same unit, then from the same line on other floors.
  - The same-line fill skips penthouse, garden and basement labels and the top two floors.
  - Coverage of training ads after each layer: 26.2%, 39.1%, 45.0%.
  - Filled sizes carry a size-imputed flag. Ads with no size get a size-unknown flag and a size term of 0.
- **Laundry:** in unit and in building, each against ads that don't mention laundry. Unit level.
- **Dishwasher:** stated on the ad. Unit level.
- **Through truck route:** the building fronts the city's through truck route network. Building level.

## Premiums

Posterior median with 90% interval.

| Column | Premium | 90% interval |
|---|---|---|
| Size, per unit of log ratio | +28.6% | 28.4 to 28.8 |
| Size, per 10% above the bedroom median | +2.4% | |
| Size unknown | -3.9% | -3.9 to -3.8 |
| Size filled in | -0.6% | -0.7 to -0.6 |
| Laundry in unit | +6.5% | 6.4 to 6.6 |
| Laundry in building | +1.7% | 1.6 to 1.7 |
| Dishwasher | +2.1% | 2.0 to 2.1 |
| Through truck route | -4.2% | -5.0 to -3.5 |

New coefficients have R-hat 1.006 or less and ESS 1,061 to 2,272.

Ads with no size sit 10 log points below ads that state one, but only 0.9 points below within the same building. The unknown flag takes up the gap between buildings, so the size slope comes from units compared within a building.

## Earlier terms

| Term | Before | After |
|---|---|---|
| Full-time doorman | +19.6% | +17.2% |
| Condo | +14.8% | +10.9% |
| Part-time doorman | +12.0% | +11.1% |
| Elevator | +9.1% | +8.0% |
| Virtual doorman | +4.4% | +3.9% |
| Studio, 2nd bath | +44.3% | +30.7% |
| 1 bed, 2nd bath | +24.6% | +18.9% |
| 2 bed, 2nd bath | +23.5% | +20.0% |
| 2 bed, 3rd bath | +34.4% | +26.1% |
| Half bath | +14.3% | +11.3% |
| 2nd bedroom | +20.0% | +21.5% |

The common bath steps fell by 3 to 14 points because they had been carrying part of the size difference between units with the same bedroom count. Two rare steps rose: a 1 bed with 3 full baths by 2.9 points (155 rows), and a studio with 4 full baths by 13 points (14 rows). The 3 bed second bath fell only 2.6 points. Bedroom steps moved by at most 1.5 points. The zone gap stayed at 30%.

## What is still unexplained

T is the error plus the building level plus the map value, with each zone's level removed, across 1.71 million training ads.

| | Before | After | Change |
|---|---|---|---|
| All ads | 0.0622 | 0.0530 | -15% |
| Manhattan | 0.0662 | 0.0551 | -17% |
| Brooklyn + Queens | 0.0566 | 0.0500 | -12% |
| Map part | 0.0310 | 0.0266 | -14% |
| Building part | 0.0252 | 0.0183 | -27% |
| Error part | 0.0165 | 0.0150 | -9% |

The parts overlap, so they add to more than the total.

## Map and buildings

- Building spread fell from 0.228 to 0.189 in Manhattan and from 0.141 to 0.117 in Brooklyn + Queens.
- Building share of location variance fell from 0.494 to 0.463 and from 0.363 to 0.318.
- Map amplitude fell from 1.03 to 0.90 in Manhattan. In Brooklyn + Queens it rose slightly, from 0.379 to 0.385.
- The map fell most in the loft districts, where units run large for their bedroom count:
  - Tribeca -0.084
  - SoHo -0.062
  - Flatiron -0.047
  - Hudson Square -0.046
  - NoMad -0.037
  - DUMBO -0.036
- It rose in Chinatown (+0.025) and Two Bridges (+0.023).
- The typical ad's map moved 0.019.
- ν rose from 3.83 to 4.11. The error sigmas fell by 0.001 to 0.002.
- 9 buildings have disagreeing chains, all with 12 ads or fewer.

## Pair gaps

RMS gap in building level between buildings 100 to 200 m apart. Both fits use the same 300,000 pairs.

| Between the pair | Pairs | Before | After |
|---|---|---|---|
| No street | 11,420 | 0.202 | 0.168 |
| Street 40 ft or less | 136,104 | 0.212 | 0.176 |
| Same, across a neighbourhood line | 8,585 | 0.227 | 0.186 |
| Street 41 to 70 ft | 45,452 | 0.230 | 0.191 |
| Same, across a neighbourhood line | 11,489 | 0.262 | 0.217 |

Every row fell by 15% to 22%. The extra gap across a 41 to 70 ft street, against a narrow one, went from 0.028 to 0.023, so most of it remains.

## Example predictions

| Ad | Ask | Before | After, with 90% interval |
|---|---|---|---|
| 796 Avenue of the Americas, 2 bed (in training) | $9,314 | $9,472 | $9,716 ($8,214 to $11,650) |
| 23 Eagle St, Greenpoint, 1 bed (held out) | $6,059 | $5,199 | $4,908 ($4,110 to $5,796) |
| 85 East End Ave, 1 bed (held out) | $6,183 | $5,385 | $5,513 ($4,661 to $6,539) |

The Greenpoint ad states no size, so it takes the -3.9% flag. Its ask now sits above the 90% interval.

## Convergence

The run passes the strict gate.
- Max R-hat is 1.0078, on Manhattan's building spread. The next highest is 1.0071, on the 2 bed 3 bath step.
- Min ESS is 456, on the Brooklyn + Queens map amplitude. The next lowest is 636, on the studio 4 bath step.

## Predictions

| | Prediction | Result | Score |
|---|---|---|---|
| U1 | Converges, slowest on a bath step | max R-hat 1.0078, min ESS 456 on the outer amplitude | partial |
| U2 | Fit 8 to 12 min, $0.33 to $0.50 | 9.9 min, $0.41 | hit |
| U3 | Size slope 0.35 to 0.60 | 0.252 | miss |
| U4 | Size unknown -2% to +1%, imputed within 1.5% | -3.9%, -0.6% | miss on unknown |
| U5 | Laundry in unit +5% to +10%, in building 0% to +4% | +6.5%, +1.7% | hit |
| U6 | Dishwasher +1% to +4% | +2.1% | hit |
| U7 | Truck route -4% to -0.5% | -4.2% | miss, just beyond |
| U8 | Earlier premiums within 2 points, condo and doorman likeliest to fall | condo -3.9, full-time doorman -2.4 | partial |
| U9 | Spread falls 0.010 to 0.030 and 0.005 to 0.020, amplitudes fall slightly | -0.039, -0.023; Manhattan amplitude -0.13 | miss |
| U10 | ν within 0.1 of 3.83 | 4.11 | miss |
| U11 | T variance 0.050 to 0.057 | 0.0530 | hit |
| U12 | Pair gaps fall to 0.215 to 0.228 and 0.190 to 0.200 | 0.191, 0.168 | miss |

Most misses came from underestimating how much of the building and map spread was unit size.

## What this leaves

- Reading the floor plans could raise size coverage from 45% to about 55%.
- The screen's other strong fields, gym, year built and floor, are the next candidates.
- The extra gap across avenues is still about 0.023.
