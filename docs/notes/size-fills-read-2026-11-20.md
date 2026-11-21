# Are filled sizes wrong often enough to blank them? (2026-11-20, no fit)

The open item in `docs/TODO.md` on size fills comes from the outlier sprint
(`docs/notes/outlier-sprint-2026-11-11.md`). Among 120 large-unit ads read there, a size
coded too large turned up in 15%, with weighted error shares of 0.41 for line fills (6 ads
read), 0.33 for unit fills (20) and 0.11 for stated sizes (94). The item proposes a rule:
do not carry a unit's size to an ad with another bedroom count or in another piece of the
apartment, and do not fill from the line when no ad of the unit states a size and the fill
is more than 40% over the bedroom median. With 26 filled ads read, it asked for a wider
read first. This note is that read, on history.

No fit was run, nothing was fetched and nothing was published. No pipeline or model code is
changed. Scripts and logs are in `docs/notes/size-fills-read-2026-11-20/`.

## Answer

- One clause of the rule is supported, in a narrower form: the unit fill should read the
  ad's own bedroom count first. The lead evidence is the later check, which compares a fill
  with the sizes its apartment states on other ads. There, a fill is off by more than 30% in
  6.3% of 19,383 unit fills from the same bedroom count, 25.5% of 208 unit fills from
  another bedroom count and 6.5% of 19,161 line fills. The own check gives 1.6%, 22.2% and
  3.3%, and it counts for less: the fill equals the stated size exactly in 74% of
  same-bedroom unit checks and 46% of line checks, so it mostly measures reposts copying an
  earlier number. Held-out ads from 2022 on with a unit fill from another bedroom count are
  13.7% below the model's 5% point and 7.8% above its 95% point (373 ads).
- The line clause is rejected at every threshold from 20% to 60%. The own check cannot
  test it, since its rows are ads that state a size and the rule blanks none of those. The
  only evidence on the rows the rule blanks is the later check: 628 of the 3,669 line fills
  over 40% (331 on half A and 297 on half B, 17%), all of them units that state a size
  later. There the fill is too large in 16.0% and 13.5% of cases, more often than other line
  fills, but its root mean squared log error is 0.31 on half A and 0.18 on half B against
  0.42 and 0.43 for the bedroom median a blanked row is given. The margin on half A is thin.
  The own check's 0.15 and 0.13 against 0.49 and 0.50 is a proxy from ads that state a size.
  Blanking these fills would swap a size that is too large in about one case in seven for a
  size that is too small in nearly all cases.
- The clause on another piece of the apartment changes no row. The model's unit fill is
  keyed on the piece, so it never crosses pieces, and no line fill of the dataset reads
  another piece of the ad's own apartment.
- The proposed order of fills is: the piece's earlier ads with the ad's bedroom count, then
  the line, then the piece's earlier ads with another bedroom count. It changes the size of
  1,830 rows of 1,896,471 (1,474 training, 356 held-out), 0.1% of the data. On rows with
  both a line fill and an other-bedroom unit fill, the line fill is the closer of the two on
  both checks and both halves, though the later check has only 79 such rows. The rows the
  order changes hold well under 1% of the low tail, so the rule is a small correction for
  the next base refit and no reason for a refit of its own.
- Large filled sizes fall low at about twice the share of large stated sizes. Held-out ads
  from 2022 on with a size over 1.4 times the bedroom median are below the 5% point in
  19.4% and 11.9% of cases by half for line fills, 20.5% and 19.5% for unit fills from the
  same bedroom count, and 9.6% and 11.5% when the ad states the size. Large sizes of every
  source have a low tail, and predicted rent does not explain the fills' excess: stated
  sizes reweighted to the fills' mix of predicted rent are 9.0% and 9.8% low. A shallower
  slope for filled sizes is the model-side answer, a candidate term for the next refit.
- Readers add little. Of 240 filled ads read blind to rent, 4.0% (se 2.0) of the 100 ads the
  proposed rule blanks and 1.4% (se 1.0) of the 140 it keeps have a size the text shows to
  be too large. Nine texts of 240 state a size, so most verdicts rest on adjectives.

## Method

**Where the fill is made.** The run's size does not come from the pipeline. It is built at
design time by `building_zones_floor_asof.size_table`: the ad's own stated size (100 to
10,000 sq ft), else `sizefill.asof_size` from training rows priced on earlier days, with
held-out sizes blanked first. The unit layer is the mean log size of earlier ads of the same
`unit_id`, the model's piece of an apartment. The line layer is the mean over other units
on the same line with the same bedrooms and full baths, each by its first stated size. A row
with neither has no size. `build.py` calls `size_table` for the size the fit read and
rebuilds both layers beside it with the makeup of their sources; the rebuilt fills equal
the fit's on all 278,775 filled rows.

**What a blank does.** The design has `unit:log_size_rel` (0 when the size is unknown),
`unit:size_imputed` for a fill and `unit:size_unknown` for none, plus the squared relative
size and the unit means of these columns. Blanking a fill moves the row's relative size to
0, which is the bedroom median, and moves it from the imputed flag to the unknown flag.

**Classes.** A unit fill is "same beds" when every source ad has the ad's bedroom count,
"other beds" when none has, and "mixed beds" otherwise. A line fill is "own apartment" when
a source unit is another piece of the ad's apartment. Rows of the dataset (run l2bt,
1,706,824 training and 189,647 held-out):

| size source | training | held-out |
| --- | ---: | ---: |
| stated on the ad | 446,539 | 54,526 |
| unit fill, same beds | 108,018 | 27,856 |
| unit fill, mixed beds | 948 | 242 |
| unit fill, other beds | 2,040 | 465 |
| line fill, other apartments | 122,523 | 16,683 |
| line fill, own apartment | 0 | 0 |
| none | 1,026,756 | 89,875 |

A piece can hold more than one bedroom count because the dataset does not cut at every
change, which is where the 3,695 mixed and other-bedroom fills come from.

**Two field checks, neither reading a rent.**

- Later check, the lead evidence. For an ad whose size is a fill, the median size its
  apartment states on other ads with the same bedrooms and full baths that no fill could
  read (training ads of the same or a later day, and held-out ads). This covers 38,911
  filled ads. It is made on the rows the rule would change, and it is noisy, since a later
  ad may describe a renovated or recounted apartment.
- Own check. An ad that states a size also has the fill the cascade would have made for it
  from earlier ads. The stated size checks that fill. This covers 311,974 ads. It is not
  circular: its sources are earlier training ads and `listing_id` is unique. But the fill
  equals the stated size exactly (within 0.5%) in 74% of same-bedroom unit checks and 46%
  of line checks, so it mostly measures reposts copying an earlier number, and its rows
  state a size, so the rule would blank none of them.

A fill is "off" when it differs from the check by more than 15% or 30% either way, "too
large" when it is more than 30% over. `rmse fill` and `rmse median` are the root mean
squared log errors of the fill and of the bedroom median against the check. A class is
worth blanking on field evidence only if the fill's error is no smaller than the median's.

**Held-out behaviour.** The gap is the log ask less the model's median. A size coded too
large raises the prediction, so the ask falls low: the mark of that error is a share below
the model's 5% point well over 5% with a negative mean gap. Halves of buildings are those of
the history scan (a hash of the building name).

**Threshold.** The 40% threshold was to be chosen among 20, 30, 40, 50 and 60% on half A
and checked on half B. The criterion, set before the tables were read by half, was the
lowest threshold above which the fill's error is no smaller than the median's.

**Readers.** 240 filled held-out ads of 2024 to 2026 with a text of 200 characters or more,
in six strata, at most two per building (219 buildings), seed 20261120. Eight Sonnet readers
took 30 ads each: the full text with dollar amounts masked, the coded bedrooms and baths,
and the filled size. They were given no rent, no gap and no stratum. Each gave the size the
text states, a verdict (plausible, too large, too small, cannot tell) and a quote. The
prompt is `reader_prompt.txt`; the codes are `codes.csv`.

## Held-out behaviour by source

Held-out ads from 2022 on (129,861), and those of 2025 and 2026:

| source | n | mean gap | below 5% (se) | above 95% | 2025-26 n | below 5% | above 95% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| stated | 35,056 | -0.005 | 6.0% (0.1) | 4.7% | 18,329 | 4.8% | 4.6% |
| none | 61,219 | -0.005 | 5.2% (0.1) | 3.9% | 34,501 | 4.6% | 3.8% |
| unit, same beds | 20,198 | -0.007 | 6.2% (0.2) | 4.3% | 11,154 | 5.4% | 4.1% |
| unit, mixed beds | 209 | -0.009 | 9.1% (2.0) | 5.7% | 140 | 7.1% | 6.4% |
| unit, other beds | 373 | -0.016 | 13.7% (1.8) | 7.8% | 221 | 13.6% | 8.1% |
| line | 12,806 | -0.004 | 4.6% (0.2) | 3.7% | 7,126 | 4.0% | 3.8% |

By half, the other-bedroom unit fills are 12.4% and 15.2% low and 9.6% and 5.5% high; the
mixed ones are 11.8% and 6.1% low. Line fills are the best-behaved source on both halves
(4.6% and 4.7% low). As a whole, fills are no worse than stated sizes. The sign is as
expected in the one class that stands out: the mean gap of other-bedroom fills is negative
and falls to -0.051 for those over 1.2 times the median and -0.078 over 1.4 times (85 and
45 ads, 21% and 27% low).

## Field checks by class

Later check, all years (the fill against sizes the apartment states elsewhere):

| fill | n | off 15% | off 30% | too large | too small | rmse fill | rmse median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| unit, same beds | 19,383 | 18.8% | 6.3% | 3.3% | 3.0% | 0.139 | 0.240 |
| unit, mixed beds | 159 | 27.0% | 8.8% | 6.3% | 2.5% | 0.157 | 0.284 |
| unit, other beds | 208 | 51.4% | 25.5% | 17.3% | 8.2% | 0.252 | 0.303 |
| line, other apartments | 19,161 | 17.6% | 6.5% | 3.8% | 2.7% | 0.134 | 0.201 |

Own check, all years (the stated size of the ad against the fill it would have had).
`exact` is the share where the fill equals the stated size within 0.5%
(`review_check.py`), which is why this check runs well below the later one:

| would-be fill | n | exact | off 15% | off 30% | too large | too small | rmse fill | rmse median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| unit, same beds | 206,189 | 74.0% | 5.2% | 1.6% | 0.8% | 0.8% | 0.071 | 0.254 |
| unit, mixed beds | 864 | 24.9% | 23.7% | 7.3% | 4.1% | 3.2% | 0.139 | 0.317 |
| unit, other beds | 1,641 | 29.1% | 37.7% | 22.2% | 11.4% | 10.8% | 0.249 | 0.302 |
| line, other apartments | 102,866 | 45.9% | 9.8% | 3.3% | 1.5% | 1.7% | 0.100 | 0.225 |
| line, own apartment | 414 | 29.7% | 19.1% | 5.1% | 2.4% | 2.7% | 0.130 | 0.257 |

The halves agree: other-bedroom fills are off by 30% in 30.0% and 19.3% on the later check
and in 22.8% and 21.6% on the own one. From 2022 on the own check gives 24.8% for them
and 1.4% for same-bedroom fills. Their errors run both ways, as a size carried between a
one-bedroom and a two-bedroom ad of one piece should.

Two details set the form of the rule.

- With mixed sources, the same-bedroom ads alone are the better fill: off by 15% in 18.1%
  and 15.7% by half against 25.1% and 22.5% for all sources, and the other-bedroom ads
  alone are off in 34.4% and 32.8% (own check, 864 ads).
- For other-bedroom fills, the line layer is better where it has a size. Head to head on
  the same rows (`review_check.py`):

  | Check | Half | Ads | Off by 30%, other-bedroom unit fill | Off by 30%, line fill | rmse, unit fill | rmse, line fill |
  |---|---|--:|--:|--:|--:|--:|
  | Own | A | 259 | 18.5% | 8.5% | 0.224 | 0.171 |
  | Own | B | 289 | 17.6% | 9.0% | 0.214 | 0.144 |
  | Later | A | 37 | 32.4% | 0.0% | 0.278 | 0.147 |
  | Later | B | 42 | 23.8% | 11.9% | 0.258 | 0.157 |

  The later-check rows are few (79), but the line fill is the closer one in every cell of
  both checks. Where the line has none (1,093 of the 1,641 own-check ads), the
  other-bedroom fill still beats the bedroom median, 0.269 and 0.256 against 0.324 and
  0.297, so on the field evidence it is better kept than blanked.

## The 40% threshold on line fills

Line fills above each threshold, by half of buildings. `too large` and the two errors are
from the own check, with the later check's errors beside them; the tails are of held-out
ads from 2022 on. The own-check columns are a proxy, since their rows are ads that state a
size and the rule blanks none of them. The later-check columns are the only evidence on the
rows the rule blanks.

| over | half | training | held-out | too large | rmse fill | rmse median | later fill | later median | below 5% | above 95% |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 20% | A | 5,526 | 660 | 3.7% | 0.117 | 0.364 | 0.204 | 0.305 | 10.5% | 2.5% |
| 20% | B | 5,488 | 696 | 3.3% | 0.110 | 0.368 | 0.164 | 0.293 | 7.9% | 3.1% |
| 30% | A | 2,713 | 320 | 4.7% | 0.132 | 0.430 | 0.252 | 0.368 | 15.5% | 2.2% |
| 30% | B | 2,630 | 324 | 3.9% | 0.120 | 0.433 | 0.159 | 0.358 | 9.9% | 3.7% |
| 40% | A | 1,725 | 214 | 5.9% | 0.149 | 0.491 | 0.307 | 0.421 | 19.4% | 2.5% |
| 40% | B | 1,523 | 207 | 4.7% | 0.133 | 0.499 | 0.182 | 0.427 | 11.9% | 3.8% |
| 50% | A | 951 | 124 | 6.6% | 0.162 | 0.550 | 0.362 | 0.496 | 21.9% | 2.1% |
| 50% | B | 801 | 103 | 4.5% | 0.139 | 0.559 | 0.168 | 0.492 | 19.4% | 2.8% |
| 60% | A | 557 | 69 | 7.5% | 0.176 | 0.599 | 0.414 | 0.523 | 30.2% | 0.0% |
| 60% | B | 538 | 63 | 5.1% | 0.152 | 0.608 | 0.165 | 0.537 | 30.2% | 2.3% |

On half A no threshold meets the criterion: the fill's error is below the median's at all
five, on both checks, and the same holds on half B. So no threshold is chosen. Above 40%,
the later check covers 628 of the 3,669 line fills (331 on half A and 297 on half B, 17%),
all of them units that state a size later. It finds a too-large share of 16.0% and 13.5%,
close to the sprint's reading that large fills are often wrong, yet on the same rows the
fill's error is 0.31 and 0.18 against 0.42 and 0.43 for the median. The margin on half A is
thin. The own check's wider margin (0.15 and 0.13 against 0.49 and 0.50) is a proxy from
ads that state a size. Only the band above twice the
median has a worse fill than median on half A (1.02 against 0.53 on 15 ads), which half B
does not repeat (0.32 against 0.69 on 12).

The low tails in this table are large, and they are what the sprint's readers were handed.
They are not special to line fills. Held-out ads from 2022 on, share below the 5% point by
band of size over bedroom median (halves A and B):

| size / median | line fill | unit fill, same beds | stated |
| --- | --- | --- | --- |
| 0.8 to 1.2 | 4.6%, 4.5% | 5.4%, 5.3% | 4.8%, 4.9% |
| 1.2 to 1.3 | 5.9%, 6.1% | 9.3%, 9.1% | 6.6%, 6.7% |
| 1.3 to 1.4 | 6.9%, 6.0% | 10.3%, 13.6% | 6.7%, 9.3% |
| 1.4 to 1.5 | 15.6%, 5.7% | 19.4%, 14.1% | 7.6%, 10.0% |
| 1.5 to 1.6 | 11.6%, 3.4% | 11.0%, 20.0% | 9.3%, 11.0% |
| 1.6 to 2.0 | 29.8%, 16.1% | 26.6%, 24.4% | 7.6%, 11.4% |
| over 2.0 | 33.3%, 66.7% | 26.5%, 24.5% | 19.1%, 15.1% |

Over 1.4 times the median as a whole, stated sizes are 9.6% and 11.5% low (4,002 ads),
line fills 19.4% and 11.9% (319) and unit fills from the same bedroom count 20.5% and
19.5% (845). Large sizes of every source have a low tail, and fills have about twice the
stated sizes' share, with unit fills from the same bedroom count as low as line fills.

Predicted rent does not explain the excess (`review_check.py`). Large stated sizes are in
the top decile of predicted rent more often than fills are: 2,669 of 4,002, against 87 of
319 line fills and 347 of 845 same-bedroom unit fills. Reweighted to the fills' mix of predicted-rent
deciles, stated sizes fall below the 5% point in 9.0% (the line fills' mix) and 9.8% (the
unit fills' mix), against 15.7% and 20.0% for the fills themselves. In the top three
deciles of predicted rent, by half, stated sizes are 10.1% and 11.6% low, line fills 16.7%
and 13.4%, and unit fills 19.1% and 20.8%.

The proposed rule would blank the line column and leave the unit column, which behaves the
same. The cause fits the field checks: the slope of the checked relative size on the filled
one is 0.78 and 0.80 for line fills and 0.83 and 0.82 for same-bedroom unit fills on the
later check, and 0.91 and 0.92, 0.96 and 0.97 on the own check, where exact copies draw it
toward 1. A large fill overstates the
apartment by a tenth to a fifth of its excess on average, while the model gives a filled
size the stated size's slope plus one flag.

## The read

Verdicts of the 240 ads: 191 plausible, 29 cannot tell, 14 too small, 6 too large.

| stratum | n | too large (se) | too small (se) | cannot tell |
| --- | ---: | ---: | ---: | ---: |
| unit, other beds | 50 | 4.0% (2.8) | 8.0% (3.8) | 4.0% |
| unit, mixed beds | 30 | 3.3% (3.3) | 3.3% (3.3) | 13.3% |
| line, over 1.4 | 50 | 4.0% (2.8) | 0.0% | 14.0% |
| line, to 1.4 | 40 | 0.0% | 15.0% (5.6) | 25.0% |
| unit, same beds, over 1.4 | 30 | 3.3% (3.3) | 0.0% | 10.0% |
| unit, same beds, to 1.4 | 40 | 0.0% | 7.5% (4.2) | 7.5% |
| the proposed rule blanks | 100 | 4.0% (2.0) | 4.0% (2.0) | 9.0% |
| the proposed rule keeps | 140 | 1.4% (1.0) | 7.1% (2.2) | 14.3% |

By half, the blanked ads are too large in 3.6% and 4.4% and the kept ones in 1.4% and
1.4%. The difference has the proposed rule's sign and is under two standard errors. The
readers' error shares are far below the sprint's 0.33 and 0.41 because this sample is drawn
by fill class with no regard to the gap, where the sprint read ads sampled by their place in
the predictive interval. Nine texts state a size: seven agree with the fill within 6%, one
other-bedroom fill is 32% over the text (3,300 against "nearly 2,500 square feet") and one
mixed fill is 15% under. The six ads coded too large are below the 5% point in three cases,
a tabulation made after the codes were fixed.

My spot check of 15 ads (seed 7, read before the readers' codes were opened) agrees with
the readers on 13. On one, a three-bedroom with one bath in a Lower East Side walkup coded
1,900 sq ft, I coded too large and the reader plausible. On the other, a studio coded 900
sq ft whose text describes a separate kitchen and a bedroom, I coded plausible and the
reader cannot tell. The readers lean lenient, so their too-large shares are a floor.

## What follows

**The rule, for the next base refit.** In `sizefill.asof_size` as the as-of design calls
it, order the layers as:

1. the mean log size of the piece's earlier training ads with the row's bedroom count
   (rounded and clipped as in the line key);
2. the line layer, unchanged;
3. the mean log size of the piece's earlier training ads with any other bedroom count.

No fill is blanked and no threshold on the bedroom median is applied. Rows whose size
changes: the 1,190 mixed fills (948 training, 242 held-out) take the same-bedroom mean, and
640 of the 2,505 other-bedroom fills (526 training, 114 held-out) take the line fill. The
other 1,865 other-bedroom fills keep their size, since it beats the median, and they are
the natural rows for a lower weight if a slope for filled sizes is fitted. The live market
table was not counted. The rule reads bedroom counts, dates and sizes only.

**Size of the consequence.** Other-bedroom fills are 0.29% of held-out ads from 2022 on and
0.71% of the 7,203 ads below the 5% point (51 ads); mixed fills are 0.16% and 0.26%. Line
fills over 40% are 0.25% of ads and about 0.7% of the low tail (50 ads), and the rule leaves
them alone. The change cannot move elpd or coverage visibly. A merged change to the fill
makes the served fit unservable until a refit, so it belongs with the next base refit's
other changes and is not worth a fit of its own.

**A model-side candidate.** A slope of its own for filled sizes (an interaction of
`unit:size_imputed` with `unit:log_size_rel`), which the field slopes of 0.8 to 0.9 and the
low tails of large fills both point to. It applies to 278,775 rows, 45,246 of them held-out,
so it is the larger lever of the two. It joins the refit terms in `docs/TODO.md`.

## Caveats

- The later check covers 14% of filled ads and reads later ads, some of them after a real
  change to the apartment, so it may overstate the error. The own check is made on ads that
  state a size, whose listers may differ from those of ads that state none, and most of its
  agreement is reposts copying an earlier number, so it understates the error. Between
  them, fills are off by 30% in 1.6% to 6.3% of same-bedroom unit fills and 3.3% to 6.5%
  of line fills, with the later check's figure the better guide.
- The rmse criterion compares a fill with the bedroom median as sizes. The model also has
  the imputed and unknown flags and unit means, so the gain or loss in elpd from a blank is
  not the same number. Only a fit can settle that, and the row counts say it would not pay.
- The held-out tails by class are of one run and its latest split, which draws each
  unit's last ads. The classes with a few hundred ads have standard errors of 2 to 4 points.
- The threshold criterion was fixed before the tables by half were read, but after the
  pooled tables by class. No threshold was chosen, so there is no selected value to check.
- The snapshot filler `rentfrontier.unit_features`, which keys units on the URL label and
  can cross pieces, was not examined. The latest-split run does not read its sizes.
- The readers are one model with one prompt, and 3.75% of texts state a size.
