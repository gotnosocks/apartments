# Studios and one-bedrooms over 1,000 sq ft (no fit)

On l2bt's latest split, held-out ads of 0 or 1 bedroom with a known size over 1,000 sq ft
cover 0.690 of their 80% interval from 2022 on, and a size scale shared by every bedroom
count leaves them at 0.702 (`docs/notes/unit-scale-2026-11-21.md`). This note asks what
those ads have in common, which way they miss, and whether a mark for them earns a place.

No fit is run and no money is spent. Scripts and logs go in `large-one-beds-2026-11-21/`.

## What is known before any reading of their errors

`comp.py` reads no rent or error. From 2022 on, l2bt holds out 1,243 such ads, 3.1% of the
sized 0-1-bedroom ads. 1,110 are coded 1 bedroom and 133 studios. 842 have the size stated
in the ad, 340 filled from the unit's other ads and 61 from its line. The median size is
1,156 sq ft, the 90% point 1,519.

## Method

`l1_read.py` reads the group on l2bt's stored held-out predictives from 2022 on as
`docs/notes/unit-scale-2026-11-21/u1_scale.py` does: a Student-t on each median with its
scale from the quartiles, the degrees of freedom picked on the stored elpd, scale and shift
marks cross-fitted by halves of buildings, with building-clustered SE. The reference holds
j1's eight terms, the gap bins, the flag-change counts and the year marks of 2022, 2023,
2025 and 2026.

1. The group's residual by half, the shares below the 10% point and above the 90% point,
   and the same split by size source (stated, filled) and by studio or 1 bedroom.
2. A scale and a shift mark for the group over the reference, then the same marks split
   by size source.
3. The 30 ads of the group with the lowest and the 30 with the highest predictive cdf
   (outside the 10% and 90% points), read by Sonnet readers from the ad's full text and
   coded fields with the ask and the model's price left out. Each reader names the
   apartment's kind (loft, a converted commercial floor, a unit with a home office or flex
   room, a size that counts outdoor space, a size or bedroom count at odds with the text,
   other) without knowing which way it missed. The same reading of 60 ads of the group
   inside the interval gives the base rate of each kind.

## Predictions, written before any reading of their errors

1. The misses lean low: the group's mean residual is below −0.01 on both halves, and over
   60% of the ads outside the 80% interval are below its 10% point.
2. Filled sizes miss more than stated ones: the coverage of filled sizes is at least 0.04
   under that of stated sizes.
3. The two marks gain +15 to +60 over the reference, positive on both halves, with a scale
   of 1.15 to 1.35. Split by size source they add under 15 more.
4. Among the 60 misses, at least one kind named by the readers is at least twice as common
   as among the 60 ads inside the interval, and holds at least 10 of the misses.
5. Lofts and converted floors are the commonest kind among the high misses, and a size or
   bedroom count at odds with the text the commonest among the low misses.
