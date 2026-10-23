# As-of floor model with a random effect per unit: predictions, 2026-10-23

This is follow-up fit 4. It answers objection 1 on the research board (`20261023T031332Z-conference-open-objections-to-the-building-zones-fl`): the base model treats repeat ads of a unit as independent. `rentfrontier.building_zones_floor_asof3_unit` adds a Normal effect for each unit, with spread `su ~ HalfNormal(0.1)`, to the as-of floor model on the build after #1242. The module docstring of `building_zones_floor_asof2_unit` describes the blocked Gibbs steps. I wrote these predictions before the launch.

Every held-out ad on the latest split is the latest ad of a unit with at least one training ad (`docs/notes/conference-followups-2026-10-22.md`, section (f)). That makes this split close to the most favorable one for a unit effect. The fit should be read alongside a unit-disjoint split (objection 17) before anyone draws conclusions about new units.

## The fit

- Model `building-zones-floor-asof3-unit`, split latest, dataset `b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc`, input `rows-b3ddebf19af1dc1e.parquet`.
- 4 chains, 300 warmup, 1,000 sweeps with every 5th kept, seed 20261021, fit-only.
- I score it with `docs/notes/conference-followups-2026-10-22/score.py` (400 draws). That script doesn't read unit effects yet, so before scoring I'll extend it to add each held-out ad's unit effect, drawn from Normal(`unit_mean`, `unit_var`) of its chain, and I'll compare it with fit 8 (cap64 on the same build, the same held-out ads) and with the asof2 fit on the held-out ads both builds share, using `compare.py`.

## Predictions

- The fit passes the gate (R-hat at most 1.01, bulk ESS over 400, including `unit_sd`) and takes 25 to 50 minutes on Modal, at $1.00 to $2.20.
- `unit_sd` has a posterior median between 0.05 and 0.10 on the log scale, with a 90% interval narrower than 0.005.
- `sigma` falls by 15% to 40% in every group. `bld_sd` falls by under 20%, since units sit inside buildings and the building levels still carry what all their units share.
- Held-out RMSE falls from about 0.116 to between 0.085 and 0.105. Held-out elpd rises by 10,000 to 50,000 against fit 8 on the same ads, far beyond 2 SE by building.
- Held-out coverage of the 90% interval stays between 0.88 and 0.92, and the median 90% interval width shrinks by 10% to 35%.
- Unit attributes that rarely change within a unit (floor, bedrooms, the elevator floor curve) move by under 1 point. The in-unit laundry and dishwasher coefficients fall by 0.5 to 3 points as the unit effects absorb unit quality that correlates with them. The building amenity coefficients (doorman types, gym, condo) move by under 1 point.

If the fit misses the gate, I'll trace the failing quantity to the data or the model structure, and I won't rerun it on a new seed.

## Changes before the launch (2026-10-23 04:45Z)

Sol's reply on objections 1 and 19 (`20261023T041606Z-sol61-re-conference-1-19-unit-dependence-is-no`) points out that a unit random intercept doesn't by itself identify an amenity premium within units. The effect is assumed independent of the unit's features, so a feature that never changes inside a unit still gets its coefficient from differences between units. Fit 8 hasn't launched, so I changed fit 4 before it starts:

- The model is now `building-zones-floor-asof3-unitmean` (`rentfrontier.building_zones_floor_asof3_unitmean`). It keeps the unit effect and adds, for each unit column whose label can change between a unit's ads, the unit's mean over its training rows, as a column named `umean:` plus the column's name. The columns are `unit:log_size_rel`, `unit:size_unknown`, `unit:size_imputed`, `unit:laundry_in_unit`, `unit:laundry_in_building`, `unit:dishwasher`, `unit:garden` and `flag:rent_stabilized`. A row of a unit with no training row takes its own value.
- I report each of those columns twice, from the saved draws: the within-unit coefficient (the column's own) and the between-unit coefficient (the column's plus its mean's). The run record counts the rows whose value differs from their unit's mean, so a reader can tell how much data each within coefficient rests on.
- Bedrooms, baths, the floor curves and the building columns get no unit mean. They rarely change between a unit's ads, so their coefficients stay between-unit, and I'll label them that way.
- I won't call any interval from this fit cluster-adjusted. The posterior intervals are the model's own. If I later report a sandwich or a cluster bootstrap, I'll name the estimator and compare its widths with the posterior's on the same terms.

Every prediction above still applies, with these added:

- Each `umean:` coefficient reaches the gate. Its draws alternate with the unit effects in the Gibbs sweep, so they may mix the slowest of any coefficient. If one misses the gate, I'll trace it to the data or to that alternation, and I won't reseed.
- In-unit laundry: the within-unit coefficient is 0 to 3 points, since most changes in the label between a unit's ads come from what an ad mentions. The between-unit coefficient is 4 to 8 points.
- Dishwasher: within 0 to 1.5 points, between 1 to 3 points.
- `unit:log_size_rel`: the within coefficient is 30% to 80% of the between coefficient, since a unit's stated size varies mostly by measurement error.
- Rent stabilized: within -4% to 0%, and the between coefficient lies below the within one.
- Garden: the within coefficient's 90% interval includes 0.
- `unit_sd` changes by under 10% against what the unit effect alone would give, as the means explain little of the unit's level next to its floor, size and building.
