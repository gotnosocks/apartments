# A noise scale by calendar year, sized on stored predictions (no fit)

`docs/TODO.md` lists Y1: a noise scale by calendar year (`drift-building-phase-year`, merged
in #1337 and never fit). The outlier sprint's free check on L1 gave +1,185 elpd, with
factors of 1.15 in 2020 and 1.18 in 2021 against 0.91 to 0.93 in 2024 to 2026, and 80%
coverage of 0.745 in 2020 to 2022 against 0.826 before and after. Y1's predictions are in
the sprint note ("Fits for after the sprint", item 5). Since then the served design gained
lease-phase levels, a Student-t unit level and the bedroom text reader. This note sizes the
year scale again on l2bt's stored held-out predictions, beside j1's eight kept terms, to
decide whether Y1 still earns a fit and what it would do to the Deals page.

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

`y1_year.log`. The t has 5 degrees of freedom on all years (7 from 2022 on). Gains are
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

| year | stored | base | base and years |
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

- The served design leaves the year scale untouched: the marks gain +1,174 on l2bt, as
  much as the sprint's +1,185 on L1. Held-out ads of 2020 and 2021 need a scale about 25%
  wider than those of 2024, 2022 about 15% and 2023 about 6%. The shifts stay under 0.008.
- After the marks every year from 2018 on covers 0.795 to 0.818. Pooling 2014 to 2019 leaves
  2014 to 2017 at 0.77 to 0.79 and 2019 at 0.82, so those years need marks of their own.
- From 2022 on, the gap bins and the flag-change counts take almost none of it: the marks keep
  +309, nearly all from 2022 and 2023 being wider than later years.
- On all years the fitted 2026 scale is 0.930 and 0.925 of the all-years intercept, so a
  year-flat noise scale makes a current ad's interval about 7% too wide. Every current Deals
  ad carries the same factor, so their order by the median's gap stays as it is. Their
  intervals narrow, and an ad well under its median moves further into the low tail.

## Predictions scored

1. Gain of +400 to +1,200, positive on both halves: right (+1,174; +531 and +643).
2. 2020 and 2021 at 1.10 or more, 2025 and 2026 within 5% of 2024: right (1.23 to 1.27;
   0.974 to 0.993).
3. Coverage 0.77 to 0.83 in every year from 2020 on: right (0.795 to 0.801).
4. From 2022 on, beside the gap bins and counts, under 80: wrong (+309). 2022 and 2023 are
   still wide.
5. 2026 scale 0.88 to 0.96 of the all-years scale: right (0.930 and 0.925).

## What follows

Y1 still earns a fit and goes to the base refit's list as its largest term: the year scale
on stored predictions (+1,174, SE 60) is about five times the flag-change counts. The
merged module `drift-building-phase-year` extends L1, so the refit needs a year scale on the
served design in a new module. It should carry a mark for each year, since a pooled 2014 to
2019 leaves 2014 to 2017 under 0.80. A fit is still needed to say how much of this the
model's other scales take once the year scale is fitted beside them.
