# A unit's own past asks, and the building's same-count ads (2026-11-12)

The outlier sprint left two questions open about the served fit, b9
(`drift-building-b0-latest-67d14e17-b9`, six chains). I answered both on thelio from b9's
saved held-out predictions, with no fit. The scripts are in
`/data1/apartments/tmp/sprint-20261112/own/` (`build.py`, `weights.py`, `bldg.py`).

## The table

For each of b9's 189,647 held-out ads I took b9's predictive median of the log ask and the
unit's training ads in the served dataset. I moved each training ask to the held-out ad's
month with a repeat-ad index fitted on 759,353 pairs of consecutive training ads of a unit
(by month, the log change clipped at 0.5, ridge 0.01). The index falls 0.215 from December
2019 to January 2021, and June 2025 is 0.369 over January 2014. The unit's own
history is the mean of its moved asks. Its deviation is that mean minus b9's median.

I then asked how much of the deviation the final ask keeps: the weight `w` in
`median + w * deviation`, chosen two ways.

- `w_mae` minimizes the median absolute error over a grid of 0 to 1.
- `w_ls` is the least-squares slope of the gap on the deviation, with no intercept.

A model that used the unit's history fully would leave both near 0.

## Units with 1 to 9 training ads

188,814 held-out ads have a unit with 1 to 9 training ads. 28.8% of them have a coded size.

| rows | n | median abs error, b9 | same, own history alone | w_mae | w_ls | rms error, b9 | rms at w_ls |
|---|---:|---:|---:|---:|---:|---:|---:|
| all | 188,814 | 0.0407 | 0.0578 | | | 0.0824 | 0.0806 |
| no size | 134,364 | 0.0399 | 0.0578 | 0.06 | 0.18 | 0.0807 | 0.0791 |
| size coded | 54,450 | 0.0426 | 0.0580 | 0.10 | 0.20 | 0.0865 | 0.0843 |

By bedroom count, `w_ls` is:

| | studio | 1 | 2 | 3 | 4+ |
|---|---:|---:|---:|---:|---:|
| no size | 0.25 | 0.14 | 0.13 | 0.23 | 0.39 |
| size coded | 0.24 | 0.12 | 0.18 | 0.26 | 0.41 |

`w_mae` stays between 0 and 0.14 in every cell, and the median error moves by at most 0.0011
(4+ bedrooms with a size). So for the typical ad b9 already weighs the unit's own asks about
as well as a fixed blend could. The unit's own history alone does much worse than b9 (0.058
against 0.041), since b9 also reads the building, the features and the market path.

The weight is higher for the large deviations:

| abs deviation | n | w_mae | w_ls | mean gap | median abs error, b9 | at w_mae |
|---|---:|---:|---:|---:|---:|---:|
| under 0.05 | 103,637 | 0.12 | 0.09 | -0.007 | 0.0363 | 0.0362 |
| 0.05 to 0.1 | 51,459 | 0.04 | 0.10 | -0.006 | 0.0419 | 0.0417 |
| 0.1 to 0.2 | 27,569 | 0.04 | 0.14 | -0.005 | 0.0520 | 0.0515 |
| 0.2 to 0.3 | 4,332 | 0.06 | 0.17 | +0.007 | 0.0795 | 0.0788 |
| 0.3 to 0.5 | 1,468 | 0.12 | 0.29 | +0.077 | 0.1422 | 0.1347 |
| over 0.5 | 349 | 0.74 | 0.47 | +0.266 | 0.3720 | 0.1960 |

The rise holds within every bedroom count. Beyond 0.3 the slope is 0.56 to 0.63 for studios,
0.18 to 0.41 for 1 and 2 bedrooms, 0.34 to 0.42 for 3 and 0.48 to 0.62 for 4 or more. A
normal prior on the unit's lasting level shrinks a deviation by the same share whatever its
size, apart from the uncertainty the unit's number of ads adds. A slope that climbs from 0.09
to 0.47 with the size of the deviation is consistent with a heavier tail in the unit levels
than the normal prior allows, and studios show it as much as large units do. The bins are
cut on the deviation itself and the index is citywide, so this is a pointer for the next
fit and not a measured tail.

The weight also falls with the time since the unit's last training ad: `w_ls` is 0.33 when
it is within 3 months, 0.28 at 3 to 12, 0.20 at 12 to 36 and 0.12 beyond. The model's walk
lets a recent ask fade faster than the next ad does.

Splitting by the number of training ads (1, 2, 3 to 4, 5 to 9) moves `w_ls` from about 0.23
down to 0.10 with no size and the same with a size, and `w_mae` stays under 0.15. A
shrinkage weight `n / (n + k)` on the unit's own mean fits best at the largest `k` tried
(64), which is the same as leaving b9's median alone.

The held-out ads of 2014 to 2019 carry higher weights (`w_ls` 0.38 to 0.75) than those of
2020 on (0.12 to 0.20). I have not looked into why.

### What it says for the next fits

- U4, a unit scale by bedroom count with studios and 1-bedrooms at 1, reads the bedroom
  pattern only in part. It would be expected to raise the weight of 2- and 3-or-more-bedroom units at
  every deviation, while the check finds the weight similar across counts for small
  deviations and high for studios in the tail.
- U2, a Student-t prior on the unit's lasting level, matches the shape better: it leaves
  small deviations shrunk and lets large ones through. The sprint's list put it after U1,
  with a prediction of degrees of freedom over 8 once U1 is in. On b9 the
  check points to a tail every count has.
- The rms gain at the least-squares weight, 0.0824 to 0.0806, is an upper bound for a
  model change. It is fitted on the held-out ads themselves.
- Size coded or not barely moves the weights here (0.18 against 0.20). The outlier sprint
  found units with no size keeping 42% to 62% of a deviation beyond 0.3 against 11% to 18%
  for small sized units. That figure came from ads whose previous ad is a training ad of
  the same unit, and from the previous ask rather than the mean of all of them, so the two
  do not contradict each other. I did not reconcile them further.

## The building's same-count ads

Readers of the Deals page judged 15 of the default top 60 false because the building's ads
with the same bedroom count ask about what the deal asks, while the median follows the
building's pricier lines. Those 15 are open ads with no final ask yet. So I asked the
question of the held-out ads: does the mean of the building's same-count training ads
(other units, the 24 months up to the ad, moved by the index) predict the final ask better
than b9's median? The table splits the ads by where b9's median lies against that mean.

| match | rows | n | median abs error, b9 | building mean | mean gap | mean building deviation | w_ls | 80% coverage |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| count | all with such ads | 166,925 | 0.0390 | 0.0572 | -0.005 | -0.001 | 0.15 | 0.810 |
| count | median over the building's ads by > 0.15 | 9,796 | 0.0605 | 0.1819 | -0.031 | -0.229 | 0.11 | 0.666 |
| count | same, unit with at most 1 training ad | 4,238 | 0.0654 | 0.1803 | -0.029 | -0.229 | 0.10 | 0.654 |
| count | median under the building's ads by > 0.15 | 8,904 | 0.0552 | 0.1833 | +0.030 | +0.225 | 0.13 | 0.695 |
| count and full baths | median over the building's ads by > 0.15 | 8,073 | 0.0604 | 0.1743 | -0.033 | -0.217 | 0.14 | 0.664 |
| count and full baths | same, unit with at most 1 training ad | 3,432 | 0.0650 | 0.1704 | -0.035 | -0.215 | 0.14 | 0.653 |

The answer is no. Where the median is more than 0.15 over the building's same-count ads,
the building's mean misses the final ask by a median 0.18 and b9's median by 0.06. The final
ask does lean toward the building's ads: it is 0.031 under the median on average, about a
seventh of the gap to them, and matching baths as well moves that to 0.033. A blend with
half the weight on the building's ads does worse than b9 (median error 0.092).

The 80% intervals undercover in these ads: coverage is 0.666 where the median is over the
building's ads and 0.695 where it is under, against 0.810 for all ads. Disagreement
between the model and the building's same-count ads goes with an ask that is harder to
call, in both directions, and b9's intervals do not widen for it.

For the Deals page this means the 15 reads are right about direction and much too strong
about size: the ask of such a deal is likelier to land a few percent under the median than
at the building's level, and its interval is too narrow. I left the page as published.

## Not done

- I did not check the 15 deals for asks posted since the market fit's scrape.
- The index is a single citywide index by month. A borough or bedroom index would move the
  deviations of units in places that moved differently, mostly in 2020 and 2021.
