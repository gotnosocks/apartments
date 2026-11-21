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

## Results

`f1_fills.log` holds the output. The rerun of `sizes` matches the snapshot on all
1,969,299 listings. A first run counted a unit fill as drawing on another bedroom count
only when the unit's stated sizes held two or more counts, which missed units whose stated
ads all have one other count; the fixed flag is the one below.

| layer | filled listings | draw on another count | 0 bd  | 1 bd  | 2 bd  | 3+ bd |
|-------|-----------------|-----------------------|-------|-------|-------|-------|
| unit  | 253,014         | 0.189                 | 0.126 | 0.154 | 0.217 | 0.283 |
| line  | 114,983         | 0.086                 | 0.060 | 0.082 | 0.111 | 0.131 |

Over 1,000 sq ft among 0-1-bedroom listings:

| sizes          | listings | over 1,000 sq ft |
|----------------|----------|------------------|
| stated         | 309,533  | 0.0397           |
| current fills  | 217,211  | 0.0264           |
| unit fills     | 135,369  | 0.0342           |
| line fills     | 81,842   | 0.0134           |
| matched fills  | 205,143  | 0.0147           |

Of the 5,733 current fills over 1,000 sq ft for 0-1-bedroom listings, 3,367 draw on
another bedroom count. Under the matched fill 2,865 stay over 1,000 sq ft, 442 fall under
it and 2,426 lose their size (2,145 of them unit fills whose unit states a size only on
ads of another count). Across all listings the matched fill takes a size from 33,747 of
930,485 (0.036): 4,021 studios, 9,642 one-bedrooms, 11,619 two-bedrooms and 8,465 with
three or more. It changes the size of 17,658 more.

## Predictions scored

1. Partly right. Unit fills draw on another bedroom count at 0.189, inside 10% to 30%;
   line fills at 0.086, under 20% to 50%.
2. Wrong. Stated sizes are over 1,000 sq ft for 0.040 of 0-1-bedroom listings, above 2%
   to 3%, and current fills for 0.026, under 4% to 8%. Matched fills, at 0.015, are 2.5
   points under the stated share.
3. Right. The matched fill brings 2,868 of the 5,733 (50%) under 1,000 sq ft or leaves
   them with no size, most of them with none.
4. Right. It takes a size from 3.6% of the listings that have one.

## What follows

Filled sizes are smaller than stated ones in this group, so large fills are not common;
the trouble is where they come from. 59% of the large 0-1-bedroom fills borrow a size from
an ad of another bedroom count of the same unit or line, and a matched fill keeps only half
of them. Whether those borrowed sizes are the deep low
misses is the next question: a mark for a fill that draws on another bedroom count, read
on l2bt's stored predictives as `docs/notes/large-one-beds-2026-11-21.md` reads its group,
with its predictions written below before the run. If it holds, the matched fill becomes a
new `unit_features` snapshot for the base refit.

## Step 2: fill marks on l2bt's stored predictives

`f2_marks.py` is `docs/notes/large-one-beds-2026-11-21/l1_read.py` with the flag from
`f1_fills.py` (a fill that draws on another bedroom count, read from bedrooms, labels and
stated sizes only). The reference is l1's reference plus its group marks for 0-1-bedroom
ads over 1,000 sq ft. Two scale and shift marks go over it, one for flagged fills inside
the group and one for flagged fills outside it, cross-fitted by halves of buildings and
read from 2022 on.

### Predictions, written before the run

1. Of the group's held-out ads with a filled size from 2022 on, 30% to 60% draw on another
   bedroom count.
2. The group's flagged ads have a mean residual below that of its stated sizes on both
   halves, and over 30% of them fall below the 10% point.
3. Outside the group the flagged ads' mean residual is within 0.01 of the other ads', as
   sizes borrowed from more and from fewer bedrooms pull both ways.
4. The two marks gain +5 to +40 over the reference, positive on both halves, most of it
   from the mark inside the group.
5. Under the reference the group's flagged ads cover under 0.75 of their 80% interval.
