# A studio reading on ads coded 1 bedroom or more, sized on stored predictions (no fit)

`docs/notes/flex-wording-2026-11-21.md` found that `ad:bed_text_smaller` falls short for one
kind of ad. These are ads coded 1 bedroom or more whose text the bedroom reader takes for a
studio (`bed_text_fewer` with a stated count of 0). On l2bt's held-out errors they ask low
12.5% and 17.5% of the time by half of buildings, against about 6% for unmarked ads. The
TODO asks for a term of their own in the next base refit, with reader fixes. This note sizes
that term the way the other refit candidates were sized: as a scale and shift mark on
l2bt's stored predictives from 2022 on, beside the terms already queued.

## Method

`s1_size.py` copies `docs/notes/large-one-beds-asof-2026-11-21/m1_asof.py`. The reference
is that script's, with the large 0-1-bedroom mark on the model's sizes added to it: j1's
eight terms, the gap bins, the counts of changed flags and the late years. The t degrees of
freedom, the halves of buildings, the cross-fit and the building-clustered SE are unchanged.
The marks come from `fx_marks.parquet` of `docs/notes/flex-wording-2026-11-21/fx1_scan.py`,
with the stated count read again by `b0bedtext` for the `bed_text_fewer` ads. They read the
text and the coded bedrooms only, never the ask. Two marks are tried, each on its own beside
the reference:

- the studio reading: `bed_text_fewer`, stated count 0, coded 1 bedroom or more;
- the whole of `bed_text_smaller` (`bed_flex_at` or `bed_text_fewer`), pooled, as a check
  that the served term already prices the group as a whole.

The reader fixes (amenity names such as "wellbeats studio", "the size of a ... studio") are
not applied, so the mark carries the reader's errors. No fit is run and no money is spent.

## Predictions, written before the run

1. From 2022 on there are 120 to 260 studio-reading ads, with a mean residual between
   −0.040 and −0.008 on both halves, and 15% to 28% of them below the 10% point on both.
2. The studio-reading mark gains +3 to +25 over the reference, positive on both halves,
   with scale 1.0 to 1.4 and shift −0.035 to 0.0 fitted on each half.
3. Its coverage of the 80% interval is 0.66 to 0.78 under the reference and rises by 0.02
   to 0.10 with the mark.
4. The pooled `bed_text_smaller` mark gains under +10, its scale 0.95 to 1.15 on each half.

If 2 holds, the studio reading joins the refit's list at its size, with the reader fixes;
if it gains under +3, the term is dropped from the list and the reader fixes alone remain.
