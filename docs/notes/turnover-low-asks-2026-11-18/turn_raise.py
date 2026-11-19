"""Size of the later change of first asks, by band and tail. Usage: turn_raise.py WORKTREE RUN FRAME"""

import sys
from pathlib import Path
import numpy as np, pandas as pd

sys.path.insert(0, f"{sys.argv[1]}/docs/notes/bedtext-base-2026-11-17")
import place
from rentfrontier import run as run_module

ADS = Path("/data1/apartments/pipeline/datasets/ads-14f9e88d75290a0f.parquet")
J = Path(run_module.RUNS) / sys.argv[2]
lid, p, ok, days, change = place.places(J, ADS)
o = pd.DataFrame(
    {
        "listing_id": np.asarray(lid).astype(str),
        "p": p,
        "ok": ok,
        "days": days,
        "change": change,
    }
)
h = pd.read_parquet(sys.argv[3]).drop(columns=["description"])
o = o.merge(h[["listing_id", "band", "building", "latest_ask", "res"]], on="listing_id")
o = o[o.ok]
o["hot"] = np.where(o.band.isin(["Q4", "units unknown"]), "Q4/unk", "other")
o["tail"] = np.select([o.p < 0.05, o.p < 0.2, o.p > 0.8], ["<5", "5-20", ">80"], "mid")
pd.set_option("display.width", 200)
print("change summary", o.change.describe().round(3).to_dict())
r = o[o.change > 0.001]
print(
    r.groupby(["hot", "tail"])
    .change.describe(percentiles=[0.25, 0.5, 0.75])
    .round(3)
    .to_string()
)
bins = [0, 0.02, 0.05, 0.07, 0.10, 0.14, 0.2, 0.3, 5]
r = r.assign(cb=pd.cut(r.change, bins).astype(str))
print(r.groupby(["hot", "tail", "cb"]).size().unstack(fill_value=0).to_string())
lo = o[(o.hot == "Q4/unk") & (o.p < 0.05)]
print(
    "\nlow hot: raised share",
    (lo.change > 0.001).mean(),
    "n",
    len(lo),
    "buildings",
    lo.building.nunique(),
)
print("after the raise, share still below pred by 5%:", ((lo.res + 0) < -0.05).mean())
print(
    lo[lo.change > 0.001]
    .assign(pct=lambda d: np.round(100 * (np.exp(d.change) - 1), 1))
    .pct.round(0)
    .value_counts()
    .sort_index()
    .to_string()
)
print(
    "days by raised", lo.groupby(lo.change > 0.001).days.describe().round(1).to_string()
)
a = (
    place.drift_deals._ads(ADS, lo.listing_id)
    if hasattr(place, "drift_deals")
    else None
)
from rentfrontier import drift_deals

a = drift_deals._ads(ADS, lo.listing_id)
lo = lo.assign(
    first=a.first_ask.to_numpy(float),
    page=a.page_price.to_numpy(float),
    free=a.months_free.to_numpy(float),
    first_day=a.first_day.to_numpy(),
    off=a.off_day.to_numpy(),
)
lo["pct"] = np.round(100 * lo.change, 1)
print(
    lo[lo.pct.between(21.5, 30.5)]
    .sort_values("building")[
        [
            "building",
            "first",
            "latest_ask",
            "page",
            "free",
            "pct",
            "days",
            "first_day",
            "p",
            "res",
        ]
    ]
    .round(3)
    .to_string()
)
print(lo[lo.change > 0.001].building.value_counts().head(15).to_string())
