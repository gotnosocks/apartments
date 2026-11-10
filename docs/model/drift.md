# The drift model

The current model of the project, written on 2026-11-10. It prices an apartment on a date
and says how sure it is, so that an ad asking well below the model's range stands out as a
candidate deal. This page gives the model, the sampler, the score, the checks and the
results. The predictions written before each fit, and the residual checks that led to the
model, are in [the note of 2026-11-10](../notes/drift-2026-11-10.md).

## Results

RESULTS-PLACEHOLDER

## The model

Each row is one ad. Its target `y` is the log of its final asking rent, gross of any free
months.

```
y_i ~ StudentT(nu, mean_i, sigma_group(i))

mean_i = x_i beta                 columns
       + L(t_i)                   citywide time
       + eta_building(i)          building level
       + u_i                      unit level
       + a_building(i)(month_i)   building drift      (drift-building, drift-local)
       + a_nbhd(i)(quarter_i)     neighbourhood drift (drift-local)
```

| Term | Prior | Size |
|---|---|---|
| `x beta` | Bedroom and bath steps, floor curves with Gaussian process priors, unit features, building amenities, lot attributes, ad fields, and the unit means of the unit columns | about 250 coefficients |
| `L(t)` | A weekly random walk plus season | one level a week since 2015 |
| `eta_s` | `Normal(F(s), b_zone)`, with `F` a smooth surface at 1 km resolution in each zone (Manhattan, the outer boroughs) | 68,000 buildings |
| `u_i = s_k + d_k(t_i)` | `s_k ~ Normal(0, ss^2)`, the unit's lasting level. `d_k` is an Ornstein-Uhlenbeck process: `Var d_k(t) = sd^2`, `Corr(d_k(t), d_k(t')) = exp(-abs(t - t') / tau)`, with `t` in years | 935,000 units |
| `a_g(m)` | A stationary AR(1) per group: `a_g(m) = rho a_g(m-1) + Normal(0, s^2 (1 - rho^2))`. Monthly for buildings, quarterly for neighbourhoods. `s ~ HalfNormal(0.1)`, `rho ~ Uniform(0, 1)` | one path per building, one per neighbourhood |
| Noise | Student-t, with `sigma` per bedroom group and one `nu` | |

A unit is a pair of building and `unit_id`. A row with no `unit_id` is a unit of its own.

The first three terms are the kitchen sink model of 2026-10-24
(`building_zones_kitchen_sink.py`), unchanged. The unit term and the two drift terms are new.

### Why a unit level that drifts

The kitchen sink has no unit effect. Its unit information comes from columns that average
the unit's earlier ads. An earlier model (fit 4) had a constant effect per unit, scored much
better on held-out ads, and failed the convergence gate: 68 of its 121 coefficients mixed
too slowly against 935,000 unit effects.

A check on residuals that cost nothing showed what a constant effect misses. Two ads of one
unit share 66% of their residual variance half a year apart and 21% eight years apart. So a
unit's recent ads say much more about its next ask than its old ones, and a constant effect
weighs them all the same. The drift model splits the unit's level into a part that lasts
(`s`) and a part that fades over a few years (`d`). A prediction for a unit then weighs each
earlier ad by how long ago it ran, and the predictive range is narrow for a unit with a
recent ad and wide for a unit the model has never seen.

### Why drift per building and per neighbourhood

With units accounted for, the residuals of ads in one building still move together for a few
months. Two ads of different units of one building within three months correlate at 0.26.
The correlation is 0.13 at three to six months, 0.075 at six to twelve, and gone after two
years. A landlord who reprices a building does it for every unit at once, and the unit term
cannot see that until each unit lists again. The building drift term carries it from one
unit's ad to its neighbours' ads.

Neighbourhoods show the same on a smaller scale: a neighbourhood's residuals by year have a
standard deviation of 0.013, and the last two years diverge between Manhattan and the outer
boroughs. The neighbourhood term follows that.

## The sampler

A blocked Gibbs sweep in JAX on one GPU, four chains. The Student-t is written as a scale
mixture, `y_i ~ Normal(mean_i, sigma^2 / lam_i)`, so that given the scales `lam` every
location term is Gaussian. The sweep is partially collapsed: each step integrates out the
terms that would otherwise slow it.

1. **Unit precisions.** Given the scales, a unit's rows are jointly Gaussian once `u` is
   integrated out, with covariance `D^-1 + K`, where `D` holds the rows' precisions and
   `K_ij = ss^2 + sd^2 exp(-abs(t_i - t_j) / tau)`. No unit has more than 22 ads, so the
   precision `W = (D^-1 + K)^-1` is a small dense matrix, built for every unit in each sweep
   in padded batches.
2. **Coefficients, walk and surface** (`theta`), drawn in one block with the building levels
   and the unit levels integrated out. This is the step that fit 4 lacked: its coefficients
   were drawn with the unit effects held fixed, and mixed slowly against them.
3. **Building spread and levels**, with the unit levels integrated out.
4. **Unit levels** `u`, by Matheron's rule: a draw from the prior, corrected toward the data.
5. **Local drift**, one term at a time, given everything else. The pair `(log s, logit rho)`
   is slice sampled on the marginal likelihood from a Kalman filter over each group's steps,
   with the paths integrated out. Then the paths are drawn by backward sampling.
6. **Noise**: `nu`, `sigma`, then the scales `lam`.
7. **Unit scales** `(ss, sd, tau)`, slice sampled on a Kalman filter's marginal likelihood
   of each unit's rows with `u` integrated out, along three directions set from the warmup
   draws' covariance, since the three trade off against each other.
8. The walk's step size, the surface amplitudes and the Gaussian process scales, as in the
   kitchen sink.

The slice updates in steps 5 and 7 place an interval at random around the current point and
only shrink it. The project's older samplers step the interval out a fixed number of times on
each side first, and a review of this model showed that the fixed count narrows the draws
when the slice is longer than the stepped-out interval (`test_drift_local.py` holds the
check). The older fits' scale parameters may be slightly too tight for that reason.

A full fit (300 warmup sweeps, 1,000 draws, 1.9 million rows) takes about 10 minutes to
build its design, 4 to compile and under a second a sweep on an A100.

The convergence gate is the project's: split R-hat at most 1.01 and bulk ESS above 400 on
every scalar and coefficient. A fit that misses the gate is not rerun on another seed.

## Predictions and the deal score

A unit's level at a new ad depends on its training ads, so the fit itself predicts every row
outside its training rows at each kept draw. Given the draw, the unit's level at the new
date is `Normal(k' W e, k0 - k' W k)`, where `e` holds the unit's training residuals, `k`
their covariances with the new ad and `k0 = ss^2 + sd^2`. A unit with no training ad gets
mean 0 and the full spread. Each drift path is carried from its group's last ad to the new
date by the same AR(1) recursion.

`drift_score.py` turns the kept draws into a predictive distribution for each row. The
Student-t noise is integrated on a grid of 96 nodes in the log of its scale, so the density
and the cumulative share at any rent are exact to seven digits. From it come

- `elpd`, the log predictive density at the realized ask, summed over the held-out rows,
- the predictive median and the 50%, 80%, 90% and 95% intervals,
- `below_share`, the share of the predictive distribution below the ask.

`below_share` is the deal score. An ask with `below_share` 0.03 is lower than 97% of what
the model expects that apartment to ask on that day. The Deals page shows the complement as
"lower than".

A low score has three possible causes, and the model cannot tell them apart: the landlord
priced low, the apartment has a flaw the ad does not state, or the ad is wrong. The
backtest says how often it is the first.

## How a fit is judged

**Held-out ads.** The latest split holds out the newest ad of every unit with at least two
ads: 189,647 ads. Each is predicted from ads that ran before it. Models are compared on the
same rows by `elpd`, by the error of the predictive median and by the coverage of the
intervals.

**Backtest.** `rentfrontier.market` builds the dataset as it stood on a past day (the ads
whose first day came later are set aside, and the ads open on that day are held out). A fit
on it scores the first ask of every ad then on the market. `drift_deals validate` tabulates
what happened next by tenth of the score: days on the market, and the share whose ask was
cut or raised before the ad closed. If the score finds real deals, the low tenths should
rent faster and be cut less often.

**The market.** The same build as of the last scraped day holds out the ads on the market
now. `drift_deals deals` scores them and `drift_deals publish` writes the Deals page's
files.

**Tests.** `frontier/tests/test_drift.py`, `test_drift_local.py`, `test_drift_score.py`,
`test_drift_deals.py` and `test_market.py`. Each sampler step is checked against dense
algebra on a small design: the unit precisions, the collapsed system for `theta`, the Kalman
likelihoods against the dense Gaussian, the backward sampler's mean and covariance. Two
recovery tests plant a unit process and a building process in simulated data and check that
the fit recovers the scales and that the held-out standardized errors have unit spread.

## Running it

```sh
ops/market-dataset HASH                      # market and backtest datasets from a pipeline build
ops/modal-fit --dataset DIR --split latest COMMIT LABEL drift-building b0 4 300 1000 5   # or --split market
python -m rentfrontier.drift_score RUN       # pred_scores.npz and the headline scores
python -m rentfrontier.drift_deals validate BACKTEST_RUN --ads ADS --out validation.json
python -m rentfrontier.drift_deals publish MARKET_RUN --out /data1/apartments/site/deals \
    --registry REGISTRY --backtest BACKTEST_RUN --heldout LATEST_RUN
```

The three model names are `drift`, `drift-building` and `drift-local`
(`drift.py`, `drift_building.py`, `drift_local.py`).

## Known limits

- **The backtest sees some later ad fields.** An ad's feature codes, amenities, laundry and
  dishwasher fields come from its latest record, which can postdate the backtest's day. No
  price leaks. The effect on the backtest's ranking should be small, and it is not measured.
- **Asks are gross.** `first_ask` and `latest_ask` are both gross of concessions. Months
  free enter as a column, so the model's range is for the gross ask given the concession.
- **Closed is not rented.** The data has asks, not leases. An ad that left the market at a
  price may have rented below it.
- **A few ads train as closed that are not.** In the market dataset 1,062 ads in contract,
  in draft or under review are training rows. The backtest's open ads include 32 drafts.
- **New units get wide ranges.** A unit with no earlier ad is priced from its columns, its
  building and the local drift, and its range is about twice as wide as a unit with a recent
  ad. Its score is honest and less sharp.
- **The design needs about 15 GB of host memory**, so full fits run on Modal.
