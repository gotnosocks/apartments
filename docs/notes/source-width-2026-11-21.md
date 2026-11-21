# A width by ad source, sized on stored predictions (no fit)

`docs/TODO.md` lists a width by ad source: on run b9's held-out ads, narrowing the
predictive of ads from a landlord's feed (`FEED`) by a tenth gained +256.6 elpd (SE 43.7),
about +140 beyond a random control (`docs/notes/first-page-read-2026-11-18.md`, "A width
by source, at no cost"). That check used a grid of one factor on a single source, with no
intercept, so part of its gain was the approximation's own preference for a narrower t.
Since then l2bt's design gained lease-phase levels, a Student-t unit level and the bedroom
text reader, and the year scale and flag-change counts have been sized beside it
(`docs/notes/year-scale-2026-11-21.md`, `docs/notes/renovation-step-2026-11-21.md`). Feed
ads may be more common in some years than others, so a width by source should be read
beside the year marks. This note sizes it again on l2bt's stored held-out predictions.

No fit is run and no money is spent. The script and log go in `source-width-2026-11-21/`.

## Method

`s1_source.py` takes the scoring of `docs/notes/year-scale-2026-11-21/y2_followup.py`:
each held-out predictive of l2bt a Student-t on its median with the scale from its
quartiles, the scale multiplied by exp(a · x) and the centre moved by b · x, with an
intercept, a and b fitted on one half of the buildings and scored on the other, and
building-clustered SE. The degrees of freedom are picked to match the stored elpd on the
ads read.

The source marks are `FEED` and `OWNER`, with `PARTNER` (brokerage ads) the reference. The
source is StreetEasy's source type on the ad's latest stored record, read by
`docs/notes/first-page-read-2026-11-18/source.py` (cached for b9's held-out ads); it reads
no ask. Held-out ads of l2bt missing from the cache are read from the records; any left
without a source get a mark of their own. Readings:

- on all years, the source marks over j1's eight kept terms and the year marks;
- from 2022 on, with the t picked on those ads, the source marks over the base, gap bins,
  flag-change counts and year marks of 2022, 2023, 2025 and 2026, which is what a current
  Deals ad would feel;
- the share of feed ads by year, and 80% coverage by source before and after the marks.

## Predictions, written before the script was run

1. From 2022 on, beside the base, gap bins, counts and year marks, the source marks gain
   +80 to +250, positive on both halves.
2. There the feed scale is 0.88 to 0.95 of brokerage ads' on each half, and its shift is
   under 0.01 in size.
3. The owner mark gains under 30 from 2022 on.
4. On all years, beside the base and year marks, the source marks gain +100 to +350.
5. After the marks, 80% coverage of feed ads from 2022 on is within 0.01 of brokerage ads'.

## Results

`s1_source_allyears.log` holds the all-years reading; that run was stopped at the 30-minute
limit on background tasks partway through the from-2022 reading, which was rerun alone as
`s1_source.py --late-only` (`s1_source_late.log`). The records gave a source for all 207
held-out ads of l2bt missing from b9's cache, so no ad lacks one: 140,755 brokerage, 45,547
feed and 3,345 owner ads.

Feed ads were 56% to 69% of the held-out ads of each year from 2014 to 2019, and 17% to 19%
in each year from 2020 on.

| marks | gain (SE) | by half | feed scale, fit on A / B | feed shift |
|---|---|---|---|---|
| source over the base and year marks, all years (t with 5) | +22.4 (8.6) | +10.0, +12.4 | 1.009 / 1.005 | +0.0019 / +0.0019 |
| source over the base, gap bins, counts and year marks, from 2022 (t with 7) | +28.9 (12.1) | +15.2, +13.7 | 0.989 / 0.984 | +0.0031 / +0.0024 |
| feed mark alone, the same, from 2022 | +28.5 (12.0) | +15.8, +12.7 | | |

The owner scale is 1.028 to 1.038 on all years and 1.000 to 1.003 from 2022 on, and the
owner mark gains +0.7 and +1.3.

80% coverage by source, before and after the marks:

| source | all years | from 2022 |
|---|---|---|
| feed | 0.797, 0.799 | 0.804, 0.801 |
| owner | 0.786, 0.799 | 0.802, 0.806 |
| brokerage | 0.799, 0.798 | 0.799, 0.799 |

- Beside the year marks, feed ads need no width of their own. On all years their scale is
  within 1% of brokerage ads'; from 2022 on it is 1% to 1.6% narrower.
- b9's +140 most likely came from the years: feed ads made up most of the ads before 2020,
  and those years need a scale about 4% narrower than 2024's
  (`docs/notes/year-scale-2026-11-21.md`). The earlier check had no year term to take it.
  The two checks also differ in model (b9 against l2bt), so this is read from the shares
  and scales, not tested on b9.
- What is left, about +29 from 2022 on, holds a shift of about +0.003 (feed asks about 0.3%
  above the median) and a scale 1% to 1.6% narrower; the two were not read apart. It is too
  small to earn a term of its own.

## Predictions scored

1. From 2022 on, +80 to +250 on both halves: wrong (+28.9; +15.2 and +13.7).
2. Feed scale 0.88 to 0.95 with a shift under 0.01: wrong on the scale (0.984 and 0.989),
   right on the shift (+0.0024 and +0.0031).
3. Owner mark under 30 from 2022 on: right (+1.3).
4. On all years +100 to +350: wrong (+22.4).
5. Feed coverage from 2022 on within 0.01 of brokerage ads' after the marks: right (0.801
   against 0.799).

## What follows

No term by ad source. The TODO item closes; the year scale (Y1) is already on the base
refit's list and takes the part of b9's gain that came from the years.

