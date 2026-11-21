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
an ad of another bedroom count of the same unit or line, and a matched fill keeps 2,865 of
all 5,733 large fills over 1,000 sq ft. Whether those borrowed sizes are the deep low
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

### Results

`f2_marks.log` holds the output. Residuals are on the log scale and the tails are the
stored predictive's 10% and 90% points, from 2022 on, by half of buildings (A | B).

| ads                          | n (A, B) | residual       | below 10%    | above 90%    |
|------------------------------|----------|----------------|--------------|--------------|
| group, fill from other count | 102, 84  | −0.020, +0.004 | 0.186, 0.167 | 0.157, 0.131 |
| group, other fill            | 124, 91  | −0.050, −0.051 | 0.298, 0.341 | 0.065, 0.044 |
| group, stated size           | 446, 396 | −0.013, −0.011 | 0.209, 0.194 | 0.114, 0.136 |
| other, fill from other count | 1839, 1777 | −0.003, −0.003 | 0.123, 0.116 | 0.106, 0.101 |
| other                        | 60440, 64562 | −0.005, −0.006 | 0.105, 0.107 | 0.081, 0.079 |

Of the group's filled ads, 0.464 draw on another bedroom count. The two fill marks change
the cross-fitted elpd by −1.3 (SE 3.0) over the reference, −1.7 and +0.4 by half. Their
scales come out near one: 1.034 and 1.008 inside the group, 0.993 and 0.953 outside it.

Coverage of the 80% interval:

| ads                          | stored | reference | + fill marks | ads     |
|------------------------------|--------|-----------|--------------|---------|
| group, fill from other count | 0.677  | 0.833     | 0.833        | 186     |
| group, other fill            | 0.628  | 0.767     | 0.767        | 215     |
| group, stated size           | 0.673  | 0.804     | 0.798        | 842     |
| other, fill from other count | 0.777  | 0.812     | 0.801        | 3,616   |
| other                        | 0.814  | 0.799     | 0.800        | 125,002 |

### Predictions scored

1. Right. 0.464 of the group's filled ads draw on another bedroom count.
2. Wrong. The flagged ads' residual is below the stated sizes' on half A (−0.020 against
   −0.013) and above it on half B (+0.004 against −0.011), and 0.19 and 0.17 of them fall
   below the 10% point.
3. Right. Outside the group the flagged ads' residual is −0.003 on both halves, within
   0.003 of the other ads'.
4. Wrong. The marks lose 1.3 (SE 3.0).
5. Wrong. Under the reference the flagged ads cover 0.833.

## What follows from Step 2

The fills that borrow a size from another bedroom count are not the low misses. Inside the
group they price no worse than stated sizes, and outside it they price like other ads, so
the matched fill is not carried into `unit_features` and goes off the base refit's list.
The group's low misses lean on fills from the same bedroom count: those 215 ads have a
residual of −0.05 on both halves and a third of them below the 10% point. They are few,
and `docs/notes/large-one-beds-2026-11-21.md` found that splitting the group's marks by
size source adds only +0.4, so no further mark is read on them.

## Which sizes the model reads

Both this note and `docs/notes/large-one-beds-2026-11-21.md` read sizes from the
`unit_features` snapshot. l2bt's design does not: `building_zones_floor_asof.size_table`
keeps an ad's stated size and fills a missing one with `sizefill.asof_size` from training
ads priced on earlier days (unit layer, then line layer), keyed by `unit_id`, with full
baths in the line key and a mean of log sizes. So the matched fill above would change no
input of the served design, and Step 2 tests the snapshot's fills, not the model's.

The model's sizes are in `/data1/apartments/tmp/po-size-fills/sizes.parquet`, built for
`docs/notes/size-fills-read-2026-11-20.md`. This count reads bedrooms and sizes only, with
no rent, and was run after Step 2 without predictions. Of the 73,684 held-out 0-1-bedroom
ads from 2022 on, the model gives 1,130 a size over 1,000 sq ft and the snapshot 1,243;
1,093 are in both. The snapshot's 842 stated sizes in that group are stated in the model
too. Of its 401 filled sizes, the model fills 251 over 1,000 sq ft, 51 under it, and leaves
99 with no size. Of the model's 227 unit fills over
1,000 sq ft, 20 draw on an ad of another bedroom count (13 on such ads alone), and 61 more
are line fills.

So under the model's own fill, a large 0-1-bedroom size borrowed from another bedroom
count is rare, and the order of layers that `docs/notes/size-fills-read-2026-11-20.md`
supports (same bedroom count, then line, then another count) already covers it for the
next base refit. The large 0-1-bedroom mark of `docs/notes/large-one-beds-2026-11-21.md`
was read on the snapshot's sizes; on the refit's list it should be defined on the model's
sizes, which keep 1,093 of its 1,243 ads.
