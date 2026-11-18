# Bedroom-text flag on the base model, tested on the backtest

Written at 8:50 PM ET on 2026-11-17, before either fit is launched.

The bedroom-text flag marks an ad whose description states a smaller unit than its coded
bedroom count: flex wording for the coded count, or a stated size below it
(`rentfrontier.b0bedtext`). Added to L2, the flag gained 224 held-out elpd on the latest
split (`docs/notes/bed-text-2026-11-16.md`). L2 does not price the Deals page, since its
market pool missed the gate and its backtest tied the base model's
(`docs/notes/l2-market-2026-11-15.md`). Ben asked for the flag to be tested on the base
model, `drift-building`, which Deals publishes from.

## Model and data

`drift-building-bedtext` (`rentfrontier.drift_building_bedtext`) is the base model's design
with the two columns the L2 variant used: `ad:bed_text_smaller` and its unit mean
`umean:ad:bed_text_smaller` over the row and the unit's earlier training rows. The sampler,
priors and settings are the base model's.

The test runs on the backtest: the build as of 2025-11-10, 1,754,606 training rows and the
9,346 ads open that day, each predicted before its ask is read. The base model's backtest
pool is `j9`. I wrote a copy of j9's dataset with the flag columns,
`b0-ddd2fe8f5da041b8-alldata-dense-nyc-asof-20251110-bedtext`. The reader took each listing's
latest description and its coded count, and no rent. 53,384 of the 1,763,952 rows carry the
flag, and 196 of the 9,346 open ads do (2.1%).

The description is the listing's latest one, as for the base model's other text columns, so
the text of an ad open on 2025-11-10 may have been edited after that day.

## The flagged open ads under j9

`docs/notes/bedtext-base-2026-11-17/place.py` places each open ad's first ask in a run's
predictive distribution, as `drift_deals validate` does. Under j9:

| Open ads | Ads | Mean place | In the lowest tenth | Their median days on market | Their share raised later |
|---|---|---|---|---|---|
| all | 9,346 | 0.598 | 601 (6.4%) | 26 | 37.1% |
| flagged | 196 | 0.523 | 23 (11.7%) | 48 | 52.2% |
| unflagged | 9,150 | 0.599 | 578 (6.3%) | 26 | 36.5% |

A flagged ad is about twice as likely as another ad to sit in j9's lowest tenth, where the
Deals candidates come from. The 23 flagged ads there stayed on the market a median of 48
days against 26 for the other 578, so renters did not take them as bargains.

## Fits

A short fit of each model on the backtest, one H100 container each, 2 chains, 500 warmup
sweeps and 320 kept, seed 1, launched from `/data1/apartments/serve/master` at the merge
commit of this note, the second after the first log reaches "synced":

```sh
IN=/data1/apartments/pipeline/datasets/rows-ddd2fe8f5da041b8.parquet
D=/data1/apartments/frontier/datasets/b0-ddd2fe8f5da041b8-alldata-dense-nyc-asof-20251110
ops/modal-fit --outside-budget --gpu H100 --dataset "$D" --input "$IN" --split market \
  --baseline drift-building-b0-market-67d14e17-j9 COMMIT base-short \
  drift-building b0 2 500 320 1 --seed 1 --level-dof 4 --no-loo --no-heldout
ops/modal-fit --outside-budget --gpu H100 --dataset "$D-bedtext" --input "$IN" --split market \
  --baseline drift-building-b0-market-67d14e17-j9 COMMIT bedbase-short \
  drift-building-bedtext b0 2 500 320 1 --seed 1 --level-dof 4 --no-loo --no-heldout
```

The comparison is `bedbase-short` against `base-short`: the same sampler, length and seed,
with the flag as the only change. `base-short` against j9 measures how far a short fit of
the backtest sits from its pool.

A short fit misses the gate on the scalars by construction, so neither run can publish. The
question for these two runs is whether a full market and backtest pool of the flagged model
is worth its cost.

Scores, each on the 9,346 open ads:

- final asks: `python -m rentfrontier.drift_score RUN` on each run, then
  `docs/notes/bed-text-2026-11-16/cmp.py` for the paired elpd difference with its SE
  clustered by building, over all ads and over the flagged ones;
- first asks: `place.py` for the flagged ads' mean place and the ads in each run's lowest
  tenth, and `drift_deals validate` for the days and cuts by tenth.

## Predictions

With 196 flagged ads the final-ask elpd is a weak test. On the latest split the L2 variant
gained 0.056 elpd for each flagged held-out ad, which would be 11 elpd here. The count of
flagged ads in the lowest tenth is the measure closest to the Deals list.

1. Both runs miss the gate on a scalar and finish (95%).
2. `base-short`'s elpd at the final asks is within 40 of j9's 9,978.6 (70%).
3. `bedbase-short` minus `base-short` at the final asks, all ads: above zero (65%), between
   -10 and +40 (70%), beyond twice its paired SE (25%).
4. On the 196 flagged ads the difference is above zero (75%), and beyond twice its SE (45%).
5. The flagged ads' mean first-ask place rises from `base-short` to `bedbase-short` (85%), by
   0.01 to 0.06 (60%).
6. `base-short` puts 18 to 28 flagged ads in its lowest tenth (75%), and `bedbase-short`
   puts fewer there (80%), by 3 to 10 (55%).
7. At least 93% of `base-short`'s lowest tenth is in `bedbase-short`'s (75%).
8. The two coefficients sum to between -0.09 and -0.03 (65%), and the unit mean's is the
   larger in size (70%).
9. Each container's Modal estimate is under $1.40 (75%).

## Rule for the next step

A full pool pair for publishing is worth proposing to Ben if `bedbase-short` moves flagged
ads out of the lowest tenth (prediction 6) and does not lose to `base-short` on all ads by
more than twice the paired SE. If the flag moves few ads, a caution label on flagged Deals
candidates does the same work for a renter at no fit cost.

## Budget

The sprint has spent $59.76 of $100. I expect $1.80 to $2.80 for the pair.
