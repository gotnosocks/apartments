# The stabilized discount split by building age, tax-bill registration and period: results, 2026-10-23

This note reports the test planned in `docs/notes/stabilized-split-predictions-2026-10-23.md`, which answers objection 5 on the research board. I ran `docs/notes/conference-followups-2026-10-22/stabilized_split.py` on thelio CPU (19 minutes with 200 permutations, 2.3 GB peak). Its outputs are in `/data1/apartments/tmp/conference-followups/stab/`: `results.json` and `table.md`, with the first pass kept as `results-v1.json` and `table-v1.md`.

The first pass showed four problems in the design, and I changed them before reading the verdicts below:

1. The permutation null for the period contrasts shuffled the flag within a building across both periods. A building whose share of flagged ads changed after 2019 then carried its rent drift into the null. The script now shuffles within building and period, and reports both nulls.
2. Building age and the calendar month entered separately. A second fit adds age-bin-by-month fixed effects, so a rent path that differs by building age can't pass for a change in the flag's effect.
3. 724 of the 29,971 flagged ads are also income restricted, 455 of them in buildings built 2008 on. I refit every split without them.
4. The tax-bill file keys condos by billing lot, so a condo building with no entry is missing from the file rather than registered with no stabilized units. I refit the tax-bill split without condo lots, and again on lots that could hold stabilized units (residential, 6 or more units, built before 1974).

## Results

Within-building OLS on log latest ask, 1,866,262 ads in the frontier dataset `b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc`, with building, month and bedroom-by-bath fixed effects. SEs are clustered by building and week. The flag coefficient is in percent, with 95% intervals.

| split | flagged ads | all ads | without income-restricted ads |
|---|---|---|---|
| pooled | 29,971 | -3.35 (-3.85 to -2.84) | -2.99 (-3.46 to -2.51) |
| built before 1974 | 17,639 | -3.80 (-4.31 to -3.28) | -3.76 (-4.28 to -3.24) |
| built 1974 to 2007 | 3,363 | -1.49 (-2.81 to -0.14) | -1.13 (-2.43 to 0.18) |
| built 2008 on | 8,810 | -2.78 (-3.90 to -1.66) | -1.98 (-3.01 to -0.94) |

Pre-1974 minus 2008-on is -1.05 log points (SE 0.65, z -1.61) on all ads and -1.83 (SE 0.60, z -3.03) without the income-restricted ads. Both lie outside their within-building permutation nulls (2.5 to 97.5 percentiles -0.30 to 0.33 on all ads and -0.30 to 0.35 without the income-restricted ads).

By period, before and after 2019-06-14:

| cell | flagged | building and month effects | plus age-by-month effects |
|---|---|---|---|
| pre-1974, before | 4,502 | -3.73 (-4.59 to -2.88) | -3.78 (-4.62 to -2.92) |
| pre-1974, after | 13,137 | -3.82 (-4.41 to -3.23) | -3.80 (-4.39 to -3.21) |
| 2008 on, before | 1,608 | +0.83 (-0.81 to 2.50) | +1.57 (-0.12 to 3.29) |
| 2008 on, after | 7,202 | -3.43 (-4.64 to -2.21) | -1.94 (-3.15 to -0.72) |

The differences and their nulls below are in percentage points, from the percent coefficients above. The building shuffle is the null I planned. The building-by-period shuffle replaced it after the first pass.

| after minus before, percentage points | estimate (z) | null median, building-by-period shuffle (2.5 to 97.5) | null median, building shuffle as planned (2.5 to 97.5) |
|---|---|---|---|
| pre-1974 | -0.09 (-0.18) | -0.09 (-0.37 to 0.22) | -0.84 (-1.11 to -0.51) |
| pre-1974, age-by-month | -0.03 (-0.06) | -0.03 (-0.31 to 0.28) | not run |
| 2008 on | -4.27 (-4.69) | -2.41 (-2.89 to -1.85) | -0.83 (-1.33 to -0.25) |
| 2008 on, age-by-month | -3.51 (-3.59) | -2.83 (-3.32 to -2.27) | not run |
| 2008 on, without income-restricted ads | -4.15 (-4.81) | -2.46 (-2.96 to -1.89) | not run |

Neither null centers on zero. The building shuffle mixes each building's flagged ads across both periods, so a building whose flagged share changed after 2019 carries its rent drift into that null: the pre-1974 estimate sits above every one of its draws. The building-by-period shuffle keeps each building's flag rate in each period, so buildings built 2008 on whose flagged share rose after 2019, and whose rents fell against the city, move this null as much as the estimate. Against the building-by-period null, the 2008-on change beyond chance is about 1.9 points with month effects and 0.7 with age-by-month effects. Against the planned building null, it is about 3.4 points. The 2008-on estimate falls below every draw of both nulls in each version.

Tax-bill split, Manhattan lots, flag coefficient in percent:

| version | flagged on lots with no entry | no entry | some stabilized units | some minus none |
|---|---|---|---|---|
| all Manhattan lots | 332 | -5.12 (-8.12 to -2.03) | -3.24 (-3.80 to -2.67) | +1.97 log points (SE 1.67) |
| condo lots dropped | 183 | -5.22 (-9.05 to -1.22) | -3.46 (-3.99 to -2.92) | +1.84 (SE 2.14) |
| lots that could hold stabilized units | 90 | -5.19 (-9.76 to -0.39) | -3.42 (-3.95 to -2.88) | +1.85 (SE 2.54) |

Of 1,107,438 Manhattan ads, 282,433 sit on a lot with no entry in the tax-bill file. The file lists lots with stabilized units on their bills, so "no entry" means either no stabilized units or a lot the file misses. It doesn't mean a bill with zero stabilized units. The last version narrows only the no-entry group; its other group matches the version without condo lots.

814 of the flagged ads (2.7%) sit in buildings with no unflagged ad to compare with.

## Against the predictions

- Pooled coefficient between -1% and -5%: -3.35%. Hit.
- 2008-on coefficient between -2% and +2%, with a 95% interval that includes 0: -2.78% (-3.90 to -1.66). Miss. Without income-restricted ads, -1.98% (-3.01 to -0.94) is inside the range, but its interval still excludes 0.
- Pre-1974 coefficient between -3% and -12%: -3.80%. Hit. Below 2008-on by more than 2 clustered SE: z -1.61, so miss. It falls beyond the permutation null, but the prediction asked for both. Without income-restricted ads the gap is z -3.03, which I note but don't count, since I added that version after the first pass.
- Lots with no tax-bill entry between -1% and +1%, and lots with stabilized units 1 to 5 points lower: no entry -5.12%, and the difference has the opposite sign (+1.97, z 1.18). Miss on both parts in every version. The no-entry group is small (90 to 332 flagged ads) and its intervals are wide.
- Pre-1974 coefficient 1 to 4 points lower after 2019-06-14: -0.09. Miss.
- 2008-on coefficient changes by under 1.5 points across 2019-06-14: -4.27 points. Miss.
- Fewer than 1 in 5 flagged ads with no within-building contrast: 2.7%. Hit.

That gives 3 hits and 5 misses.

## Reading

The flag's discount doesn't follow the split I predicted. Pre-1974 buildings carry a steady discount of about 3.8% inside the building, unchanged across the 2019 law. The 2008-on buildings, mostly 421-a rentals, show no discount before 2019 and about 2% to 3.4% after it. Part of that change comes from buildings whose flagged share and rent path moved together, as the building-by-period null shows, and the age-by-month control cuts the part beyond that null from 1.9 to 0.7 points. The income-restricted set-asides don't explain it.

Within a building, the flag compares a unit advertised as stabilized with its neighbors that aren't, so the 3.8% is the gap among units of one building and not the gap between a stabilized unit's legal rent and the market's. The stabilized ads that sit far below market may be the ones that are never advertised.

I'd keep the single flag in the model for now. The 2008-on change after 2019 is the one result that could justify a split, and it should be rechecked with building-by-period fixed effects before anyone acts on it. The tax-bill comparison needs a file that records lots with zero stabilized units before it can test the misuse hypothesis.
