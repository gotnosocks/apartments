# Size fills across bedroom counts (no fit)

`docs/notes/large-one-beds-2026-11-21.md` found that 21 of the 30 lowest held-out misses
among 0-1-bedroom ads over 1,000 sq ft have a filled size, against 16 of the 60 ads of that
group inside the 80% interval. `unit_features.sizes` fills an ad's missing size in two
layers, and neither matches the ad's bedroom count all the way:

- `unit` takes the median stated size over every listing of the unit, whatever its
  bedroom count, so a unit re-listed as a 2-bedroom lends that size to its 1-bedroom ads.
- `line` keys each listing by building, line and bedroom count, but then keeps one key per
  unit (`drop_duplicates("unit")`, the first row's bedroom count) and files under it the
  unit's median over all its bedroom counts.

This note counts how often a fill draws on a stated size from another bedroom count, and
how a fill matched on bedroom count would change the sizes of 0-1-bedroom ads. It reads
bedrooms, labels and stated sizes only, with no rent or error. No fit is run and no money
is spent. Scripts and logs go in `size-fill-beds-2026-11-21/`.

## Method

`f1_fills.py` loads the rows that `unit_features.main` reads and runs `sizes` on them,
checking that its output matches the snapshot `20261021-16cea7c`. It then builds a matched
fill: the unit layer is the median stated size over the unit's listings with the same
bedroom count (4 or more pooled), and the line layer is the median over the other units on
the line of each unit's matched median for that bedroom count. For every listing it
records whether its current fill draws on a stated ad of another bedroom count, and its
size under both fills.

1. Among filled listings, the share whose fill draws on another bedroom count, by layer
   and by bedroom count.
2. For 0-1-bedroom listings, the share over 1,000 sq ft among stated sizes, current fills
   and matched fills, and how many current fills over 1,000 sq ft the matched fill leaves
   over it, gives a size the other way, or leaves with none.
3. How many listings lose a size under the matched fill, by bedroom count.

## Predictions, written before the counts

1. Among unit fills, 10% to 30% draw on another bedroom count; among line fills, 20% to 50%.
2. Of 0-1-bedroom listings, 2% to 3% of stated sizes are over 1,000 sq ft, against 4% to
   8% of current fills. Under the matched fill the share of fills over 1,000 sq ft comes
   within 1.5 points of the stated share.
3. Of the current fills over 1,000 sq ft for 0-1-bedroom listings, the matched fill brings
   30% to 60% under 1,000 sq ft or leaves them with no size.
4. The matched fill takes a size from under 5% of the listings that have one now.

If prediction 3 holds, the matched fill goes into `unit_features` as a new snapshot, and
the large one-bedroom mark is read again on a fit that uses it; a change to the size data
changes the served model's inputs, so that refit goes on the base refit's list.
