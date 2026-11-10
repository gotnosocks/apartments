# The drift model

The current model of the project, written on 2026-11-10. It prices an apartment on a date
and says how sure it is, so that an ad asking well below the model's range stands out as a
candidate deal. This page gives the model, the sampler, the score, the checks and the
results. The predictions written before each fit, and the residual checks that led to the
model, are in [the note of 2026-11-10](../notes/drift-2026-11-10.md).

## Results

`drift` is the served model. Its three full fits of 2026-11-10 (round six of that day's
note) all pass the convergence gate, the first fits in the project with a unit term to do
so on the full data.

| Fit | Data | Chains x draws | Worst split R-hat | Least bulk ESS | Cost |
|---|---|---|---|---|---|
| f6 | latest split: 1,706,824 ads fitted, 189,647 held out | 4 x 4,060 | 1.0050 | 1,207 | $3.75 |
| m6 | market of 2026-11-09: 1,893,502 fitted, 6,774 open ads predicted | 4 x 3,680 | 1.0038 | 1,034 | $3.62 |
| k6 | backtest as of 2025-11-10: 1,754,606 fitted, 9,346 open ads predicted | 4 x 3,740 | 1.0051 | 1,072 | $3.69 |

On the 189,647 held-out ads (the newest ad of every apartment with at least two):

| Model | elpd | Median abs. error (log) | RMSE | Coverage at 50 / 80 / 90 / 95% | Gate |
|---|---|---|---|---|---|
| Fit 8 | 148,234 | 0.0664 | 0.1158 | 0.493 / 0.798 / 0.903 / 0.954 | passed |
| Kitchen sink | 156,105 | 0.0636 | 0.1112 | 0.495 / 0.801 / 0.904 / 0.955 | passed |
| Fit 4 | 177,137 | 0.0560 | 0.1018 | 0.496 / 0.789 / 0.893 / 0.949 | missed |
| `drift` (f6) | 195,320 | 0.0506 | 0.0949 | 0.513 / 0.799 / 0.896 / 0.949 | passed |
| `drift-building` (b6, pooled) | 230,885 | 0.0406 | 0.0825 | 0.525 / 0.808 / 0.901 / 0.952 | missed by 0.0006 |

Posterior means in f6: the unit's lasting level `ss` 0.0483, its drift `sd` 0.0786 with a
time scale `tau` of 5.56 years, `nu` about 1.7.

The backtest (k6): the 9,346 ads open on 2025-11-10, each scored at its first ask.

| Place of the first ask in the model's range | Ads | Median days on market | Share later cut |
|---|---|---|---|
| lowest tenth | 501 | 27 | 18% |
| second | 454 | 32 | 26% |
| fifth | 725 | 47 | 42% |
| ninth | 1,319 | 56 | 69% |
| highest tenth | 2,367 | 62 | 79% |

`drift-building` adds a path per building and is worth another 35,565 elpd on the same
ads. Its chains agree on every scale to three digits, and its pooled fits miss the gate on
one quantity each: drift_tau at R-hat 1.0106 on the latest split and bld_sd[outer] at
1.0135 on the market data. It is not served. The note gives the reason (a chain of four in
an hour is too short for the R-hat line, whatever the number of chains) and what was tried
next. ROUND-SEVEN-PLACEHOLDER

## The model

Each row is one ad. Its target `y` is the log of its final asking rent, gross of any free
months.

```
y_i ~ StudentT(nu, mean_i, sigma_group(i))

mean_i = x_i beta                 columns
       + L(t_i)                   citywide time
       + eta_building(i)          building level
       + u_i                      unit level
       + a_building(i)(quarter_i) building drift      (drift-building, drift-local)
       + a_nbhd(i)(quarter_i)     neighbourhood drift (drift-local)
```

| Term | Prior | Size |
|---|---|---|
| `x beta` | Bedroom and bath steps, floor curves with Gaussian process priors, unit features, building amenities, lot attributes, ad fields, and the unit means of the unit columns | about 250 coefficients |
| `L(t)` | A weekly random walk plus season | one level a week since 2015 |
| `eta_s` | `Normal(F(s), b_zone)`, with `F` a smooth surface at 1 km resolution in each zone (Manhattan, the outer boroughs) | 68,000 buildings |
| `u_i = s_k + d_k(t_i)` | `s_k ~ Normal(0, ss^2)`, the unit's lasting level. `d_k` is an Ornstein-Uhlenbeck process: `Var d_k(t) = sd^2`, `Corr(d_k(t), d_k(t')) = exp(-abs(t - t') / tau)`, with `t` in years | 935,000 units |
| `a_g(m)` | A stationary AR(1) per group: `a_g(m) = rho a_g(m-1) + Normal(0, s^2 (1 - rho^2))`. One step a quarter. `s ~ HalfNormal(0.1)`, `rho ~ Uniform(0, 1)` | one path per building, one per neighbourhood |
| Noise | Student-t, with `sigma` per bedroom group and one `nu` | |

A unit is a pair of building and `unit_id`. A row with no `unit_id` is a unit of its own.

The first three terms are the kitchen sink model of 2026-10-24
(`building_zones_kitchen_sink.py`), less two bath steps that 37 and 26 ads set
(`drift.DROPPED_STEPS`). The unit term and the two drift terms are new.

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
terms that would otherwise pin what it draws.

1. **Unit precisions.** Given the scales, a unit's rows are jointly Gaussian once `u` is
   integrated out, with covariance `D^-1 + K`, where `D` holds the rows' precisions and
   `K_ij = ss^2 + sd^2 exp(-abs(t_i - t_j) / tau)`. No unit has more than 22 ads, so the
   precision `W = (D^-1 + K)^-1` is a small dense matrix, built for every unit in padded
   batches.
2. **Coefficients, walk and surface** (`theta`), drawn in one block with the building levels
   and the unit levels integrated out. This is the step that fit 4 lacked: its coefficients
   were drawn with the unit effects held fixed, and mixed slowly against them.
3. **Every scale of the units and the noise together** (`update_scales`): `(ss, sd, tau)`,
   the four `sigma` and `nu`, slice sampled along eight directions set in the warmup,
   with `u`, the building levels and the building paths all integrated out. The density is the units' Kalman likelihood plus one term a building from
   `B' W B`, where `B` maps the building's state to its rows, and `W` is rebuilt at every
   point tried. `nu` has no closed form with `lam` integrated out, so `lam` rides along:
   each row keeps its standardized `log lam` while `nu` moves.
4. **Building columns** (`update_slow`, with a building path only). The coefficients of
   the `bld:` columns are drawn once more with `u`, the levels and the paths integrated
   out. A building amenity code is set from the building's ads up to each row's day, so it
   changes within a building over time and a path can stand in for it: given the paths,
   as step 2 has them, these coefficients are pinned.
5. **Buildings** (`update_cells`). A building's state is its level and its path at the
   quarters where it has an ad. Each zone's spread and the path's `(log s, logit rho)` are
   slice sampled with the states and `u` integrated out, then every building's state is
   drawn in one go from a dense system of at most 53 dimensions, and the path's other
   quarters are filled in between.
6. **Unit levels** `u`, by Matheron's rule: a draw from the prior, corrected toward the data.
7. **Noise**: `nu`, `sigma`, then the scales `lam`, given `u`.
8. The walk's step size, the surface amplitudes and the Gaussian process scales, as in the
   kitchen sink.

The model failed the convergence gate four times on 2026-11-10 before this sweep, each
time for the same reason one level apart: a scale was drawn given a latent that pinned it
(sigma given `u`, a building's path given `u`, the unit scales given the paths, `nu` given
`u`). The chains agreed with each other and crept. Steps 3 to 5 are what came of it, and
[the note](../notes/drift-2026-11-10.md) has each round's predictions and results.

**The directions of step 3.** The step samples the scales given theta and the rows'
standardized mixing scales, and that density is narrower than the posterior and tilted
against it: with the mixing scales held, `nu` and the four `sigma` can move a long way
together and hardly at all apart. Directions cut from the covariance of the warmup draws
cross that ridge at an angle, and the unit scales then took 23 to 37 sweeps to forget where
they were. So the warmup sets the directions twice, each time first from the draws'
covariance and then from the curvature of the step's own density at the chains' states
(`scales_curvature`, `conditional_dirs`). With those the unit scales take 8 to 10 sweeps.
The fit's log prints how much of the posterior's variance one scale update can renew along
each axis; in the pilot the least was a quarter.

The slice updates place an interval at random around the current point and only shrink it
(`slice_along`). The project's older samplers step the interval out a fixed number of times
on each side first, and a review of this model showed that the fixed count narrows the
draws when the slice is longer than the stepped-out interval (`test_drift_local.py` holds
the check). The older fits' scale parameters may be slightly too tight for that reason.

**Time.** A fit has an hour (`ops/modal/cap.py`). Outside the sweeps it spends 13 to 15
minutes on the image, the design, the compile and the output. The sweeps stop at a kept draw
once they have taken 42 minutes (`Settings.budget_seconds`), and the fit reports the draws it
has. Mid-run checkpoints cost 2 to 4 minutes each and are off (`Settings.checkpoints`).

Measured on the full data, four chains: a `drift` sweep takes 0.55 to 0.59 s on an H100
(0.8 s on an A100), so an hour holds about 4,100 draws a chain after a warmup of 500. A
`drift-building` sweep takes 1.14 to 1.28 s on an H100 (1.75 s on an A100), of which the
redraw of the `bld:` columns is about 0.3 s, so an hour holds 1,350 to 1,600 draws a chain.
Sweeps to an independent draw of the slowest scales: 7 to 16 in `drift` (sigma of the
one-bedroom group slowest), 12 to 16 in `drift-building` (drift_tau slowest). In the pilot
of round six every `bld:` coefficient took under 4.

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
ops/modal-fit --gpu H100 --dataset DIR --split latest COMMIT LABEL drift-building b0 4 500 6000 25 --seed 1
python -m rentfrontier.drift_pool RUN PART PART ...   # one run from a fit's containers
python -m rentfrontier.drift_score RUN       # pred_scores.npz and the headline scores
python -m rentfrontier.drift_deals validate BACKTEST_RUN --ads ADS --out validation.json
python -m rentfrontier.drift_deals publish MARKET_RUN --out /data1/apartments/site/deals \
    --registry REGISTRY --backtest BACKTEST_RUN --heldout LATEST_RUN
```

The three model names are `drift`, `drift-building` and `drift-local`
(`drift.py`, `drift_building.py`, `drift_local.py`). `--split market` fits a market or
backtest dataset.

**An hour a container.** A fit stops its sweeps at 2,520 s and saves the draws it has
(`Settings.budget_seconds`), so the draws asked for are a ceiling and 6,000 means "all the
hour holds". A fit can be launched as several containers that differ only in `--seed`, and
`rentfrontier.drift_pool` writes one run from them: every part's chains, cut to the
shortest part's draws, with the convergence table computed over all of them. The number of
containers is written in the fit's note before launch, and a fit that misses the gate does
not get another.

**What pooling buys and what it does not.** More chains add effective draws and make the
R-hat estimate steadier. They do not lower it: split R-hat compares half-chains, and its
expected excess over 1 is about 1 / (2 x the effective draws in one half-chain). A quantity
that takes 16 sweeps a draw needs half-chains of about 2,000 draws to sit near 1.004, and
at 800 it sits at the 1.01 line however many chains there are (the reviewer's simulation
of chains like these: 0.0094, 0.0092 and 0.0094 over 1 at 4, 12 and 36 chains). Put as a
rule: the R-hat line needs well over 50 effective draws in every half-chain, so a total
ESS well over 100 times the number of chains. With 4 chains that is the ESS gate of 400;
with 12 it is 1,200, where the pooled fit b6 landed (1,184, R-hat 1.0106). So size a fit by
the length of a chain first (fewer chains a container make a sweep faster) and by the
number of chains second.

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
- **First asks run high.** The model is fitted to final asks. A quarter of the backtest's
  ads opened in the top tenth of their range, and on the market of 2026-11-09 the lowest
  twentieth of the score holds 302 ads where an even spread would put 339. The score ranks
  ads against each other well (the backtest), and its level is conservative for an ad that
  has not yet been cut.
- **The building path steps by quarter**, to fit a fit in its hour. A monthly path scored
  2,590 elpd higher in round two (233,273 against 230,683), all of it on ads with another
  unit's ad in the same quarter.
- **`drift-building` has not passed the gate.** Its pooled fits of round six miss by 0.0006
  and 0.0035 in R-hat on one quantity each. On the market and backtest data the outer
  boroughs' building spread also holds a small offset from chain to chain that does not
  move within a run; its cause is not known (the note gives the test to run next).
- **`drift-local` was not refitted** after round two, where the neighbourhood path added
  952 elpd to the building model, 2.5% of the building path's gain.
