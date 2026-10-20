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

## The fit (not launched)

    ops/modal-fit --dataset /data1/apartments/frontier/datasets/b0-30b3edae310c2fae-alldata-v36-dense --split latest <commit> dense-w1500 building-attrs b0 16 1500 500 12 --max-leapfrog-steps 64 --seed 20261020 --no-loo --no-heldout

## Predictions (written before the fit)

Convergence, against ea4bcbd6:

| Prediction | ea4bcbd6 | Expected |
|---|---|---|
| max R-hat over all traced quantities | 1.004 | under 1.02 |
| min bulk ESS | 2,296 | over 800 |
| divergences while sampling | 0 | 0 |
| wall time | 23 min | 35 min or less |
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
| B8 | Each of the four noise scales sigma[0..3] falls by 3% to 12% against ea4bcbd6. |
| B9 | The bedroom and bath contrasts of the normal walk's scorecard items 1 to 4 each move by under 4 percentage points. |
| B10 | tau moves by under 15%, and the 2020 trough by under 2 points. |
