# Predictions: building level plus AR(1) deviation (2026-10-14)

I wrote these before the fit. Ben approved the fit at 23:51Z on 2026-10-13. The coordinator's brief
followed at 23:52Z and a follow-up at 23:57Z.

## The fit

The fit is C with one change. C is `m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise-sizeunkslope`
on `nb8-nostuy-v1`, row split, served data rules. The new model is the same name plus `-arwalk`,
and its config differs from C only in `walk_ar=True`.

In C each building has a level b_j ~ N(0, building_scale²) and a random walk on half-year knots,
pinned at 0 on the first knot (2010 H1). In the new model the level stays, and the walk becomes a
stationary AR(1) deviation on the same knots:

- w_j(0) ~ N(0, sd²);
- w_j(k) = rho w_j(k-1) + eta, with eta ~ N(0, sd² (1 - rho²)).

The deviation has variance sd² on every knot. Its correlation between knots L apart is rho^L, so
at rho near 1 it behaves like the walk over a few years and stops growing over decades.

The priors:

- sd (`walk_scale`) keeps C's half-normal prior on the walk scale;
- rho gets Beta(20, 1.2). Its 1% and 99% quantiles are 0.78 and 0.9988, its mean is 0.943, and
  12% of its mass lies above 0.99.

The Gibbs sampler integrates out knots no row touches, as it does for C's walk. Given the
touched knots, it draws the rest from the AR(1) bridge. It updates (sd, rho) by collapsed
Metropolis steps with the deviation integrated out, plus a Gibbs step for sd and Metropolis steps
for log(-log rho) given the deviation.

## Long-lag check (before the fit)

Using 250 of C's kept draws on all 193,376 training rows, I took each row's residual plus C's
building terms (level, bedroom premium, feature slopes, walk). I averaged it per building and
half-year, demeaned it per half-year, and correlated the cells by lag:

| lag (half-years) | 1 | 10 | 20 | 25-30 |
|---|---|---|---|---|
| correlation | 0.83 | 0.72 | 0.64 | 0.50-0.54 |

The split-half correlation at lag 0 is 0.85. A fit of A + B rho^L gives A 0.00 ± 0.44, B 0.83 and
rho 0.986 ± 0.008. A straight line fits about as well. Over 15 years the decay shows no plateau,
so the check cannot separate a high-rho AR(1) with little level variance from a walk.

## Predictions as briefed (23:52Z)

Medians with 80% intervals:

1. Paired PSIS-LOO against C on shared rows: +20 (-20 to +60) nats, a tie.
2. New-building 80/95 coverage, row-weighted: 87.5/97.2 (86-89 / 96.5-98).
3. New-building 80/95 coverage, building-weighted: 83.5/95.2 (82-85 / 94.5-96).
4. The 80% year gap (2024-26 minus 2014-16, within row bins): +1.5 pp (0.5 to 2.5).
5. Building-weighted new-building lpd against C: +60 (+20 to +120) nats, with a lot-clustered SE.
6. New-building median miss: unchanged, within 0.1 pp of C's 11.89%.
7. rho 0.95 (0.90-0.98); sd 0.08 (0.06-0.11).
8. Descriptive share within 0.4 pp of C's.

The prediction misses if:

- the year gap is 3 pp or more;
- PSIS-LOO is worse than C's by more than 2 SE;
- rho's posterior lies above 0.99;
- the fit fails the convergence gate after one retry.

## Revised after the long-lag check, before the fit (2026-10-14T00:15Z)

The long-lag check moves only the parameter predictions:

- rho 0.985 (0.97-0.995);
- sd 0.15 (0.10-0.19);
- building_scale 0.08 (0.02-0.13).

The coverage, year-gap, PSIS-LOO, lpd and median-miss predictions stay as above, and so do the
miss criteria, including rho above 0.99. I will score both blocks.

## Scoring

1. Convergence checks: the run's gate (max R-hat below 1.01, ESS above 400, group R-hat below
   1.05).
2. Paired PSIS-LOO against C on shared rows, with iid and lot-clustered SEs.
3. `python -m rentfrontier.newbuilding` (PR #723): median miss, 80/95 coverage by row and by
   building, year gap, coverage by row bin, building-weighted lpd with a lot-clustered SE. For the
   AR deviation, a new building's prior variance adds sd² ((1-f)² + f² + 2f(1-f) rho) at a row
   between two knots with weight f on the later one.
4. Descriptive share.
5. Posterior medians and 80% intervals for rho, sd and building_scale.

This fit does not go through autoselect, and nothing gets served or published from it. Ben's
hold on those steps from 03:16Z on 2026-10-13 still stands.

## Convergence retry (2026-10-14T02:05Z)

The first fit (commit 24a7e9b) failed the convergence gate: R-hat 1.041 on rho and ESS 39 on sd.
The result is in `docs/model/arwalk-2026-10-14.md`. Ben approved one retry at 01:47Z on
2026-10-14.

The retry fits the same design with C's settings. The only change is in the sampler: under
`walk_ar`, the collapsed solo updates on sd and on -log rho become updates along the principal
axes of the pair's warmup covariance. The ridge between log sd and log(-log rho), whose
correlation is -0.99, stays in the posterior, and the updates now step along it. Both prediction blocks above apply unchanged, and the retry settles the
last miss criterion: it misses if the retry also fails the gate.

I wrote this before the retry. The first fit's result is known, and its posterior medians would
make predictions for the retry trivial, so I add no new ones.

### Expected mixing (2026-10-14T03:15Z, before the retry)

I compared the old and new samplers on simulated AR(1) panels: 200 buildings over 120 months,
two chains, warmup 300 and 1,500 draws each, with the same seed and the same run time per sweep.

| Case (rho, building sd, sd) | ESS rho, old / new | ESS sd, old / new | ESS building_scale, old / new |
|---|---|---|---|
| 0.92, 0.144, 0.08 | 31 / 132 | 30 / 112 | 41 / 98 |
| 0.985, 0.05, 0.08 | 40 / 99 | 38 / 82 | 42 / 55 |

The posterior quantiles agree between the two samplers. Adding log building_scale as a third
axis gave about the same ESS (114 and 132 for rho), so the retry uses two axes.

On the full data the first fit reached ESS 39 on sd. The simulated gains on sd were 2.2 and 3.7
times, which put the retry near 85 to 145, below the gate's 400. The first fit also failed the group
R-hat check (1.065 on the unit effects), which this change does not address. I expect the retry
to fail the ESS check and possibly the group R-hat check, so I expect the last miss criterion to
be met. If it is, a longer chain at the new sampler would be
the next step. That needs Ben's approval, since it costs more than one fit at C's settings.

## Refits on the corrected data (2026-10-14T09:45Z, before either fit)

Ben stopped the retry at 08:58Z. At 09:01Z he asked for the data issue behind the $1,000 row to be
fixed first, then a refit. PR #730 adds `latest-ask-v2`, which prices each row at its listing's
last on-market ask, and `quarantine-v13`. Both fits swap those two rules in for `quarantine-v12`
and change nothing else:

- C refit: C's model and settings (2 chains, warmup 300, 4,500 draws kept every 9th).
- arwalk refit: the AR(1) model with the axis updates from #726, at 18,000 draws kept every 36th.
  That keeps 500 draws per chain, as C does. The 24,000-draw chain I proposed at 03:11Z would
  run past the 3-hour Modal container timeout at about 0.45 s per iteration. The limiter
  estimate is $5.56.

The rule change moves the price on about a third of the rows, so neither refit pairs with a run
from before it. The arwalk refit is scored against the C refit.

Predictions, medians with 80% intervals:

C refit against C:

1. New-building median miss 11.7% (11.4-12.0) against 11.89%. Most listings that change price
   cut it (70% of changes, median cut 3%), so a latest ask sits closer to the price a unit
   rents at, and I expect slightly less noise around the model.
2. New-building 80/95 coverage, row-weighted: 90.5/98.1 (89.5-91.5 / 97.7-98.5) against
   90.7/98.2.
3. The fit passes the convergence gate, as C did (90% likely).

The C refit misses if its median miss falls outside 11.4-12.0% or it fails the gate.

arwalk refit against the C refit:

4. Paired PSIS-LOO: +350 (+200 to +500) nats, a win by more than 2 lot-clustered SEs.
5. Year gap: +1.5 pp (0.8 to 2.2).
6. Building-weighted new-building lpd: +65 (+30 to +100) nats.
7. rho 0.89 (0.87-0.91); sd 0.077 (0.070-0.085); building_scale 0.157 (0.145-0.170).
8. Convergence, against the gate (max split R-hat below 1.01, min bulk ESS above 400, group
   R-hat below 1.05):
   - max split R-hat 1.006 (1.002-1.012);
   - min bulk ESS 450 (300-600), on sd, so the ESS check is about 60% likely to pass;
   - the unit R-hat of 15 E 17th St #4, now priced at $10,000, falls below 1.01 (90% likely),
     and the group R-hat check passes (85% likely).
9. Descriptive share: the arwalk refit's within 0.4 pp of the C refit's, both measured on the
   new rules (80% likely).

The arwalk refit misses if it fails any part of the gate, ESS included, if PSIS-LOO does not win by 2 SE, or if the year gap
reaches 3 pp.

## Fixed-rho refit within the cap (2026-10-14T10:20Z, before the fit)

At 09:57Z Ben capped every fit at about 1 hour or about $2 of Modal, which rules out the longer
chains above. The first fit's slow mixing came from the ridge between sd and rho, so this
variant holds rho fixed and samples only sd and the building scale, along with everything
else in C:

- model `m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise-sizeunkslope-arwalk-fixedrho`
  (`walk_ar_rho=0.89`), with no axis updates and no Metropolis steps on rho;
- C's settings: 2 chains, warmup 300, 4,500 draws kept every 9th;
- C's rules with `latest-ask-v2` and `quarantine-v13` in place of `quarantine-v12`, scored against
  the C refit `m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise-sizeunkslope-nb8-nostuy-v1-rows-bcaac064-a100-4500k9cb1-nb8-ul15r1s4q13ad3la2`.

The value 0.89 is the posterior median from the first arwalk fit, which priced rows at the first
ask before #730. The refit prices rows at the latest ask, so the best rho may have moved a
little. This fit cannot show that, since it does not sample rho.

The first arwalk fit at the same settings took 2,156 s to fit and 371 s for PSIS-LOO and cost
$2.00. With rho fixed, I expect 40 to 48 minutes in all and about $2, within the cap.

Predictions against the C refit, medians with 80% intervals. Those for PSIS-LOO and the year gap
are the AR(1) medians from the corrected-data block above, with the intervals widened by about 10%
for the fixed rho:

1. Paired PSIS-LOO: +350 (+185 to +515) nats, a win by more than 2 lot-clustered SEs.
2. Year gap: +1.5 pp (0.75 to 2.25).
3. Building-weighted new-building lpd: +65 (+30 to +100) nats.
4. sd 0.077 (0.070-0.085); building_scale 0.157 (0.145-0.170).
5. The fit passes the gate (max split R-hat below 1.01, min bulk ESS of at least 400, group
   R-hat below 1.05): 80-85% likely. Without the rho ridge, sd should mix like C's walk scale,
   which passed at these settings.
6. Descriptive share within 0.4 pp of the C refit's (80% likely).

The fit misses if it fails any part of the gate, if PSIS-LOO does not win by 2 SE, or if the
year gap reaches 3 pp. I will record any miss as a miss.

By the time I opened this PR the C refit had finished. It fails the gate on group R-hat alone: max
split R-hat 1.007 and min ESS 518 pass, while 128 unit effects in one building, the West Coast,
reach 1.28, with the building's level at 1.10. If the fixed-rho fit passes the gate and the C
refit does not, the paired scores still hold as comparisons, but the C refit cannot serve as a
converged baseline until that building mixes. Against my C-refit predictions above:

- median miss 11.95% against 11.7% (11.4-12.0), a hit;
- row 80/95 coverage 90.4/98.0 against 90.5/98.1, a hit;
- passes the gate (90% likely), a miss.

Since then, master has gained `tune-westcoast-split-v1` (#745), and Modeling has queued a C fit on it
(prediction in #747). If Modeling launches the fixed-rho fit with that rule as well, I score it
against that C fit and not against the C refit, so the two stay paired on the same rules. The
predictions above stay as written.

## Fixed-rho fit on the West Coast split (2026-10-14T11:14Z, before any fit)

The coordinator's plan changed at 11:14Z. The fixed-rho fit waits on Ben's answer. If he agrees, it
runs once, on `tune-westcoast-split-v1` (#745) in addition to `latest-ask-v2` and
`quarantine-v13`, and only after Modeling's C fit on the split passes the gate. It is scored
against that split C, so the pair has a converged reference. The run on `latest-ask-v2` and
`quarantine-v13` alone is dropped, since the C refit it would pair with fails the gate.

The split moves the labels of one tax lot, so I keep the medians and intervals from the block
above, now against the split C:

1. Paired PSIS-LOO: +350 (+185 to +515) nats, a win by more than 2 lot-clustered SEs.
2. Year gap: +1.5 pp (0.75 to 2.25).
3. Building-weighted new-building lpd: +65 (+30 to +100) nats.
4. sd 0.077 (0.070-0.085); building_scale 0.157 (0.145-0.170).
5. The fit passes the gate: 80-85% likely.
6. Descriptive share within 0.4 pp of the split C's (80% likely).

The miss criteria stay the same: any part of the gate failing, PSIS-LOO not winning by 2 SE, or a
year gap of 3 pp or more.

## Fixed-rho fit on the wing-rule data (2026-10-14T18:40Z, rules filled in at 18:41Z, before the fit)

Ben approved the fixed-rho fit at 18:39Z. Modeling runs it right after its C refit on the West
Coast wing rule, and only if that C passes the gate. The rules differ from the split version above,
so I add this block. Both fits use the same rules, from Modeling's list:

- `baths-ad-v3`, `bedrooms-ad-v3`, `fields-review-v3`, `unit-reviews-v1`, `unit-splits-v4`, as before;
- `west-coast-wings-v1`, Data improvements' wing rule, not yet merged;
- `building-joins-v1` (#769), which folds 97 Horatio St into the West Coast;
- `latest-ask-v3` (#758) in place of v2, `quarantine-v14` and `unit-labels-v16`.

The wing needs a registry row, so both fits may run on a twin of `nb8-nostuy-v1` with new registry
and NTA snapshots. If other rules merge before the launch, Modeling uses the rules in force then,
and the pair still shares them.

The arwalk fit is scored against that C. The new rules quarantine 13 rows, fold 8 into the West
Coast, join some spelled-out unit labels, regroup one lot's labels and change 92 latest asks (#758).
Those are small next to the 193,000 training rows, so I keep the medians and intervals from #748 and
#749:

1. Paired PSIS-LOO: +350 (+185 to +515) nats, a win by more than 2 lot-clustered SEs.
2. Year gap: +1.5 pp (0.75 to 2.25).
3. Building-weighted new-building lpd: +65 (+30 to +100) nats.
4. sd 0.077 (0.070-0.085); building_scale 0.157 (0.145-0.170).
5. The fit passes the gate: 80-85% likely.
6. Descriptive share within 0.4 pp of the wing-rule C's (80% likely).

The miss criteria stay the same: any part of the gate failing, PSIS-LOO not winning by 2 SE, or a
year gap of 3 pp or more.

## Fixed-rho fit on the quarantine-v17 wing data (2026-10-14T22:55Z, before the fit)

The wing C on quarantine-v15 failed the gate on 110 W 26th St. Modeling's next C runs on these
rules, and the fixed-rho fit follows on the same list if that C passes:

- `baths-ad-v3`, `bedrooms-ad-v3`, `building-joins-v1`, `fields-review-v3`, `unit-reviews-v1`,
  `unit-splits-v4`, `west-coast-wings-v1`, as in the block above;
- `latest-ask-v4` in place of v3, `unit-labels-v17` in place of v16;
- `quarantine-v17` (#789) in place of v14. It adds v16's five 110 W 26th St rows and about 35
  Brooklyn ads that StreetEasy filed under Manhattan buildings.

These changes still touch a few dozen rows out of about 193,000, so I keep the medians and
intervals for the score. The gate is stricter now. Since #788 every building effect needs split
R-hat at most 1.01 and bulk ESS over 400, where the old check traced 32 buildings. The first AR(1)
fit mixed worse than C, and the deviation can trade off against a building's level in the same way
C's walk did at 110 W 26th St, so I lower the chance of passing.

1. Paired PSIS-LOO: +350 (+185 to +515) nats, a win by more than 2 lot-clustered SEs.
2. Year gap: +1.5 pp (0.75 to 2.25).
3. Building-weighted new-building lpd: +65 (+30 to +100) nats.
4. sd 0.077 (0.070-0.085); building_scale 0.157 (0.145-0.170).
5. The fit passes the all-building gate: 55-65% likely. If it fails, I expect 1-6 buildings over
   1.01, and the worst one among buildings with fewer than ten listing periods.
6. Descriptive share within 0.4 pp of the v17 wing C's (80% likely).
7. Wall time 42-52 min with the `building_all` trace, about $2.10.

The miss criteria stay the same: any part of the gate failing, PSIS-LOO not winning by 2 SE, or a
year gap of 3 pp or more.

## Fixed-rho fit on the Midtown West data (2026-10-15T02:05Z, before either fit)

The v17 wing C failed the all-building gate at 106 E 10th St and 222 E 17th St. Modeling traced
the failure to ads coded as studios but priced like three and four bedrooms, and Data improvements
corrected them (`bedrooms-ad-v5`, #807). Modeling's next C is the Midtown West fit, so the
fixed-rho fit now pairs with it, on the same feature set and rules:

- feature set `nb9-nostuy-v1`, which adds 81,797 Hell's Kitchen and Hudson Yards rows to NB8's
  215,156 (#774) and 6,683 buildings in all;
- rules `baths-ad-v3`, `bedrooms-ad-v5`, `building-joins-v1`, `elevator-from-ad-v1`,
  `fields-review-v3`, `latest-ask-v4`, `pets-from-ad-v1`, `quarantine-v22`, `west-coast-wings-v1`,
  `unit-labels-v17`, `unit-reviews-v2`, `unit-splits-v4`;
- the C label `a100-4500k9cb1-nb9-ul17r2s4q22ad5la4ep1`, at master 4e64c04f.

The data grow by about 38%, so I scale the summed scores by that much and keep the per-row ones:

1. Paired PSIS-LOO: +480 (+250 to +710) nats, a win by more than 2 lot-clustered SEs.
2. Year gap: +1.5 pp (0.75 to 2.25).
3. Building-weighted new-building lpd: +85 (+40 to +135) nats.
4. sd 0.077 (0.068-0.087); building_scale 0.157 (0.142-0.172). Midtown West has more new
   towers with short histories, so both intervals widen a little.
5. The fit passes the all-building gate: 50-60% likely. If it fails, I expect 1-8 buildings over
   1.01.
6. Descriptive share within 0.4 pp of the NB9 C's (80% likely).
7. Wall time within 5 minutes of the NB9 C's. The first AR(1) fit cost the same as C at the same
   settings. If the NB9 C takes over 55 minutes, I don't launch the AR(1) and record it as
   blocked by the 1-hour cap. The v17 wing C took 49 minutes on NB8, so if time grows with rows
   the NB9 C takes 60 to 70 minutes. I put a 60% chance on the AR(1) being blocked this way. In
   that case I redesign it to fit the cap, with fewer draws, before it runs.

The miss criteria stay the same: any part of the gate failing, PSIS-LOO not winning by 2 SE, or a
year gap of 3 pp or more.

### Rule update before launch (2026-10-15T02:30Z, before either fit)

At 02:06Z Modeling moved the NB9 C to master 8b3ce683, which swaps in `bedrooms-ad-v6` and
`quarantine-v23` (#809) for `bedrooms-ad-v5` and `quarantine-v22`. The new label is
`a100-4500k9cb1-nb9-ul17r2s4q23ad6la4ep1`. The AR(1) fit follows on the same list. These versions
recode 13 studios and hold out 56 blank ones out of 296,320 kept rows, so every prediction in the
block above stands unchanged.
