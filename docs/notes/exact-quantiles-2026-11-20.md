# Exact quantiles for the Deals table (2026-11-20, no fit)

The Deals table's `below_share` is computed exactly from the mixture over kept draws, but
its median and bounds were sampled: 32 replicates per kept draw since #1471 and #1473,
which left seed noise of about 0.4% in the 95% bounds and 0.15% in the median. A reviewer
suggested inverting the cdf instead. This note records what was built and what it costs.
No fit was run, nothing was spent and nothing was published.

## Is the predictive a mixture with a closed-form cdf?

Every row the sampler handles has the same form. Given a kept draw (or, in the Today
table, a kept sweep of a kept draw), the log rent is

    y = loc + usd z + sigma t,   z ~ Normal(0, 1),  t ~ StudentT(nu).

A unit with a record has a small `usd` and a `loc` that holds its level. A unit with none,
and a unit in a new building, has mean 0 for its level and the full spread in `usd`.
Noise phases and the Today table's lease phases only scale `sigma`. The Today table's
Student-t lasting levels enter as extra components with their own `usd`. No case has
another noise term.

The sum of a Normal and a Student-t has no closed-form cdf in the strict sense.
`drift_score` already writes the Student-t as a scale mixture of Normals on a fixed grid of
96 nodes, and `below_share` is that grid's cdf: an average of Normal cdfs over draws and
nodes. So the predictive that the table reports is a finite mixture of Normals, and its
cdf can be inverted. The grid's own error is small: with 768 nodes the quantiles of 50 of
the served run's ads move by at most 1.1e-9 in log rent.

## What was built

`rentfrontier.drift_quantiles.exact` solves `cdf(q) = p` for each row and level. It runs
Newton's method on the probit of the cdf, which is close to a line, and keeps every level
inside a bracket that all of the row's evaluations narrow. The bracket's midpoint, a
bisection step, replaces a Newton step in three cases: the step would leave the bracket,
it is longer than half the level's step before it, or the bracket has not halved over
the level's last three evaluations. These are the safeguards of Numerical Recipes'
rtsafe. The first version had only the first case, and review found rows on which it
never converged: where the probit bends sharply between two groups of components,
Newton's step from each end of the bracket lands on the other end, the bracket never
narrows and no bisection step is taken. On 200 seeded synthetic blocks of 40 such rows
(`hard` in the tests) 29 blocks raised after 80 evaluations. With the safeguards a
closed bracket halves at least once in four evaluations of its level, so the solver
converges within its limit of 120. A level stops after a
Newton step shorter than 1e-5. The error after such a step is of the order of the step
squared: against a tolerance of 1e-12 the largest difference on 501 served ads was
7e-10. Plain bisection to 1e-6 would need about 22 evaluations of the cdf per level.
This takes 3.

`drift_score.score_rows` and `score_run` take `exact=True`. `drift_deals.deals` and
`publish` use it by default, and `--sampled` gives the old table. `drift_today.table` and
`publish` take it as an option (`--exact`), off by default for the cost below. The fit's own
scores, the backtest's `validation.json` and the Today table's check are unchanged and
still sampled.

## Measurements on the served run

The run is `drift-building-bedtext-layout-range-b0-market-6cd1f12b-range-m3`: 6,502 ads
and 360 kept draws. Both tables were written to `/data1/apartments/tmp/po-exact-quantiles/`
with the registry, backtest and texts of `ops/deals-refresh publish`, under a 5 GB cap.

| | sampled | exact |
|---|---|---|
| `publish`, wall time | 1 min 53 s | 2 min 59 s |
| `publish`, peak memory | 3.59 GB | 3.55 GB |
| `score_run` alone, wall time | 17.8 s | 87.1 s |
| `score_run` alone, peak memory | 0.62 GB | 0.63 GB |

The peak of `publish` is the backtest's validation and the tables it reads, not the
quantiles.

The figures above are from the first version of the solver. With the safeguards
`score_run` takes 88.2 s, its quantiles on the 6,502 ads are within 7.5e-10 in log rent of
the first version's, and the published `deals.json` is byte for byte the same.

The sampled table is byte for byte the live `deals.json`. The exact table has the same
ads in the same order with the same `below_share` and the same values in every column but
the median, the six bounds and `discount_pct`. The bounds differ from the live file by the
sampling noise they no longer carry:

| bound | max difference | median difference | ads whose ask changes side |
|---|---|---|---|
| median | 0.43% | 0.05% | 16 |
| lo50 (25%) | 0.49% | 0.06% | 16 |
| hi50 (75%) | 0.48% | 0.06% | 24 |
| lo80 (10%) | 0.78% | 0.09% | 18 |
| hi80 (90%) | 0.64% | 0.08% | 12 |
| lo95 (2.5%) | 1.46% | 0.21% | 4 |
| hi95 (97.5%) | 1.24% | 0.21% | 15 |

In all, 105 of the 6,502 ads have their ask on another side of at least one of the seven
values. `discount_pct` moves by at most 0.4 points.

In the live file 100 comparisons of an ask with a bound disagree with `below_share` (an
ask under the sampled 2.5% point with a share above 0.025, and so on). In the exact table
9 do, and in each of the 9 the ask equals the bound after the table rounds it to a dollar.

## The Today table

The Today table has about 937,000 apartments with 192 components each. On a synthetic
block of 2,500 such apartments the sampled quantiles take 1.7 s. The exact ones take 18 to
29 s on one thread and 5 to 7 s on eight, in under 0.5 GB. The whole table would then
take hours on one thread, and perhaps 20 to 40 minutes on the 16 cores of its Modal
container, where the whole job now takes 6 minutes and has a 55 minute limit. That was not
run, since it costs money. So the Today table keeps sampling by default and `--exact` is
there for when the cost is wanted.

## Tests

`frontier/tests/test_drift_quantiles.py` checks on a synthetic posterior (units with and
without a record, two-peaked rows, nu from 1.2 to 40) that the exact quantiles sit at their
levels of the cdf to 1e-6, that sampled quantiles with 8,000 replicates per draw come to
them, and that an ask is under a bound exactly when its share is under the bound's level.
Two tests cover the solver's safeguards: a seeded row on which the unguarded Newton step
cycled, and 400 seeded hard rows, each checked to 1e-6 at every level.
One existing test changed: `test_the_tables_draws_are_keyed_by_block` in
`test_drift_today.py` now names the sampled path in its comment and passes `exact=False`.
No pinned value or seed changed.
