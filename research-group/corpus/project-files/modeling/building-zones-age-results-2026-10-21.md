# Building zones with year built, alteration and retail: results

Run `building-zones-age-b0-latest-f023987f-dense-w1000`, fitted October 21, 2026 on Modal. Fit stage 13.3 min, about $0.54. Fit-only. 4 chains, 300 warmup and 1,000 sweeps each, every 5th kept (200 draws per chain). Model: PR #1194. Results note: PR #1195.

The design is the gym model (size, laundry, dishwasher, gym, building features, bath cap, 1 km surface) with truck route back in and three MapPLUTO columns added: year built in bands, alteration since 2000, and ground-floor retail. Comparisons are against `building-zones-gym-b0-latest-f2d01c92-dense-w650` unless noted.

Visual explainer: https://claude.ai/artifact/NqN1Mbun8GxgqjPhbxFVms
Data page: https://claude.ai/artifact/CaAoDoDPMjYrHqr6qUjosj

## Summary

Year built does not explain the truck discount. Truck route held at -3.9% (it was -4.2% without age), and the gap between truck-route buildings' own levels and their neighbors' fell only from 5.3 to 4.6 log points. In 2000 to 2009 buildings it widened. Year built and alteration earn their place: they score better on held-out ads, mainly in Brooklyn + Queens and in buildings with few training ads. Retail costs 1.9% but makes the unexplained part slightly larger. The run passes the convergence gate.

## Premiums

Posterior median with 90% interval. Year built is against 1900 to 1939.

| Column | Gym fit | This fit | 90% interval |
|---|---|---|---|
| Truck route | (out; -4.2% in the unit fit) | -3.9% | -4.6 to -3.3 |
| Retail | | -1.9% | -2.1 to -1.6 |
| Retail unknown | | -0.6% | |
| Built before 1900 | | +4.1% | 3.8 to 4.4 |
| Built 1940 to 1979 | | -0.8% | |
| Built 1980 to 1999 | | -1.7% | |
| Built 2000 to 2009 | | -1.7% | |
| Built 2010 on | | +4.0% | 3.6 to 4.5 |
| Year unknown | | +1.2% | |
| Altered since 2000 | | +3.8% | 3.7 to 4.0 |
| Gym | +7.6% | +6.8% | 6.3 to 7.4 |
| Full-time doorman | +14.1% | +15.6% | |
| Part-time doorman | +8.4% | +8.8% | |
| Virtual doorman | +3.3% | +2.8% | |
| Elevator | +6.7% | +6.8% | |
| Condo | +10.5% | +10.4% | |

Size, laundry and dishwasher moved by at most 0.06 points. The zone gap is 31.3%.

The era pattern is not monotone. Pre-1900 buildings ask more than 1900 to 1939 buildings, likely brownstones and cast-iron lofts. Postwar through 2009 asks slightly less, and 2010 on asks more.

## Is the truck discount newness?

If truck-route buildings looked nicer only because they are newer, naming year built would close the gap between their own levels and their neighbors' in the same 500 m cells. Ad-weighted gap in log points:

| Group | Buildings | Unit fit | This fit |
|---|---|---|---|
| All truck-route buildings | 1,292 | +5.3 | +4.6 |
| Built before 1900 | 257 | +2.7 | +3.0 |
| 1900 to 1939 | 687 | +1.3 | +0.8 |
| 1940 to 1979 | 60 | +8.2 | +6.6 |
| 1980 to 1999 | 43 | +7.6 | +5.7 |
| 2000 to 2009 | 109 | +5.4 | +5.8 |
| 2010 on | 127 | +1.9 | +1.3 |
| 1 to 5 units | 667 | +2.6 | +3.6 |
| 6 to 19 units | 315 | +2.1 | +2.1 |
| 20 to 99 units | 191 | +6.1 | +4.7 |
| 100+ units | 117 | +4.3 | +4.0 |

The gap persists within every era and every size band, so newness is not the cause. An unmeasured quality could still be correlated with truck routes, so a real -4% truck effect cannot be confirmed from this fit alone. Buildings with 1 to 4 ads show almost no gap (+1.8 against +1.6 for neighbors), because their own levels are shrunk to zero. That is where the truck column changes predictions.

Truck-route held-out ads moved by -0.06 points on average. Their held-out log score is +4.0 (SE 2.8) against the gym fit.

## Held out

Latest split: 189,649 ads, 68 draws per run. Log score is this fit minus the named fit.

| | Ads | vs gym fit | vs unit fit |
|---|---|---|---|
| All | 189,649 | +31.7 (SE 18.4) | +20.4 (SE 18.5) |
| Manhattan | 117,638 | -9.6 (SE 12.1) | -9.4 (SE 12.0) |
| Brooklyn + Queens | 72,011 | +41.4 (SE 13.9) | +29.7 (SE 14.0) |
| Gym buildings | 66,343 | +6.9 (SE 6.5) | |
| Other buildings | 123,306 | +24.9 (SE 17.2) | |
| Truck route | 8,854 | +4.0 (SE 2.8) | |
| Retail | 93,336 | -0.7 (SE 10.6) | |

RMSE is 0.11728 against 0.11732. The clearest single gain is in buildings built 2000 on with 1 to 4 training ads: +7.1 (SE 2.9). There year built carries information that the building's own level has not had the data to learn.

## Unexplained variance

T (map + building level + error, demeaned within zone) across the fits:

| Fit | T |
|---|---|
| Building features only | 0.0622 |
| + size, laundry, dishwasher, truck | 0.0530 |
| + gym, truck out | 0.0511 |
| + truck, year built, alteration, retail | 0.0509 |

Manhattan is 0.0528 and Brooklyn + Queens 0.0482.

Shapley rise in T if each group were removed, averaged over all orderings:

| Group | Rise |
|---|---|
| Size | 0.0079 |
| Laundry | 0.0037 |
| Gym | 0.0037 |
| Dishwasher | 0.0010 |
| Year built | 0.0009 |
| Altered since 2000 | 0.0005 |
| Truck route | -0.0003 |
| Retail | -0.0006 |

Truck route and retail come out negative. Their buildings' own levels move to cancel them, so removing either would lower T.

## Map and buildings

- Building spread: 0.184 in Manhattan (0.187 in the gym fit) and 0.114 in Brooklyn + Queens (0.117).
- Building share: 0.452 and 0.306.
- Map amplitude: 0.90 and 0.36.
- ν is 4.11.
- 1 building, with 6 ads, has disagreeing chains.

## Example predictions

| Ad | Ask | Gym fit | This fit |
|---|---|---|---|
| 796 Avenue of the Americas, 2 bed | $9,314 | $9,717 | $9,712 |
| 23 Eagle St, 1 bed, held out | $6,059 | $4,908 | $4,908 |
| 85 East End Ave, 1 bed, held out | $6,183 | $5,514 | $5,512 |

The NoMad building was built 2000 to 2009, altered since, and has retail. Gym adds 6.8%, alteration 3.8%, the era -1.7% and retail -1.9%. Its own level holds at +2.4%.

## Convergence

The run passes the strict gate. Max R-hat is 1.0044, on the income-restricted flag. Min ESS is 604, on the Brooklyn + Queens map amplitude that missed last time. The longer run fixed it. Nothing was reseeded.

## Predictions

| | Prediction | Result | Score |
|---|---|---|---|
| A1 | Truck between -3.5% and -1% | -3.9% | miss, barely shrank |
| A2 | Gym falls 1 to 3 points | 6.8%, a fall of 0.8 | miss, fell less |
| A3 | Era bands (see PR #1194) | +4.1, -0.8, -1.7, -1.7, +4.0 | hit on 1980-99 and 2010 on, miss on three |
| A4 | Altered 0% to +4% | +3.8% | hit |
| A5 | Retail -3% to +0.5% | -1.9% | hit |
| A6 | Doorman and elevator fall 0.5 to 3, unit columns under 0.5 | doorman rose 1.5, elevator flat, unit columns 0.06 | miss on doorman and elevator |
| A7 | T falls 0.001 to 0.004 | fell 0.0002 | miss |
| A8 | 2000-09 truck gap halves or more | +7.8 against +1.9 (was +6.4 against +1.0) | miss, widened slightly |
| A9 | Passes, about 14 min, $0.55 | R-hat 1.004, ESS 604, 13.3 min, $0.54 | hit |

## Recommendation

- Keep year built and alteration. They name part of the building levels and improve held-out scores where buildings have little data.
- The newness explanation for the truck discount is not supported. Whether truck route itself costs about 4% or marks something else about avenue buildings stays open. Its held-out score is mildly positive, and it is the only column here that changes predictions for buildings with few ads.
- Retail has a clear -1.9% premium but a negative Shapley and a flat held-out score. Dropping it is a candidate for a later test, which would need your go.
