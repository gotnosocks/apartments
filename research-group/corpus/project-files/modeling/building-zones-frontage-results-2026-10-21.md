# Building zones with street frontage, 1 km surface: results

Run `building-zones-front-b0-latest-9652d249-dense-w650`, fitted October 20, 2026, 11:39 to 11:50 PM ET on a Modal A100. Fit stage 9.6 min, $0.41. Fit-only. The run uses the same data and sampler settings as the 1 km building-features run (`building-zones-attrs-b0-latest-9bd8c1a3-dense-w650`). It includes the 2 bed bath cap (PR #1185), and the model went in through PR #1186.

Visual explainer: https://claude.ai/artifact/9bzEXWfAgjhsFcpTD6H7mT

## Summary

Within the same spot on the map, buildings on wider streets ask about 2 to 3% less, and corner lots 0.7% less. Frontage does not explain the jumps in building level across avenues: the gap between neighbours across a 41 to 70 ft street is unchanged at 0.230. The run passes the repo's strict convergence gate.

## Frontage columns

- **Width:** the widest street a building fronts, curb to curb, from the city's street centerlines. The roadways of a divided street that share a name are summed. The search reaches 20 m plus half the roadway width from the building footprint. That 20 m is search distance only and is never added to a width.
- **Bands:** against 40 ft or less, the bands are 41 to 60 ft, 61 to 80 ft and over 80 ft, plus a width-unknown flag. I used bands because widths cluster at 30 to 34 ft side streets and 56 to 84 ft avenues.
- **Corner:** taken from PLUTO's lot type. Street geometry is used only for lot type 0. There is also a corner-unknown flag.
- **Coverage:** width is known for 96% of training rows and corner for 99.4%.
- **Share of ads by band:**

| | 40 ft or less | 41 to 60 ft | 61 to 80 ft | Over 80 ft | Unknown |
|---|---|---|---|---|---|
| Manhattan | 51% | 24% | 20% | 2% | 3% |
| Brooklyn + Queens | 74% | 16% | 3% | 2% | 5% |

## Premiums

Posterior median with 90% interval.

| Column | Premium | 90% interval |
|---|---|---|
| Street 41 to 60 ft | -2.07% | -2.40 to -1.74 |
| Street 61 to 80 ft | -2.78% | -3.44 to -2.12 |
| Street over 80 ft | -0.29% | -1.38 to +0.91 |
| Width unknown | -2.12% | -3.53 to -0.61 |
| Corner | -0.69% | -1.05 to -0.32 |
| Corner unknown | +0.16% | -2.14 to +2.47 |

Every frontage term has R-hat of 1.002 or less and ESS of 1,930 or more.

The other features each moved by less than 1.5 points:

| Feature | Premium |
|---|---|
| Full-time doorman | +20.2% |
| Condo | +14.6% |
| Part-time doorman | +12.2% |
| Elevator | +9.2% |
| Virtual doorman | +4.5% |
| Roof height | -0.4% per e-fold |

### Why the signs are negative

Wide streets run through expensive areas, and the map already sits high along them. Averaged across a zone, buildings on avenues ask more. Compared with neighbours on the same patch of map, they ask a little less. That fits noise and traffic, but I haven't tested that reading.

### A lead I haven't checked

Weighted by ads, Manhattan's leftover building levels still differ by width band after the fit:
- side streets: -6%
- 41 to 60 ft: -1%
- 61 to 80 ft: +4%

Brooklyn + Queens is flat. The frontage terms are shared across zones and fitted building by building, so a separate frontage term for each zone may fit Manhattan better.

## The pair-gap test

The table shows the rms gap in leftover building level between pairs of buildings 100 to 200 m apart, using the same 300,000 pairs in both fits.

| Between the pair | Pairs | Before | After |
|---|---|---|---|
| No street | 11,420 | 0.202 | 0.202 |
| Street 40 ft or less | 136,104 | 0.212 | 0.212 |
| Same, across a neighbourhood line | 8,585 | 0.227 | 0.227 |
| Street 41 to 70 ft | 45,452 | 0.230 | 0.230 |
| Same, across a neighbourhood line | 11,489 | 0.262 | 0.263 |

The frontage premiums are about 0.02 on the log scale, against a gap of 0.23, and both buildings of a pair often sit in the same band. Whatever makes rents jump across avenues is not the building's own frontage.

## Rest of the model

- Building spread: 0.229 in Manhattan, 0.140 in Brooklyn + Queens. Both are unchanged.
- Building share of location variance: 0.50 and 0.36.
- The map moved by at most 0.036 on the log scale against the 1 km fit.
- Zone gap: +30.5%.
- ν: 3.83. σ is unchanged.
- The NoMad example's prediction moved from $9,472 to $9,469.
- 14 buildings have disagreeing chains, all with 17 ads or fewer.

## Convergence

The run passes the strict gate. The max R-hat is 1.0077, on the studio second bath step. The min ESS is 442, on the studio 4-bath step.

## Predictions

| Prediction | Result | Score |
|---|---|---|
| Cost under the cap | 9.6 min, $0.41 | hit |
| Converges, min ESS at least 450 | 442 | near miss |
| Street 41 to 60 ft positive | -2.1% | miss |
| Street 61 to 80 ft positive | -2.8% | miss |
| Width unknown near zero or positive | -2.1% | miss |
| Corner positive | -0.7% | miss |
| Earlier features stay in range | under 1.5 points | hit |
| ν, σ and zone gap hold | ν 3.83, gap 30.5% | hit |
| Pair gap across 41 to 70 ft streets shrinks from 0.230 | 0.230 | miss |

## Known flaw

A building that faces no street and has lot type 0 or no lot type gets "not a corner" from geometry, where it should get unknown. Few rows are affected.

## What this leaves

The block-level step from the earlier plan is the natural next test. It would add a tax-block level between the map and the buildings, and measure how much variance sits at the street-bounded scale. If that stays well above the random-cell null, a kernel that cuts correlation across wide streets is worth building.
