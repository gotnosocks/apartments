"""Tails of first-ad training rows by input, on the proxy of the 2026-11-12 note.

A row's proxy residual is its log ask less the mean of the other training rows of its
building, bedroom count and year (cells of three or more rows). The yardstick is the
robust scale of all first-ad rows; `far3` and `far6` are the shares beyond 3 and 6 of it.
"""

import numpy as np
import pandas as pd
from common import OUT, bins, half, ratio_se

p = pd.read_parquet(f"{OUT}/proxy.parquet")
t = pd.read_parquet(f"{OUT}/inputs.parquet")
t = t[~t.held]
p["half"] = half(p.building)
rs = lambda x: 1.4826 * np.median(np.abs(x - np.median(x)))  # noqa: E731
first = p[p.k == 1].merge(t, on="listing_id", validate="1:1", suffixes=("", "_t"))
later = p[p.k > 1]
scale = rs(first.cell_res.to_numpy())
print(
    "first-ad training rows with a cell", len(first), "of", len(t), "yardstick", scale
)


def line(name, g):
    out = [f"{name:14}"]
    for h in (0, 1):
        x = g[g.half == h]
        if len(x) < 50:
            out.append(f"{len(x):7} {'':34}")
            continue
        a = np.abs(x.cell_res.to_numpy() - np.median(first.cell_res))
        f6, f3 = a > 6 * scale, a > 3 * scale
        one = np.ones(len(x))
        out.append(
            f"{len(x):7} {x.building.nunique():6} {rs(x.cell_res.to_numpy()):.3f}"
            f" {100 * f3.mean():5.2f} {100 * f6.mean():5.2f}"
            f" ({100 * ratio_se(f6, one, x.building):.2f})"
        )
    print(" | ".join(out).rstrip())


print("columns per half: rows, buildings, own robust scale, far3 %, far6 % (SE)")
line("later rows", later)
line("first-ad rows", first)
b = bins(first)
for col in b:
    print(col)
    for v in sorted(b[col].unique()):
        line("  " + v, first[b[col] == v])
