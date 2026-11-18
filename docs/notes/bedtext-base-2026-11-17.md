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
days against 26 for the other 578, and 8.7% of them were later cut against 18.0%. With 23
ads these figures carry wide error, and I draw no conclusion from them.

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
gained 0.056 elpd for each flagged held-out ad (278 over 5,022 ads, inside its lead of 224
over all ads), which would be 11 elpd here. The count of
flagged ads in the lowest tenth is the measure closest to the Deals list.

1. Both runs miss the gate on a scalar and finish (95%).
2. `base-short`'s elpd at the final asks is within 40 of j9's 9,978.6 (70%).
3. `bedbase-short` minus `base-short` at the final asks, all ads: above zero (65%), between
   -10 and +40 (70%), above zero by more than twice its paired SE (25%).
4. On the 196 flagged ads the difference is above zero (75%), and above zero by more than
   twice its SE (45%).
5. The flagged ads' mean first-ask place rises from `base-short` to `bedbase-short` (85%), by
   0.01 to 0.06 (60%).
6. `base-short` puts 18 to 28 flagged ads in its lowest tenth (75%), and `bedbase-short`
   puts fewer there (80%), by 3 to 10 (55%).
7. At least 93% of `base-short`'s lowest tenth is in `bedbase-short`'s (75%).
8. The two coefficients sum to between -0.09 and -0.03 (65%), and the unit mean's is the
   larger in size (70%).
9. Each container settles under $1.40 by Modal's estimate (75%).

## Rule for the next step

A full pool pair for publishing is worth proposing to Ben if `bedbase-short` puts at least 3
fewer flagged ads in its lowest tenth than `base-short` does and does not lose to
`base-short` on all ads by more than twice the paired SE. The distance of `base-short`'s
flagged count from j9's 23 shows how much of such a move is sampling noise. If the flag
moves fewer than 3 ads, a caution label on flagged Deals candidates does the same work for a
renter at no fit cost.

## Budget

The sprint has spent $59.76 of $100. The ledger reserves $1.93 for each container ($3.86
for the pair), and I expect the pair to settle at $1.80 to $2.80.

## Results

Scored at 9:25 PM ET on 2026-11-17. Both containers finished, and both miss the gate on a
scalar, as short fits do:

| Run | Worst R-hat | Sampling | Modal estimate |
|---|---|---|---|
| `drift-building-b0-market-0f8aa7f8-base-short` | 1.162 (`building_ar_sd`) | 210 s | $1.17 |
| `drift-building-bedtext-b0-market-0f8aa7f8-bedbase-short` | 1.084 (`sigma[3]`) | 215 s | $1.31 |

The flag's coefficients are -0.0035 (ad, posterior sd 0.0008) and -0.0598 (unit mean, sd
0.0011), so a unit advertised that way on every ad is priced 6.1% lower.

Final asks of the 9,346 open ads (`drift_score`, then `cmp.py`):

| Score | j9 (pool) | `base-short` | `bedbase-short` |
|---|---|---|---|
| elpd | 9,978.6 | 9,961.8 | 9,975.0 |
| median absolute error | 0.0474 | 0.0474 | 0.0471 |
| 50% / 80% / 95% coverage | 51.4 / 79.2 / 94.5% | 51.3 / 78.9 / 94.5% | 51.2 / 79.0 / 94.4% |

| Open ads | Ads | elpd, `bedbase-short` minus `base-short` | SE | Mean shift of the median |
|---|---|---|---|---|
| all | 9,346 | +13.2 | 9.6 | 0.000 |
| flagged | 196 | +5.3 | 6.8 | -0.032 |
| stated size above the coded count | 44 | -0.2 | 0.3 | -0.001 |
| no bedroom-text column set | 9,106 | +8.1 | 6.7 | +0.001 |

First asks (`place.py`):

| Open ads | Ads | Mean place, base | Mean place, flag | Lowest tenth, base | Lowest tenth, flag | In both |
|---|---|---|---|---|---|---|
| all | 9,346 | 0.598 | 0.598 | 610 | 607 | 596 |
| flagged | 196 | 0.522 | 0.612 | 23 | 14 | 14 |
| unflagged | 9,150 | 0.599 | 0.597 | 587 | 593 | 582 |

The flagged model moves 9 of `base-short`'s 23 flagged ads out of the lowest tenth and
brings none in. `base-short` itself puts the same 23 flagged ads there as j9 counted, so
sampling noise between a short fit and the pool moved none of them. Six unflagged ads enter
the lowest tenth in their place and one leaves. Over all ads the lowest tenth's median days
on market stays at 26 and its share raised later moves from 36.6% to 36.4%.

The 14 flagged ads left in the flagged model's lowest tenth stayed on the market a median of
62 days. They are low for the model even after the flag's 6% and may be worth an expert
read.

Prediction scores:

1. Right: both miss the gate and finish.
2. Right: `base-short` sits 16.8 below j9.
3. Right on the sign and the range (+13.2). The lead is 1.4 SE, under twice the SE, as the
   75% side of that part expected.
4. Right on the sign (+5.3), and it is under twice its SE, the 55% side.
5. Right on the direction, wrong on the size: the flagged ads' mean place rises by 0.090,
   above the 0.01 to 0.06 I gave. Flagged ads now sit at 0.612, a little above the 0.598 of
   all ads.
6. Right on all three parts: 23 flagged ads in `base-short`'s lowest tenth, fewer under the
   flag, by 9.
7. Right: 596 of 610, 97.7%.
8. Right: the sum is -0.063, and the unit mean's coefficient is the larger.
9. Right: $1.17 and $1.31.

## Reading

The rule for the next step is met: 9 fewer flagged ads in the lowest tenth against a
threshold of 3, and a lead of 13 elpd on all ads where the rule asked only for no loss
beyond twice the SE. The elpd lead by itself is within noise on 9,346 ads. The change in
the Deals candidates is clear: about 1.5% of the lowest tenth is replaced, and the ads
removed are ones whose text says the unit is smaller than its coded count.

Publishing from the flagged model needs a full market pool and a full backtest pool, each
passing the gate. j9's containers ran about 2,860 s each, which is about $4.20 a container
at these runs' rate, so three containers a pool comes to about $12.50 a pool and $25 for
the pair. The sprint has spent $62.24, so the pair would leave about $12.50. That spend is
Ben's decision.

The caution label on flagged Deals candidates remains the alternative with no fit cost. It
warns a renter and leaves the ad's place as it is, and the flagged model lowers the price
it expects for the unit, so the 9 ads leave the list.

## Budget

`base-short` settled at $1.17 and `bedbase-short` at $1.31 by Modal's estimates, $2.48 for
the pair. The sprint has spent $62.24 of $100.
