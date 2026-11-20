"""The backtest's lowest tenth by support of the building, and Student-t tail shares."""

import numpy as np
import pandas as pd
from scipy import stats

pd.set_option("display.width", 250)
b = pd.read_parquet("/data1/apartments/tmp/po-thinlevel/back_ads.parquet")
print(len(b), b.caut.eq("").sum(), b.place.describe().round(3).to_dict())
b["sb"] = pd.cut(b.n_bld, [-1, 0, 5, 10, 1e9], labels=["0", "1-5", "6-10", "11+"])
b["far"] = b.level.abs() > 0.1
low = b[(b.place <= 0.1)]
print("lowest tenth by first ask", len(low), "uncautioned", low.caut.eq("").sum())
u = low[low.caut.eq("")]
print(
    u.groupby(["sb", "far"], observed=True)
    .agg(
        ads=("gap", "size"),
        raised=("change", lambda c: (c > 0).mean()),
        level=("level", "mean"),
    )
    .round(3)
    .to_string()
)
print("all backtest ads by support and far")
print(
    b.groupby(["sb", "far"], observed=True)
    .agg(
        ads=("gap", "size"),
        bld=("building", "nunique"),
        gap=("gap", "mean"),
        b5=("cdf", lambda s: (s < 0.05).mean()),
        a95=("cdf", lambda s: (s > 0.95).mean()),
    )
    .round(3)
    .to_string()
)
t = b[(b.n_bld >= 1) & (b.n_bld <= 5)]
print(
    "thin with a level:",
    len(t),
    "far",
    t.far.sum(),
    "over .3",
    (t.level > 0.3).sum(),
    "under -.3",
    (t.level < -0.3).sum(),
)
t10 = b[(b.n_bld >= 1) & (b.n_bld <= 10)]
print(
    "1-10:",
    len(t10),
    "far",
    t10.far.sum(),
    "mean abs gap",
    t10.gap.abs().mean().round(4),
    "far mean abs gap",
    t10.gap[t10.far].abs().mean().round(4),
    "far gap*sign(level)",
    (t10.gap * np.sign(t10.level))[t10.far].mean().round(4),
)
print(
    "thin far gap*sign(level)",
    (t.gap * np.sign(t.level))[t.far].mean().round(4),
    "se",
    ((t.gap * np.sign(t.level))[t.far].std() / np.sqrt(t.far.sum())).round(4),
)
o = pd.read_parquet("d1_ads.parquet")
x = o[(o.n_bld <= 5) & (o.level.abs() > 0.1)]
for h in (0, 1):
    y = x[x.half == h]
    s = y.gap * np.sign(y.level)
    print(
        "l2bt thin far half",
        "AB"[h],
        len(y),
        "gap*sign(level)",
        s.mean().round(4),
        "se",
        (s.std() / np.sqrt(len(y))).round(4),
    )
for k in (4, 6, 8, 12):
    print(
        "t",
        k,
        "beyond 3 and 4 scales",
        [round(2 * stats.t(k).sf(q), 4) for q in (3, 4)],
    )
