"""Thin buildings on the latest split: does the miss sit where the building's training ads
are all the ad's own unit (the split of the level from the unit cannot matter there)?"""

import numpy as np
import pandas as pd

pd.set_option("display.width", 250)
o = pd.read_parquet("d1_ads.parquet")
t = o[o.n_bld <= 5].copy()
t["own_only"] = t.n_other == 0
t["band"] = pd.cut(
    t.level,
    [-9, -0.3, -0.1, 0.1, 0.3, 9],
    labels=["<-.3", "-.3:-.1", "mid", ".1:.3", ">.3"],
)
clean = ~t.odd & ~t.own_odd
g = lambda x: pd.Series(
    dict(
        ads=len(x),
        bld=x.building.nunique(),
        gap=x.gap.mean(),
        gap_med=x.gap.median(),
        below5=(x.cdf < 0.05).mean(),
        above95=(x.cdf > 0.95).mean(),
        level=x.level.mean(),
    )
)  # noqa: E731
print(t.groupby(["own_only", "band"], observed=True).apply(g).round(3).to_string())
print("by half, level over .3")
print(t[t.level > 0.3].groupby(["half", "own_only"]).apply(g).round(3).to_string())
print("clean only")
print(
    t[clean].groupby(["own_only", "band"], observed=True).apply(g).round(3).to_string()
)
for nm, m in (("own only", t.own_only), ("other units too", ~t.own_only)):
    for h in (0, 1):
        x = t[m & (t.half == h)]
        b = np.polyfit(x.level, x.gap, 1)
        print(nm, "AB"[h], len(x), "slope", round(b[0], 3))
hi = o[(o.n_bld <= 5) & (o.level > 0.3)]
lo = o[(o.n_bld <= 5) & (o.level < -0.3)]
for nm, x in (("thin high", hi), ("thin low", lo)):
    od = x.odd | x.own_odd
    print(
        nm,
        "ads",
        len(x),
        "bld",
        x.building.nunique(),
        "odd ads",
        od.sum(),
        "gap odd",
        round(float(x.gap[od].mean()), 3) if od.any() else None,
        "gap rest",
        round(float(x.gap[~od].mean()), 3),
        "below5 rest",
        (x.cdf[~od] < 0.05).mean().round(3),
        "above95 rest",
        (x.cdf[~od] > 0.95).mean().round(3),
    )
    print("   read classes", x.read_class.value_counts().to_dict())
far = o[(o.n_bld <= 5) & (o.level.abs() > 0.1)]
print(
    "thin far ads",
    len(far),
    far.building.nunique(),
    "odd",
    (far.odd | far.own_odd).sum(),
)
print(
    "share of all held-out ads: thin",
    round((o.n_bld <= 5).mean(), 4),
    "thin far",
    round(len(far) / len(o), 4),
)
# what the whole-score stake is: sum of squared gap removed by the best linear shrink
for h in (0, 1):
    x = o[(o.half == h) & (o.n_bld <= 5)]
    b = np.polyfit(x.level, x.gap, 1)
    r = x.gap - np.polyval(b, x.level)
    print(
        "half",
        "AB"[h],
        "thin rmse",
        np.sqrt((x.gap**2).mean()).round(4),
        "after own-half fit",
        np.sqrt((r**2).mean()).round(4),
        "R2",
        round(1 - (r**2).sum() / ((x.gap - x.gap.mean()) ** 2).sum(), 4),
    )
