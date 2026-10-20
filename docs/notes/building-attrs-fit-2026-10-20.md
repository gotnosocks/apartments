# Building attributes on the normal walk, 2026-10-20

Ben asked for a few high-level building attributes from MapPLUTO, the NJ parcels and
StreetEasy, added to the converged model with no location surface: the qualities that explain
most of the variance between buildings, rather than everything on file.

## The screen

I started from the converged all-data normal walk, `normal-walk-b0-latest-ea4bcbd6-dense-w1500`
(max R-hat 1.004, NJ included). At its posterior medians I took each training row's residual
and averaged the residuals in each building. Across 73,395 buildings the residual sd between
buildings comes to 0.32 against 0.13 within a building, so about 86% of the variance the
model leaves sits between buildings.

I then scored attribute groups by the share of that between-building variance they explain
out of fold. I held buildings out in five folds, weighted each building by the precision of
its mean, and compared against a null with the attribute rows shuffled across buildings. The
null's 95th percentile came out near 0 for every group. The scripts are in
`/data1/apartments/tmp/battrs/` (`resid.py`, `build.py`, `screen3.py`).

| Group | Alone | Within a neighbourhood | Drop from all seven |
|---|---|---|---|
| floors | 16.1% | 2.5% | -4.3 pts |
| elevator | 11.6% | 4.5% | -2.2 pts |
| tenure (condo, co-op) | 9.9% | 3.5% | -1.7 pts |
| doorman | 9.1% | 4.5% | -0.4 pts |
| landmark or historic district | 9.1% | 0.3% | -5.2 pts |
| residential units | 4.4% | 0.2% | -1.9 pts |
| era | 1.3% | 1.2% | -0.7 pts |
| borough labels, for comparison | 19.6% | | |

All seven together explain 31%, and 11.5% within neighbourhoods. I dropped the landmark flag
and the unit count: within a neighbourhood they add almost nothing, so they mostly stand in
for location, which the model is meant to explain with measured qualities and not labels. The
five I kept explain 23% of the between-building variance (17% in Manhattan, 7% in Brooklyn,
6% in NJ) and 7.5% within neighbourhoods.

A hand check of the joins found MapPLUTO's floor count wrong for towers on lots with a podium
or several buildings: 8 floors for 8 Spruce (76 in its ads), 14 for Gotham West (32), 6 for
the Anthem (21). PLUTO counts the lot's primary building. So the snapshot reads floors and
elevator from the building's ads first and falls back to the lot.

## The design

`rentfrontier.building_attrs` appends twelve columns to the normal walk's fixed design, each
with the flag prior Normal(0, 0.5):

1. log(floors / 5), and floors unknown;
2. elevator, and elevator unknown (against none);
3. full-time, part-time and virtual doorman (against none stated);
4. condo and co-op (against rental);
5. built 1980 to 2004, built 2005 on, and year unknown (against before 1980).

Tenure and doorman have no unknown level. A lot with no MapPLUTO match (about 3.7% of rows)
counts as rental, and a building whose ads state no doorman counts as none stated.

The snapshot is `/data1/apartments/external/building-attrs/20261020-0a7254f/attrs.parquet`,
built from pipeline rows `rows-30b3edae310c2fae` with `python -m rentfrontier.building_attrs
snapshot`. It covers every building of the dataset's rows. Share of rows at each level:

| Column | NYC | NJ |
|---|---|---|
| floors unknown | 0.1% | 68% |
| elevator | 53% | 64% |
| elevator unknown | 0.7% | 28% |
| full-time doorman | 19% | 5% |
| virtual doorman | 21% | 5% |
| condo | 16% | 34% |
| co-op | 3.6% | 0% |
| built 2005 on | 18% | 33% |
| year unknown | 0.4% | 24% |

The model, starting values and sampler are the normal walk's, unchanged.

## The fit, on NYC rows only

Ben chose to run the fit without the NJ rows, whose floor and elevator coverage is thin (see
the table above). I wrote `b0-30b3edae310c2fae-alldata-v36-dense-nyc` with `python -m
rentfrontier.b0nyc` (#1177): it keeps 1,896,486 rows and sets aside the 72,598 rows whose
building is in the NJ registry.

    ops/modal-fit --dataset /data1/apartments/frontier/datasets/b0-30b3edae310c2fae-alldata-v36-dense-nyc --split latest <commit> dense-w1500 building-attrs b0 16 1500 500 12 --max-leapfrog-steps 64 --seed 20261020 --no-loo --no-heldout

The base fit ea4bcbd6 included NJ, so its sigma does not compare directly. I took its
residuals at the posterior medians on training rows and found, per noise group, the Student-t
scale with the most likelihood at its median nu (21.5). On all rows that recovers the
posterior sigma to within 0.0001. On NYC rows alone the base scales come to:

| Group | Posterior sigma, all rows | Scale on NYC rows |
|---|---|---|
| 0 | 0.2354 | 0.2360 |
| 1 | 0.2802 | 0.2819 |
| 2 | 0.2842 | 0.2839 |
| 3 | 0.3399 | 0.3414 |

The script is `/data1/apartments/tmp/battrs/sigma_nyc.py`.

## Predictions (written before the fit)

Convergence, against ea4bcbd6:

| Prediction | ea4bcbd6 | Expected |
|---|---|---|
| max R-hat over all traced quantities | 1.004 | under 1.02 |
| min bulk ESS | 2,296 | over 800 |
| divergences while sampling | 0 | 0 |
| wall time | 23 min | 35 min or less (4% fewer rows) |
| cost | $0.83 | $0.80 to $1.30 |

Estimates, each a posterior median (B1 to B7 are in `building_attrs.scorecard`):

| # | Prediction |
|---|---|
| B1 | An elevator adds +6% to +22%. |
| B2 | A condo building adds +6% to +22%. |
| B3 | A co-op building adds +3% to +16%. |
| B4 | A building e times as tall (5 floors to 14) adds +6% to +16%. |
| B5 | A full-time doorman adds -2% to +12%. |
| B6 | A virtual doorman is -9% to +1%. |
| B7 | Built 2005 on is -18% to -3% against before 1980. The model has no location term, so I expect this to carry where new buildings stand rather than what being new is worth. |
| B8 | Each of the four noise scales sigma[0..3] falls by 3% to 12% against ea4bcbd6's scale on NYC rows (the table above). |
| B9 | The bedroom and bath contrasts of the normal walk's scorecard items 1 to 4 each move by under 4 percentage points. |
| B10 | tau moves by under 15%, and the 2020 trough by under 2 points. |

## Results

The fit `building-attrs-b0-latest-041e6aa9-dense-w1500` ran on Modal from 07:16 to 07:41 ET
on 2026-10-20, fit-only on the NYC dataset. It converged: max R-hat 1.004 (tau), min bulk ESS
2,108 (tau), no divergences while sampling, 25 min and about $0.92. The convergence, time and
cost predictions all hit.

| # | Prediction | Posterior median | Result |
|---|---|---|---|
| B1 | elevator +6% to +22% | +12.2% | hit |
| B2 | condo +6% to +22% | +5.9% | miss |
| B3 | co-op +3% to +16% | 0.0% | miss |
| B4 | e times as tall +6% to +16% | +13.4% | hit |
| B5 | full-time doorman -2% to +12% | +6.7% | hit |
| B6 | virtual doorman -9% to +1% | -1.8% | hit |
| B7 | built 2005 on -18% to -3% | -2.5% | miss |
| B8 | sigma falls 3% to 12% | falls 24% to 33% (0.165, 0.187, 0.213, 0.260) | miss |
| B9 | items 1 to 4 move under 4 points | +4.8, +12.7, -29.7, +4.4 points | miss |
| B10 | tau under 15%, trough under 2 points | tau -36% (0.0074), trough +1.7 points (-22.5%) | miss on tau |

The other terms: part-time doorman +9.4%, built 1980 to 2004 -1.6%, floors unknown -13.0%,
elevator unknown +7.7%, year unknown +4.3%. Each 90% interval is under half a point wide.
The model treats ads as independent while ads in a building share a great deal, so these
intervals are far too narrow.

The tail parameter nu fell from 21.5 to 6.9, so the sigmas do not compare one for one. On
the NYC training rows both fits share, I took the residuals at the posterior medians
(`/data1/apartments/tmp/battrs/resid_cmp.py`):

| Residual spread | Base | Building attributes |
|---|---|---|
| all rows, sd | 0.301 | 0.245 |
| between buildings (5+ rows), sd of means | 0.280 | 0.248 |
| within a building, sd | 0.149 | 0.130 |

The between-building fall matches the screen. The within-building fall cannot come from the
new columns, which are constant inside a building. It comes from the bedroom and bath terms,
which moved: 2 beds over 1 went from +1.5% to +14.2%, and a second full bath on a 2-bed from
+67% to +37%. My reading is that the base fit's bath and bedroom terms carried part of
building type, since extra baths and bedrooms go with newer elevator buildings. With building
type in the design those terms fit the differences between units in the same building better.

The run is fit-only (no PSIS-LOO or grouped building holdout), so it is not scored for
selection or served. Co-op and built 2005 on likely carry location, which the design leaves
out.
