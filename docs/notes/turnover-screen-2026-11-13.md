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
