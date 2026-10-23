# Kitchen sink fit (a): results, 2026-10-23

Fit (a) is `building-zones-kitchen-sink` at a12cd507, run `building-zones-kitchen-sink-b0-latest-a12cd507-ks-jointamp-w1000`. It ran fit-only on a Modal A100-40GB with the launch line in `docs/handoff/kitchen-sink.md`, on the dataset, split and seed of fit 8. The predictions are in `kitchen-sink-predictions-2026-10-23.md`. Fit (b), the 150 m twin, waits on the limiter, and I will add it here when it lands.

The design has 250 columns on 1,706,824 training ads: fit 8's 130, then 38 `ad:` columns, 25 building amenity columns (with `bld:amenities_unstated`), 12 lot columns and 45 unit means. Every aggregate over a building's or a unit's ads reads only the row's own ad and earlier training ads.

## Convergence

It passes the repo's checks. The worst quantity on both is `beta[bed=0:full>=3]`, a studio with three full baths (38 training rows): R-hat 1.0065 and ESS 537. Sampling took 1,566 s and the whole fit stage 2,187 s, at $1.57.

## Held-out ads, latest split

I scored the 189,647 held-out ads of the latest split from 400 kept draws in a Modal CPU container (`kitchen-sink-2026-10-23/modal_score.py`, which runs `docs/notes/conference-followups-2026-10-22/score.py`), since the kitchen sink's design doesn't fit in thelio's memory. Every run below shares all 189,647 ads.

| run | elpd | RMSE | coverage 50/80/90/95 |
|---|---|---|---|
| fit 8 | 148,234 | 0.1158 | 0.493, 0.798, 0.903, 0.954 |
| kitchen sink (a) | 156,105 | 0.1112 | 0.495, 0.801, 0.904, 0.955 |
| fit 4 (unit effects) | 177,137 | 0.1018 | 0.496, 0.789, 0.893, 0.949 |

Paired on the shared ads (`compare.py`):

| comparison | elpd change | SE by row | by building | two-way |
|---|---|---|---|---|
| kitchen sink over fit 8 | +7,871 | 140 | 228 | 322 |
| kitchen sink over fit 4 | -21,032 | 309 | 527 | 851 |

The kitchen sink beats fit 8 by about 24 two-way SE, and the intervals keep their coverage. Fit 4 beats it by about 25 SE. Every held-out ad on this split is the latest ad of a unit with training rows, so fit 4's unit effects carry each unit's own earlier rents, and the kitchen sink has only the unit means of ad labels.

## Variance shares

I split each draw's fitted log rent over the 1,706,824 training ads into its terms and gave each term Cov(term, fitted) / (Var(fitted) + Var(residual)), as `rentfrontier.variance` does, from 100 kept draws of each chain (`kitchen-sink-2026-10-23/shares.py`, run in a Modal CPU container by `modal_score.py` beside it). Medians with 90% intervals:

| term | fit 8 | kitchen sink |
|---|---|---|
| the columns (`features`) | 52.0% (51.8 to 52.3) | 53.5% (53.3 to 53.7) |
| the walk and season (`time`) | 11.5% (11.5 to 11.5) | 11.1% (11.1 to 11.1) |
| the neighborhood surface | 17.8% (17.6 to 18.0) | 17.3% (17.2 to 17.5) |
| the building levels (descriptive) | 10.7% (10.5 to 10.9) | 10.6% (10.3 to 10.8) |
| residual | 8.0% (8.0 to 8.0) | 7.5% (7.5 to 7.5) |

The columns' share rises by 1.5 points, about half a point each from the residual, the surface and the walk. The descriptive share, the building levels', barely moves (10.7% to 10.6%), though `bld_sd` fell 12% in Manhattan. The share counts each term's covariance with the fitted rent, so a narrower spread of building levels can keep nearly the same share.

## Scales

| quantity | fit 8 | kitchen sink | change |
|---|---|---|---|
| `sigma`, groups 0 to 3 | 0.0834, 0.0820, 0.0882, 0.1011 | 0.0808, 0.0791, 0.0851, 0.0979 | -3.1% to -3.5% |
| `bld_sd`, Manhattan and outer | 0.185, 0.114 | 0.162, 0.107 | -12%, -6% |
| `amp`, Manhattan and outer | 0.901, 0.370 | 0.763, 0.369 | -15%, 0% |
| `zone_sd`, Manhattan and outer | 0.198, 0.161 | 0.181, 0.156 | -9%, -3% |
| `gp_amp` (floor curves) | 0.0715, 0.0996 | 0.0671, 0.0996 | |
| `nu` | 4.10 | 4.10 | |

The new columns take about an eighth of the Manhattan building levels' spread and a seventh of the Manhattan surface amplitude. The outer-borough surface keeps all of its amplitude.

## Coefficients

Coefficients are in log points ×100 (about percent), as posterior medians with 90% intervals over all kept draws. The chain spread of each median is under 0.4 points everywhere but `bed=0:full>=3` (0.71). `/data1/apartments/tmp/kitchen-sink/coefs.py` prints them all; I list the ones that move or matter.

### Rebuilt building columns

I rebuilt fit 8's elevator, doorman and gym from the row's ad and earlier training ads. That changed the elevator on 36,671 training ads, the full doorman on 30,957, the part-time doorman on 43,988, the virtual doorman on 92,875 and the gym on 13,885.

| column | fit 8 | kitchen sink |
|---|---|---|
| `bld:doorman_full` | 14.04 | 1.25 (1.08 to 1.42) |
| `bld:doorman_part` | 8.11 | 1.06 (0.91 to 1.21) |
| `bld:doorman_virtual` | 2.86 | 0.62 (0.53 to 0.70) |
| `bld:elevator` | 3.54 | -1.47 (-1.63 to -1.31) |
| `bld:gym` | 6.33 | 1.69 (1.51 to 1.88) |
| `bld:log_height` | -0.95 | 4.64 (4.27 to 4.97) |
| `bld:condo` | 10.02 | 12.90 (12.42 to 13.39) |

In fit 8 these labels hold one value for each building, so the building levels and the label share the difference between buildings, and the label takes most of it. Once I rebuild them as of each ad, a building's label switches on partway through its ads, at the first ad that lists a doorman. The building level absorbs the building's lasting premium, and the coefficient comes to rest on the change from one ad to the next, inside one building. That change is mostly a broker starting to list the doorman, so the rent barely moves with it. Most of the collapse probably comes from this change in what identifies the coefficient. Some may come from the new building columns (D class, condo, height, unit count, amenities), which describe the same buildings. The fit alone can't separate the two. A fit with the as-of labels and none of the new building columns would.

The served model's labels are fit 8's, so none of this changes the site.

### Unit columns, within and between units

With a past-only unit mean beside it, a column's coefficient is the rent change from the unit's earlier ads, and its sum with the unit mean's is the difference between units. I take the medians of the within and between draws; the between intervals are under 0.4 points wide.

| column | within | between | within / between | fit 4 within, between |
|---|---|---|---|---|
| `unit:log_size_rel` | 12.64 | 28.75 | 0.44 | 4.27, 31.63 |
| `ad:log_size_rel_sq` | 7.59 | 26.98 | 0.28 | |
| `unit:laundry_in_unit` | 3.67 | 6.34 | 0.58 | 2.09, 8.46 |
| `unit:laundry_in_building` | 0.77 | 1.74 | 0.44 | 0.74, 2.56 |
| `unit:dishwasher` | 1.40 | 2.16 | 0.65 | 0.58, 2.90 |
| `flag:rent_stabilized` | -0.99 | -2.70 | 0.37 | -1.33, -3.54 |

The within shares run larger than fit 4's. Fit 4's unit means average over all of a unit's training ads, and its unit effects soak up each unit's level. Here a unit's first ad is its own mean, so the within coefficient gets nothing from first ads, and later ads compare the row only with what came before it.

### New columns

Ad columns, from each ad's own record:

| column | median (90%) |
|---|---|
| `ad:months_free` (per month) | -5.68 (-5.75 to -5.61) |
| `ad:lease_short` | -3.18 (-3.96 to -2.39) |
| `ad:lease_long` | 2.08 (1.90 to 2.28) |
| `ad:private_outdoor_private_roof_deck` | 2.58 (2.33 to 2.82) |
| `ad:tour3d` | -1.54 (-1.82 to -1.26) |
| `ad:source_feed` | 1.18 (1.09 to 1.27) |
| `ad:pets_not_allowed` | -0.91 (-1.07 to -0.75) |
| `ad:log1p_photos` | -0.55 (-0.60 to -0.51) |
| `ad:floorplan` | 0.28 (0.19 to 0.36) |

The months free come out at about 5.7% of the ask per month free. A net effective rent over 12 months would give 8.3%, so the asks partly price the concession in. The other ad columns sit within 3 points of zero.

Building amenity columns, as of the ad: shared garden 6.38, children's playroom 2.41, wheelchair access 2.06, pool 1.63, locker cage 1.47, shared outdoor space 1.26, hot tub 1.04, package room 0.98, concierge 0.32, shared roof deck 0.06, assigned parking -2.09 and valet service -4.47. The rebuilt doorman and gym take values of the same small size.

Lot columns: D class (elevator apartments) 7.99, `bld:lot_unknown` 13.57 (857 rows), log residential units -3.69, `bld:units_unknown` 4.64, log lot frontage 2.78, log floor area per unit 1.84, landmark 1.95 (0.78 to 3.23) and a corner lot 1.16.

The bath steps fall from fit 8's by 2 to 9 points (studio with two full baths 28.9 to 19.7, two bedrooms with three 22.6 to 16.4, half bath 10.6 to 8.8). The extra rooms (`ad:extra_rooms` 0.19 within, 1.45 between) and the square of the size take part of what the baths carried.

## Against the predictions

1. Passes the checks, with a thin column worst: R-hat 1.0065 and ESS 537 on a 38-row bath step. Hit.
2. `sigma` falls 2 to 6%: 3.1% to 3.5%. Hit.
3. `bld_sd` falls 5 to 15%: 12% and 6%. Hit.
4. Doorman stays the largest building premium, pool, concierge, roof deck and parking at +1 to +4 points: the doorman falls to 1.25, below the D class and condo columns, and concierge, roof deck and parking come in under 1 point. Miss.
5. The rebuilt columns move by under 0.5 points: the full doorman moves 12.8 points. Miss.
6. Photos, floor plan and 3D tour positive, pets-not-allowed negative, all within 2 points: the photos and the 3D tour come in negative. Miss.
7. Within a quarter to a half of between: size, in-building laundry and rent stabilization fall in range, in-unit laundry (0.58) and the dishwasher (0.65) don't. Miss.
8. Surface amplitudes within 10% of fit 8's: Manhattan falls 15%. Miss.
9. Sampling 20 to 30 minutes: 26 minutes. Hit.
10. The verdict: the kitchen sink beats fit 8 on the latest split by less than 2 combined SE: it wins by 24. Miss.

That gives 4 hits and 6 misses. Predictions 10 and 11 of the predictions note concern fit (b).

## Verdict

On the latest split, the kitchen sink beats fit 8, the best targeted model without unit effects, by 7,871 elpd at about 24 SE. I predicted a tie. The targeted work had left a lot on the table: the ad's own terms (the months free, the lease length) and the past-only unit means of its labels carry most of the gain I can attribute. Fit 4, the targeted model with unit effects, beats the kitchen sink by 21,032 at about 25 SE, and both gains come from a unit's own past.

Neither fit enters the served model's selection. The building-zones family sits outside `autoselect` and `latestselect`, and the site serves the eight-neighborhood fit, so I changed nothing on the site.

The kitchen sink also costs interpretability. Rebuilding the building labels as of each ad changes what their coefficients measure, so the doorman's 1.25 isn't comparable to fit 8's 14.04, and neither is the doorman's worth by itself.

Next comes a third fit, the kitchen sink with fit 4's unit effects, after fit (b). Its predictions note comes first.

The explainer for this fit is at https://claude.ai/artifact/TopriQc7pSVGcdK8Zm7izN.
