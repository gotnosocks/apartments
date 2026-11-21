# Which first-day inputs mark the wide asks of units with no earlier ad (no fit)

2026-11-20. No fit was run and nothing was published. Scripts and short logs are in
`docs/notes/first-ad-noise-inputs-2026-11-20/`. Each figure below names its log.

## Summary

- The latest split cannot answer the question. It holds out the last ad of units with two or
  more ads, so none of its 189,647 held-out ads belongs to a unit with no training ad
  (`logs/latest.log`). The evidence here is the market backtest as of 2025-11-10 (9,346 open
  ads held out, 3,168 of them of units with no earlier ad) and a rent gap on the 889,621
  first rows of units in the training data of every year.
- Base rate. On the backtest of the Deals model, asks of units with an earlier ad need a scale
  factor of 0.98 and 1.00 on the two halves of the buildings, and asks of first-ad units need
  1.09 and 1.09. Their 80% range covers 76.2% and 74.4%.
- The unit label failing the label standard does not mark the wide asks (factor 0.99 and
  0.96 on 78 and 86 ads). Neither does the lister's reposting so far, counted over all the
  lister's ads.
- The building's ad history marks only buildings with under five earlier ads (factor 1.22
  and 1.36), and they hold 142 and 168 ads, too few to trust alone.
- One input separates on both halves, on both models and on the training rows. Take a
  first-ad unit, and ask whether its lister closed an ad of the same bedroom and bath counts
  under another label in the same building in the 30 days before this ad opened. Where the
  lister did not (43% of first-ad ads), the factor is 1.23 and 1.32 and the 80% range covers
  71.2% and 66.2%. Where the lister did, the factor is 0.99 and 0.91 and coverage is 79.8%
  and 80.8%.
- A factor for the first group, chosen on one half and scored on the other, is worth 12.2
  (SE 11.9) and 37.8 (SE 9.2) elpd, 50 in all on 9,346 ads. It is proposed as a candidate
  for the next base refit. The size of the gain rests on one backtest day.

## What the model does now

`docs/model/drift.md` ("New units get wide ranges") says a unit with no earlier ad is priced
from its columns, its building and the local drift. Its unit level is drawn from the
population of unit levels, so its range is wider. The Deals model
(`building-bedtext-layout-range`) gives every new unit the same unit sd (0.06 in the run
used here) and has no other term for a first ad. The mean width of its 80% range is 0.256 in
log rent for first-ad units against 0.175 for the others (`logs/heldout-crj.log`). The phase
models add a noise factor on the row scale for a row with no earlier ad (the "none" phase,
1.48 against rows 10 to 13 months after the unit's last ad in run `l2j`). Neither model
uses anything about the label, the lister or the building's history to set the width.

## Evidence used, and why not the latest split

`latest.py` counts the held-out ads of the latest-split run `l2bt` whose unit has no
training ad: 0 of 189,647. The split holds out the last ad of each unit with two or more
ads. So the question was taken to two other places.

1. The market backtest as of 2025-11-10: every ad open on that day is held out, and the model
   is fitted to ads that closed before it. Two runs are scored on the same 9,346 ads
   (`score.py`): `crj`, the Deals model, which is the main one here, and `l2j`, a phase
   model, as a second opinion. 3,168 held-out ads are of units with no training ad.
2. A proxy on training rows of all years (`proxy.py`): the log ask of a unit's first row less
   the mean log ask of the other training rows of the same building, bedroom count and year,
   where at least three such rows exist. 651,637 of 889,621 first rows have such a cell. The
   yardstick is the robust scale of that gap over first rows, 0.0735. The proxy is not a
   model error, and it leaves out small buildings. It is used to see whether a pattern of
   one day recurs over the years, not to size a factor.

Halves. Buildings are split by the first byte of sha1("first-ad-noise-2026-11-20" + building
id), even to half 0 and odd to half 1 (`common.py`). Cut points and forms were chosen on
half 0. Both halves are reported everywhere. Standard errors are clustered by building.

Scale factor. As in `docs/notes/history-scan-2026-11-18.md`, each held-out ad's predictive
is approximated by a Student t centred on the median, with scale from the quartiles and the
degrees of freedom that match the stored log density (7 for `crj`, 4 for `l2j`; mean log
density 1.0641 approximated against 1.0629 stored). The factor m is the multiple of the
scale with the greatest likelihood for a group. Its SE comes from a bootstrap of buildings.
The gain is the elpd change from giving a group the other half's m.

## The inputs and why each reads no later ad

`build.py` computes every input in duckdb from the outlier sprint's ads table
(`docs/notes/outlier-sprint-2026-11-11.md`), for the first row of each unit and for every
held-out row. No input reads a rent.

- **Label standard.** Record labels of the lot dated before the ad's first day, second spells
  opened before it, and the grid of floors and lines built from those. Statuses: pass, fail,
  thin records, no grid. Records and ads are filtered to dates before the first day.
- **Label seen before.** The same label on another unit id in the building, in an ad opened
  earlier. The window ends one day before the first day.
- **Lister's reposting.** The lister's count of earlier ads, and the share of them opened
  within 7 days of the lister closing the same counts under another label in the building
  (the relabel share). The window ends one day before the first day, and the share uses only
  the open and close days of those earlier ads.
- **Lister's ads here.** The lister's count of earlier ads in the building, and in the last 90
  days. The window ends one day before the first day.
- **Building history.** The count of ads of the building opened earlier, and the years since
  its first. The window ends one day before the first day.
- **Lister's turnover here ("closed").** Whether the same lister closed an ad in the building
  under another label, with the same bedroom and bath counts or any counts, in the 7 or 30
  days before this ad opened. The join takes only ads opened before the first day and closed
  on or before it.

Test in code. `check.py` rebuilds the inputs from a copy of the data cut at a day: ads opened
after the day are dropped, records dated after it are dropped, and any later close day is
replaced by the day after the cut. It then compares all 28 columns for the ads opened on
that day with the full build. Five days were tested, two of them inside the backtest's
held-out ads (`logs/check.log`).

| Cut day | Ads opened that day | Held-out among them | Columns that differ |
| --- | --- | --- | --- |
| 2025-11-03 | 329 | 310 | 0 of 28 |
| 2025-10-14 | 236 | 146 | 0 of 28 |
| 2022-06-01 | 209 | 0 | 0 of 28 |
| 2018-09-05 | 457 | 0 | 0 of 28 |
| 2015-03-02 | 294 | 0 | 0 of 28 |

What the test cannot see. The ads table stores one final value per ad for its lister, label
and counts, so an earlier ad whose lister or label was edited after the first day would be
read with the later value. The condo unit list is not dated. The lot and its apartment count
are static. None of these reads a rent or whether the unit is listed again.

## Base rate

Deals model backtest (`logs/heldout-crj.log`). "far6" is the share of ads farther from the
median than six of the ad's own robust scales.

| Group | Half | Ads | Buildings | m (SE) | 80% cover | 95% cover | far6 % |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Unit has earlier ad | 0 | 3,109 | 1,734 | 0.98 (0.02) | 81.0 | 96.0 | 0.10 |
| Unit has earlier ad | 1 | 3,069 | 1,761 | 1.00 (0.02) | 79.8 | 95.8 | 0.03 |
| First-ad units | 0 | 1,570 | 935 | 1.09 (0.03) | 76.2 | 91.6 | 0.57 |
| First-ad units | 1 | 1,598 | 974 | 1.09 (0.03) | 74.4 | 91.8 | 0.56 |

One factor of 1.09 for all first-ad units is worth 7.4 (SE 6.3) and 7.6 (SE 5.5) elpd. On
the phase model the factors are 0.95 and 0.97 for units with an earlier ad and 1.11 and 1.11
for first-ad units (`logs/heldout-l2j.log`). So the Deals model's ranges for new units are
about 9% too narrow, and its tails hold about eight times the far asks of other units.

On the proxy, 0.63% and 0.67% of first rows are beyond six yardsticks against 0.44% and
0.45% of later rows (`logs/proxy.log`). The TODO item's 0.82% against 0.31% was for
single-ad units, which reads whether the unit is listed again.

## Each input among first-ad units

Deals model backtest, `logs/heldout-crj.log`. Gain is the elpd change from giving that group
alone the other half's m.

| Group | Ads | m (SE) h0 | m (SE) h1 | 80% cover | 95% cover |
| --- | --- | --- | --- | --- | --- |
| Label: fail | 78, 86 | 0.99 (0.10) | 0.96 (0.12) | 82.1, 77.9 | 94.9, 90.7 |
| Label: pass | 825, 797 | 1.03 (0.04) | 1.05 (0.04) | 77.3, 76.2 | 92.7, 92.6 |
| Label: thin records | 645, 678 | 1.17 (0.06) | 1.16 (0.05) | 74.6, 71.4 | 89.6, 90.9 |
| Label seen before: no | 1,275, 1,316 | 1.08 (0.04) | 1.07 (0.04) | 76.6, 75.4 | 91.8, 91.9 |
| Label seen before: yes | 295, 282 | 1.10 (0.06) | 1.16 (0.06) | 74.6, 69.9 | 90.5, 91.1 |
| Closed, 7 days: no | 814, 857 | 1.20 (0.04) | 1.25 (0.04) | 72.0, 68.7 | 89.3, 88.6 |
| Closed, 7 days: yes | 756, 741 | 0.97 (0.04) | 0.90 (0.03) | 80.8, 81.0 | 94.0, 95.5 |
| Closed, 30 days: no | 646, 702 | 1.23 (0.05) | 1.32 (0.05) | 71.2, 66.2 | 87.8, 87.6 |
| Closed, 30 days: yes | 924, 896 | 0.99 (0.05) | 0.91 (0.03) | 79.8, 80.8 | 94.3, 95.1 |
| Lister ads here: 0 | 185, 193 | 1.29 (0.10) | 1.38 (0.07) | 68.6, 59.6 | 84.9, 87.6 |
| Lister ads here: 1-4 | 219, 254 | 1.13 (0.07) | 1.08 (0.06) | 74.9, 74.4 | 91.8, 92.9 |
| Lister ads here: 20+ | 872, 817 | 1.05 (0.05) | 1.02 (0.05) | 77.4, 77.5 | 92.8, 92.5 |
| Lister ads here: 5-19 | 294, 334 | 1.02 (0.07) | 1.07 (0.06) | 78.6, 75.4 | 92.2, 91.6 |
| Building ads: 0 | 43, 53 | 1.22 (0.18) | 1.36 (0.19) | 74.4, 58.5 | 83.7, 84.9 |
| Building ads: 1-4 | 99, 115 | 1.22 (0.13) | 1.36 (0.14) | 71.7, 67.0 | 87.9, 85.2 |
| Building ads: 100+ | 664, 617 | 1.04 (0.04) | 1.05 (0.05) | 78.5, 75.0 | 91.4, 93.4 |
| Building ads: 20-99 | 528, 574 | 1.10 (0.07) | 1.08 (0.06) | 75.6, 75.8 | 93.2, 90.9 |
| Building ads: 5-19 | 236, 239 | 1.12 (0.06) | 1.03 (0.06) | 73.7, 76.6 | 91.5, 94.6 |
| Building years: 0 | 43, 53 | 1.22 (0.19) | 1.36 (0.16) | 74.4, 58.5 | 83.7, 84.9 |
| Building years: 1-3 | 178, 147 | 1.12 (0.10) | 1.20 (0.12) | 74.7, 70.1 | 91.6, 89.8 |
| Building years: 3+ | 1,012, 1,052 | 1.05 (0.04) | 1.08 (0.03) | 78.2, 74.9 | 91.5, 92.4 |
| Building years: under 1 | 337, 346 | 1.16 (0.09) | 1.02 (0.07) | 71.5, 77.2 | 92.9, 91.9 |
| Lister ads: 10-99 | 85, 81 | 1.02 (0.12) | 1.22 (0.10) | 78.8, 64.2 | 89.4, 91.4 |
| Lister ads: 100-999 | 274, 231 | 1.13 (0.11) | 1.09 (0.07) | 74.1, 74.5 | 90.1, 92.6 |
| Lister ads: 1000+ | 1,195, 1,261 | 1.07 (0.04) | 1.07 (0.04) | 76.8, 75.5 | 92.2, 91.8 |
| Relabel share: 2-5% | 65, 62 | 1.24 (0.14) | 0.99 (0.13) | 63.1, 79.0 | 89.2, 91.9 |
| Relabel share: over 5% | 1,450, 1,473 | 1.07 (0.03) | 1.08 (0.03) | 77.0, 74.8 | 92.0, 92.0 |

The same groups, the share beyond six scales and the gain.

| Group | far6 % | Gain (SE) h0 | Gain (SE) h1 |
| --- | --- | --- | --- |
| Label: fail | 0.00, 0.00 | -0.1 (0.5) | 0.0 (0.1) |
| Label: pass | 0.73, 0.38 | 0.4 (2.1) | 1.2 (1.1) |
| Label: thin records | 0.31, 0.88 | 10.8 (8.0) | 9.7 (7.1) |
| Label seen before: no | 0.63, 0.46 | 5.5 (4.8) | 4.2 (4.6) |
| Label seen before: yes | 0.34, 1.06 | 1.2 (3.3) | 3.9 (2.1) |
| Closed, 7 days: no | 0.86, 1.05 | 17.5 (9.9) | 30.0 (8.9) |
| Closed, 7 days: yes | 0.26, 0.00 | -2.4 (5.1) | 2.6 (1.0) |
| Closed, 30 days: no | 1.08, 1.28 | 17.0 (10.5) | 36.7 (9.2) |
| Closed, 30 days: yes | 0.22, 0.00 | -4.8 (6.3) | 1.0 (0.4) |
| Lister ads here: 0 | 1.62, 1.55 | 8.1 (6.7) | 15.2 (4.9) |
| Lister ads here: 1-4 | 1.37, 0.79 | 2.1 (1.6) | 0.6 (2.7) |
| Lister ads here: 20+ | 0.23, 0.49 | 1.0 (1.2) | -0.2 (2.5) |
| Lister ads here: 5-19 | 0.34, 0.00 | -0.3 (1.5) | 0.5 (0.5) |
| Building ads: 0 | 0.00, 1.89 | 0.8 (2.8) | 3.3 (2.2) |
| Building ads: 1-4 | 3.03, 2.61 | 1.9 (4.4) | 6.7 (3.7) |
| Building ads: 100+ | 0.15, 0.32 | 0.5 (1.9) | 0.9 (1.6) |
| Building ads: 20-99 | 0.76, 0.35 | 3.2 (3.9) | 2.1 (3.8) |
| Building ads: 5-19 | 0.42, 0.42 | 1.0 (0.6) | -1.0 (2.0) |
| Building years: 0 | 0.00, 1.89 | 0.8 (2.8) | 3.3 (2.2) |
| Building years: 1-3 | 0.56, 1.36 | 1.0 (3.9) | 3.2 (2.7) |
| Building years: 3+ | 0.69, 0.57 | 0.8 (3.6) | 3.6 (2.5) |
| Building years: under 1 | 0.30, 0.00 | 1.4 (1.1) | -3.4 (4.4) |
| Lister ads: 10-99 | 1.18, 0.00 | -1.8 (2.3) | 0.5 (0.2) |
| Lister ads: 100-999 | 0.36, 0.87 | 2.7 (4.0) | 1.0 (2.6) |
| Lister ads: 1000+ | 0.59, 0.56 | 4.2 (3.5) | 4.0 (4.0) |
| Relabel share: 2-5% | 0.00, 0.00 | -0.2 (0.1) | -1.9 (2.0) |
| Relabel share: over 5% | 0.48, 0.61 | 4.6 (5.4) | 6.1 (4.2) |

Share of first-ad ads: label fail 5.2%, thin records 41.8%, building under five ads 9.8%,
lister with no earlier ad in the building 11.9%, lister closed no same counts in 30 days
42.6% (1,348 of 3,168), in 7 days 52.7%.

Reading by candidate.

**(a) The label standard.** Failing labels are not wide: factor 0.99 and 0.96, coverage 82.1%
and 77.9%, no ad beyond six scales. On the proxy they are the tightest group (0.39% and 0.40%
beyond six yardsticks against 0.73% and 0.78% for passing labels). The outlier sprint found
the same on an earlier run. First-ad units on lots with thin records are wider (1.17 and
1.16), but the proxy does not agree (0.54% and 0.55%, under the first-row average), so that
is not a mark of the unit. A label already seen on another unit id points the right way on
half 1 only.

**(b) The lister's reposting so far.** Counted over all the lister's ads it does not
separate. Listers with 1,000 or more earlier ads hold 78% of first-ad ads and need 1.07 and
1.07. Listers whose share of repostings under a new label is over 5% hold 92% and need 1.07
and 1.08. The smaller groups have under 100 ads a half and disagree between halves.

**(c) The building's ad history.** Only buildings with under five earlier ads stand out
(1.22 and 1.36, 3.03% and 2.61% beyond six scales in the 1 to 4 group), on 142 and 168 ads
with SEs of 0.13 to 0.19. From five ads up the factor falls from about 1.1 to 1.04 with no
step. The proxy shows no such pattern (0.52% to 0.68% for buildings under 100 ads), though
it leaves out most small cells. Years in the data add nothing beyond the count.

**The input that separates: the lister's turnover in the building.** What the candidates
were reaching for is whether this ad is one of a stream from a lister who is working the
building. A first ad that opens just after the same lister closed the same bedroom and bath
counts under another label is either the same apartment under a new label or the next unit
of a lease-up, and the model has fresh asks of its neighbours. A first ad with no such close
before it is a one-off, and it is where the wide asks are. The mark does nothing for units
with an earlier ad: factors 0.95 and 0.99 without the close, 1.01 and 1.00 with it
(`logs/forms-crj.log`).

## Forms compared

`forms.py` gives first-ad units two factors, one for the marked group and one for the rest,
fitted on one half and scored on the other (`logs/forms-crj.log`, `logs/forms-l2j.log`).
"Marked" is the group expected to be wide.

| Marked group | Marked ads | m marked | m rest | Gain (SE) h0 | Gain (SE) h1 |
| --- | --- | --- | --- | --- | --- |
| Closed no same counts, 7 days | 814, 857 | 1.20, 1.25 | 0.97, 0.90 | 15.2 (9.7) | 32.6 (8.8) |
| Closed no same counts, 30 days | 646, 702 | 1.23, 1.32 | 0.99, 0.91 | 12.2 (11.9) | 37.8 (9.2) |
| Closed no ad, any counts, 7 days | 671, 683 | 1.18, 1.23 | 1.02, 0.98 | 11.1 (7.9) | 19.6 (7.1) |
| Closed no ad, any counts, 30 days | 510, 533 | 1.20, 1.30 | 1.03, 0.98 | 8.0 (9.0) | 22.9 (7.0) |
| Lister had no ad here in 90 days | 374, 393 | 1.25, 1.23 | 1.04, 1.04 | 14.0 (6.9) | 14.0 (6.3) |
| Lister has no earlier ad here | 185, 193 | 1.29, 1.38 | 1.06, 1.04 | 11.0 (7.5) | 16.7 (6.2) |
| Lister has under 5 ads here | 404, 447 | 1.20, 1.21 | 1.04, 1.04 | 11.5 (6.6) | 13.1 (5.9) |
| Lister has under 20 ads here | 698, 781 | 1.13, 1.15 | 1.05, 1.02 | 8.0 (5.6) | 11.0 (5.5) |
| Building has under 5 ads | 142, 168 | 1.22, 1.36 | 1.07, 1.06 | 7.5 (6.9) | 12.8 (5.9) |
| Building has under 20 ads | 378, 407 | 1.15, 1.16 | 1.06, 1.06 | 8.7 (5.8) | 9.2 (5.2) |

Against these, one factor for all first-ad units is worth 7.4 and 7.6. On half 0 the 30-day
form has the highest gain inside the half (19.2 against 19.1 for 7 days), so it is the form
picked for the Deals model. The two windows are tied there, and the phase model's half 0
picks 7 days (20.4 against 19.6). Summed over halves the 30-day form is worth 50.0 elpd on
the Deals model (SE about 15) and 46.4 on the phase model, and the 7-day form 47.8 and 47.4.
Half 1 gives about three times the gain of half 0 on every lister form. The half 0 figure is
within one SE of zero, the half 1 figure is four SEs from it.

With the other half's factor, the 80% range of the marked ads covers 83.1% and 78.1% (from
71.2% and 66.2%) and the 95% range 95.5% and 93.9% (from 87.8% and 87.6%).

Within the marked group the building's count of ads adds nothing: 1.23 and 1.32 for
buildings with 20 or more earlier ads and 1.23 and 1.32 for fewer.

The proxy agrees over all years (`logs/proxy.log`). Here far6 is the share of rows beyond six
yardsticks.

| First rows of units | Rows h0, h1 | far6 % (SE) h0 | far6 % (SE) h1 |
| --- | --- | --- | --- |
| Closed no same counts, 30 days | 133,279, 132,390 | 1.20 (0.05) | 1.25 (0.05) |
| Closed same counts, 30 days | 194,188, 191,780 | 0.24 (0.02) | 0.26 (0.02) |
| Closed no same counts, 7 days | 176,813, 176,071 | 0.99 (0.04) | 1.04 (0.04) |
| Closed same counts, 7 days | 150,654, 148,099 | 0.20 (0.02) | 0.22 (0.02) |
| All first rows | 327,467, 324,170 | 0.63 (0.03) | 0.67 (0.03) |
| Later rows of units | 333,798, 337,134 | 0.44 (0.02) | 0.45 (0.02) |

First rows that follow the lister's close of the same counts are tighter than later rows of
known units. The far asks of first-ad units sit in the other group, at five times the rate.

## Candidate for the next base refit

Coding. For a row whose unit has no earlier ad, set `quiet` to 1 when no ad satisfies all of
these: same lister, same building, a different label, the same bedroom and bath counts,
opened before this ad's first day, closed on or before it and at most 30 days before it. Set
it to 0 otherwise, and for every row of a unit with an earlier ad. A row with no lister is
quiet.

Ads. 1,348 of the backtest's 9,346 held-out ads (14.4%), 42.6% of its first-ad ads. In the
training data, 41% of first rows with a proxy cell.

Size. The predictive scale of a quiet first ad should be about 1.25 times what the Deals
model gives now (1.23 and 1.32; 1.25 and 1.34 on the phase model). The other first ads are
at 0.99 and 0.91, so they need no widening and may want a little less.

Expected on the 2025-11-10 backtest. About 50 elpd on 9,346 ads (SE about 15, halves 12 and
38), against 15 for one factor for all first-ad units. The 80% coverage of quiet first ads
rises from 68.6% to about 80% and the 95% coverage from 87.7% to about 95%. Ads of units
with an earlier ad do not change.

Form in the model, open. A new unit's range comes mostly from the unit sd (0.06) and little
from the row scale (0.019 to 0.029), so a factor on the row scale alone cannot widen the
range by a quarter. The factor would have to act on the level of a new unit, for example a
second unit sd for quiet first ads, or on the whole predictive scale of the row. That choice
belongs to whoever writes the fit's note. No model code was written here.

Scoring. The latest split holds no first-ad units, so it cannot score this change. The fit
has to be judged on the market backtest, and a second backtest day would test whether the
gain of one day recurs.

Draft of the written prediction for the fit.

> One change to the base: first ads whose lister closed no ad of the same counts under
> another label in the building in the 30 days before opening get their own spread for the
> new unit's level. Predicted on the 2025-11-10 backtest against the base on the same 9,346
> ads: the spread for quiet first ads is 1.15 to 1.40 times that of other new units; elpd
> rises by 20 to 70, most likely 40; 80% coverage of the 1,348 quiet first ads rises from
> 68.6% to between 76% and 83%; elpd on the 6,178 ads of units with an earlier ad moves by
> less than 5 either way; the median's error does not change by more than 0.0005; the fit
> passes the gate. The change fails if the elpd gain is under 15 or the ratio's 90% interval
> includes 1.

## What is uncertain

- One backtest day, open ads only, 3,168 first-ad ads. The half 0 gain is within one SE of
  zero. The proxy supports the direction over all years but cannot size the factor.
- The t approximation stands in for the model's predictive. It matches the stored mean log
  density to 0.001, but a fitted factor inside the model may differ from 1.25.
- The 7-day and 30-day windows are tied on half 0. Thirty days was picked by a margin of 0.1
  elpd.
- The ads table holds final values of each earlier ad's lister, label and counts. The cut
  test shows the code reads no later row. It cannot show that a stored field was not edited
  after the ad's first day.
- The mark is partly a mark of large managed buildings. Within the quiet group the
  building's size made no difference, but lister and building are hard to pull apart on one
  day.
- The backtest's first-ad units include ads still open on 2025-11-10, whose asks may yet be
  cut. That applies to every group here alike.
