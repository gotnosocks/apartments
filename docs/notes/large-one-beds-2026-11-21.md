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

## Results

`l1_read.log`, `l3_tally.log` and `l4_fills.log` hold the output. From 2022 on, by half
of buildings:

| ads                | n (A / B) | residual (A / B) | below 10% (A / B) | above 90% (A / B) |
|--------------------|-----------|------------------|-------------------|-------------------|
| group              | 672 / 571 | −0.021 / −0.015  | 0.222 / 0.214     | 0.112 / 0.121     |
| stated size        | 446 / 396 | −0.013 / −0.011  | 0.209 / 0.194     | 0.114 / 0.136     |
| filled size        | 226 / 175 | −0.036 / −0.025  | 0.248 / 0.257     | 0.106 / 0.086     |
| studios            | 72 / 61   | −0.026 / −0.001  | 0.264 / 0.246     | 0.097 / 0.131     |
| other ads          | 62k / 66k | −0.005 / −0.006  | 0.106 / 0.107     | 0.082 / 0.079     |

65% of the group's misses fall below the 10% point. The reference gains 2,504.0 (SE 92.7)
over the stored predictives at 7 degrees of freedom. The group's scale and shift marks add
+65.2 (SE 13.7), +37.0 and +28.2 by half, with a scale of 1.257 and 1.251 and a shift of
−0.012 and −0.011. Split by size source and studio they add +0.4 (3.8) more. Coverage of
the 80% interval:

| ads           | own   | reference | + group | + split | ads     |
|---------------|-------|-----------|---------|---------|---------|
| filled size   | 0.651 | 0.703     | 0.798   | 0.808   | 401     |
| stated size   | 0.673 | 0.684     | 0.804   | 0.789   | 842     |
| other ads     | 0.813 | 0.801     | 0.800   | 0.800   | 128,618 |

Three Sonnet readers named one kind for each of the 120 sampled ads, shuffled, with dollar
amounts blanked and no direction given:

| kind      | low | high | inside | misses per inside |
|-----------|-----|------|--------|-------------------|
| loft      | 8   | 10   | 14     | 1.29              |
| other     | 8   | 6    | 17     | 0.82              |
| flex      | 6   | 3    | 13     | 0.69              |
| luxury    | 2   | 6    | 12     | 0.67              |
| mismatch  | 5   | 1    | 0      | none inside       |
| outdoor   | 1   | 3    | 2      | 2.00              |
| converted | 0   | 1    | 2      | 0.50              |

The five low mismatches are a size that counts an 800 sq ft basement, a full floor of a
house with two bedrooms, and three sizes filled from the line (a building ad, a
rent-stabilized studio at 1,562 sq ft, and an ad that calls itself both a studio and a one
bedroom). Coded size source splits the sample more than any kind does:

| size source | low | high | inside |
|-------------|-----|------|--------|
| stated      | 9   | 21   | 44     |
| unit fill   | 16  | 9    | 13     |
| line fill   | 5   | 0    | 3      |

Filled sizes are 21 of the 30 low misses, 9 of the 30 high and 16 of the 60 inside.
`l4_fills.py` checks the 38 unit fills in the sample against the unit's other ads with a
stated size and no rent: the size came from an ad with more bedrooms for 2 of 16 low, 2 of
9 high and 1 of 13 inside, so a fill from a larger layout explains few of them.

## Predictions scored

1. Right. The residual is −0.021 and −0.015 by half, and 65% of misses are low.
2. Wrong. Filled sizes cover 0.651 against 0.673 on the stored predictives, a gap of 0.022,
   and 0.703 against 0.684 under the reference.
3. Partly right. The marks gain +65.2, above the +15 to +60 range, and are positive on both
   halves with a scale of 1.25 in range; the split adds +0.4, under 15.
4. Wrong. No kind is twice as common among misses as inside with 10 misses. Lofts lead
   the misses at 18 with a ratio of 1.29; a size at odds with the text holds 6 misses and
   none inside.
5. Partly right. Lofts are the commonest high miss (10 of 30). Among the low misses lofts
   and other tie at 8, with a size at odds with the text at 5.

## What follows

The group's wide spread is real and broad: a scale of 1.25 and a small low shift earn
+65.2, and no kind a reader names takes the misses as a block. The low tail's deepest
misses lean on filled sizes, more than the marks split by source pick up, and the
readers' few clear errors there are sizes filled from the line or sizes that count a
basement or a whole floor. Two items go to the TODO: carry a large 0-1-bedroom mark beside
U1 on the base refit's list (U1 alone leaves the group at 0.702), and a data check on
line fills over 1,000 sq ft for 0-1-bedroom ads, which may need a cap on the line fill
before any model term.
