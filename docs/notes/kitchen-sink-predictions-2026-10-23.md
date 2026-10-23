# Kitchen sink fits: predictions, 2026-10-23

Ben asked for a kitchen sink model. It keeps the parts of the served model we trust: the neighborhood surface, the building levels, the walk, the bedroom and bath steps and the floor curves. It adds every other unit and building column I can code. I left out map and distance columns (transit, parks, water, noise, schools), since the surface stands in for them. He also asked for a second fit with the surface at about 150 m. I wrote these predictions before launching either fit.

The base is fit 8, `building-zones-floor-asof3-cap64`. The models are `rentfrontier.building_zones_kitchen_sink` and its 150 m twin, `rentfrontier.building_zones_kitchen_sink_150m`. Both run fit-only on Modal (`--no-loo --no-heldout`), on the same dataset, split and seed as fit 8, with the joint amplitude step of fit 4:

| fit | model | surface | GPU | estimate |
|---|---|---|---|---|
| (a) | `building-zones-kitchen-sink` | 1 km, 195 waves | A100-40GB | 20 to 30 min of sampling |
| (b) | `building-zones-kitchen-sink-150m` | 150 m, about 8,400 waves | H100 | to be timed before launch |

If the timing for (b) comes out over the hour cap, I will redesign it (a smaller box, or the 150 m surface in Manhattan only) and record it as blocked rather than launch it.

## Columns

On top of fit 8's 130 columns, I append these groups:

1. `ad:` columns from each ad's own latest raw record (`rentfrontier.listing_codes`) and the pipeline rows:
   - every unit feature code, private outdoor type, view and fireplace type set on at least 2,000 training rows, apart from the codes fit 8 already carries (dishwasher, furnished, washer/dryer), with `ad:features_unstated` for an ad whose feature list is empty;
   - rooms beyond the bedrooms, the logged photo count, a floor plan, a video and a 3D tour;
   - the listing source (a feed or an owner, against a partner broker), the months free, a lease over or under 12 months, each window exposure and the pet policy;
   - the square of `unit:log_size_rel`, the only engineered unit term.
2. `bld:` amenity codes for the building (pool, concierge, roof deck, parking types, storage and so on), each kept when at least 100 buildings carry it, plus `bld:amenities_unstated`.
3. `bld:` lot columns from MapPLUTO: logged residential units and lot frontage, a corner lot, the share of the allowed floor area built, landmark status, several buildings on a lot, the C, D and S building classes and the logged residential floor area per unit, plus `bld:lot_unknown`.
4. `umean:` unit means of fit 4's unit columns and of every `ad:` column, so each of those columns splits into a change within the unit and a difference between units.

On a 3,000-building subset (86,755 rows) the design has 225 columns at full rank. I dropped columns that exactly duplicated others: the outdoor-space flag (fit 8's `feat_private_outdoor_space`), the R building class (`bld:condo`), the unit mean of `unit:garden` (no unit's ads change it) and the count of window exposures (the sum of the four exposures).

## No later ads

Ben ruled that no column may read ads that came after the row's own ad. Every aggregate over a building's or a unit's ads either uses the row's own ad plus the training ads priced on earlier days, or is left out.

Built as of the ad:

- the building amenity codes of group 2, by majority over the stating ads;
- the unit means of group 4 (fit 4 averaged over all of a unit's training ads);
- the base's building elevator, doorman and gym, which fit 8 reads from all of a building's training ads at any date. Inside these fits I rebuild them from the row's ad and the earlier training ads, with fit 8's MapPLUTO fallbacks, and move the row's floor columns to whichever curve the rebuilt elevator picks. On the subset this changes the elevator on 1,295 training rows, the full doorman on 1,488, the part-time doorman on 2,085, the virtual doorman on 3,441 and the gym on 1,031;
- the base's top floor, where MapPLUTO has no floor count: the highest floor among the row's ad and the building's earlier ads. On the subset 377 training rows change their top-floor column on the elevator curve.

The served model keeps fit 8's values. `run_record` saves the counts of rows changed by the rebuild, and the results note will report how much the elevator, doorman and gym coefficients move.

Left out:

- building means of unit columns (Fit B, `building_zones_mundlak_asof`) and the building's bedroom mix, since both average over a building's later ads;
- rent stabilization registrations and HPD violations, since our external snapshots cover Manhattan lots only.

One read from the future remains. The lot columns come from MapPLUTO 26v2, a current release, so an ad from 2018 reads its lot's 2026 unit count and landmark status. Fit 8 reads its height, age and retail columns from the same release. Lot facts change slowly, so I expect this to matter little.

## Predictions

Fit (a), 1 km:

1. It converges by the repo's checks: max R-hat under 1.01 and min ESS over 400. The joint amplitude step settled fit 4's `amp[outer]`, so I expect the worst quantity to be a thin new column, like a rare amenity code, rather than the surface.
2. The residual scale `sigma` falls by 2 to 6% from fit 8's (0.083 to 0.101 by group). The unit means take most of the fall, as in fit 4. Fit 4 dropped `sigma` by about 40%, but most of that came from unit effects, which this model leaves out.
3. `bld_sd` falls by 5 to 15% from fit 8's 0.185 (Manhattan) and 0.114 (outer boroughs), as the amenity and lot columns explain part of each building's level.
4. The building amenities carry most of the new building variance. A doorman stays the largest building premium. Pool, concierge, roof deck and parking each come in at +1 to +4 points, with intervals clear of zero.
5. The rebuilt elevator, doorman and gym move by under 0.5 points each from fit 8's.
6. Among the `ad:` columns, the photo count, the floor plan and a 3D tour come in positive (better-marketed units ask more), and a pets-not-allowed ad comes in negative. Each sits within 2 points of zero.
7. The unit means repeat fit 4's split: each within-unit coefficient comes to a quarter to a half of its between-unit counterpart.
8. The surface keeps its amplitudes within 10% of fit 8's. A building column that is mostly location would take variance from the surface, and I left those out on purpose.
9. Sampling takes 20 to 30 minutes on an A100-40GB at about 1.2 s a sweep, against fit 8's 0.78 s.

Fit (b), 150 m:

10. A 150 m surface takes variance from `bld_sd`: its building-level scale falls by 20 to 40% from fit (a)'s.
11. It does not pass the convergence checks. With about 8,400 waves against 195, I expect the surface amplitudes and waves to mix poorly, with min ESS under 400 on the amplitudes. If so, I record it as a miss and look at the data and the model structure, in that order, before any sampler change.

The verdict will compare fit (a) against the targeted building-zones results (#1240 to #1274) on PSIS-LOO over shared rows and on the latest split, once I score it. My prediction is that the kitchen sink beats fit 8 on the latest split by less than 2 combined SE. The targeted work already took the large terms, and most of the new columns are small.
