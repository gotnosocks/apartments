# Do thin buildings' levels need more shrinkage? (2026-11-20)

No fit and no money spent. This note reads the outputs of fits that exist, proposes one change
with its predictions, and recommends not spending on it now. Nothing here is launched.

`docs/notes/thin-level-caution-2026-11-20.md` ended on an open question: a building level far
from zero on a few training ads looks too far from zero, high and low. This note sizes that on
held-out history, asks where it comes from, and says what a fit would have to show.

## Summary

- The miss is real and small. In buildings with 5 or fewer training ads the held-out gap falls
  by 0.097 (half A) and 0.068 (half B) for each unit of level, so those levels should be 90% to
  93% of what they are. With 6 to 10 ads the factor is 96% to 98%, with 11 or more it is 99.6%.
- It sits in the far levels only. Within 0.1 of zero the slope is not negative in either half.
  Beyond 0.1 the part over 0.1 should be 81% (A) and 87% (B) of what it is.
- It is carried by 1,399 held-out ads in 1,225 buildings, 0.74% of the 189,647. Odd rows
  (commercial, dear placeholders, the buildings of the building-level read) are 44 of them and
  explain none of the slope on half A and a quarter of it on half B.
- The prior is a likely cause but not the only one. The Student-t prior with 4 degrees of
  freedom expects 4.0% of buildings beyond 3 spreads; buildings with 30 or more ads show 0.7%
  to 2.2% (Manhattan 0.7% to 1.4%). But the miss is as large where every training ad of the building
  is the scored ad's own apartment, where the split between building and unit cannot matter.
- Proposal, if a fit is wanted: `--level-dof 8` at the held scales, one backtest fit at about
  $2.04, then a market fit at about $2.11 only if the backtest does not reject it.
- Recommendation: do not fit it now. The expected change is 2 to 8 ads of the first 300 on
  Deals, the worst of these ads already carry the `thin_level` caution, and the backtest is
  too small to tell a gain from none.

## Data

Run `drift-building-phase-unitkn-level-bedtext-b0-latest-c1ffaefd-l2bt`, the latest split,
189,647 held-out ads, each the newest ad of its unit. Levels, counts of training rows and
gaps are the files `b1.py` of the caution note wrote, with the same halves of the buildings
(a hash of the building's name). The gap is log final ask less the predictive median. The
level is the posterior mean of `kept/bld`, fitted on training rows only, and the count is
every training row of the building. A held-out ask is used only as the outcome.

Two limits of this split matter below. Every held-out ad has an earlier training ad of its
own unit, so the split holds no ad of a unit new to the fit. And the run is the free-scales
latest-split fit of a neighbouring model, not the served one; the two share the building
level, its prior and its sampler.

## The gap by support and level

Scripts `d1.py` and `tab.py`. Over all ads the gap is -0.004, 5.9% are below the 5% point and
4.7% above the 95% point.

| training ads | level | ads | buildings | gap | gap A | gap B | below 5% | above 95% |
|---|---|---|---|---|---|---|---|---|
| 1 | under -0.3 | 2 | 2 | +0.120 | +0.108 | +0.133 | 0.0% | 0.0% |
| 1 | -0.3 to -0.1 | 42 | 42 | +0.039 | +0.024 | +0.048 | 7.1% | 11.9% |
| 1 | middle | 773 | 773 | -0.002 | -0.001 | -0.004 | 5.3% | 4.1% |
| 1 | 0.1 to 0.3 | 87 | 87 | +0.029 | +0.038 | +0.019 | 3.4% | 5.7% |
| 1 | over 0.3 | 28 | 28 | -0.086 | -0.093 | -0.082 | 0.0% | 0.0% |
| 2 | under -0.3 | 4 | 4 | +0.193 | +0.659 | +0.037 | 0.0% | 25.0% |
| 2 | -0.3 to -0.1 | 63 | 59 | -0.028 | -0.017 | -0.037 | 4.8% | 1.6% |
| 2 | middle | 1,247 | 1,184 | +0.003 | +0.003 | +0.003 | 4.3% | 4.4% |
| 2 | 0.1 to 0.3 | 148 | 141 | +0.003 | +0.004 | +0.002 | 4.1% | 4.1% |
| 2 | over 0.3 | 35 | 33 | -0.047 | -0.074 | -0.011 | 14.3% | 0.0% |
| 3-5 | under -0.3 | 10 | 7 | +0.045 | -0.010 | +0.099 | 0.0% | 10.0% |
| 3-5 | -0.3 to -0.1 | 326 | 286 | +0.002 | +0.005 | -0.000 | 4.0% | 5.5% |
| 3-5 | middle | 4,321 | 3,634 | -0.001 | -0.001 | -0.000 | 4.7% | 4.7% |
| 3-5 | 0.1 to 0.3 | 528 | 429 | -0.020 | -0.029 | -0.009 | 9.1% | 3.0% |
| 3-5 | over 0.3 | 126 | 107 | -0.062 | -0.065 | -0.060 | 17.5% | 3.2% |
| 6-10 | under -0.3 | 21 | 18 | -0.103 | -0.094 | -0.130 | 33.3% | 0.0% |
| 6-10 | -0.3 to -0.1 | 660 | 431 | +0.001 | +0.003 | -0.002 | 5.2% | 4.5% |
| 6-10 | middle | 6,654 | 4,574 | -0.007 | -0.008 | -0.006 | 5.5% | 4.4% |
| 6-10 | 0.1 to 0.3 | 897 | 608 | -0.012 | -0.005 | -0.017 | 7.9% | 4.7% |
| 6-10 | over 0.3 | 131 | 93 | -0.025 | -0.026 | -0.025 | 10.7% | 6.9% |
| 11+ | under -0.3 | 655 | 113 | +0.004 | +0.004 | +0.005 | 5.2% | 6.4% |
| 11+ | -0.3 to -0.1 | 17,667 | 2,669 | -0.004 | -0.004 | -0.005 | 6.4% | 5.0% |
| 11+ | middle | 130,820 | 18,399 | -0.004 | -0.005 | -0.004 | 5.7% | 4.7% |
| 11+ | 0.1 to 0.3 | 22,538 | 2,248 | -0.004 | -0.004 | -0.005 | 6.3% | 4.6% |
| 11+ | over 0.3 | 1,864 | 238 | -0.009 | -0.003 | -0.018 | 9.8% | 5.2% |

What the table shows:

- Over 0.3 on 1 to 5 ads the gap is -0.05 to -0.09 in every support band and both halves but
  one cell (2 ads, half B, -0.011).
- Between 0.1 and 0.3 the sign is mixed: positive on 1 ad, zero on 2, -0.02 on 3 to 5.
- The low side is 16 ads on 5 or fewer and agrees in sign. On 6 to 10 ads it is the other way:
  21 ads with a gap of -0.103, a third of them below the 5% point. So "too far from zero in
  both directions" holds for the thinnest buildings and is not a general rule of low levels.
- With 11 or more ads nothing is left but a wider spread over 0.3 (9.8% below 5%, 5.2% above
  95%), which the caution note already found to be spread and not bias.

## The slope of the gap on the level

If the levels were right on average, the gap would not depend on the level. A slope of -k
says a level should have been (1 - k) of what it is. Ordinary least squares with an
intercept, standard errors clustered by building (`d1.py`, `d2.py`).

| training ads | ads A | slope A | se | ads B | slope B | se | factor A | factor B |
|---|---|---|---|---|---|---|---|---|
| 1 | 481 | -0.100 | 0.089 | 451 | -0.145 | 0.079 | 0.90 | 0.86 |
| 2 | 746 | -0.109 | 0.053 | 751 | +0.028 | 0.037 | 0.89 | 1.03 |
| 3-5 | 2,707 | -0.092 | 0.024 | 2,604 | -0.082 | 0.026 | 0.91 | 0.92 |
| 1-5 together | 3,934 | -0.097 | 0.022 | 3,806 | -0.068 | 0.023 | 0.90 | 0.93 |
| 6-10 | 4,113 | -0.023 | 0.022 | 4,250 | -0.041 | 0.019 | 0.98 | 0.96 |
| 11+ | 84,020 | -0.004 | 0.004 | 89,524 | -0.005 | 0.003 | 1.00 | 1.00 |

The single bands of 1 and 2 ads are too small to read alone; half B's band of 2 ads has the
other sign. The pooled band of 1 to 5 ads is 4.4 and 3.0 standard errors from zero, and half
B confirms half A at a somewhat smaller size.

The shape is not a plain rescaling. Split at 0.1 either side of zero, 1 to 5 ads:

| part | slope A | se | slope B | se |
|---|---|---|---|---|
| level within 0.1 of zero (3,253 and 3,088 ads) | +0.055 | 0.047 | +0.029 | 0.042 |
| level beyond 0.1 (681 and 718 ads) | -0.117 | 0.027 | -0.082 | 0.027 |
| on the part of the level beyond 0.1, all ads | -0.192 | 0.039 | -0.134 | 0.038 |

So ordinary thin levels are shrunk enough, and the far ones keep 13% to 19% too much of
their distance past 0.1. That is the mark of a tail that is too heavy, since a heavy-tailed
prior shrinks a far value less than a near one.

A factor fitted on one half and applied to the other half's predictions (`d2.py`) moves the
whole thin group's error by nothing that can be measured: mean absolute gap 0.0770 to 0.0773
on B with A's factor, 0.0758 to 0.0757 on A with B's. On the ads over 0.3 it takes the mean
gap from -0.056 to -0.011 (B) and from -0.070 to -0.040 (A). The best line through a half's
own thin ads explains 0.8% (A) and 0.5% (B) of their squared gap (`d3.py`). The stake is a
bias on a few hundred ads, not the score.

## Who carries it, and how much is odd rows

| group, latest split | ads | buildings |
|---|---|---|
| 5 or fewer training ads | 7,740 | 6,816 |
| of those, level beyond 0.1 | 1,399 | 1,225 |
| of those, level over 0.3 | 189 | 168 |
| of those, level under -0.3 | 16 | 13 |

Odd rows are data, and a model change should not be credited with them. An ad counts as odd
here if its building's training ads hold a commercial ad or a placeholder ad over 1.5 times
the area median (the flags of the caution note's `t2.py`), if the building is one of the 96
of `docs/notes/building-level-read-2026-11-20.md` other than the 11 classed as model shape,
or if its own text is a placeholder or commercial.

| 1 to 5 training ads | slope A | slope B |
|---|---|---|
| all ads | -0.097 | -0.068 |
| odd ads left out (75 and 80 ads) | -0.097 | -0.051 |
| beyond 0.1, all | -0.117 | -0.082 |
| beyond 0.1, odd left out (17 and 27 ads) | -0.121 | -0.063 |

Of the 1,399 far ads 44 are odd. Of the 189 over 0.3, 13 are odd with a mean gap of -0.157,
and the other 176 have -0.056, 14.2% below the 5% point. Two of the 189 are in buildings of
the building-level read. None of the 16 low ads is odd. So the wrong-ask and commercial rows
are under a tenth of the ads, none of the slope on half A and a quarter of it on half B. With
them out, the factor for thin buildings is 0.90 (A) and 0.95 (B).

## Where it comes from

### The prior's tail is heavier than well-supported buildings show

The level's prior is `StudentT(4, 0, b_zone)`, drawn as a normal with variance
`b_zone^2 / kap` and `kap ~ Gamma(2, rate 2)` per building (`drift.Settings.level_dof`,
`site_var` in `drift.py`). The run's spreads are 0.113 in Manhattan and 0.068 in the outer
boroughs, the same as the held sets `base-n9` and `base-j9`. Posterior mean levels by the
building's training ads (`d2.py`; "beyond 3" is the share further than 3 spreads from zero):

| zone | training ads | buildings | sd | robust sd | beyond 3 | beyond 4 |
|---|---|---|---|---|---|---|
| Manhattan | 1 | 2,604 | 0.202 | 0.141 | 10.2% | 5.4% |
| Manhattan | 3-5 | 2,643 | 0.191 | 0.124 | 7.4% | 4.3% |
| Manhattan | 11-29 | 4,788 | 0.136 | 0.098 | 3.0% | 1.2% |
| Manhattan | 30-99 | 5,606 | 0.113 | 0.090 | 1.4% | 0.4% |
| Manhattan | 100+ | 2,259 | 0.105 | 0.092 | 0.7% | 0.2% |
| outer | 1 | 9,425 | 0.065 | 0.051 | 1.0% | 0.1% |
| outer | 3-5 | 10,155 | 0.082 | 0.054 | 2.3% | 1.1% |
| outer | 11-29 | 8,017 | 0.076 | 0.058 | 1.7% | 0.6% |
| outer | 30-99 | 4,133 | 0.070 | 0.058 | 1.4% | 0.2% |
| outer | 100+ | 1,051 | 0.077 | 0.060 | 2.2% | 0.7% |

| prior at the same spread | sd over spread | beyond 3 | beyond 4 |
|---|---|---|---|
| Student-t, 4 degrees of freedom | 1.41 | 4.0% | 1.6% |
| Student-t, 8 | 1.15 | 1.7% | 0.4% |
| Student-t, 12 | 1.10 | 1.1% | 0.2% |
| normal | 1.00 | 0.3% | 0.01% |

Two readings:

- Buildings with 30 or more ads, whose levels the data settle (posterior sd about 0.04), have
  an sd about equal to the fitted spread and tails near a Student-t with 8 to 12 degrees of
  freedom. The prior with 4 expects two to five times as many far buildings as Manhattan shows, and
  about twice as many as the outer boroughs' largest buildings (2.2%).
- Thin Manhattan buildings are more spread than well-supported ones (sd 0.20 on one ad
  against 0.11), though a posterior mean on one ad is shrunk and should be less spread. So
  either thin Manhattan buildings are a wider population (townhouses, single condos, odd
  product), or their levels carry what is not a building's level. The prior's 4 degrees of
  freedom make room for them. The outer boroughs show nothing like it.

The 4 was not chosen from the levels' shape. It was set to take the leverage of about ten
odd outer-borough buildings off `bld_sd[outer]` so that the free-scales fits passed the gate
(`docs/model/drift.md`).

### The observation side: part of it is not the level at all

A thin building's ads are explained by the level, the building's quarterly path (sd 0.077),
the unit's lasting level and drift (0.061 and 0.044 in `base-n9`) and row noise with
`nu` near 1.7 and a scale near 0.02. For one ad 0.5 above its area, the noise's tail and the
level's tail are about equally likely explanations (densities within a factor of two by
hand), which is why single-ad buildings give two modes
(`docs/notes/kept-rhat-audit-2026-11-20.md`). A lighter level tail tips that toward "this row
is an outlier".

One check can be made without a fit (`d3.py`). Where every training ad of the building is
the scored ad's own apartment, the prediction uses the sum of level, path and unit effect,
and how the fit splits them cannot change it much:

| 1 to 5 training ads, level over 0.3 | ads | gap | below 5% | slope A, all levels | slope B |
|---|---|---|---|---|---|
| all training ads are the ad's own unit | 40 | -0.099 | 10.0% | -0.144 | -0.101 |
| other units too | 149 | -0.053 | 15.4% | -0.087 | -0.061 |

The miss is at least as large in the first row. So part of what the regression calls
under-shrinkage of the level is that a far-out ask of one apartment is taken as lasting
(level, path and unit together) when its next ask comes back toward the area. A lighter
level tail acts on that too, by making the lasting explanations less likely than noise for
a far ad, but by how much cannot be told from outputs.

### What can and cannot be told without a fit

Can: the size and shape of the miss on history, that odd rows are not most of it, that the
prior's tail is heavier than well-supported buildings show, and that the kept draws hold no
`kap` and no row weights `lam`, so the split of one building's ads between level and noise
cannot be read from any existing run.

Cannot: how a new unit in a thin building is priced, since the latest split has none and the
backtest has 294 such ads with a slope of -0.09 and a standard error of 0.14 (`d2.py`);
whether a lighter tail moves the thin levels by the 10% history asks for or by more; whether
the gate holds; and what happens to the scales, which a held-scales fit does not refit.

## The proposal: 8 degrees of freedom at the held scales

One change: `--level-dof 8` in place of `--level-dof 4`, everything else as the served pair
(`drift-building-bedtext-layout-range`, scales held at `base-j9` and `base-n9`, 2 chains,
200 warmup, 3,600 draws, keep every 20, seed 1). The flag exists (`drift.run_parser`), so no
model module is added or edited and no hashed file changes. `ops/deals-refresh` writes
`--level-dof 4` into its `fit` and `backtest-fit` steps, so the fit is launched with the
same `ops/modal-fit` line by hand, or after a small change that lets the script read
`LEVEL_DOF` from the environment.

Why 8 and not a normal prior or a rule on support:

- Size. A quadrature for one building at the held scales (`m1.py`: Gaussian data, the rows'
  heavy tail left out, so a rough guide) gives the level under another prior as a share of
  its value under 4 degrees of freedom:

| zone | ads | level at dof 4 | dof 8 | dof 12 | normal |
|---|---|---|---|---|---|
| Manhattan | 1 | 0.30 | 0.89 | 0.83 | 0.71 |
| Manhattan | 1 | 0.45 | 0.88 | 0.81 | 0.63 |
| Manhattan | 3 | 0.45 | 0.92 | 0.87 | 0.71 |
| Manhattan | 5 | 0.15 | 0.96 | 0.95 | 0.91 |
| outer | 1 | 0.30 | 0.72 | 0.60 | 0.43 |
| outer | 3 | 0.30 | 0.80 | 0.70 | 0.51 |
| outer | 3 | 0.45 | 0.85 | 0.74 | 0.44 |
| outer | 5 | 0.15 | 0.86 | 0.80 | 0.69 |

  History asks for 0.90 to 0.93 on the level and 0.81 to 0.87 on the part past 0.1. Eight
  degrees of freedom is the nearest of these; a normal prior takes three to five times as
  much off and would be expected to price truly dear thin buildings too low.
- Shape. Eight to twelve is what the well-supported buildings' tails show.
- The gate. The normal prior failed the gate through `bld_sd[outer]`. With the scales held
  that scalar is not drawn, but the buildings behind it are still there, and 8 keeps most of
  the tail that took their leverage away.
- A scale that depends on the building's support would be new model code, and nothing above
  says thin buildings need a tighter spread: Manhattan's thin buildings are wider.

Its known weakness: the held spreads were fitted under 4 degrees of freedom, so at 8 the
prior's sd falls from 1.41 to 1.15 spreads with nothing refitted. A free-scales refit
(about $22) would settle the spread and the gate together, and is over the budget left
($19.57). A held-scales pair is the only test that fits in it.

Cost, from `/data1/apartments/modal/ledger.jsonl`: `range-j` settled at $2.04 and `range-m3`
at $2.11. The backtest fit comes first and decides; the market fit is bought only on
adoption. So $2.04 to reject, $4.15 to adopt.

## Predictions, written before any fit

For a backtest fit as of 2025-11-10, compared with `range-j` on the same 9,346 ads. Present
values are from the published `validation.json` and `k1.py`.

| quantity | now (`range-j`) | predicted at dof 8 | adopt only if |
|---|---|---|---|
| worst split R-hat, scalars and coefficients | passes | 1.004 to 1.010 | at most 1.01 |
| least bulk ESS | passes | 450 to 700 | above 400 |
| cost | $2.04 | $1.90 to $2.20 | |
| final-ask elpd | 10,042 | 10,030 to 10,055 | at least 10,032 |
| median absolute error | 0.0469 | 0.0466 to 0.0472 | at most 0.0474 |
| coverage at 90% | 0.894 | 0.891 to 0.897 | |
| uncautioned lowest tenth, ads | 361 of 604 | 356 to 366 | |
| same ads as now in that tenth | | 350 to 359 of 361 | |
| share of it later raised | 24.7% | 23.8% to 25.6% | at most 25.5% |
| share of it gone within 14 days | 21.9% | 20.8% to 23.0% | at least 20.9% |
| ads marked `thin_level` | 12 | 6 to 10 | |
| levels over 0.3 on 5 or fewer ads, ratio to now | 1 | median 0.75 to 0.92 | under 0.97 |
| levels of buildings with 30+ ads, median abs. change | 0 | under 0.005 | under 0.01 |
| ads in buildings of 1 to 10 ads, level beyond 0.1 | 179 | | |
| their mean absolute gap | 0.122 | 0.118 to 0.125 | at most 0.125 |

What rejects it: a miss of the gate (it is not rerun on another seed); elpd under 10,032 or
median error over 0.0474; the lowest tenth's raised share over 25.5% or its 14-day share
under 20.9%; thin far levels that do not move (ratio 0.97 or more, the change does nothing)
or well-supported levels that do (the change is not confined to thin buildings); or a mean
absolute gap over 0.125 on the 179 thin far ads.

What the backtest cannot do is show the gain. It has 100 ads in buildings of 1 to 5 ads
with a level beyond 0.1, their gap in the level's direction is +0.012 with a standard error
of 0.022 (on the latest split it is -0.021 and -0.011 with standard errors of 0.005), and 18
of the 362 ads of the uncautioned lowest tenth (counted before the `thin_level` caution took
one out) sit in buildings of 10 or fewer ads with a far
level. So a pass means "no harm on the backtest, and the direction history supports", not a
measured improvement. The measured test would be a pair of held-scales fits on the latest
split, 4 against 8, on its 1,399 thin far ads. No held set exists for that split, and the
sets that do exist were fitted on asks the split holds out, which `docs/leak-free-scoring.md`
does not allow without Ben's word.

On the live table (`l1.py`, the table published from `range-m3`; a normal approximation to
each ad's predictive, the median moved by the factor times the level):

| live Deals ads | all 6,502 | first 300 |
|---|---|---|
| in buildings with 1 to 5 training ads | 290 | 17 |
| in buildings with 6 to 10 | 240 | 13 |
| of both, level beyond 0.1 | 132 | 7 |

| scenario | leave the first 300 | first-300 ads moving 10+ places |
|---|---|---|
| history's factors on the level (0.10, 0.03 for 6 to 10 ads) | 2 | 11 |
| history's factors on the part past 0.1 (0.19, 0.05) | 1 | 5 |
| three times history's factor (0.30, 0.10) | 8 | 39 |

Predicted for the market fit: 2 to 8 of the first 300 ads change and 5 to 40 move ten places
or more. Of the 16 live ads in buildings of 1 to 5 ads with a level over 0.3, 8 to 14 keep a
level over 0.3.

## Recommendation

Do not fit it now. The main reason: the miss is a bias of 0.05 to 0.09 on about 200 held-out
ads in 190,000, the Deals page already holds back the ones that make false deals with the
`thin_level` caution, and the one test the budget allows cannot measure a gain, only rule
out harm, for a change of 2 to 8 ads in the first 300.

If a free-scales base refit is bought for another reason, the levels' degrees of freedom are
worth a fit of their own then, with the gate and the spread refitted. The cheaper work that
bears on the same ads is the data: the 68 drafted ledger rows of the building-level read.

## What I am unsure of

- Whether the slope is the level's prior or a far ask reverting. The own-unit rows above say
  a good part is the second, and then a lighter tail helps less than the quadrature says.
- New units in thin buildings, which is where a wrong level does most harm on Deals. No
  existing output prices enough of them.
- The quadrature leaves out the rows' heavy tail, so the shares in its table are a guide to
  order, not predictions. The fit's own levels are the prediction's test.
- The latest-split run is a neighbouring model with free scales. Its level prior and spreads
  match the served fits', and the caution note saw the same sign on the backtest's 12 ads.

## Files

`thin-building-shrinkage-2026-11-20/`: `d1.py` (table and slopes by half), `tab.py` (the
table above), `d2.py` (pooled slopes, the split at 0.1, cross-half factors, the backtest by
new unit, the levels' spread), `d3.py` (own-unit rows, odd rows), `k1.py` (the backtest's
lowest tenth, tail shares), `l1.py` (the live table), `m1.py` (the quadrature), `p1.py` (what
the runs keep), and their logs under `logs/`. They were run in
`/data1/apartments/tmp/po-thinshrink/` and read the parquet files of the caution note in
`/data1/apartments/tmp/po-thinlevel/` and the live levels in
`/data1/apartments/tmp/po-bldmodes/`, none of which is committed.
