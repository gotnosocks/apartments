# A noise scale by calendar year, sized on stored predictions (no fit)

`docs/TODO.md` lists Y1: a noise scale by calendar year (`drift-building-phase-year`, merged
in #1337 and never fit). The outlier sprint's free check on L1 gave +1,185 elpd, with
factors of 1.15 in 2020 and 1.18 in 2021 against 0.91 to 0.93 in 2024 to 2026, and 80%
coverage of 0.745 in 2020 to 2022 against 0.826 before and after. Y1's predictions are in
the sprint note ("Fits for after the sprint", item 5). Since then the best design on the
latest split (l2bt) gained lease-phase levels, a Student-t unit level and the bedroom text
reader. This note sizes the year scale again on l2bt's stored held-out predictions, beside
j1's eight kept terms, to decide whether Y1 still earns a fit and what it would do to the
Deals page.

No fit is run and no money is spent. The script and log go in `year-scale-2026-11-21/`.

## Method

`y1_year.py` takes the scoring of `docs/notes/renovation-step-2026-11-21/j5_gap.py`: each
held-out predictive of l2bt a Student-t on its median with the scale from its quartiles, the
scale multiplied by exp(a · x) and the centre moved by b · x, a and b fitted on one half of
the buildings and scored on the other, with building-clustered SE. Unlike j1 to j5 it takes
all 189,647 held-out ads of the split (2014 to 2026), so the base is j1's eight kept terms
refitted on all years.

The year marks are the calendar year of each ad's `price_at`: 2014 to 2019 pooled (26,536
ads), then one mark each for 2020, 2021, 2022, 2023, 2025 and 2026, with 2024 the
reference. They read only the date. Each has a scale and a shift, added together beside the
base. Three readings follow:

- the year marks over the base on all ads, with 80% coverage by year before and after;
- on ads from 2022 on, the marks for 2022, 2023, 2025 and 2026 beside the base, the gap bins
  and the flag-change counts of the renovation note, which is what a current Deals ad would
  feel;
- the ratio of the fitted 2026 scale to the all-years scale, the factor Y1 would put on a
  Deals ad's interval.

## Predictions, written before the script was run

1. On all ads the year marks gain over the base by +400 to +1,200, positive on both halves.
   The intercept already takes the overall width, and l2bt's lease-phase levels and unit
   Student-t take some of the sprint's +1,185.
2. The scale for 2020 and 2021 is 1.10 or more against 2024 on each half, and the scales of
   2025 and 2026 are within 5% of 2024.
3. After the marks, 80% coverage is between 0.77 and 0.83 in every year from 2020 on.
4. On ads from 2022 on, beside the gap bins and counts, the marks for 2022 to 2026 gain
   under 80.
5. The fitted 2026 scale is 0.88 to 0.96 of the all-years scale, so Y1 would narrow a Deals
   ad's interval by 4% to 12%.

## Results

`y1_year.log`. The t has 5 degrees of freedom, picked on all years and used for the
from-2022 readings too, so its from-2022 base is not comparable with j5's. Gains are
cross-fitted; scales and shifts are fitted on half A, then on B, against 2024.

| marks | gain (SE) | by half |
|---|---|---|
| j1's eight terms over the stored predictive, all years | +1,934.9 (78.5) | |
| year marks over the base, all years | +1,173.6 (60.3) | +530.5, +643.0 |
| year marks for 2022 to 2026 over the base, gap bins and counts, from 2022 | +308.9 (30.4) | +145.8, +163.2 |

| year | scale, all years | shift, all years | scale, from 2022 beside gap and counts |
|---|---|---|---|
| 2014 to 2019 | 0.963 / 0.968 | +0.0015 / +0.0010 | |
| 2020 | 1.231 / 1.259 | +0.0019 / +0.0030 | |
| 2021 | 1.241 / 1.266 | +0.0009 / −0.0013 | |
| 2022 | 1.142 / 1.160 | −0.0070 / −0.0051 | 1.145 / 1.164 |
| 2023 | 1.061 / 1.067 | −0.0030 / −0.0034 | 1.062 / 1.067 |
| 2025 | 0.989 / 0.993 | +0.0006 / −0.0006 | 0.987 / 0.990 |
| 2026 | 0.974 / 0.977 | +0.0010 / +0.0018 | 0.973 / 0.974 |

80% coverage by year:

| year | t from stored quartiles | base | base and years |
|---|---|---|---|
| 2014 | 0.817 | 0.810 | 0.773 |
| 2015 | 0.811 | 0.804 | 0.779 |
| 2016 | 0.817 | 0.807 | 0.774 |
| 2017 | 0.830 | 0.819 | 0.791 |
| 2018 | 0.848 | 0.833 | 0.805 |
| 2019 | 0.858 | 0.845 | 0.818 |
| 2020 | 0.753 | 0.733 | 0.801 |
| 2021 | 0.744 | 0.721 | 0.796 |
| 2022 | 0.776 | 0.760 | 0.800 |
| 2023 | 0.804 | 0.790 | 0.795 |
| 2024 | 0.829 | 0.818 | 0.800 |
| 2025 | 0.835 | 0.820 | 0.798 |
| 2026 | 0.839 | 0.825 | 0.798 |

- l2bt's design (the best on the latest split; Deals reads
  `drift-building-bedtext-layout-range`) leaves the year scale whole: the marks gain +1,174
  on l2bt, as much as the sprint's +1,185 on L1. Held-out ads of 2020 and 2021 need a scale
  about 25% wider than those of 2024, 2022 about 15% and 2023 about 6%. The shifts stay
  under 0.008.
- After the marks every year from 2018 on covers 0.795 to 0.818. Pooling 2014 to 2019 leaves
  2014 to 2017 at 0.77 to 0.79 and 2019 at 0.82, so those years need marks of their own.
- From 2022 on the marks keep +309 beside the gap bins and the flag-change counts. The
  follow-up below reads them with the t picked on these ads and splits the gain by year.
- On all years the fitted 2026 scale is 0.930 and 0.925 of the all-years intercept, so in
  l2bt's design a year-flat noise scale makes a 2026 ad's interval about 7% too wide. From
  2022 on, beside the gap bins and counts, the same ratio is 0.971 and 0.974, about 3%: the
  year-flat scale is too wide for 2026 ads mostly because of the years before 2022. The Deals model
  has no year or phase scale and its backtest covers 0.792 at 80% (`docs/model/drift.md`),
  so these figures do not say its intervals are too wide. A common factor on the row noise
  would keep the order of Deals ads by `below_share` nearly as it is, since the parameter
  spread in each predictive does not scale with it.

## Predictions scored

1. Gain of +400 to +1,200, positive on both halves: right (+1,174; +531 and +643).
2. 2020 and 2021 at 1.10 or more, 2025 and 2026 within 5% of 2024: right (1.23 to 1.27;
   0.974 to 0.993).
3. Coverage 0.77 to 0.83 in every year from 2020 on: right (0.795 to 0.801).
4. From 2022 on, beside the gap bins and counts, under 80: wrong (+309). 2022 and 2023 are
   still wide.
5. 2026 scale 0.88 to 0.96 of the all-years scale: right on all years (0.930 and 0.925),
   and outside the range from 2022 on beside the gap bins and counts (0.971 and 0.974),
   the reading the Method named for a current ad.

## What follows

Y1 still earns a fit and goes to the base refit's list. On all years it gains +1,174 (SE
60); on the ads from 2022 on, where j5 sized the flag-change counts at +230 beside the gap
bins, it gains +329 (follow-up below), about 1.4 times as much. The merged module
`drift-building-phase-year` extends L1, so the refit needs a year scale on l2bt's design in
a new module. It should carry a mark for each year, since a pooled 2014 to
2019 leaves 2014 to 2017 under 0.80. A fit is still needed to say how much of this the
model's other scales take once the year scale is fitted beside them.

## Follow-up reading, predictions written after review

Review found that the from-2022 readings used the all-years t (5 degrees of freedom), that
no from-2022 reading of the year marks without the gap bins and counts was run, that the
gain was not split by year, and that the coverage column labelled stored is the t built from
the stored quartiles. `y2_followup.py` picks the degrees of freedom on ads from 2022 on, as
j5 did, and reads the year marks for 2022, 2023, 2025 and 2026 over the base alone and over
the base, gap bins and counts, with each gain split by year. It also takes 80% coverage by
year from the stored predictive's own 10% and 90% quantiles. Predictions:

1. From 2022 the year marks over the base alone gain +250 to +450, and beside the gap bins
   and counts they keep at least 80% of that.
2. Ads of 2022 and 2023 hold at least 70% of the gain beside the gap bins and counts.
3. The stored predictive's own 80% coverage is within 0.015 of the t from its quartiles in
   every year.
4. The fitted 2026 scale from 2022 on is 0.96 to 0.99 of the intercept without year marks.

## Follow-up results

`y2_followup.log`. The t has 7 degrees of freedom, picked on ads from 2022 on as in j5, so the
gap bins and counts gain +368.1 (SE 35.5) over the base, j5's +138 and +230 together.

| marks, from 2022 | gain (SE) | by half | by year: 2022, 2023, 2024, 2025, 2026 |
|---|---|---|---|
| year marks over the base | +302.9 (30.7) | +140.8, +162.1 | +186, +45, +4, +8, +60 |
| year marks over the base, gap bins and counts | +328.7 (32.1) | +154.6, +174.1 | +195, +44, +5, +15, +70 |

The scales match the first reading: 1.14 to 1.16 in 2022, 1.06 to 1.07 in 2023, 0.985 to
0.994 in 2025 and 0.973 to 0.980 in 2026, against 2024. The 2026 scale is 0.963 and 0.962 of
the intercept without year marks over the base alone, and 0.972 and 0.975 beside the gap bins
and counts.

80% coverage from the stored predictive's own 10% and 90% quantiles runs 0.730 (2021) to
0.846 (2019): 0.738 and 0.730 in 2020 and 2021, 0.760 in 2022, 0.816 to 0.826 in 2024 to
2026. It is within 0.008 of the follow-up's t from the quartiles (7 degrees of freedom) in
every year, and up to 0.016 apart from the first reading's column (5 degrees of freedom):
0.015 in 2020 and 0.016 in 2023.

- The gap bins and counts take none of the year scale: the marks gain a little more beside
  them (+329 against +303).
- Ads of 2022 hold 59% of that gain and 2023 another 13%. The 2026 ads add +70, from a scale
  about 2.5% narrower than 2024's.
- The year scale and the flag-change counts are separate terms on current ads, the year
  scale about 1.4 times the counts; the base refit should carry both.

## Follow-up predictions scored

1. Over the base alone +250 to +450, keeping at least 80% beside the gap bins and counts:
   right (+303; +329 beside them, 109%).
2. Ads of 2022 and 2023 hold at least 70% of the gain beside the gap bins and counts: right,
   narrowly (73%).
3. Own 80% coverage within 0.015 of the t from the quartiles in every year: wrong against
   the column the prediction named, the first reading's t with 5 degrees of freedom (0.015
   in 2020, 0.016 in 2023); right against the follow-up's t with 7 (at most 0.008).
4. 2026 scale 0.96 to 0.99 of the intercept without year marks: right (0.962 to 0.975).
