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
