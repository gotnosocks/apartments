# Building zones with a floor curve: results

Run `building-zones-floor`, fitted October 21, 2026, 6:40 to 6:59 PM ET on a Modal A100. 4 chains, 300 warmup and 1,000 sweeps each. Fit-only, $0.73. Model: PR #1196. Results note: PR #1197 (docs/notes/building-zones-floor-2026-10-21.md).

The design is the year built model (truck, gym, year built, alteration, retail, size, laundry, dishwasher, building features, 1 km surface) plus a unit floor term. Comparisons are against `building-zones-age-b0-latest-f023987f-dense-w1000`.

Visual explainer: https://claude.ai/artifact/1HnpNRK5AJqHXnD5udwHg3
Data page: https://claude.ai/artifact/FxkYoSW942AWctAVGrf1iF

## Summary

Floor is the largest gain since unit size. Held-out log score rose +2,945 (SE 83) and RMSE fell from 0.1172 to 0.1154. Almost all of the gain is in elevator buildings, where rent climbs with floor and climbs faster the higher you go. Walk-ups are nearly flat. Penthouses, which the year built model priced about 10% too low, are now priced within 0.3%. The run passes the convergence gate.

## Design

- **Two floor curves.** One for elevator buildings and one for walk-ups. Buildings with unknown elevator (0.7% of ads, median floor 2) go with walk-ups.
- **Gaussian process on log floor.** Each curve is an exact GP with a squared exponential kernel, pinned to 0 at floor 1, so neighboring floors share strength. Log floor lets a step near the ground matter more than the same step high up.
- **Caps.** Floors are capped at 47 in elevator buildings and 6 in walk-ups, about the 99th percentile of each group.
- **Flags on top of the curve, at the unit's own floor.** Top floor (one per group), penthouse, garden, basement or lower level, and floor unknown (one per group). Garden and lower-level units sit at floor 1 on the curve.
  - A 10th floor unit on its building's top floor is curve(10) plus the top-floor flag. A 10th floor unit in a taller building is curve(10) alone.
- **Top floor source.** MapPLUTO's floor count for 202,482 listings, and the highest floor seen in the building's ads for 8,552.
- **Sampler.** A simulated test before launch showed the elevator amplitude mixing poorly (ESS 58). The sampler now draws the lengthscale with the amplitude integrated out, then draws the amplitude exactly.
  - This needed an inverse gamma prior on amplitude squared, with a median amplitude of 0.15.
  - Each floor can vary on its own by a tenth of the amplitude.

## Floor curves

Elevator buildings, premium over floor 1:

| Floor | Premium |
|---|---|
| 2 | +1.2% |
| 5 | +2.1% |
| 10 | +3.8% |
| 20 | +6.7% |
| 30 | +10.0% |
| 40 | +13.8% |
| 47 and up | +19.5% |

Above floor 2, each doubling of the floor adds more than the one before: 0.3 points from 2 to 4, 1.6 from 4 to 8, 2.6 from 8 to 16 and 4.8 from 16 to 32. Nine pairs of neighboring floors dip, by at most 0.6 points.

Walk-ups: every floor rents slightly below floor 1, falling about 0.2 points per floor to -0.9% at floor 5. That may be a discount for the stairs.

GP hyperparameters:
- Elevator: amplitude 0.074, lengthscale 0.98 on log floor.
- Walk-up: amplitude 0.100, lengthscale 1.40, twice its prior median, with a wide interval.

## Flags

| Flag | Premium on top of the curve |
|---|---|
| Penthouse | +8.3% |
| Garden | +2.9% |
| Elevator top floor | +1.75% |
| Walk-up top floor | -0.3% |
| Lower level | -3.7% |
| Elevator, floor unknown | +4.0% (about the curve at floor 10) |
| Walk-up, floor unknown | -0.55% |

## Earlier terms

- Elevator fell from +6.8% to +3.6%. The floor curve now carries part of what having an elevator was worth, since elevator units sit higher.
- Bath steps for two or more full baths fell 0.5 to 1.9 points, since large units tend to be on higher floors.
- Every other column moved 0.6 points or less.

## Held out

Latest split, 189,649 ads.

| Group | elpd vs year built fit |
|---|---|
| All | +2,945 (SE 83) |
| Ads with a known floor | +3,107 (SE 80) |
| Elevator, floors 3 to 5 | +726 |
| Elevator, floors 10 to 19 | +643 |
| Top floors | +911 |
| Penthouses | +706 |
| Elevator, floor unknown | -202 (12 SE) |

For scale, the year built fit gained +32 over the gym fit.

- **Penthouses:** RMSE fell by a fifth and 90% coverage rose from 69% to 79%. The year built fit priced them a median 10.5% too low, and this fit misses by 0.3%.
- **Elevator ads with no floor:** one flag at +4.0% fits them slightly worse than before. A better fill for missing floors, or splitting that flag by building height, is worth a look.
- **Floors 40 and up:** the year built fit priced them 2.6% too low, and this fit prices them 3.3% too high. Merging every floor from 47 into the 90s into one column likely contributes.

## Unexplained variance

| Ads | Within-building variance | T |
|---|---|---|
| Known floor | -5.0% | -3.9% |
| Elevator, known floor | -6.8% | |
| Walk-up, known floor | about -1% | |

Building effects correlate 0.998 with the year built fit's, and the map 0.99998. Floor explains variation between units in the same building and leaves the building and map terms nearly untouched. That differs from the building columns tested earlier, which mostly took weight from building levels without changing predictions.

## Convergence

Passes the gate.
- Max R-hat is 1.0097 and min ESS is 590, both on the Brooklyn + Queens map amplitude.
- The four floor-curve hyperparameters have R-hat 1.001 or less and ESS above 3,600.
- The four chains' curve medians agree within 0.08 points at every floor.

## Predictions

17 of 23 hit. The misses:
- Floor 10 came in at +3.8%, below the predicted +4% to +12%.
- The walk-up curve peaks at floor 1, not floor 2 or 3.
- The walk-up lengthscale moved well off its prior.
- Lower level came in at -3.7%, short of the predicted -15% to -4%.
- The within-building error fell 4.9%, against the predicted 1% to 4%.
- The elevator curve has nine small dips, against a prediction of none.

## Recommendation

- Make this the new base model. It is the clearest held-out gain of any test today, and it explains rent differences between units in the same building, which the building terms cannot.
- Worth a later look: the elevator floor-unknown flag, and the cap at 47 for very tall buildings.
- Replacing the base needs your go. No other fit has started.
