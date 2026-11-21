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
