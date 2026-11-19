"""A building flag from training rows alone: ads of the building opened in the year before the
backtest day whose ask rose by 15% or more from its first row to its last. Tested on the
held-out ads' places on the day and their later change. Usage: turn_flag.py WORKTREE RUN FRAME DATASET"""

import sys
from pathlib import Path
import numpy as np, pandas as pd, pyarrow.parquet as pq

sys.path.insert(0, f"{sys.argv[1]}/docs/notes/bedtext-base-2026-11-17")
import place
from rentfrontier import run as run_module

ADS = Path("/data1/apartments/pipeline/datasets/ads-14f9e88d75290a0f.parquet")
J = Path(run_module.RUNS) / sys.argv[2]
h = pd.read_parquet(sys.argv[3]).drop(columns=["description"])
r = pq.read_table(
    f"{sys.argv[4]}/rows.parquet",
    columns=["listing_id", "building", "price_at", "latest_ask"],
).to_pandas()
r["listing_id"] = r.listing_id.astype(str)
day = pd.to_datetime(h.price_at).max()
print("day", day, "rows", len(r))
from rentfrontier import drift_deals

tr = r[~r.listing_id.isin(set(h.listing_id)) & r.building.isin(set(h.building))]
tr = tr[pd.to_datetime(tr.price_at) >= day - pd.Timedelta(days=760)].reset_index(
    drop=True
)
a = drift_deals._ads(ADS, tr.listing_id)
first_day = pd.to_datetime(a.first_day.to_numpy(), utc=True)
ad = pd.DataFrame(
    {
        "building": tr.building.to_numpy(),
        "first_at": first_day,
        "first": a.first_ask.to_numpy(float),
        "last": tr.latest_ask.to_numpy(float),
    }
)
ad = ad[np.isfinite(ad["first"]) & (ad["first"] > 0)]
print("recent training ads", len(ad))
ad["rise"] = ad["last"] / ad["first"] - 1
print(ad.rise.describe(percentiles=[0.05, 0.5, 0.9, 0.95, 0.99]).round(3).to_dict())
for win in (365, 730):
    rec = ad[ad.first_at >= day - pd.Timedelta(days=win)]
    b = rec.groupby("building").agg(
        n=("rise", "size"),
        up15=("rise", lambda x: (x >= 0.15).sum()),
        up8=("rise", lambda x: (x >= 0.08).sum()),
    )
    h[f"n{win}"] = h.building.map(b.n).fillna(0)
    h[f"up15_{win}"] = h.building.map(b.up15).fillna(0)
    h[f"up8_{win}"] = h.building.map(b.up8).fillna(0)
lid, p, ok, days, change = place.places(J, ADS)
o = pd.DataFrame(
    {
        "listing_id": np.asarray(lid).astype(str),
        "p_first": p,
        "ok": ok,
        "days": days,
        "change": change,
    }
)
h = h.merge(o, on="listing_id")
h["low"] = h.cdf < 0.05
h["lowf"] = h.ok & (h.p_first < 0.05)
h["up_later"] = h.change >= 0.15
pd.set_option("display.width", 200)


def tab(flag, name):
    print(f"\n{name}: {int(flag.sum())} ads in {h.building[flag].nunique()} buildings")
    x = (
        h.assign(flag=flag)
        .groupby("flag")
        .agg(
            n=("low", "size"),
            res=("res", "mean"),
            low=("low", "mean"),
            high=("cdf", lambda v: (v > 0.95).mean()),
            lowf=("lowf", "mean"),
            raised15=("up_later", "mean"),
        )
    )
    print(x.round(4).to_string())
    lf = h[h.lowf].assign(flag=flag[h.lowf])
    print(
        "  first asks below 5%:",
        lf.groupby("flag")
        .agg(
            n=("low", "size"),
            raised15=("up_later", "mean"),
            cut=("change", lambda v: (v < -0.001).mean()),
            days=("days", "median"),
        )
        .round(3)
        .to_string()
        .replace("\n", "\n  "),
    )
    print(
        "  by half:",
        h.assign(flag=flag)
        .groupby(["half", "flag"])
        .agg(
            n=("low", "size"),
            low=("low", "mean"),
            lowf=("lowf", "mean"),
            raised15=("up_later", "mean"),
        )
        .round(3)
        .to_string()
        .replace("\n", "\n  "),
    )


tab(h.up15_365 >= 1, "one ad raised 15%+, 365 days")
tab(h.up15_365 >= 2, "two ads raised 15%+, 365 days")
tab(h.up15_730 >= 2, "two ads raised 15%+, 730 days")
tab(
    (h.up15_365 >= 2) & (h.up15_365 / h.n365.clip(lower=1) >= 0.1),
    "two ads and a tenth of the year's ads raised 15%+",
)
tab(h.up8_365 >= 2, "two ads raised 8%+, 365 days")
print("\nband by flag (two ads 15%+, 365 days)")
print(pd.crosstab(h.band, h.up15_365 >= 2).to_string())
f = h.up15_365 >= 2
print("\nwithout flagged buildings, by band: low, lowf")
print(
    h[~f]
    .groupby("band")
    .agg(
        n=("low", "size"),
        res=("res", "mean"),
        low=("low", "mean"),
        lowf=("lowf", "mean"),
    )
    .round(4)
    .to_string()
)
