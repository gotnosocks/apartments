# Building turnover against j9's misses on new units (2026-11-13)

S5 (`docs/notes/causal-screens-2026-11-13.md`, parts B and C) found that backtest j9
(`drift-building-b0-market-67d14e17-j9`) prices too low the held-out ads of buildings with few
training ads, and the ads in a building's first year in the data. Its 84 held-out ads in
buildings with no training ads ask 9.2 ± 3.2% over j9's mean location, the 331 in buildings
with 1 to 4 ask 5.1 ± 1.1% over it, and the excess falls to 0.5 ± 0.2% at 100 or more. S5 asked
whether a building's first ads in the data follow a long tenancy, a renovation or a new owner.
In a building whose units rarely come up for rent, I'd expect both few ads and a long tenancy
behind each one. So I count how often each building's other units came up for rent before each
held-out ad, and split j9's misses by that rate.

I read saved runs here and fit nothing.

## The count

For each held-out ad I count the ads of its building opened in the 730 days before the day it
was priced, leaving out the ads of its own unit (building and unit_id, with a row lacking a
unit_id as its own unit). An ad's opening day is its `on_day` in the ads file the dataset's
build read, or the day of its price_at when that comes first, as in
`rentfrontier.b0amenitycarry`. I count the dataset's rows, training and held-out alike, and read
no rent. Then I divide the count by two and by the lot's residential units (`unitsres` in the
PLUTO file of `docs/notes/causal-screens-2026-11-13/common.py`, joined through the registry's
bbl), which gives ads per residential unit and year.

The bands are:

- none, for an ad with no other ads of its building in the 730 days;
- the quartiles of the nonzero rate among j9's held-out ads. I set them from the rates alone
  before reading any gap, and apply them unchanged to L1;
- units unknown, for a lot without `unitsres` above zero.

For the cross with the training-ad count I cut the rate at the median of the nonzero rates:
low turnover is a rate at or below it, none included, and high turnover is a rate above it.

## j9

The population is S5b's: j9's 9,346 held-out ads, the ads on the market on 2025-11-10 under
the market split, in j9's dataset
`/data1/apartments/frontier/datasets/b0-ddd2fe8f5da041b8-alldata-dense-nyc-asof-20251110`. The
gap is the log ask less the mean of j9's predicted location over its kept draws, in percent. A
building's training-ad count is its rows outside the held-out set in j9's dataset, cut at 0,
1-4, 5-19, 20-99 and 100+ as in S5b. SEs are clustered by building.

I report:

1. the gap by turnover band, with each band's training-ad counts;
2. the gap by count bin and turnover band;
3. the contrast between low and high turnover within each count bin, pooled over the bins with
   weights proportional to their ads. A building falls in a single count bin, so the bins'
   contrasts are independent and their SEs add in quadrature;
4. the same pooled contrast over the ads outside their building's first year in the data,
   counted from the building's first opened ad.

## L1

The population is L1's held-out ads (`drift-building-phase-b0-latest-9a7830fb-l1`, the latest
split). I keep those priced at least 730 days after the first opening day in L1's dataset, so
the window lies inside the data. The gap is the log ask less L1's median, and a building's
training-ad count is its training rows in L1's dataset. The bands and the contrast follow j9's.

## Predictions

I wrote these before the script ran.

1. Among j9's held-out ads, the turnover rate and the building's training-ad count have a
   Spearman correlation above 0.2. (75%)
2. Of the 415 held-out ads in buildings with fewer than 5 training ads, more than 60% fall in
   the band with no other ads. (70%)
3. Within count bins, j9's low-turnover ads ask more over its mean location than its
   high-turnover ads. The pooled contrast is positive (60%), and more than 2 SEs above zero
   (35%).
4. In the 1-4 bin the gap stays above +3% in both the low and the high half, wherever a half
   holds at least 50 ads. (60%) If so, turnover doesn't account for the few-ad excess.
5. Outside the building's first year, the pooled contrast keeps at least half its size. (50%)
6. On L1, the pooled contrast lies within ±0.5 points. (70%)
7. The verdict is neither (55%), a column built for a later fit (35%), or a fit (10%).

The screen reads saved runs on the CPU in one `MemoryMax=3G` scope, for no Modal cost.

## Results

`screen.py` in `docs/notes/turnover-screen-2026-11-13/` ran in a single `MemoryMax=3G` scope
and saved its counts to

    /data1/apartments/tmp/sprint-20261113/turnover-screen.json

Gaps are in percent, with SEs clustered by building. Both ads files matched the SHA-256 in their dataset's manifest.

The quartile edges of the nonzero rate among j9's held-out ads are 0.123, 0.223 and 0.417 ads
per residential unit and year, so low turnover is a rate of 0.223 or less. j9's count by
training ads matches S5b's on every bin, from 84 ads at +9.2 ± 3.2 in buildings with none to
5,115 at +0.5 ± 0.2 in buildings with 100 or more.

### j9 by turnover band

| Band | Rate | Ads | Buildings | Gap | Median training ads | Under 5 training ads |
|---|---|---|---|---|---|---|
| none | 0 | 378 | 378 | +5.59 ± 0.97 | 4 | 53% |
| Q1 | to 0.123 | 2,183 | 1,214 | +2.25 ± 0.29 | 108 | 2.4% |
| Q2 | to 0.223 | 2,180 | 953 | +1.17 ± 0.24 | 235 | 1.4% |
| Q3 | to 0.417 | 2,208 | 1,053 | +0.79 ± 0.26 | 152 | 3.3% |
| Q4 | above | 2,153 | 1,152 | -0.72 ± 0.28 | 98 | 2.3% |
| units unknown | | 244 | 64 | +1.42 ± 0.91 | 226 | 3.7% |

The gap falls by about 3 points from the first quartile to the fourth. Outside the band with no
other ads, the training-ad count doesn't fall with it: the median runs 108, 235, 152 and 98
over the quartiles. Across the ads with a known rate, the rate and the training-ad count have
a Spearman correlation of 0.14.

### j9 by training ads and turnover

| Training ads | All | Low turnover | High turnover | Low less high |
|---|---|---|---|---|
| 0 | 84, +9.23 ± 3.19 | 72, +9.00 ± 3.08 | 12, +10.6 ± 13.7 | too few |
| 1-4 | 331, +5.08 ± 1.09 | 211, +5.84 ± 1.31 | 111, +5.05 ± 1.85 | +0.78 ± 2.17 |
| 5-19 | 982, +1.47 ± 0.47 | 575, +2.87 ± 0.66 | 386, -0.71 ± 0.64 | +3.58 ± 0.87 |
| 20-99 | 2,834, +1.30 ± 0.23 | 1,351, +2.61 ± 0.36 | 1,449, +0.02 ± 0.29 | +2.59 ± 0.43 |
| 100+ | 5,115, +0.49 ± 0.17 | 2,532, +0.99 ± 0.22 | 2,403, -0.10 ± 0.26 | +1.10 ± 0.34 |

Pooled over the bins from 1-4 up, the low-turnover ads ask 1.81 ± 0.26 points more over j9's
mean location than the high-turnover ads (9,018 ads). Over the 8,178 ads outside their
building's first year the contrast is +1.82 ± 0.27.

At 5 or more training ads, then, the low-turnover half holds most of each bin's excess, and the
high-turnover half comes close to zero. In the 1-4 bin the split makes no difference: both halves
ask 5% to 6% over j9's mean location, and the bin's 134 ads with no other ads of their building
in the window ask +6.57 ± 1.70, a little above the bin's +5.08 ± 1.09. Turnover doesn't account
for the few-ad excess, and the excess and the turnover gradient look like separate patterns.

### Checks added after the first results

I hadn't written predictions for these.

- I counted turnover over training rows alone, leaving out the other held-out ads open at the
  time, and cut it at its own nonzero median (0.210). The pooled contrast is +1.91 ± 0.26, so
  the gradient doesn't come from several of a building's ads on the market at once.
- S5b's population holds 6,178 ads whose unit has training rows in j9, and 3,168 units new to
  j9. The pooled contrast is +1.31 ± 0.24 for the first (5,941 ads with a known rate) and +3.12
  ± 0.56 for the new units (2,987). Among the new units the gap runs +9.77 ± 1.69 with no other
  ads (185), +4.62 ± 0.65 in the first quartile (746), +1.96 ± 0.56 and +2.31 ± 0.73 in the
  middle two, and -0.37 ± 0.52 in the fourth (905).
- For the ads whose unit has an earlier training ad, I compared fixed-effect slopes on the
  low-turnover flag. Within count bins it is +1.30 ± 0.24. Within count bins crossed with the
  months since the unit's latest earlier training ad (under 12, 12 to 36, 36 or more) it is
  +1.14 ± 0.25, even though the low-turnover share rises from 35% to 52% to 65% over those
  bands. The time since the unit's own last ad takes up little of the gradient.

### L1

All 189,647 held-out ads stay in: L1's dataset opens on 2011-06-18 and its earliest held-out ad
is priced on 2014-01-01. 3,459 of them are priced before 2016, so their window starts
in the thin early data. Every held-out unit has training rows, so L1 has no bin with no
training ads.

| Band | Ads | Gap |
|---|---|---|
| none | 10,301 | -0.60 ± 0.11 |
| Q1 | 38,050 | -0.49 ± 0.05 |
| Q2 | 44,191 | -0.34 ± 0.04 |
| Q3 | 45,969 | -0.30 ± 0.04 |
| Q4 | 48,074 | -0.60 ± 0.04 |
| units unknown | 3,062 | -0.46 ± 0.22 |

| Training ads | All | Low turnover | High turnover | Low less high |
|---|---|---|---|---|
| 1-4 | 5,972, -0.14 ± 0.15 | 5,050, -0.15 ± 0.16 | 873, -0.04 ± 0.39 | -0.11 ± 0.42 |
| 5-19 | 23,105, -0.84 ± 0.07 | 14,442, -0.80 ± 0.09 | 8,437, -0.90 ± 0.11 | +0.10 ± 0.14 |
| 20-99 | 66,871, -0.62 ± 0.04 | 28,775, -0.65 ± 0.05 | 37,661, -0.59 ± 0.05 | -0.06 ± 0.07 |
| 100+ | 93,699, -0.24 ± 0.03 | 44,275, -0.20 ± 0.05 | 47,072, -0.27 ± 0.04 | +0.07 ± 0.06 |

The pooled contrast is +0.02 ± 0.04 points (186,585 ads), +0.01 ± 0.04 outside the first
year, +0.06 ± 0.04 with turnover from training rows alone, and -0.01 ± 0.04 within count bins
and months since the unit's last ad. Over the 70,171 ads priced from 2025 on it is +0.15 ±
0.07. The Spearman correlation of rate and count is 0.15. L1 shows neither the gradient nor a
few-ad excess: its 1-4 bin has a gap of -0.14 ± 0.15.

From saved runs I can't tell which difference between j9 and L1 removes the gradient. L1 adds
lease phases to j9's line, and its held-out ads are the latest ads of units with earlier
training ads, where j9's are the ads on the market on a single day. After the months check
above, I doubt the phases account for all of it, and after the 2025 check I doubt the year
does. No run of L1's line on the market split exists.

## Predictions scored

1. Spearman correlation above 0.2: wrong, 0.14.
2. More than 60% of the 415 ads with fewer than 5 training ads in the band with no other ads:
   wrong, 199 (48%).
3. Pooled contrast positive: right, +1.81 ± 0.26. More than 2 SEs above zero: right.
4. Both halves of the 1-4 bin above +3%: right, +5.84 ± 1.31 and +5.05 ± 1.85.
5. Outside the first year at least half the contrast: right, +1.82 ± 0.27.
6. L1's pooled contrast within ±0.5: right, +0.02 ± 0.04.
7. The verdict below is a column, which I gave 35%.

## Verdict

A column. The few-ad excess stays as S5 left it. On the market split, though, j9's low-turnover
half asks about 1.8 points more over its mean location than the high-turnover half within count
bins, and about 3 points more among units new to j9. j9 is the backtest for ads on the market,
the population the Deals page ranks. If L1's line misses the same way on those ads, the page
ranks ads in buildings whose other units rarely come up for rent as overpriced, and ads in
fast-turning buildings as deals.

The column holds each row's count of its building's other ads opened in the 730 days before its
price day, and the lot's residential units, built by a new `rentfrontier.b0` module like
`b0amenitycarry` into a new dataset. It costs about an hour of work and a build of seconds in a
`MemoryMax=3G` scope, with no Modal. The screen divides by the residential units of a single
PLUTO release (20261017) for every ad, so an ad priced in 2014 reads its lot's units from 2026.
That reads no rent, but the column should take each row's units from the release out at its
price month, as the co-op column does (`docs/notes/coop-column-2026-11-13.md`).

The screen doesn't separate how long tenants stay from what kind of building it is. Low
turnover per residential unit is also what a condo or co-op building, or a large one, would
show, and S5c found that condo and co-op ads ask more than j9 expects. A fit reading the column
should stand it beside the `coop` and `condo` columns.

No fit yet. On the latest split, the scoring split for model changes, L1's held-out ads put the
gain near zero (+0.02 ± 0.04 points). A fit reading the column would need a market-split
backtest of L1's line to compare against first. That backtest is one Modal full fit from the
approved budget, about $11 for three containers as j9 cost $10.91, with the column's fit
after it as a second.
