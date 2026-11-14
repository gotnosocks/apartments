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
