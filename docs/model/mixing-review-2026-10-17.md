# Mixing review of the served model (2026-10-17)

I reviewed the served rent model and its Gibbs sampler for weakly identified parameters,
posterior dependencies and parameterizations slowing the chains. For each problem I propose a
change, and I rank the changes by the effective sample size each adds per second of sampling.
A proposal keeps the model's inferential assumptions unless its section says otherwise. I wrote
the predictions at the end before running any of the fits they cover.

## Measured fits

Both fits run `m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise-sizeunkslope-slopemin3-unitnu4`
with 2 chains of 4,500 sweeps.

- NB9, the served fit (`...-nb9-nostuy-lots2-v1-rows-5dbdc4f1-a100-...-l2un4`), covers 266,513
  rows in 6,644 buildings. On a Modal A100 its sampling phase took 1,548 s, or 0.344 s per sweep.
  It passes the gate, with min ESS 510 at 444 W 20th St and max R-hat 1.0058.
- The all-scraped fit (`...-all-scraped-v1-rows-e694a775-a40`) covers 67,735 buildings. Its
  sampling phase took 15,533 s, or 3.45 s per sweep. It fails the gate at the Carlyle, with ESS
  11.7 and R-hat 1.093.

I measure the integrated autocorrelation time (IACT) in sweeps, on log scales. A scalar's ESS
over two chains is then 9,000 / IACT, and the gate's bar of ESS 400 takes 200 x IACT sweeps per
chain.

| scalar | NB9 ESS | NB9 IACT | all-scraped ESS | all-scraped IACT |
|---|---|---|---|---|
| nu | 600 | 15.0 | 472 | 19.1 |
| building_scale | 799 | 11.3 | 280 | 32.1 |
| slowest sigma group | 956 (group 26) | 9.4 | 743 (group 42) | 12.1 |
| bedroom_slope_scale | 1,106 | 8.1 | 866 | 10.4 |
| fslope_scale_1 (sqft_unknown) | 1,115 | 8.1 | 950 | 9.5 |
| sigma | 1,264 | 7.1 | 1,169 | 7.7 |
| walk_scale | 1,319 | 6.8 | 819 | 11.0 |
| unit_scale | 1,552 | 5.8 | 1,021 | 8.8 |

On NB9, nu sets the run length, with building_scale next. On all-scraped, building_scale sets it
among the scalars, but the slowest building effects fall far below every scalar, for reasons in
the data (P6).

## Findings and proposals

### P1. The nu step is 13 to 15 times nu's posterior sd

Each sweep runs 10 Metropolis steps of the noise update (`noise_mh`, `gibbs.py` lines 1740 to
1775). A step moves all 68 group log sigmas with one shared step size and accepts each group
separately. It then moves the multipliers with the same step size, and finally log nu with a
second step size. Warmup sets both sizes from phase 1 (lines 2282 to 2290). In phase 2 it
multiplies both by a single factor, adapted from the groups' mean acceptance toward 0.3 (line
2359). So nu's step follows the groups' acceptance, and the trace records only the groups'
mean acceptance.

| | NB9 | all-scraped |
|---|---|---|
| adapted step on log nu | 0.118 | 0.051 |
| posterior sd of log nu | 0.0089 | 0.0034 |
| step / sd | 13 | 15 |
| sweeps with nu unchanged | 60% | 64% |
| acceptance per step, implied | 0.051 | 0.043 |
| lag-1 autocorrelation | 0.86 | 0.88 |
| IACT | 15.0 | 19.1 |

Accepted moves have a median size of 0.0046 on NB9 and 0.0018 on all-scraped. From those I put
nu's sd, given the rest of the state, at about 0.56 of its marginal sd. The squared correlation
between nu and the rest of the state then comes to about 0.7. With a well-sized step, nu should
approach the Gibbs limit for that dependence, an IACT of (1 + 0.7) / (1 - 0.7), or about 5.7.

The sigma groups share a step, though their posterior sds on log sigma run from 0.009 to 0.135.
Narrow groups take steps far larger than their sd, and wide groups take steps far smaller.

I propose these sampler changes in `gibbs.py`:

- adapt nu's step from nu's acceptance toward 0.44, and trace that acceptance;
- give each sigma group and each multiplier its own step, sized in phase 1 from its own sd and
  adapted from its own acceptance toward 0.44.

Both changes leave the posterior and the cost of a sweep as they are.

### P2. building_scale moves only as fast as the building effects

Two updates move building_scale: the collapsed joint proposal over 79 scales, and a draw given
the building effects b. Given b, the sd of log building_scale is about 1/sqrt(2N) for N
buildings: 0.0087 on NB9 and 0.0027 on all-scraped. The marginal sds come out wider, at 0.0207
and 0.0126, because the data constrain many b only weakly (P3). For a two-block Gibbs sampler
with those sds I expect an IACT of 10.3 on NB9 and 41.6 on all-scraped. The fits show 11.3 and
32.1. The IACT grows with the number of buildings, so it worsens as the fits cover more of the
city.

The joint proposal adds little. Its adapted step moves building_scale by 0.146 of its posterior
sd on NB9 and 0.047 on all-scraped. An efficient random walk in 79 dimensions would step
2.38 / sqrt(79), or 0.27 sd, and would still need an IACT in the hundreds.

I propose two fixes, in this order:

- (a) Config only: add building_scale to `--solo-scales`. The solo update integrates out the
  latent effects with one `block_solve`. Since building_scale isn't in `PART_SCALES`, it skips
  `block_parts`. On CPU one solve took 2.8 s of an estimated 36.6 s sweep, so I expect about 8%
  more time per sweep. I expect building_scale's IACT to fall to 4 to 8.
- (b) Code: a rescale move on (building_scale, b), like the walk, unit and line moves. Each step
  costs a pass over the rows, with no solve.

bedroom_slope_scale mixes the same way (IACT 8.1 and 10.4). On NB9 it won't set the run length
after P1 and P2, so I'd add a solo for it only once it does.

### P3. Building levels anchored in 2010 are weakly identified

b is each building's level on the walk's first knot, 2010 H1, where the walk starts at 0. Most
buildings' rows come years later. The data then constrain b plus the walk at the rows' dates and
say little about b alone. I measured the data's share of b's posterior precision,
1 - (posterior sd of b / building_scale)^2. Its median is 0.225 on all-scraped and 0.504 on NB9.

The walk also misfits the levels. Under a walk, the spread of building levels grows over time,
but on NB9 it stays flat at 0.14 to 0.17. The correlation between a building's 2015 and 2025
levels comes out at 0.813, against about 0.66 under the walk and about 0.82 under an AR(1) with
rho 0.89.

The registered AR(1) model (`-arwalk-fixedrho`, #748) replaces the walk with a stationary
deviation around b. b then becomes the building's long-run level, and all its rows inform it. On
NB9 the unitnu4 AR fit raises the data's share of b from 0.504 to 0.719, and building_scale's
ESS by 52% for 2% more time. Its paired PSIS-LOO against the plain unitnu4 fit is +433.2, with a
row-level SE of 44.0. The framework's building-grouped SE will be wider. Modeling's first AR fit,
on older data, gave +395 with SE 55 by building. The NB9 AR fit failed the gate only at
346 W 36th St, and latest-ask-v9 (#977) corrected that building's stale asks.

I propose refitting the AR fixedrho unitnu4 model on NB9 with latest-ask-v9. It replaces the
walk with a stationary deviation, a change of assumption, so it goes through the paired LOO and
the latest split like any model change.

### P4. The gate checks b, while the level at the data can mix slowly

The every-building check reads b. Since b and the walk trade off, b can mix well while the
building's level at its data mixes slowly. From the saved draws I computed each building's level
at its median data knot, b plus the walk there.

- On NB9, 2 buildings have a level ESS under 400, and the b check passes both. 870 Broadway
  (10 rows) has level ESS 125 and b ESS 3,529. 444 W 20th St has level ESS 269 and b ESS 510.
- On all-scraped, 80 buildings have a level ESS under 400, against 9 by b, and 11 of those fall
  under 100. 92 have R-hat over 1.01, some by chance among 67,735 buildings.

I propose adding the level at the median data knot to the every-building check. The check reads
the saved draws after the fit, at no sampling cost. Under it the served NB9 fit would fail at 870 Broadway, for a data reason (P6).

### P5. Raw feature slopes add a second building intercept

The model gives each building a slope on 4 feature columns, alongside their global coefficients:
`mu + sum(fslope[building] * x[:, fslope_index])` (`model.py` line 646). The columns enter raw.
Where a column holds a constant c across a building's rows, its slope s adds s * c to the
building's level, an intercept beside b. On the served NB9 fit:

- sqft_unknown holds a constant nonzero value in 33% of buildings, with 18% of rows. 84% of its
  sum of squares lies between buildings. Across buildings, the median posterior correlation of b
  with the building's sqft_unknown slope is -0.25.
- log_floor has 82% of its sum of squares between buildings, around a raw mean of 1.13.
- The posterior correlation of log building_scale with log fslope_scale_1 (sqft_unknown) is -0.32,
  and -0.26 on all-scraped.

In those buildings the level gets an extra prior variance of s^2 c^2, and b trades off with the
slope. The slopes are there to describe differences within a building, so this side effect
looks unintended.

I propose centering each slope column within its building, over training rows, in the slope term
only. The global coefficients keep the raw columns. A building with a constant column then gets
no level shift from that slope, and b carries the level alone. This changes the model a little:
the prior on building levels no longer depends on a building's mean floor or size-unknown share,
and the predictive spread for new buildings narrows slightly. So it needs its own full fit, the
paired LOO, new-building coverage on the latest split and the descriptive share. It would go in
as a new config option with its own registry name, leaving hashed model files as they are.

### P6. Conflicting prices behind the slowest buildings

On all-scraped, the 9 buildings failing the gate are 68 Clinton (62 rows), the Carlyle, 114A
Patchen, 116 Patchen, 124 DeKalb, 294 Carlton, 50 Newel, 90 Hull and 13 Cook. Each holds two
clusters of prices. The model can explain the outlying cluster through the unit effects (t, nu 4)
or through the residual (t, nu about 2.25), and the sampler moves between those explanations only
through the lam and kappa updates, so these buildings mix slowly. Only 2 of their 97 rows are
ask jumps like the 346 W 36th St ones.

On NB9 the two slow levels from P4 come from the same kind of conflict:

- At 870 Broadway, unit 1 asks $3,549 in 2023 as a 715 sqft one-bedroom and $7,899 in 2026 at
  875 sqft. Unit 3 appears as a 625 sqft one-bedroom ($3,300 in 2014, $3,500 in 2016) and as a
  1,000 sqft studio ($6,000 in 2017, $5,600 in 2022). Unit 2 appears as a 1,000 sqft studio at
  $6,700 in 2017 and as a one-bedroom at $3,500 in 2022. Two kinds of apartment seem to share
  these unit labels.
- At 444 W 20th St, one garden duplex asks $15,000 to $15,750 under 3 unit labels (gardendplx,
  garden, 1).

I'm handing these to Data improvements as candidates. A correction needs independent evidence
beyond the ad text.

### Later

- The rescale moves accept at 0.245, against a target of 0.44.
- The joint proposal runs `block_parts` and `block_solve` every sweep, 7.7 s of the estimated
  36.6 s CPU sweep, or 21%. With solos on the slow scales it adds little. After P1 and P2 a fit
  without it would show whether to drop it.
- The research plan found four chains don't batch on thelio's card. I haven't tested batching
  on Modal's A100 or H100.
- If P1 fails, fixing nu at its median (`nu_fixed` exists) is a fallback. Its posterior sd is
  0.34% on all-scraped.

## Ranking by ESS per second

For each proposal I divide the IACT of the slowest scalar before the change by its IACT after,
then divide by the change in seconds per sweep. On all-scraped the building effects stay far
below the scalars until the P6 data work happens.

| proposal | kind | time per sweep | NB9 gain | all-scraped gain | posterior |
|---|---|---|---|---|---|
| P1 nu and group steps | sampler code | same | 1.33x (nu 15.0 to building_scale 11.3) | none alone | same |
| P2a building_scale solo | config | +8 to 10% | none alone; 1.45x with P1 (to group 26 at 9.4) | 1.55x alone (to nu 19.1); 2.4x with P1 (to group 42 at 12.1) | same |
| P3 AR fixedrho | registered model | +2% | building_scale ESS +52% | not measured | changes |
| P4 level check | gate | none | stricter gate | stricter gate | same |
| P5 centered slopes | model | same | small | small | changes slightly |
| P6 conflicting prices | data | none | 2 buildings | 9 buildings | data |

The all-scraped fit can't pass the gate within the hour cap even after P1 and P2. Prepare and
warmup take 912 s and 900 s, which leaves about 520 sweeps per chain, and at an IACT of 12 two
chains give an ESS of about 87.

## Tests and predictions

Each test runs as its own Modal full fit on NB9, about $2 on an A100. The control is Modeling's
next refit of the served model on latest-ask-v9 data. A test uses the same model and data as the
control and differs only as stated. For the sampler tests the posterior stays the same, so I
compare ESS per second of sampling, and paired PSIS-LOO should agree within 2 SE.

### P2a: building_scale solo (config only)

The fit adds building_scale to the solo list:
`--solo-scales walk_scale,fslope_scale_0,fslope_scale_1,fslope_scale_2,fslope_scale_3,building_scale`.

Medians with 80% intervals:

1. building_scale IACT: 5.5 (3.5 to 8), against 11.3 (9 to 14) in the control.
2. building_scale solo acceptance: 0.45 (0.35 to 0.55).
3. Seconds per sweep: +9% (+5% to +15%) over the control.
4. nu stays the slowest scalar at IACT 15 (12 to 19), so the min scalar ESS moves by less than
   15%.
5. Paired PSIS-LOO against the control: 0 (-10 to +10) nats.

The prediction misses if building_scale's IACT comes out above 8, if seconds per sweep rise by
more than 15%, or if the LOO difference exceeds 2 SE.

### P1: nu and sigma-group steps (sampler code)

The fit runs the P1 changes in `gibbs.py` with the control's solo list.

Medians with 80% intervals:

1. nu acceptance per step: 0.44 (0.38 to 0.50).
2. nu lag-1 autocorrelation: 0.70 (0.60 to 0.78).
3. nu IACT: 6 (4.5 to 8.5).
4. Slowest sigma group IACT: 8 (6 to 10).
5. Seconds per sweep: within 3% of the control.
6. Paired PSIS-LOO against the control: 0 (-10 to +10) nats.

The prediction misses if nu's IACT comes out above 8.5, if the slowest group's IACT rises above
11, or if the LOO difference exceeds 2 SE.

### P3: AR fixedrho on latest-ask-v9

The fit is `...-slopemin3-unitnu4-arwalk-fixedrho` on the control's data.

1. Chance of passing the gate: 75%.
2. Paired PSIS-LOO against the control: +420 (+300 to +540) nats.
3. building_scale ESS per second of sampling: 1.5x (1.2x to 1.9x) the control's.
4. Median data share of b: 0.72 (0.66 to 0.78).

The prediction misses if the LOO gain falls outside +300 to +540 or the ESS ratio falls under
1.2x.

### P4: level check on the control

This one is a free check on the control's saved draws.

1. Buildings with level ESS under 400 that pass the b check: 2 (1 to 4).
2. 870 Broadway is one of them, unless Data improvements has changed its rows by then.

The prediction misses if the check flags none, or more than 4.

### P5: slopes centered within building

The fit is the control's model with the slope columns centered within building.

1. Paired PSIS-LOO against the control: +15 (-40 to +70) nats, a tie.
2. building_scale: +4% (0% to +9%).
3. fslope_scale_1: -20% (-40% to -5%).
4. Posterior correlation of log building_scale with log fslope_scale_1: 0.0 (-0.10 to +0.10).
5. building_scale IACT: 10% lower (0% to 25%).
6. New-building 80% and 95% coverage on the latest split: within 1 pp of the control's.

The prediction misses if the correlation stays below -0.15, if fslope_scale_1 doesn't fall, or
if new-building coverage moves by more than 1 pp.
