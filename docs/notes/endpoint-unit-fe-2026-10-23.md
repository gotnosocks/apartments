# Within-unit premiums on Sol's audited endpoints (2026-10-23)

I fitted a unit fixed-effects OLS on the 61,914 repeat-ad pairs Sol audited
(`members/sol61/checks/season_exploratory_endpoints.parquet`), for comparison with fit 4's
coefficients (`building-zones-floor-asof3-unit`) once fit 4 has run. The predictions,
written before I read any rent, are in `docs/notes/endpoint-unit-fe-predictions-2026-10-23.md`
(PR #1262).

## Method

`docs/notes/endpoint-unit-fe-2026-10-23/counts.py` rebuilt fit 4's as-of tables from the
training rows of the latest split on `b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc` and ran the floor
design on the 123,828 endpoint ads. `unit_fe.py` in the same folder then read each ad's latest ask
from the model rows and fitted, on the endpoint rows:

- target: log latest ask;
- fixed effects for the unit and for the calendar month of the row's own `latest_day` (60
  months), absorbed by alternating projections in 50 sweeps;
- all 43 design columns that change within at least one unit, in one regression. Bedrooms,
  baths and the other building and floor columns never change within a pair, so the unit effects
  absorb them.

Standard errors are two-way clustered by unit and by the ISO week of the row's own `latest_day`
(262 weeks). The week-dependence target allows any correlation among the errors of ads dated in
the same ISO week, first or second endpoints, from any unit, plus any correlation between a
unit's two endpoints. Ads in different weeks and different units count as independent, so shocks
lasting several weeks are not covered. Of the unit and week clusters, the unit ones give the
larger one-way standard errors on every reported term, and the two-way ones come out close to them.
A second set of standard errors, clustered by building and week, follows in
[Building clustering](#building-clustering).

The main run reads the asks of all endpoints, including the 1,888 later endpoints that fit 4's
latest split holds out. A second run dropped the 1,888 units with such an endpoint.
[Holdout masks](#holdout-masks) says which mask each count comes from.

Outputs: `/data1/apartments/tmp/conference-followups/unit-fe/` (`counts.json`,
`endpoint_design.parquet`, `results.json`, `tables.md`), with copies of the two json files in the
docs folder. Both scripts ran under a 3 GB memory cap, in 80 s and 12 s.

## Results

Binary terms as percent premiums, 100 (exp(b) - 1); `log_size_rel` as an elasticity.

| column | units changing | within-unit estimate | 95% interval | predicted range | score |
|---|---:|---:|---|---|---|
| unit:laundry_in_unit | 5,651 | +0.78% | +0.49 to +1.08 | +0.5 to +4.0 | hit |
| unit:laundry_in_building | 6,129 | +0.43% | +0.19 to +0.67 | -0.5 to +1.5 | hit |
| unit:dishwasher | 11,992 | +0.53% | +0.38 to +0.68 | 0.0 to +2.0 | hit |
| unit:log_size_rel | 9,339 | 0.002 | -0.007 to 0.011 | 0.03 to 0.25 | miss |
| unit:size_imputed | 7,742 | +0.20% | +0.01 to +0.40 | -1.5 to +1.5 | hit |
| unit:size_unknown | 5,126 | +0.13% | -0.14 to +0.39 | -2.0 to +2.0 | hit |
| flag:shared_space | 858 | -0.23% | -0.72 to +0.27 | -45 to -5 | miss |
| flag:rent_stabilized | 547 | -0.72% | -1.44 to -0.003 | -6.0 to +1.0 | hit |
| bld:altered_2000_on | 422 | +1.19% | +0.35 to +2.04 | -1.0 to +4.0 | hit |
| unit:walkup_floor_unknown | 201 | -0.10% | -3.19 to +3.10 | -2.0 to +2.0 | hit |

Eight of the ten point predictions hit.

- The size elasticity came out at zero, below the predicted range. A change in a unit's stated
  or filled size between its two ads moves its ask by nothing I can detect: the interval rules out
  elasticities above about 0.011. Errors in stated sizes would pull this estimate toward zero, so
  it says more about how sizes get reported than about what space is worth.
- The shared-space flag barely moves the ask. I had read it as a room share priced per room.
  The flag comes from a regex on the description (`shared (bath|kitchen)`, `sro`, `roommate`),
  so an ad saying "roommates welcome" sets it, and a change between a unit's ads mostly records
  that wording.

Against the paper's within-building pooled premiums (`docs/notes/delist-audit-2026-10-23.md`):

| column | pooled | within-unit | within / pooled |
|---|---:|---:|---:|
| in-unit laundry | 6.65% | 0.78% | 0.12 |
| dishwasher | 2.31% | 0.53% | 0.23 |
| rent stabilized | -3.22% | -0.72% | 0.22 |

- In-unit laundry below 6.65% with the interval below it: hit (upper end 1.08%).
- Dishwasher below 2.31% with the interval below it: hit (upper end 0.68%).
- Both under half their pooled premiums: hit.

Dropping the units with a held-out endpoint moved no predicted coefficient by more than 0.13
points (rent stabilized; 0.001 for the size elasticity), so the held-out check hits.

The terms with too few changes for a prediction gave wide intervals around values near zero:
`walkup_top` -0.27% (54 units), `elev_floor_unknown` +0.28% (67), the walk-up floor steps
between -0.2% and +0.9% (18 to 94 units each), `income_restricted` -4.0% (10). The elevator
floor steps change in 14 or fewer units each, several in a single unit, and with one changing
unit a cluster-robust interval means nothing. I list them in `results.json` without reading
them.

## Building clustering

Added 2026-10-23, after Astra asked on the board for standard errors clustered by building and
endpoint week. I added them to `unit_fe.py` and reran it on the same 123,828 endpoints. They
are two-way, by building (15,565 buildings) and by the ISO week of each row's own `latest_day`,
and `results.json` keeps them beside the unit and week ones. The estimates don't change.

| column | estimate | 95%, unit and week | 95%, building and week | SE ratio |
|---|---:|---|---|---:|
| unit:laundry_in_unit | +0.78% | +0.49 to +1.08 | +0.44 to +1.13 | 1.18 |
| unit:laundry_in_building | +0.43% | +0.19 to +0.67 | +0.14 to +0.72 | 1.19 |
| unit:dishwasher | +0.53% | +0.38 to +0.68 | +0.34 to +0.71 | 1.24 |
| unit:log_size_rel | 0.002 | -0.007 to 0.011 | -0.008 to 0.012 | 1.10 |
| unit:size_imputed | +0.20% | +0.01 to +0.40 | -0.04 to +0.44 | 1.24 |
| unit:size_unknown | +0.13% | -0.14 to +0.39 | -0.19 to +0.44 | 1.19 |
| flag:shared_space | -0.23% | -0.72 to +0.27 | -0.75 to +0.29 | 1.05 |
| flag:rent_stabilized | -0.72% | -1.44 to -0.003 | -1.53 to +0.09 | 1.13 |
| bld:altered_2000_on | +1.19% | +0.35 to +2.04 | -0.01 to +2.41 | 1.43 |
| unit:walkup_floor_unknown | -0.10% | -3.19 to +3.10 | -3.21 to +3.12 | 1.01 |

The SE ratio divides the building and week standard error by the unit and week one. The
intervals widen on all ten terms, by 1% to 43% in standard error. The largest change is on
`altered_2000_on`, which is a building column, so its changes cluster within buildings. Three
intervals that excluded zero now reach it: `size_imputed`, `rent_stabilized` and
`altered_2000_on`. The laundry and dishwasher intervals stay clear of zero and below the pooled
premiums, so the scores above don't change. The run without fit 4's held-out units gives ratios
between 1.01 and 1.39 on the same terms.

## Holdout masks

Two masks enter this note:

1. Sol's 61,914 pairs come from rows outside the official holdout of the original fit
   (`building-zones-floor-b0-latest-6b5a5b4a-dense-w1000`, its `heldout` array over
   `b0-edc83b49f9bacd8c-alldata-v36-dense-nyc`). That mask excludes 189,649 rows, and no
   endpoint here is one of them.
2. The 1,888 count comes from the rebuilt fit 4 split, `splits.SPLITS["latest"]` on
   `b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc`, which `counts.py` records as `fit4_held_out`.
   Those 1,888 later endpoints pass the original mask and fail the rebuilt one.

The main run uses Sol's sample as screened by the original mask, the 1,888 included. The second
run also drops the units the rebuilt mask touches, so it is clear of both.

## Comparison with fit 4

Fit 4 has not run. When it does, this section will set its coefficients on the ten terms above
next to the within-unit OLS ones, with term definitions and units checked to match.

## Caveats

- A flag can change between a unit's ads through what the ad reports, through a renovation that
  bundles several changes, or through an identity error that pairs two different units. The
  within-unit estimates mix all three. The laundry and dishwasher coefficients
  estimate the premium of a reported change, not of installing the appliance.
- Fit 4's unit effects use every training ad of a unit, often more than these two endpoints,
  and fit 4 has other priors, columns and a time model. A gap between its coefficients and these
  ones mixes sample, estimator and prior, so it does not measure prior sensitivity alone.
- The endpoints were chosen for seasonal identification, at least 270 days apart, so they are
  not a representative sample of within-unit amenity changes.
- These intervals are OLS sandwich intervals with the clustering stated above. Nothing here
  makes fit 4's posterior intervals cluster-adjusted.
