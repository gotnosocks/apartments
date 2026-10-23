# Predictions: within-unit premiums on Sol's audited endpoints (2026-10-23)

I wrote these predictions before reading any rent on these ads. Fit 4
(`building-zones-floor-asof3-unit`, a random intercept per unit) has not run yet. When it does, I
will compare its coefficients with a unit fixed-effects OLS fitted on the repeat-ad endpoints that
Sol audited (`members/sol61/checks/season_exploratory_endpoints.parquet` on the research board,
post `20261023T045622Z-sol61-re-unit-means-supported-audited-explorat`).

## Sample and counts

`docs/notes/endpoint-unit-fe-2026-10-23/counts.py` rebuilds fit 4's as-of tables from the model
dataset `b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc` (training rows of the latest split), runs the
floor design on the endpoint ads, and counts the units whose two endpoints differ on each design
column. It reads no ask. Its output is `counts.json` in the same folder.

- 123,828 endpoint ads, 61,914 units, 15,565 buildings. Every endpoint is in the model rows with
  Sol's unit and building.
- Fit 4's latest split holds out 1,888 of these ads, all of them later endpoints of different
  units. Sol screened holdout rows with the mask of an earlier build (edc83b49), and this
  build's split differs on those rows.
- Every unit has a unit effect in fit 4, so each one has at least the two training rows it
  needs (apart from the 1,888 held-out ads).
- 8,842 pairs pass Sol's strict screen.
- The earlier endpoint falls between 2014-01-01 and 2018-03-29 and the later one between
  2014-10-01 and 2018-12-31. The ads span 60 calendar months and 262 ISO weeks. The gap between
  endpoints runs from 270 to 1,095 days, with a median of 505 and quartiles at 392 and 752.

Units whose value changes between endpoints, by fit 4 column:

| column | units changing | on | off |
|---|---:|---:|---:|
| unit:dishwasher | 11,992 | 8,088 | 3,904 |
| unit:log_size_rel | 9,339 (6,576 by more than 0.05) | | |
| unit:size_imputed | 7,742 | 6,576 | 1,166 |
| unit:laundry_in_building | 6,129 | 3,455 | 2,674 |
| unit:laundry_in_unit | 5,651 | 3,041 | 2,610 |
| unit:size_unknown | 5,126 | 0 | 5,126 |
| flag:shared_space | 858 | 449 | 409 |
| flag:rent_stabilized | 547 | 243 | 304 |
| bld:altered_2000_on | 422 | 422 | 0 |
| unit:walkup_floor_unknown | 201 | 107 | 94 |
| unit:walkup_f2 .. f6 | 94, 77, 47, 24, 18 | | |
| unit:elev_floor_unknown | 67 | 32 | 35 |
| unit:walkup_top | 54 | 26 | 28 |
| unit:elev_f2 .. f47 | 14 or fewer each | | |
| unit:elev_top | 13 | 6 | 7 |
| flag:income_restricted | 10 | 5 | 5 |

"On" counts units where the later ad has the flag and the earlier one lacks it. Bedrooms, baths,
the bedroom-by-bath columns, every building column except `bld:altered_2000_on`, and the garden,
penthouse and lower-floor flags never change within a pair. The unit effects absorb them.
`bld:altered_2000_on` changes because it turns on once the ad's year reaches the building's
MapPLUTO alteration year.

Many of these changes come from what an ad states, not from the unit. The later ad states
dishwasher twice as often as it drops one. Every `size_unknown` change goes from unknown to known,
and most `size_imputed` changes are a later ad without a stated size, which the as-of fill then
gives the size the earlier ad stated.

## Regression

`docs/notes/endpoint-unit-fe-2026-10-23/unit_fe.py` will fit OLS on the endpoint rows:

- target: log latest ask, from the model rows;
- fixed effects for the unit and for the calendar month of each row's own `latest_day`, absorbed
  by alternating projections;
- every fit 4 column above with at least one changing unit, all in one regression;
- standard errors two-way clustered by unit and by the ISO week of each row's own `latest_day`
  (Cameron, Gelbach and Miller), with the larger one-way variance where the two-way one comes
  out negative.

The week-dependence target allows any correlation among the errors of ads dated in the same ISO
week, whether they are first or second endpoints and in whatever unit, and any correlation
between the two endpoints of a unit. It treats ads in different weeks and different units as
independent, so it does not cover shocks lasting over several weeks. Since each endpoint row
carries its own week, shocks shared by first endpoints fall into week clusters as well as
second-endpoint ones.

I report each coefficient as a percent premium, 100 (exp(b) - 1), with a 95% interval, and
`log_size_rel` as an elasticity. A second run drops the 1,888 units with an endpoint held out by
fit 4's split, as a check on that sample difference.

## Predictions

For terms with about 200 or more changing units:

| column | point estimate | hit range |
|---|---:|---|
| unit:laundry_in_unit | +2.0% | +0.5 to +4.0% |
| unit:laundry_in_building | +0.5% | -0.5 to +1.5% |
| unit:dishwasher | +0.8% | 0.0 to +2.0% |
| unit:log_size_rel | 0.10 | 0.03 to 0.25 |
| unit:size_imputed | 0.0% | -1.5 to +1.5% |
| unit:size_unknown | 0.0% | -2.0 to +2.0% |
| flag:shared_space | -20% | -45 to -5% |
| flag:rent_stabilized | -2.0% | -6.0 to +1.0% |
| bld:altered_2000_on | +1.5% | -1.0 to +4.0% |
| unit:walkup_floor_unknown | 0.0% | -2.0 to +2.0% |

My reasoning: a flag that changes within a unit mostly records a change in what the ad says. An
ad that starts to mention in-unit laundry or a dishwasher often describes the same unit more
fully, so the within-unit estimates should shrink toward zero from the pooled ones. Some changes
are renovations, which bundle new appliances with other work and push the estimate up. I expect
the shrinkage to dominate. The size terms change mostly through stated sizes that disagree and
through fills, so I expect a small elasticity. A unit that becomes a room share is priced per room
and should drop steeply.

Against the paper's within-building pooled premiums (in-unit laundry 6.65%, dishwasher 2.31%,
rent stabilized -3.22%, from `docs/notes/delist-audit-2026-10-23.md`), I predict:

- the within-unit laundry-in-unit premium is below 6.65%, and its 95% interval stays below 6.65%;
- the within-unit dishwasher premium is below 2.31%, and its 95% interval stays below 2.31%;
- both within-unit premiums are under half the pooled ones (under 3.3% and 1.15%).

Dropping the units with a held-out endpoint moves no predicted coefficient by more than 0.3
percentage points (0.03 for `log_size_rel`).

Too few changes to say anything: `flag:income_restricted` (10), the floor curve columns
(`walkup_f2` to `f6` at 94 or fewer, `elev_f*` at 14 or fewer), `elev_top` (13), `walkup_top`
(54) and `elev_floor_unknown` (67). I keep them in the regression so that floor changes don't
load onto other columns, and I report them without predictions. The garden, penthouse and
lower-floor flags never change, so the regression has no within-unit estimate for them, and fit
4's coefficients on them come only from differences between units.

## Scoring

- A point-estimate prediction hits when the estimate falls in its hit range.
- A comparison with the pooled premiums hits when every part of its bullet holds.
- The held-out check hits when none of the ten predicted coefficients moves by more than 0.3
  points (0.03 for `log_size_rel`).

The results note will be `docs/notes/endpoint-unit-fe-2026-10-23.md`.
