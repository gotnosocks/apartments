"""Do held-out errors cluster by neighbourhood and quarter beyond buildings?

For each held-out ad from Y0 on, the mean residual of the other held-out ads in the same
neighbourhood and quarter, leaving out the ad's own building. A slope of the ad's residual
on that mean near zero says nothing is left for a neighbourhood path."""

import sys

import numpy as np
import pandas as pd

DS = "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc/rows.parquet"
tag, y0 = sys.argv[1], int(sys.argv[2])
h = pd.read_parquet(f"baths-{tag}.parquet")
r = pd.read_parquet(DS, columns=["listing_id", "neighbourhood"]).drop_duplicates(
    "listing_id"
)
h = h.drop(columns=["neighbourhood"], errors="ignore").merge(
    r, on="listing_id", how="left"
)
h = h[h.year >= y0].copy()
h["day"] = pd.to_datetime(h.day).dt.tz_localize(None)
PER = {
    "Q": h.day.dt.year.astype(str) + "Q" + h.day.dt.quarter.astype(str),
    "2Q": h.day.dt.year.astype(str) + "H" + ((h.day.dt.month - 1) // 6 + 1).astype(str),
    "Y": h.day.dt.year.astype(str),
}
h["low"] = h.cdf < 0.05
pd.set_option("display.width", 220)
for name, per in (("quarter", "Q"), ("half year", "2Q"), ("year", "Y")):
    h["per"] = PER[per]
    g = h.groupby(["neighbourhood", "per"])
    gs, gn = g.res.transform("sum"), g.res.transform("size")
    b = h.groupby(["neighbourhood", "per", "building"])
    bs, bn = b.res.transform("sum"), b.res.transform("size")
    on = gn - bn
    h["other"] = (gs - bs) / on.where(on > 0)
    k = h[on >= 20]
    x, y = k.other - k.other.mean(), k.res - k.res.mean()
    slope = (x * y).sum() / (x * x).sum()
    # se clustered by neighbourhood-period
    e = y - slope * x
    cl = (x * e).groupby([k.neighbourhood, k.per]).sum()
    se = np.sqrt((cl**2).sum()) / (x * x).sum()
    r2 = 1 - (e**2).sum() / (y**2).sum()
    print(
        f"\n{name}: ads with 20+ others {len(k)} of {len(h)}; sd of the others' mean {k.other.std():.4f}; slope {slope:.3f} (se {se:.3f}); R2 {r2:.4f}"
    )
    k = k.assign(bin=pd.qcut(k.other, [0, 0.05, 0.25, 0.75, 0.95, 1]))
    print(
        k.groupby("bin", observed=True)
        .agg(
            n=("res", "size"),
            other=("other", "mean"),
            res=("res", "mean"),
            low=("low", "mean"),
            high=("cdf", lambda c: (c > 0.95).mean()),
        )
        .round(4)
        .to_string()
    )
    for hf in (0, 1):
        kk = k[k.half == hf]
        x, y = kk.other - kk.other.mean(), kk.res - kk.res.mean()
        print(f"  half {hf}: slope {(x * y).sum() / (x * x).sum():.3f}")
# The neighbourhood-years furthest below prediction.
g = (
    h.groupby(["neighbourhood", "year"])
    .agg(
        n=("res", "size"),
        bld=("building", "nunique"),
        res=("res", "mean"),
        low=("low", "mean"),
    )
    .reset_index()
)
g = g[(g.n >= 150) & (g.bld >= 30)]
print(
    "\nneighbourhood-years with 150+ ads in 30+ buildings:",
    len(g),
    "sd of mean res",
    g.res.std().round(4),
)
print(g.sort_values("res").head(15).round(4).to_string(index=False))
print(g.sort_values("res").tail(8).round(4).to_string(index=False))
