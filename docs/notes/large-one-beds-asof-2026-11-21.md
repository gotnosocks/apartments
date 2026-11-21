# Large 0-1-bedroom ads on the model's sizes (no fit)

`docs/notes/large-one-beds-2026-11-21.md` found that a scale and shift mark for
0-1-bedroom held-out ads over 1,000 sq ft gains +65.2 (SE 13.7) on l2bt's stored
predictives from 2022 on, with scale 1.25 and coverage rising from 0.69 to 0.80. It drew
the group from the `unit_features` snapshot. l2bt's design reads sizes from the as-of fill
instead (`building_zones_floor_asof.size_table`), and the two agree on 1,093 of the
snapshot group's 1,243 ads ("Which sizes the model reads" in
`docs/notes/size-fill-beds-2026-11-21.md`). A refit term must be defined on the sizes the
fit reads, so this note reads the same mark on the model's sizes.

## Method

`m1_asof.py` copies `l1_read.py` and changes only the source of sizes. It takes `sqft` and
the source (stated, unit, line, none) from
`/data1/apartments/tmp/po-size-fills/sizes.parquet`, which
`docs/notes/size-fills-read-2026-11-20/build.py` checked against `size_table` for l2bt.
The reference, the t degrees of freedom, the halves of buildings, the cross-fit, the split
by source and studio and the coverage tables all stay the same. The group is 0-1-bedroom
held-out ads whose model size is over 1,000 sq ft, read from 2022 on. This script writes
no reader sample. No fit is run and no money is spent. From the size-fill note's count,
the group holds 1,130 ads from 2022 on: 842 stated, 227 unit fills and 61 line fills.

## Predictions, written before the run

1. The group's mean residual is between −0.025 and −0.010 on both halves, and 60% to 70%
   of its misses fall below the 10% point.
2. The group mark gains +45 to +75 over the reference, positive on both halves, with scale
   1.15 to 1.35 fitted on each half.
3. The group's coverage of its 80% interval is 0.66 to 0.72 under the reference and 0.77
   to 0.83 with the mark.
4. The split by source and studio adds under +5 over the group mark.

If predictions 2 and 3 hold, the refit's large 0-1-bedroom mark is defined on the model's
sizes, with the same form.

## Results

`m1_asof.log` holds the output. From 2022 on, by half of buildings (A | B):

| ads            | n (A, B)       | residual         | below 10%    | above 90%    |
|----------------|----------------|------------------|--------------|--------------|
| group          | 618, 512       | −0.0256, −0.0212 | 0.231, 0.229 | 0.102, 0.117 |
| stated size    | 446, 396       | −0.0128, −0.0109 | 0.209, 0.194 | 0.114, 0.136 |
| filled size    | 172, 116       | −0.0585, −0.0564 | 0.291, 0.345 | 0.070, 0.052 |
| other ads      | 62,333, 66,398 | −0.0051, −0.0056 | 0.106, 0.107 | 0.082, 0.079 |

0.679 of the group's misses fall below the 10% point. The group mark gains +71.9 (SE 14.6)
over the reference, +42.0 and +29.9 by half, with scale 1.266 fitted on each half and
shift −0.016 and −0.013. On the snapshot's sizes it gained +65.2 (SE 13.7), scale 1.25.
The split by source and studio adds +9.9 (SE 6.6), +3.9 and +6.0 by half; its filled-size
mark has scale 1.083 and 1.043 and shift −0.025 and −0.033. On the snapshot's sizes the
same split added +0.4.

Coverage of the 80% interval:

| ads         | stored | reference | + group | + split | ads     |
|-------------|--------|-----------|---------|---------|---------|
| filled size | 0.625  | 0.656     | 0.774   | 0.806   | 288     |
| stated size | 0.673  | 0.684     | 0.804   | 0.796   | 842     |
| other       | 0.813  | 0.801     | 0.800   | 0.800   | 128,731 |

The group as a whole covers 0.677 under the reference and 0.796 with the mark.

## Predictions scored

1. Partly right. The residual is −0.0212 on half B, inside −0.025 to −0.010, and −0.0256
   on half A, just below it; 0.679 of misses are low, inside 60% to 70%.
2. Right. +71.9, positive on both halves, scale 1.266 on each.
3. Right. 0.677 under the reference and 0.796 with the mark.
4. Wrong. The split adds +9.9 (SE 6.6), positive on both halves.

## What follows

The mark holds on the sizes the fit reads, a little stronger than on the snapshot's, so
the refit's large 0-1-bedroom mark is defined on the model's sizes with the same form.
On these sizes the filled ads are a clearer block than on the snapshot's: residual −0.058
and −0.056, a third of them below the 10% point, and a shift of their own worth +9.9 at
1.5 SE. That agrees with the refit candidate from `docs/notes/size-fills-read-2026-11-20.md`,
a slope of its own for filled sizes, which these marks do not replace: it acts on every
bedroom count and on size, where this split covers 288 ads. The filled-size result is added
to that TODO item as support, and no separate mark is proposed.
