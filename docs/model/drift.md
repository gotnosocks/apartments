# The drift model

The current model of the project, written on 2026-11-10. It prices an apartment on a date
and says how sure it is, so that an ad asking well below the model's range stands out as a
candidate deal. This page gives the model, the sampler, the score, the checks and the
results. The predictions written before each fit, and the residual checks that led to the
model, are in [the note of 2026-11-10](../notes/drift-2026-11-10.md).

[drift-explainer.html](drift-explainer.html) is the visual walk through the model and its
results, also published at https://claude.ai/artifact/CidAo43kMNH2Kw7GHwTHf7 (private to
Ben unless shared). It is built from `docs/notes/drift-2026-11-10/artifact-data/extract-full.json`
by `artifact/pagedata.py` and `artifact/build.py` in the same folder.

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
| `drift-building` (b6, pooled) | 230,885 | 0.0406 | 0.0825 | 0.525 / 0.808 / 0.901 / 0.952 | missed on one scale |

Posterior means in f6: the unit's lasting level `ss` 0.0483, its drift `sd` 0.0786 with a
time scale `tau` of 5.56 years.

The backtest (k6): the 9,346 ads open on 2025-11-10, each scored at its first ask.

| Place of the first ask in the model's range | Ads | Median days on market | Share later cut |
|---|---|---|---|
| lowest tenth | 630 | 28 | 18% |
| second | 627 | 35 | 26% |
| fifth | 905 | 49 | 39% |
| ninth | 1,067 | 58 | 53% |
| highest tenth | 1,566 | 61 | 60% |

The first ask of an ad with free months is put net of them, the basis of the model's asks
(`drift_deals.first_net`). The table published before 2026-11-10 10:05Z did not do this
and read 79% cut in the highest tenth; the note has the correction. Over the 7,092 ads
with no free months, which need no change of basis, the stay runs from 27 to 60 days and
the share cut from 15% to 63%.

`drift-building` adds a path per building and is worth another 35,565 elpd on the same
ads. It is not served: every one of its pooled fits misses the gate.

| Fit | Chains by draws | Worst R-hat | Least ESS | elpd |
|---|---|---|---|---|
| b6, latest split | 12 by 1,600 | 1.0106, drift_tau | 1,184 | 230,885 |
| n6, market | 12 by 1,350 | 1.0135, bld_sd[outer] | 1,371 | |
| j6, backtest | 8 by 1,550 | 1.0447, bld_sd[outer] | 68 | |
| b7, latest split | 6 by 3,440 | 1.0130, bld_sd[outer] | 1,485 | 230,861 |
| n7, market | 6 by 2,920 | 1.0202, bld_sd[outer] | 159 | |

Round six's misses on drift_tau and sigma were chain length: with chains twice as long
(round seven, two chains a container) every quantity but one is well inside the gate
(next worst R-hat 1.0067 in b7 and 1.0048 in n7), and the score does not move. The one
that is left is bld_sd[outer], the spread of building levels in the outer boroughs.

The best-supported cause is about ten buildings in 68,000. Seven or eight of the ten
have a cluster of ads coded as studios or 1-bedrooms at the rents of the building's 3-
and 4-bedrooms. In the eight buildings whose ads were read, every such ad has a blank or
placeholder text and the source's own count of 0 bedrooms; what those apartments really
are is inferred from their rents and unit labels. One of the ten may be an honest
mixture and one is a building far below its neighbourhood. A
studio at a 3-bedroom's rent is 0.5 to 0.8 above what the model expects, a building of
them sits 5 to 6 spreads from its neighbourhood, and the sampler takes thousands of
sweeps to settle whether the building is dear or the rows are outliers: warmup leaves it
dear, and in round seven's longer chains these buildings move to the other answer one at
a time and none moves back. Under the normal prior on the levels each such building
moves the zone's spread by its square over 2 b N, with an N of about 14,000 implied by
the fitted slope, and every
building with little data follows the spread. Across chains the summed squares of ten
buildings explain 95 to 98% of the differences in bld_sd[outer], in all three pooled
runs, and 90 to 97% when the ten are picked on half the draws and tested on the other
half. The ten ranked just below them by the same rule explain 0 to 26%, and random tens
reach 52 to 66% at the 95th percentile, on six to eight chain means a run (within chains
the ten explain 16 to 51%). So a fit probably ends with its chains at different stages of the same
arrival, which is what R-hat would then be reporting, and the outer spread it gives
(0.091) is probably high by about 0.0003. None of these buildings has a predicted
ad and the held-out predictions show no mark of it.

What fixes it, in the project's order. The data: 1,596 training ads coded as
studios name two or more bedrooms in a text that never says "studio" (25 of 40 read were
whole apartments, so roughly 750 to 1,250 of them), and 4,517 more are placeholder
listings no text can sort; a rule for either needs a dataset and a fit of its own. The
model: a Student-t prior on the levels (`Settings.level_dof`, 4 degrees of freedom) takes
the leverage away whatever the data hold. Round eight ran it on one container, `b8c`,
with the settings and seed of `b7c`, the part of b7 that failed alone:

| | `b8c` (Student-t levels) | `b7c` (normal levels) |
|---|---|---|
| Own gate, two chains of 3,440 draws | passes, worst R-hat 1.0090 (nu) | fails, 1.0218 on bld_sd[outer] |
| bld_sd[outer], R-hat | 1.0057 | 1.0218 |
| The spread regressed on the ten buildings' squares, within chains | R squared 0.02 | R squared 0.84 |
| Held-out elpd | 230,794 | 230,668 |
| Median abs. error (log), coverage at 80% | 0.0407, 0.806 | 0.0407, 0.806 |

(A container of two chains scores about 190 under a pool of six, which is why both sit
under b7's 230,861.) One container is not a fit to publish from: `n7a` and `n7b` each
passed alone while their pool failed. The next step is the three full fits with
`--level-dof 4`, pooled from three containers each. The note has the evidence and the
scored predictions of rounds seven and eight.

## The model

Each row is one ad. Its target `y` is the log of its final asking rent, net of any free
months (the dataset's `latest_ask`).

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

**Cautions.** A fourth cause is in plain sight in the ad and unknown to the model. Of 22
ads read from the first 40 of the list of 2026-11-09, 12 were such: seven income-restricted
units, an office suite, an apartment open only to the building's owners, and others.
`rentfrontier.cautions` gives a row of the deals table a code for each reason it finds:
`income`, `not_home` and `owners_only` from the ad's own text, `beds` when the apartment's
ads carry more than one bedroom count, `off_market` from the ad's status. A caution changes
no score. The Deals page leaves cautioned ads out of its list unless asked, and says how
many. The text patterns were kept or dropped by reading every ad on the market that a
wider set of candidates matched (237 ads); the kept income pattern matches 55 ads, the 55
the readers classed as income-restricted. The dataset's own `income_restricted` flag, a model input, catches 22 of
those 55.

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
python -m rentfrontier.drift_deals texts MARKET_RUN --out TEXTS.parquet   # the ads' own texts
python -m rentfrontier.drift_deals publish MARKET_RUN --out /data1/apartments/site/deals \
    --registry REGISTRY --backtest BACKTEST_RUN --heldout LATEST_RUN --texts TEXTS.parquet
```

`texts` reads the pipeline's records file of the newest clean build (about a minute and
4 GB on thelio) and refuses a build other than the dataset's. Without `--texts` the table
carries only the cautions the dataset gives, and `meta.json` says the texts were not read.

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
- **Asks are net of free months, and price histories are gross.** `latest_ask`, the
  model's target, is the net-effective ask; 21% of the asks on the market of 2026-11-09
  are net, and the ad's own page shows the higher gross rent (the Deals page shows both).
  Months free also enter as a column. An ad's `first_ask` comes from its price history
  and is gross, so anything that compares the two must change basis first
  (`drift_deals.first_net`).
- **Closed is not rented.** The data has asks, not leases. An ad that left the market at a
  price may have rented below it.
- **A few ads train as closed that are not.** In the market dataset 1,062 ads in contract,
  in draft or under review are training rows. The backtest's open ads include 32 drafts.
- **New units get wide ranges.** A unit with no earlier ad is priced from its columns, its
  building and the local drift, and its range is about twice as wide as a unit with a recent
  ad. Its score is honest and less sharp.
- **The design needs about 15 GB of host memory**, so full fits run on Modal.
- **First asks run high.** The model is fitted to final asks. 17% of the backtest's ads
  opened in the top tenth of their range and 7% in the bottom tenth, and on the market of 2026-11-09 the lowest
  twentieth of the score holds 302 ads where an even spread would put 339. The score ranks
  ads against each other well (the backtest), and its level is conservative for an ad that
  has not yet been cut.
- **The building path steps by quarter**, to fit a fit in its hour. A monthly path scored
  2,590 elpd higher in round two (233,273 against 230,683; the monthly fit's chains did not
  mix, so the gap is a guide). The quarterly path was 2,762
  behind on ads with another unit's ad in the same quarter and slightly ahead elsewhere.
- **`drift-building` has not passed the gate.** Its pooled fits of round six miss by 0.0006
  and 0.0035 in R-hat on one quantity each. On the market and backtest data the outer
  boroughs' building spread also holds a small offset from chain to chain that does not
  move within a run. A quarter of it is a handful of buildings in two states; the cause
  of the rest is not known (the note, "The direct check").
- **`drift-local` was not refitted** after round two, where the neighbourhood path added
  952 elpd to the building model, 2.5% of the building path's gain.
