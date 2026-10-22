# Building zones with a gym column, truck route removed: results

Run `building-zones-gym-b0-latest-f2d01c92-dense-w650`, fitted October 21, 2026, 12:14 to 12:24 PM ET on Modal. Fit stage 557 s, about $0.38. Fit-only. Model: PR #1192. Results note: PR #1193.

The design is the unit features model (size, laundry, dishwasher, building features, bath cap, 1 km surface) with the truck route column removed and a building gym column added. Comparisons are against `building-zones-unit-b0-latest-a3aec3ff-dense-w650` unless noted.

Visual explainer: https://claude.ai/artifact/TDXi9ALx3i7ji4TFopJEqa
Data page: https://claude.ai/artifact/Mj7DNLFMQzus4fYcXehbqs

## Summary

A building with a gym asks 7.6% more in this fit. That premium came out of the doorman, elevator and condo columns and the buildings' own levels, and predictions did not change. On held-out ads the fit with gym scores the same as the fit without it. The run narrowly misses the convergence gate on one quantity. Because the goal is to tie rent to measured qualities, and gym moves about 4 points of the building gap into a named amenity at no cost to prediction, I recommend adding gym to the master model.

## Gym column

- A building has a gym when at least half of its ads that list amenities include a gym.
- 31.7% of training ads sit in gym buildings (4,302 buildings), and 0.5% sit in buildings with no amenities listed, counted as no gym.
- 98% of ads in gym buildings also have an elevator. 42% have a full-time doorman, against 7% in other buildings.

## Premiums

| Term | Without gym | With gym |
|---|---|---|
| Gym | | +7.6% (7.1 to 8.2) |
| Full-time doorman | +17.2% | +14.1% |
| Part-time doorman | +11.1% | +8.4% |
| Elevator | +8.0% | +6.7% |
| Condo | +10.9% | +10.5% |
| Virtual doorman | +3.9% | +3.3% |
| Roof height, per e-fold | -0.4% | -0.7% |

Size, laundry and dishwasher moved by at most 0.03 points. Bed and bath steps, σ and ν are unchanged. The zone gap is 30.2%.

## Where the gym premium came from

Average change in log points against the fit without gym, weighted by ads:

| | Building columns | Building's own level | Map | Net |
|---|---|---|---|---|
| Ads in gym buildings | +4.1 | -3.4 | -0.4 | +0.3 |
| Ads in other buildings | -0.6 | +0.7 | +0.2 | +0.3 |

Both groups shift by the same 0.3 points, which is a common shift in the market level. Relative to other ads, the gym changed nothing.

## Held out

Latest split: 189,649 ads, 68 draws per run.

| | Building features only | + size, laundry, dishwasher | + gym |
|---|---|---|---|
| RMSE, all | 0.1244 | 0.1173 | 0.1173 |
| RMSE, gym buildings | 0.1222 | 0.1139 | 0.1139 |
| RMSE, other buildings | 0.1255 | 0.1191 | 0.1191 |
| 90% coverage | 0.879 | 0.882 | 0.882 |

The gym fit's log score is -11 (SE 3) against the fit without gym, and +9,807 (SE 162) against building features alone. Mean bias in gym buildings is -0.92%, against -0.90% without gym.

## Unexplained variance

T (map + building level + error) fell from 0.0530 to 0.0511. Manhattan is 0.0531 and Brooklyn + Queens 0.0483. Any building column takes variation out of the buildings' own levels, so T falls even when predictions do not change. The held-out score is the better guide for what goes in the master model.

Gym's Shapley rise in T is 0.0041. The building-level screen explains 1.1% of the building effects in the run without gym, which beats the permutation null but is small.

## Truck route removal

Removing truck route changed predictions on truck-route ads by +0.04 points on average, on both training and held-out ads. Their building levels fell 5.1 points, giving back the rise that had cancelled the old term.

## Map and buildings

- Building spread: 0.187 in Manhattan (0.189 without gym) and 0.117 in Brooklyn + Queens.
- Building share: 0.439 and 0.310.
- Map amplitude: 0.95 and 0.38.
- 7 buildings have disagreeing chains, all with 12 ads or fewer.

## Example predictions

| Ad | Ask | Without gym | With gym |
|---|---|---|---|
| 796 Avenue of the Americas, 2 bed | $9,314 | $9,716 | $9,717 |
| 23 Eagle St, 1 bed, held out | $6,059 | $4,908 | $4,908 |
| 85 East End Ave, 1 bed, held out | $6,183 | $5,513 | $5,514 |

## Convergence

The run misses the strict gate on one quantity: the Brooklyn + Queens map amplitude, with R-hat 1.015 and ESS 415. Its four chain medians are 0.371, 0.375, 0.379 and 0.381. It was already the slowest quantity in the run without gym (ESS 456). Every premium passes, and the gym premium's chain medians run from 7.60% to 7.68%. Nothing was reseeded.

## Predictions

| | Prediction | Result | Score |
|---|---|---|---|
| G1 | Gym +1% to +5% | +7.6% | miss, high |
| G2 | Doorman, elevator and condo fall | full-time doorman -3.1, part-time -2.7, elevator -1.3, condo -0.4 | hit |
| G3 | Size, laundry, dishwasher steady | under 0.03 points | hit |
| G4 | Truck-route predictions unchanged | +0.04 points | hit |
| G5 | T falls by under 0.001 | -0.0019 | miss |
| G6 | Screen explains 5% to 15% | 1.1% | miss |
| G7 | Held-out elpd 0 to +1,500, RMSE steady | -11, RMSE steady | miss on elpd |
| G8 | Converges | R-hat 1.015 on the outer amplitude | miss |

## Recommendation

- Add gym to the master model. The goal is to explain rent with measured qualities, and held-out prediction is a check that nothing got worse.
  - Gym buildings' own levels fell from +6.1% to +3.3%, and other buildings' rose from -2.8% to -1.5%, so about 4 points of the gap now sits in a named amenity.
  - The shift away from doorman, elevator and condo is expected, since those features co-occur with gyms. The intervals stay narrow, so the data separates them.
  - The held-out score is unchanged, which is what a correct explanatory feature should show when building levels already absorbed its effect.
- Truck route stays out. There the buildings' own levels moved to cancel the column, so it explained nothing. (Superseded: the year built fit put truck back in, where it held at -3.9%. See building-zones-age-results-2026-10-21.md.)
- The master model is size, laundry, dishwasher and gym on the building-features base, with no truck route. Serving it needs one fit of that design.
- The Brooklyn + Queens map amplitude has been the slowest quantity in both recent runs. It may need a longer run or a look at its data before the master fit.
