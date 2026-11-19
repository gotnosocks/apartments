"""Building turnover against the Deals backtest's errors and outcomes.

The bands of docs/notes/turnover-screen-2026-11-13.md (rate = other units' ads opened in the
730 days before the price day, per residential unit and year; cuts 0.123, 0.223, 0.417) on
the backtest of the Deals model. Usage: turn.py WORKTREE RUN FRAME TURNOVER_DATASET
"""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

W = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location(
    "place", W / "docs/notes/bedtext-base-2026-11-17/place.py"
)
place = importlib.util.module_from_spec(spec)
spec.loader.exec_module(place)
ADS = Path("/data1/apartments/pipeline/datasets/ads-14f9e88d75290a0f.parquet")
J = Path("/data1/apartments/frontier/runs") / sys.argv[2]
h = pd.read_parquet(sys.argv[3])
h["listing_id"] = h.listing_id.astype(str)
cols = ["listing_id", "price_at", "bld_opened_730", "res_units_asof"]
t = pq.read_table(f"{sys.argv[4]}/rows.parquet", columns=cols).to_pandas()
t["listing_id"] = t.listing_id.astype(str)
h = h.merge(t, on=["listing_id", "price_at"], how="left", validate="1:1")
n = h.bld_opened_730.to_numpy(float)
u = h.res_units_asof.to_numpy(float)
known = np.isfinite(u) & (u > 0)
rate = np.where(known, n / 2 / np.where(known, u, 1), np.nan)
band = np.select(
    [n == 0, ~known, rate <= 0.123, rate <= 0.223, rate <= 0.417],
    ["none", "units unknown", "Q1", "Q2", "Q3"],
    "Q4",
)
h["band"] = band
h["rate"] = rate
h["new"] = np.where(h.kind == "no unit history", "no unit history", "unit seen")
h["low"] = h.cdf < 0.05
h["high"] = h.cdf > 0.95
pd.set_option("display.width", 200)


def tab(d, key):
    def one(g):
        b = g.groupby("building").res.agg(["sum", "count"])
        m = g.res.mean()
        se = np.sqrt(((b["sum"] - m * b["count"]) ** 2).sum()) / len(g)
        return pd.Series(
            {
                "n": len(g),
                "bld": len(b),
                "res": m,
                "se": se,
                "sdz": g.z.std(),
                "low": g.low.mean(),
                "high": g.high.mean(),
            }
        )

    return d.groupby(key).apply(one).round(4)


print("held", len(h), "bands", h.band.value_counts().to_dict())
print("\nby band")
print(tab(h, "band").to_string())
print("\nby band and unit history")
print(tab(h, ["new", "band"]).to_string())
print("\nby band and half of buildings")
print(tab(h, ["band", "half"]).to_string())
print("\nby band, bedrooms")
h["bdg"] = np.minimum(h.bedrooms, 3)
print(tab(h, ["bdg", "band"]).to_string())

k = np.isfinite(rate) & (n > 0)
for name, g in (
    ("all", k),
    ("half 0", k & (h.half == 0)),
    ("half 1", k & (h.half == 1)),
):
    d = h[g]
    x = np.log(d.rate.to_numpy())
    x = x - x.mean()
    y = d.res.to_numpy() - d.res.mean()
    b = (x * y).sum() / (x * x).sum()
    e = pd.Series(x * (y - b * x)).groupby(d.building.to_numpy()).sum()
    se = np.sqrt((e**2).sum()) / (x * x).sum()
    print(
        f"slope of res on log rate, {name}: {b:.4f} (se {se:.4f}), sd of log rate {x.std():.3f}"
    )

lid, p, ok, days, change = place.places(J, ADS)
o = pd.DataFrame({"listing_id": lid, "p": p, "ok": ok, "days": days, "change": change})
o = o.merge(h[["listing_id", "band", "new"]], on="listing_id", how="left")
for cut in (0.05, 0.1, 0.2):
    print(f"\nfirst ask below the {cut:.0%} point, by band")
    for b_, g in o[o.ok].groupby("band"):
        lo = g[g.p < cut]
        print(
            f"  {b_:14s} ads {len(g):5d} low {len(lo):4d} ({100 * len(lo) / len(g):4.1f}%)"
            f" cut {100 * (lo.change < -0.001).mean():5.1f}% raised {100 * (lo.change > 0.001).mean():5.1f}%"
            f" median days {lo.days.median():.0f}"
        )
print("\nall places, by band")
for b_, g in o[o.ok].groupby("band"):
    print(
        f"  {b_:14s} cut {100 * (g.change < -0.001).mean():5.1f}% raised {100 * (g.change > 0.001).mean():5.1f}%"
        f" median days {g.days.median():.0f}"
    )
