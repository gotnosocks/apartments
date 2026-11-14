# S7's within-building duplex contrast, with the (n-1)/n correction (2026-11-14)

S7 part C (`causal-screens-2026-11-13.md`, `s7c_unitkey.py`) reported that 38% of the duplex
ads' excess in L1's clipped squared gap remains within building: +0.0021 ± 0.0002 within
building, against +0.0054 ± 0.0003 over all held-out ads. For the within-building figure, s7c
took each held-out ad's clipped gap, subtracted the mean clipped gap of its building's held-out
ads and squared what was left. Because that mean includes the ad itself, the square comes out low
in two ways:

1. In a building with n held-out ads, the gap less the building's mean carries (n-1)/n of the
   ad's variance about the building's center, so its square comes out low by that factor, and
   by half in a building of two.
2. An ad alone in its building gets a square of zero. S14 counted 14.3% of the duplex ads alone
   in their building, against 6.6% of the other held-out ads, so a larger part of the duplex
   side is set to zero.

S14's script (`u2_scatter.py`, in `unusual-units-2026-11-13.md`) corrects both. It keeps the
buildings with at least 2 held-out ads and multiplies the demeaned square by n/(n-1), and for the
gap itself it subtracts the mean of the building's other held-out ads. Its duplex row gives +0.0039 ± 0.0002
within building. That figure covers only the ads in buildings with 2 or more held-out ads, while
S7's +0.0054 covers every held-out ad, so the two don't make a share.

In this check I put both on the same ads. The script is
`docs/notes/duplex-within-building-2026-11-14/w1_within.py`. It reads L1's held-out ads of the
latest split and L1's saved predictions (`pred_scores.npz` of the pool
`drift-building-phase-b0-latest-9a7830fb-l1`), with the loaders s7c and u2 use, and writes to
`/data1/apartments/tmp/duplex-within-building-2026-11-14/`. In order, I:

1. rerun s7c's uncorrected figures on every held-out ad, to check that my loading gives back
   +0.0021, +0.0054 and 38% before I change anything;
2. keep the buildings with 2 or more held-out ads, and on those ads compute the duplex ads'
   overall excess in the clipped squared gap over the rest, the excess within building with
   S14's correction, and the share, with SEs clustered by building and an interval on the share
   from 2,000 resamples of the buildings;
3. take the correction in its two steps, first dropping the ads alone in their building and then
   scaling by n/(n-1), so I can say how much of the change from 38% each step accounts for;
4. check the scaling itself. Where a building's ads have unequal variances, the scaled square of
   each ad estimates a blend of its own variance and the others', and in a building of two both
   ads get the same expected value. So for buildings with 3 or more held-out ads I also take the
   square of the gap less the mean of the other ads and subtract the other ads' sample variance
   over n-1. If the ads share a center, that quantity has the ad's own variance about it as its
   expectation;
5. recompute the level within building of S7 part A's table (all duplex ads, those with a stated
   size, those without), from the mean of the building's other held-out ads, and as a check by a
   regression of the demeaned gap on the demeaned duplex indicator;
6. add the corrected within-building squared gap to part C's table by the unit's previous ad.

Then I audit the other screens of the sprint for the same construction and recompute the
figures that fed a recommendation or a scored prediction.

Nothing here is fit. Nothing runs on Modal or the GPU, and no model, feature set or data rule
changes.

## Predictions

I wrote these before computing any of the figures below. S14 has already computed two of them on
the same ads, and I mark those.

1. My loading gives back s7c's figures: +0.0021 within building, +0.0054 overall, a share of
   0.38 (97%).
2. With S14's correction, the duplex ads' excess within building comes out at S14's +0.0039 ±
   0.0002 (95%, already in S14).
3. On the buildings with 2 or more held-out ads, the duplex ads' overall excess falls between
   +0.0044 and +0.0056 (70%). Ads alone in their building are mostly in small buildings, where
   both groups scatter wider, so I expect it a little under +0.0054.
4. The share within building on those buildings falls between 0.65 and 0.85 (65%), and above
   0.5 (95%). The coordinator guessed 0.6 to 0.8.
5. Of the move away from 0.38, the n/(n-1) scaling accounts for more than dropping the ads alone
   in their building (55%).
6. On buildings with 3 or more held-out ads, the estimator of step 4 gives a higher share than
   the scaled square on the same ads (75%), between 0.75 and 1.05 (55%).
7. Part A's level within building, from the mean of the other ads: the row of all duplex ads
   comes out between -0.2% and +0.3% (85%, close to S14's +0.07 ± 0.12% on the same ads); with a
   stated size, between -0.9% and -0.3% (65%); without one, between +0.2% and +0.7% (65%). The
   regression on the demeaned indicator puts each row within 0.15 points of the mean of the
   other ads (70%).
8. In part C's split, the duplex ads whose previous ad was the same duplex with the same
   bedrooms keep a corrected within-building squared gap at least 1.4 times that of other ads
   with the same bedrooms (75%).
9. No conclusion of S7 changes: the duplex scale factor stays a fit candidate, and part A's
   verdict of no fit for the level holds (90%).

From a first pass over the other scripts, S4's top decile within building (-0.20%) and S7's
outdoor slope (-0.02 ± 0.16% per doubling) come from the same construction, and so do the two
within-building figures S7 gives for j9's new units. For those:

10. S4's top decile, from the mean of the building's other held-out ads, moves further from zero
    than -0.20%, to between -0.6% and -0.25% (55%), and S4's verdict of no fit holds (85%).
11. On the same 681 ads, S7's outdoor slope on the gap itself comes out between +0.4% and +1.2%
    per doubling (65%), which would account for the outdoor-size note's failure to reproduce
    S7's flat slope.
12. On j9's new units, the corrected within-building squared excess of the duplex ads comes out
    above +0.0020 (60%), and their level within building stays within 0.8 points of zero (75%).

## The share within building

I ran `w1_within.py` under a 3 GB memory scope. Its log and `w1_within.json` are in the output
folder. My loading gives back s7c's figures to the last digit s7c printed: +0.002054 within
building, +0.005427 overall, a share of 0.3785, on 189,647 held-out ads with 10,331 duplex ads.

The duplex ads' excess over the rest in the clipped squared gap, with SEs clustered by building
and, for the share, the 2.5% and 97.5% points over 2,000 resamples of the buildings:

| held-out ads | duplex ads | overall | within building | share |
|---|---|---|---|---|
| all, as s7c ran | 10,331 | +0.0054 ± 0.0003 | +0.0021 ± 0.0002 | 0.38 |
| buildings with 2 or more, unscaled | 8,851 | +0.0050 ± 0.0003 | +0.0028 ± 0.0002 | 0.57 |
| buildings with 2 or more, times n/(n-1) | 8,851 | +0.0050 ± 0.0003 | +0.0039 ± 0.0002 | 0.78 (0.74 to 0.83) |
| buildings with 3 or more, times n/(n-1) | 7,587 | +0.0046 ± 0.0003 | +0.0038 ± 0.0003 | 0.83 (0.79 to 0.87) |
| buildings with 3 or more, own variance | 7,587 | +0.0046 ± 0.0003 | +0.0044 ± 0.0003 | 0.95 (0.90 to 1.00) |

The buildings with 2 or more held-out ads hold 176,345 ads in 22,905 buildings, and those with 3
or more hold 163,053 in 16,259. On the first set the corrected within-building squared gap of
the duplex ads is 0.0093 against 0.0054 for the rest, S14's figures. When I drop the ads alone in
their building, the share moves from 0.38 to 0.57, and the n/(n-1) scaling then moves it to 0.78.
On buildings with 3 or more held-out ads, the estimator of step 4 puts the share at 0.95.

Dropping the lone ads changes both sides of the share. If I drop them from the within-building
numerator only and keep the overall excess of every held-out ad, 0.0054, as the denominator, the
share comes to 0.52. So of the step from 0.38 to 0.57, the zeros account for 0.14, and the
overall excess falling from 0.0054 to 0.0050 on the buildings with 2 or more accounts for about
0.05.

Most of the duplex ads' extra scatter therefore holds against other ads of their own building.
S7's 38% came mostly from the way s7c built its within-building figure. Of the move from 0.38 to
0.78:

- the missing n/(n-1) accounts for 0.22;
- the ads alone in their building, each set to zero, account for 0.14;
- the smaller overall excess on the buildings with 2 or more held-out ads accounts for about
  0.05.

## Part C's table by the unit's previous ad

The corrected within-building squared gap covers the ads in buildings with 2 or more held-out
ads, with its SE clustered by building:

| ads, by the unit's previous ad | ads | in buildings with 2 or more | squared gap there | within building, corrected |
|---|---|---|---|---|
| duplex, previous ad a duplex, same bedrooms | 8,178 | 6,948 | 0.0103 | 0.0091 ± 0.0003 |
| duplex, previous ad not a duplex, same bedrooms | 1,867 | 1,676 | 0.0113 | 0.0101 ± 0.0005 |
| duplex, previous ad a duplex, other bedrooms | 161 | 129 | 0.0168 | 0.0133 ± 0.0017 |
| duplex, previous ad not a duplex, other bedrooms | 125 | 98 | 0.0146 | 0.0115 ± 0.0015 |
| other ads, same bedrooms | 177,259 | 165,789 | 0.0056 | 0.0053 ± 0.00005 |
| other ads, other bedrooms | 2,057 | 1,705 | 0.0174 | 0.0153 ± 0.0006 |

For a duplex whose previous ad was the same duplex with the same bedrooms, the squared gap
within building is 1.7 times that of other ads with the same bedrooms, against 1.9 times
overall. Part C's reading of this row stands.

## Part A's level within building

In percent of the ask, with SEs clustered by building. I measure the level within building in
two ways:

- from the other ads' mean: I subtract the mean of the building's other held-out ads from each
  ad's gap, so ads alone in their building drop out, and compare the duplex ads' mean with the
  rest;
- by regression: within the row's ads, I regress the gap less its building's mean on the duplex
  mark less its building's mean.

When I subtract the other ads' mean, I take out only the ad's own term. A duplex ad in a building
with other duplex ads is still compared partly with them, so wherever duplex ads cluster by
building, that contrast comes out smaller than the difference between a duplex and the other
units of its building. In the regression each duplex ad is compared only with the building's ads
of the other kind, and buildings with ads of one kind drop out. So I take the regression as the
corrected level and give the other ads' mean beside it. For the rows by stated size, the regression
compares a duplex with the building's other ads of the same kind, and the other ads' mean takes
all of them.

| duplex ads | ads | in buildings with 2 or more | as S7 ran | regression, corrected | from the other ads' mean |
|---|---|---|---|---|---|
| all | 10,331 | 8,851 | +0.06 ± 0.08 | +0.12 ± 0.17 | +0.07 ± 0.12 |
| with a stated size | 3,323 | 2,589 | -0.46 ± 0.13 | -0.67 ± 0.37 | -0.76 ± 0.23 |
| without one | 7,008 | 6,262 | +0.30 ± 0.10 | +0.52 ± 0.20 | +0.41 ± 0.14 |

The two corrections agree within 0.11 points on every row. Both leave the row of all duplex ads
near zero and move the two rows by stated size further apart. Every row stays under 1% in size.

## The audit

I read the scripts in `causal-screens-2026-11-13/`, `unusual-units-2026-11-13/`,
`blind-spots-2026-11-14/`, `studio-rooms-2026-11-14/`, `outdoor-size-2026-11-14/` and
`nonresidential-2026-11-14/` for a mean of a building's held-out ads that includes the ad
itself, used as a group's mean or squared with no n/(n-1). These figures use that construction,
and all but the fifth fed a scored prediction. I recomputed each one in `w1_within.py`:

1. `causal-screens-2026-11-13/s7c_unitkey.py:46`, part C's within-building squared gap and its
   share of 38%, above.
2. `causal-screens-2026-11-13/s7_score.py:41`, used at `:62`, part A's level within building
   (the table of S7 in `causal-screens-2026-11-13.md`), above.
3. `causal-screens-2026-11-13/s7_score.py:105`, used at `:115` and `:121`, the outdoor bins
   within building and the slope of -0.02 ± 0.16% per doubling. The demeaning there runs over the
   held-out ads with the private outdoor flag, and 41% of the 681 sized ads are the only flagged
   ad of their building, so their within-building gap is zero.
4. `causal-screens-2026-11-13/s7_score.py:141`, used at `:146`, j9's level within building, +0.25
   ± 0.25%.
5. `causal-screens-2026-11-13/s7b_spread.py:67`, j9's within-building squared excess, +0.0001 ±
   0.0006. Part B reports it beside its scoring without scoring it, and I recomputed it because it
   bears on the duplex factor.
6. `causal-screens-2026-11-13/s4_supply.py:89`, used at `:112`, the within-building column of
   S4's decile table, -0.20% in the top decile.

The other within-building figures in those folders need no correction:

- `u2_scatter.py:76` and `:77` already apply S14's correction;
- `s4_supply.py:127`, `s6_regulated.py:152` and `:153`, and `s8_portfolio.py:181` demean both
  sides of a regression;
- the scripts of the blind spots, studio rooms and outdoor size notes, and S14's `u4`, either
  take no within-building mean or already subtract the mean of the other ads;
- in the nonresidential note, `n5_screen.py` uses the building only to cluster its SEs and to
  resample buildings for the spread's SE. `n1_prior.py`, `n2_candidates.py` and `n2b_overlap.py`
  use it to join lot fields, key units and count buildings, and `n3_draw.py` and `n4_score.py`
  don't read it. No figure there takes a building's mean.

Two more scripts compare a level against a mean that includes the ad, and I checked both against
a regression on the demeaned mark:

- `s2_fare.py:107` subtracts the mean of a building's held-out ads in the half-year, then compares
  no-fee with fee ads in buildings holding both. Section 7 of `w1_within.py` gives back S2's
  figures and, by the regression within building, +1.5 ± 1.4% in 2024H1, +1.8 ± 1.0% in 2024H2
  and +1.5 ± 0.9% in 2025H1, against S2's 1.4%, 1.7% and 1.6%. S2's prediction of 1% to 3%
  holds.
- `s3d_pairs.py:37` subtracts the mean change of the pairs with the same quarters, held-out
  and training pairs together. The review of PR #1390 regressed the change on the demeaned
  held-out mark within each pair of quarters and got -0.30%, against -0.27 ± 0.03% as S3 ran.
  I read its script and didn't rerun it, since it pairs every row of the dataset. The two
  figures differ by 0.03 points, so S3's reading stands.

### j9's new units

| on j9's held-out new units | as S7 ran | corrected |
|---|---|---|
| duplex ads alone in their building | | 56%, against 35% of the rest |
| squared excess within building | +0.0001 ± 0.0006 | +0.0043 ± 0.0018 |
| squared excess overall, same ads | +0.0099 ± 0.0016 | +0.0076 ± 0.0023 |
| share of the excess within building | 0.005 | 0.56 (0.26 to 0.83) |
| level within building | +0.25 ± 0.25% | +1.6 ± 1.6% by regression, +0.59 ± 0.81% from the other ads' mean |

The corrected figures cover the 6,010 held-out ads, 208 of them duplex, in buildings with 2 or
more held-out ads. On j9 more than half of the duplex ads are the only held-out ad of their
building, so s7c's construction set more than half of the duplex side to zero. Corrected, about
half of j9's duplex excess holds within building, with an interval from 0.26 to 0.83 over 2,000
resamples of the 1,435 buildings. The level within building is too uncertain to rule out an
excess of 1% to 2%.

### S7's outdoor size

On the same 681 ads, the slope per doubling of the stated outdoor size is -0.02 ± 0.16% on the
within-building gap as S7 ran it, and +0.00 ± 0.38% on the gap itself. With the gap and the log
size both demeaned within building, on the 196 ads in 63 buildings with 2 or more such ads, it is
+1.5 ± 0.7%. The bins, from the mean of the building's other flagged ads:

| outdoor size | ads | gap | within building as S7 ran | ads with another flagged ad | from the other ads' mean |
|---|---|---|---|---|---|
| under 100 sq ft | 68 | -0.08% | +0.26% | 57 | -0.10 ± 1.36% |
| 100 to 300 | 187 | +2.49% | +1.11% | 126 | +2.05 ± 0.72% |
| 300 to 700 | 262 | +2.00% | +0.82% | 137 | +2.09 ± 0.97% |
| 700 or more | 164 | +1.85% | +1.08% | 80 | +2.85 ± 1.48% |

Measured from the mean of the other flagged ads of their building, the ads from 100 sq ft up
come out about 2% higher against L1's median, close to their raw gap, where S7 wrote about 1%.
Since the gap itself gives a flat slope on these 681 ads, the way S7 demeaned the gap doesn't
account for the outdoor-size note's +0.8% on 994 ads. The two notes take different ads: S7 takes
the outlier sprint's private outdoor flag, and the outdoor-size note takes L1's coded ads with a
size from 20 to 5,000 sq ft.

### S4's top decile

| decile of the building's other ads per unit | ads | as S4 ran | regression against the building's other deciles, corrected | from the other ads' mean |
|---|---|---|---|---|
| top | 12,834 | -0.20% | -0.49 ± 0.12% | -0.25 ± 0.06%, on 12,056 ads |
| bottom | 12,834 | +0.10% | +0.19 ± 0.10% | +0.11 ± 0.06% |

The regression compares an ad in the top decile with ads of its own building in other deciles,
mostly the same building in quieter months, and puts the effect at about half a point. I take
it as the corrected figure, for the reason given under part A: a top-decile ad's other ads
include other top-decile ads of the same busy months, so when I subtract their mean I remove part
of the contrast too. In every other bin, S4's mean and the mean from the other ads differ by
under 0.02 points.

## Scoring the predictions

1. **Hit.** +0.002054, +0.005427 and 0.3785.
2. **Hit.** +0.0039 ± 0.0002, S14's figure.
3. **Hit.** +0.0050 ± 0.0003, under +0.0054 as I expected.
4. **Hit on both.** 0.78, with 0.74 to 0.83 over the resamples.
5. **Hit, narrowly.** Dropping the ads alone in their building moves the share by 0.19, the
   scaling by 0.22. About 0.05 of the 0.19 comes from the smaller overall excess on those
   buildings, so the zeros themselves account for 0.14 against the scaling's 0.22.
6. **Hit on both.** 0.95 against 0.83 for the scaled square on the same ads.
7. **Hit on all four.** From the other ads' mean the rows come out at +0.07%, -0.76% and +0.41%,
   and the regression lies 0.05, 0.09 and 0.11 points from them. The regression, which I take as
   the corrected level, puts the rows at +0.12%, -0.67% and +0.52%, also inside the three
   ranges.
8. **Hit.** 0.0091 against 0.0053, a ratio of 1.7.
9. **Partial hit.** The prediction's two verdicts hold. Part D's factor scales the duplex
   ads' noise, and with the correction more of their excess scatter lies within building, so D1
   remains the fit for it. On L1 the level within building stays under 1% in every row by both
   corrections, so part A's verdict of no fit for the level holds. The opening clause misses:
   the correction changes the scoring of part C's first prediction, and part A's reading that j9
   prices a new duplex with no excess left over no longer holds.
10. **Hit on both, the first narrowly.** -0.254% from the other ads' mean against my bound of
    -0.25%, and -0.49 ± 0.12% by the regression, the corrected figure. S4's verdict rests on the
    decile shift's 43 ± 20 elpd, which doesn't depend on a building's mean.
11. **Miss.** +0.00 ± 0.38% per doubling on the gap itself. S7's demeaning doesn't account for
    the outdoor-size note's +0.8%.
12. **Hit on the squared excess. On the level, hit from the other ads' mean and outside on the
    regression.** The squared excess comes out at +0.0043 ± 0.0018, above +0.0020. The level
    comes out at +0.59 ± 0.81% from the other ads' mean, inside 0.8 points of zero, and at +1.6
    ± 1.6% by the regression, the corrected level, outside that bound with an SE too large to
    tell.

Nine predictions hit in full. Predictions 9 and 12 hit in part, and prediction 11 missed.

## What changes in the earlier notes

- **S7 part C.** Its first prediction, half of the excess within building, was scored as close
  at 38%. Corrected, the share is 0.78 (0.74 to 0.83), so the prediction missed on the high side.
  I added a dated paragraph under part C in `causal-screens-2026-11-13.md` and left the original
  text.
- **S7 part A.** "3% to 8% within building" still misses, at +0.12 ± 0.17% by the regression
  and +0.07 ± 0.12% from the other ads' mean. "1% to 4% once size is counted" still misses on L1,
  at -0.67 ± 0.37% by the regression and -0.76 ± 0.23% from the other ads' mean. On j9 the
  regression gives +1.6 ± 1.6%, inside 1% to 4% on its point estimate, and the other ads' mean
  gives +0.59 ± 0.81%. With SEs that wide, the j9 half of that prediction neither hits nor
  misses clearly, so I can no longer say, as part A did, that j9 prices a new duplex with no
  excess left over. The verdict of no level fit rests on L1 and holds.
- **S7 part B.** On j9 the duplex excess holds within building too, at +0.0043 ± 0.0018, a share
  of 0.56 (0.26 to 0.83) of the overall excess. Part B gave +0.0001 ± 0.0006. That supports a
  factor for duplex units on a model without unit history.
- **S7's outdoor slope.** The prediction of 0.5% to 2% per doubling still misses on the gap
  itself. Within building, on 196 ads, the slope of +1.5 ± 0.7% falls inside it, in line with
  the outdoor-size note's +1.0% per doubling. The verdict on outdoor space in S7's summary rests
  on part B's period split and its elpd, which don't depend on a building's mean.
- **S4.** The first prediction, 0.5% to 1.5% in the top decile, still misses within building,
  narrowly, at -0.49 ± 0.12% by the regression. The verdict of no fit holds. The 0.2% within
  building in its last sentence becomes about 0.5% once corrected, or 0.25% from the other ads'
  mean.

No fit recommendation changes.

## D1

D1's predictions (`duplex-factor-2026-11-13.md`) don't use the 38% or the +0.0021. Its opening
paragraph quotes part A's +0.06 ± 0.08% within building. Corrected, that comes out at
+0.12 ± 0.17% by the regression and +0.07 ± 0.12% from the other ads' mean, both near zero, so
the sentence holds. Its revised predictions 6 and 8 use the text penthouses' gap within
building as S14 measured it, from the mean of the building's other held-out ads, so no ad is
compared with itself. Prediction 8 specifies that method and can be scored as written. Where
the penthouses cluster by building, the regression would likely put their level further from
zero, so I would give it beside S14's figure when D1 is scored. The derivation of k uses the
overall excess of 0.0052, which doesn't depend on a building's mean. The corrected share makes
D1's premise firmer: the duplex ads' extra scatter belongs to the duplex units more than to
their buildings, so a factor on the duplex rows suits it better than one on their buildings.

## Refusals

The permission check refused two commands, each because it could not verify that a git call
stayed in the worktree: `ops/lint --changed` followed by `git -C` on the worktree, and the
commit followed by an echo of its exit status. I ran each part as a separate command from the
worktree, and the commit took its message from a file. One script run failed on a singular
matrix, in the regression for S4's "missing" bin, which the building alone sets. I skipped the
regression for such a bin and ran the script again.

After the review of PR #1390 I added j9's share interval, the numerator-only share and S2's fee
contrast to `w1_within.py` and ran it again under the same scope. The figures it had already
written came back unchanged. The permission check refused one command, a Python edit script
passed through a heredoc, and I wrote the script to a file and ran it from there.
