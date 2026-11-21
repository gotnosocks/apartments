"""Test that no input reads a later ad: rebuild with the tables cut at a day and compare.

Usage: check.py DATASET_DIR DAY [DAY ...]. For each day, `build.main` runs on tables holding
no ad opened after the day, no record first dated after it and no closing day past the day
after it. The inputs of the ads opened on the day must equal those of the full build.
"""

import os
import sys

import build
import pandas as pd

OUT = build.OUT
full = pd.read_parquet(f"{OUT}/inputs.parquet").set_index("listing_id")
for day in sys.argv[2:]:
    build.main(sys.argv[1], day)
    cut = pd.read_parquet(f"{OUT}/inputs-cut-{day}.parquet").set_index("listing_id")
    os.remove(f"{OUT}/w-cut-{day}.duckdb")
    same = full[pd.to_datetime(full.d) == pd.Timestamp(day)].sort_index()
    cut = cut.sort_index()[same.columns]
    assert len(cut) == len(same) and (cut.index == same.index).all()
    bad = []
    for c in same:
        a, b = same[c], cut[c]
        if pd.api.types.is_numeric_dtype(a):
            a, b = a.astype(float), b.astype(float)
        if not a.equals(b):
            bad.append(c)
    print(
        day,
        "ads opened that day",
        len(same),
        "held-out",
        int(same.held.sum()),
        "columns compared",
        same.shape[1],
        "columns that differ",
        bad,
    )
