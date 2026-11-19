"""Low ads on the backtest day by how they got there: at the first ask, cut, or raised.

Reads the per-ad frame of `current.py` saved with each ad's first day and off day
(columns place, own, after, mark, off, first_day). Usage: kinds.py FRAME
"""

import sys

import numpy as np
import pandas as pd

DAY = pd.Timestamp("2025-11-10")

t = pd.read_parquet(sys.argv[1])
t["left"] = (t.off - DAY).dt.days
t["age"] = (DAY - t.first_day).dt.days
t["kind"] = np.select(
    [t.own < -0.001, t.own > 0.001],
    ["cut before the day", "raised before the day"],
    "at first ask",
)


def table(frame, label):
    out = frame.groupby(["kind", "mark"]).agg(
        ads=("after", "size"),
        up15=("after", lambda v: (v >= 0.15).mean()),
        up5=("after", lambda v: (v >= 0.05).mean()),
        cut5=("after", lambda v: (v <= -0.05).mean()),
        gone14=("left", lambda v: (v <= 14).mean()),
        gone30=("left", lambda v: (v <= 30).mean()),
        days_left=("left", "median"),
        age=("age", "median"),
    )
    print(label)
    print(out.round(3).to_string())


table(t, "all")
table(t[t.place < 0.05], "below the 5% point")
table(t[t.place < 0.10], "below the 10% point")
table(t[(t.place > 0.3) & (t.place < 0.7)], "30% to 70% points")
