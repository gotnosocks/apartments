# Mixing review of the served model (2026-10-17)

I reviewed the served rent model and its Gibbs sampler, looking for weakly identified parameters,
posterior dependencies and parameterizations slowing the chains. For each problem I propose a
change. I then rank the changes by the effective sample size each adds per second of sampling on
Modal's GPUs. P1, P2 and P4 leave the posterior unchanged. P3 and P5 change the model's
assumptions, as described in their sections. I wrote each prediction at the end of this review
before running its fit.

## Measured fits

I measured mixing on two Modal fits of
`m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise-sizeunkslope-slopemin3-unitnu4`,
each with 2 chains of 4,500 sweeps on an A100-SXM4-40GB.

- The all-scraped fit (`...-all-scraped-v1-rows-e694a775-a40`), started at 10:15 pm ET on
  Oct 16, covers the full dataset: 1,575,187 rows in 67,735 buildings. Sampling took 15,533 s,
  or 3.45 s per sweep. The fit fails the gate at the Carlyle, with ESS 11.7 and R-hat 1.093.
- The served NB9 fit (`...-nb9-nostuy-lots2-v1-rows-5dbdc4f1-a100-...-l2un4`) covers 266,513
  rows in 6,644 buildings. Sampling took 1,548 s, or 0.344 s per sweep. It passes the gate, with
  min ESS 510 at 444 W 20th St and max R-hat 1.0058.

I measure each scalar's integrated autocorrelation time (IACT) in sweeps, on the log scale. With
two chains, a scalar's ESS comes to 9,000 / IACT. To clear the gate's bar of ESS 400, each chain
then needs 200 x IACT sweeps.

| scalar | all-scraped ESS | all-scraped IACT | NB9 ESS | NB9 IACT |
|---|---|---|---|---|
| nu | 472 | 19.1 | 600 | 15.0 |
| building_scale | 280 | 32.1 | 799 | 11.3 |
| slowest sigma group | 743 (group 42) | 12.1 | 956 (group 26) | 9.4 |
| bedroom_slope_scale | 866 | 10.4 | 1,106 | 8.1 |
| fslope_scale_1 (sqft_unknown) | 950 | 9.5 | 1,115 | 8.1 |
| sigma | 1,169 | 7.7 | 1,264 | 7.1 |
| walk_scale | 819 | 11.0 | 1,319 | 6.8 |
| unit_scale | 1,021 | 8.8 | 1,552 | 5.8 |

On all-scraped, building_scale mixes slowest among the scalars, followed by nu. The slowest
building effects there mix far slower than any scalar, because of conflicting prices in their
data (P6). On NB9, nu mixes slowest, followed by building_scale.

## Costs on Modal's GPUs

Every fit runs on Modal, so I estimate the cost of each sampler change from Modal fits.

A solo update on a scale outside `PART_SCALES` costs a `block_solve`. The cleanest Modal evidence
for that cost comes from a pair of H100 fits started on 2026-09-23 with the same commit, model and
data (47,374 rows), differing by 3 added solos. With 3 solos a sweep took 753.0 ms on the rows
split and 757.2 ms on the units split. With 6 solos it took 975.4 and 976.8 ms. Each added solo
cost about 74 ms, or 10% of the 3-solo sweep. The two splits agreed within 1%.

NB8 fits on A100s (193,376 rows) took 215.7 ms per sweep with 3 solos (#641), 225.7 and 262.9 ms
with 4, and 282.1 ms with 5 (#648). Each added solo in that series came with an added model term,
so its steps of +5% to +25% mix the two costs. Other 5-solo NB8 fits, on other commits and terms,
ran from 197 to 326 ms per sweep.

From this evidence I expect an added solo to cost about 9% of an NB9 sweep, within +5% to +20%.
The P2a fit measures it directly.

## Findings and proposals

### P1. The nu step is 13 to 15 times nu's posterior sd

Each sweep runs 10 Metropolis steps of the noise update (`noise_mh`, `gibbs.py` lines 1741 to
1775). In each step the sampler moves all 68 group log sigmas with a shared step size, accepting
or rejecting each group separately. It then moves the multipliers with the same step size. Last,
it moves log nu with a second step size.

In phase 1 of warmup the sampler sets both step sizes from posterior sds (lines 2282 to 2290). In
phase 2 it multiplies both by a single factor, adapting that factor from the groups' mean
acceptance toward 0.3 (line 2359). As a result nu's step follows the groups' acceptance. The
sampler traces only the groups' mean acceptance, leaving nu's own acceptance unrecorded.

| | all-scraped | NB9 |
|---|---|---|
| adapted step on log nu | 0.051 | 0.118 |
| posterior sd of log nu | 0.0034 | 0.0089 |
| step / sd | 15 | 13 |
| sweeps with nu unchanged | 64% | 60% |
| acceptance per step, implied | 0.043 | 0.051 |
| lag-1 autocorrelation | 0.88 | 0.86 |
| IACT | 19.1 | 15.0 |

Accepted moves have a median size of 0.0018 on all-scraped and 0.0046 on NB9. From those I put
nu's sd, given the rest of the state, at about 0.56 of its marginal sd, so the squared correlation
between nu and the rest of the state comes to about 0.7. With a well-sized step, I expect nu to
approach the Gibbs limit for that dependence: an IACT of (1 + 0.7) / (1 - 0.7), or about 5.7.

The sigma groups share a step, although their posterior sds on log sigma run from 0.009 to 0.135.
Narrow groups take steps far larger than their sd, while wide groups take steps far smaller.

I propose these sampler changes in `gibbs.py`:

- adapt nu's step from nu's own acceptance toward 0.44, and trace that acceptance;
- give each sigma group and each multiplier its own step, sized in phase 1 from its own sd and
  adapted from its own acceptance toward 0.44.

With these changes the sampler targets the same posterior. Per-element step sizes add a vector
multiply to each noise step, small next to the block solves in a sweep.

### P2. building_scale moves only as fast as the building effects

The sampler updates building_scale in two places: the collapsed joint proposal over 79 scales, and
a draw given the building effects b. Given b, the sd of log building_scale is about 1/sqrt(2N) for
N buildings: 0.0027 on all-scraped and 0.0087 on NB9. The marginal sds come out wider, at 0.0126
and 0.0207, because the data constrain many b only weakly (P3). For a two-block Gibbs sampler with
those sds I expect an IACT of about 42 on all-scraped and 10 on NB9, against 32.1 and 11.3 in the
fits. The IACT grows with the number of buildings, so building_scale mixes more slowly as fits
cover more of the city.

The joint proposal helps little. Its adapted step moves building_scale by 0.047 posterior sd on
all-scraped and 0.146 on NB9. An efficient random walk in 79 dimensions steps about
2.38 / sqrt(79), or 0.27 sd, at which size its IACT still runs in the hundreds.

I propose:

- (a) Add building_scale to `--solo-scales`, a config change. The solo update integrates out the
  latent effects with a single `block_solve`. Since building_scale lies outside `PART_SCALES`, the
  update skips `block_parts`. From the Modal evidence above I expect the solo to add about 9% to
  each sweep (+5% to +20%), with building_scale's IACT falling to between 3.5 and 8.
- (b) After (a), a rescale move on (building_scale, b) in `gibbs.py`, like the walk, unit and line
  moves. Its steps each cost a pass over the rows, without a solve.

bedroom_slope_scale mixes the same way, with IACT 10.4 on all-scraped and 8.1 on NB9. After P1 and
P2 it still mixes faster than the slowest sigma group on NB9, so I'd hold off on a solo for it
until it becomes the slowest scalar.

### P3. Building levels anchored in 2010 are weakly identified

The model defines b as each building's level on the walk's first knot, 2010 H1, where the walk
starts at 0. Most buildings' rows come years later. Their data constrain b plus the walk at the
rows' dates, while saying little about b alone. To measure this I computed the data's share of b's
posterior precision, 1 - (posterior sd of b / building_scale)^2. Its median comes to 0.225 on
all-scraped and 0.504 on NB9.

The walk also misfits the levels. Under a random walk the spread of building levels grows over
time, but on NB9 it stays flat at 0.14 to 0.17. The correlation between a building's 2015 and
2025 levels comes out at 0.813, against about 0.66 under the walk and about 0.82 under an AR(1)
with rho 0.89.

The registered AR(1) model (`-arwalk-fixedrho`, #748) replaces the walk with a stationary
deviation around b. b then becomes the building's long-run level, informed by all its rows. On NB9
the unitnu4 AR fit raises the data's share of b from 0.504 to 0.719. It also raises building_scale's
ESS by 52%, at 2% more time per sweep. Against the plain unitnu4 fit, its paired PSIS-LOO gain
comes to +433.2 with a row-level SE of 44.0. I expect the framework's building-grouped SE to come
out wider. Modeling's first AR fit, on older data, gave +395 with SE 55 by building. The NB9 AR
fit failed the gate only at 346 W 36th St, where latest-ask-v9 (#977) has since corrected the
stale asks.

I propose refitting the AR fixedrho unitnu4 model on NB9 with latest-ask-v9. As a change of
assumption, it goes through the paired LOO and the latest split like any model change.

### P4. The gate checks b, while the level at the data can mix slowly

The gate's every-building check computes ESS and R-hat on b. Because b and the walk trade off, b
can mix well while the building's level at its data mixes slowly. From the saved draws I computed
each building's level at its median data knot, b plus the walk there.

- On all-scraped, 80 buildings have a level ESS under 400, against 9 by b. Of those 80, 11 fall
  under 100. Level R-hat exceeds 1.01 in 92 buildings, a count partly due to chance among 67,735
  buildings.
- On NB9, 2 buildings have a level ESS under 400 while passing the b check. 870 Broadway (10 rows)
  has level ESS 125 against b ESS 3,529. 444 W 20th St has level ESS 269 against b ESS 510.

I propose adding the level at the median data knot to the every-building check. The check uses the
saved draws after the fit, at no sampling cost. With it, the served NB9 fit fails at 870 Broadway
and at 444 W 20th St, both for data reasons (P6).

### P5. Raw feature slopes add a second building intercept

Each building gets a slope on 4 feature columns, alongside their global coefficients:
`mu + sum(fslope[building] * x[:, fslope_index])` (`model.py` line 646). The columns enter raw.
Where a column holds a constant c across a building's rows, the building's slope s adds s * c to
its level, acting as an intercept beside b. On the served NB9 fit:

- sqft_unknown holds a constant nonzero value in 33% of buildings, covering 18% of rows. Of its
  sum of squares, 84% lies between buildings. Across buildings, the median posterior correlation
  of b with the building's sqft_unknown slope comes to -0.25.
- log_floor has 82% of its sum of squares between buildings, around a raw mean of 1.13.
- The posterior correlation of log building_scale with log fslope_scale_1 (sqft_unknown) comes to
  -0.32, and to -0.26 on all-scraped.

In those buildings the level's prior variance gains a term fslope_scale^2 c^2, so b trades off
with the slope. The slopes describe differences within a building. For a building with a constant
column, the slope acts only on the level.

I propose centering each slope column within its building, over training rows, in the slope term
only. The global coefficients still multiply the raw columns. After centering, a constant column
gives its building no level shift through the slope, leaving b to carry the level alone. Centering
changes the model slightly:

- the prior variance of a building's level comes out the same whatever the building's mean floor
  or size-unknown share;
- the predictive spread for new buildings narrows a little.

So I'd test it with its own full fit, the paired LOO, new-building coverage on the latest split
and the descriptive share. I propose adding it as a new config option with its own registry name,
leaving the hashed model files unchanged.

### P6. Conflicting prices behind the slowest buildings

On all-scraped, 9 buildings fail the gate: 68 Clinton (62 rows), the Carlyle, 114A Patchen,
116 Patchen, 124 DeKalb, 294 Carlton, 50 Newel, 90 Hull and 13 Cook. Each holds two clusters of
prices. The model can explain the outlying cluster through the unit effects (t, nu 4) or through
the residual (t, nu about 2.25). The sampler moves between those explanations only through the
lam and kappa updates, so these buildings mix slowly. Of their 97 rows, 2 are ask jumps like
those at 346 W 36th St.

On NB9 the two slow levels from P4 come from the same kind of conflict:

- At 870 Broadway, unit 1 asks $3,549 in 2023 as a 715 sqft one-bedroom and $7,899 in 2026 at
  875 sqft. Unit 3 appears both as a 625 sqft one-bedroom ($3,300 in 2014, $3,500 in 2016) and as
  a 1,000 sqft studio ($6,000 in 2017, $5,600 in 2022). Unit 2 appears both as a 1,000 sqft studio
  at $6,700 in 2017 and as a one-bedroom at $3,500 in 2022. Two kinds of apartment seem to share
  these unit labels.
- At 444 W 20th St, one garden duplex asks $15,000 to $15,750 under 3 unit labels (gardendplx,
  garden, 1).

I'm handing these to Data improvements as candidates. Any correction needs independent evidence
beyond the ad text.

### Later

- The sampler accepts 0.245 of rescale moves, against a target of 0.44.
- In every sweep the sampler runs `block_parts` and `block_solve` for the joint proposal, at least
  the cost of a solo, or about 9% of a sweep. With solos on the slow scales the joint proposal
  helps little. After P1 and P2, I'd run a fit without it to decide whether to drop it.
- On thelio's card, Modeling found that four chains don't batch (`docs/research-plan.md`). I
  haven't tested chain batching on Modal's A100 or H100.
- As a fallback for P1, `nu_fixed` holds nu at its median. Its posterior sd is 0.34% on
  all-scraped, so fixing it changes the posterior little.

## Ranking by ESS per second

For each proposal I divide the IACT of the slowest scalar before the change by its IACT after,
then divide by the change in seconds per sweep. For P2a I assume the solo adds 9% to each sweep.
On all-scraped the slowest building effects mix far slower than the scalars until the P6 data work
happens.

| proposal | kind | time per sweep | all-scraped gain | NB9 gain | posterior |
|---|---|---|---|---|---|
| P1 nu and group steps | sampler code | about the same | none alone | 1.33x (nu 15.0 to building_scale 11.3) | same |
| P2a building_scale solo | config | +9% (+5% to +20%) | 1.54x alone (to nu 19.1); 2.43x with P1 (to group 42 at 12.1) | none alone; 1.46x with P1 (to group 26 at 9.4) | same |
| P3 AR fixedrho | registered model | +2% | not measured | building_scale ESS +52% | changes |
| P4 level check | gate | none | stricter gate | stricter gate | same |
| P5 centered slopes | model | same | small | small | changes slightly |
| P6 conflicting prices | data | none | 9 buildings | 2 buildings | data |

Even after P1 and P2, the all-scraped fit needs more than the hour cap to pass the gate. Prepare
and warmup take 912 s and 900 s, leaving at most 1,788 s for sampling. At 3.76 s per sweep with
the extra solo, that comes to about 475 sweeps per chain. At an IACT of 12, two chains then give
an ESS of about 79, against the bar of 400.

## Tests and predictions

I run each test as its own Modal full fit on NB9, about $2 on an A100. The control is Modeling's
next refit of the served model on latest-ask-v9 data. Each test uses the same model and data as
the control, differing only as stated. For the sampler tests the posterior stays the same, so I
compare ESS per second of sampling and expect paired PSIS-LOO to agree within 2 SE.

### P2a: building_scale solo (config only)

The fit adds building_scale to the solo list:
`--solo-scales walk_scale,fslope_scale_0,fslope_scale_1,fslope_scale_2,fslope_scale_3,building_scale`.

Medians with 80% intervals:

1. building_scale IACT: 5.5 (3.5 to 8), against 11.3 (9 to 14) in the control.
2. building_scale solo acceptance: 0.45 (0.35 to 0.55).
3. Seconds per sweep: +9% (+5% to +20%) over the control.
4. nu stays the slowest scalar at IACT 15 (12 to 19), so the min scalar ESS moves by less than
   15%.
5. Paired PSIS-LOO against the control: 0 (-10 to +10) nats.

The prediction misses if building_scale's IACT comes out above 8, if seconds per sweep rise by
more than 20%, or if the LOO difference exceeds 2 SE.

### P1: nu and sigma-group steps (sampler code)

The fit runs the P1 changes in `gibbs.py` with the control's solo list.

Medians with 80% intervals:

1. nu acceptance per step: 0.44 (0.38 to 0.50).
2. nu lag-1 autocorrelation: 0.70 (0.60 to 0.78).
3. nu IACT: 6 (4.5 to 8.5).
4. Slowest sigma group IACT: 8 (6 to 10).
5. Seconds per sweep: +1% (-5% to +5%) against the control.
6. Paired PSIS-LOO against the control: 0 (-10 to +10) nats.

The prediction misses if nu's IACT comes out above 8.5, if the slowest group's IACT comes out
above 10, or if the LOO difference exceeds 2 SE.

### P3: AR fixedrho on latest-ask-v9

The fit is `...-slopemin3-unitnu4-arwalk-fixedrho` on the control's data.

1. Chance of passing the gate: 75%.
2. Paired PSIS-LOO against the control: +420 (+300 to +540) nats.
3. building_scale ESS per second of sampling: 1.5x (1.2x to 1.9x) the control's.
4. Median data share of b: 0.72 (0.66 to 0.78).

The prediction misses if the LOO gain falls outside +300 to +540 or the ESS ratio falls under
1.2x.

### P4: level check on the control

I run this as a free check on thelio, using the control's saved draws.

1. Buildings passing the b check with a level ESS under 400: 2 (1 to 4).
2. 870 Broadway among them, unless Data improvements has changed its rows by then.

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
