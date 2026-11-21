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
the source (stated, unit, line, none) from `/data1/apartments/tmp/po-size-fills/sizes.parquet`,
which `docs/notes/size-fills-read-2026-11-20/build.py` checked against `size_table` for
l2bt. The reference, the t degrees of freedom, the halves of buildings, the cross-fit, the
split by source and studio and the coverage tables all stay the same. The group is
0-1-bedroom held-out ads whose model size is over 1,000 sq ft, read from 2022 on. This
script writes no reader sample. No fit is run and no money is spent. From the size-fill
note's count, the group holds 1,130 ads from 2022 on: 842 stated, 227 unit fills and 61
line fills.

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
