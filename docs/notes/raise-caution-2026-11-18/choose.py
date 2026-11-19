"""Choice of the raise caution's rule on half of the buildings, checked on the other half.

A rule is (W, K): the ad's building has K or more ads of other units that opened in the W
days before the ad, closed before it opened and ended 15% or more above their first ask.
The Deals page lists low asks, so a rule is judged on low first asks: held-out ads of the
latest-split run whose first ask is 15% or more under the prediction. Fixed before the run:
on half A, among rules whose marked low first asks are raised 15% or more later at least
half the time, take the rule that marks the most raised low first asks.
Usage: choose.py ADS HELD_FRAME"""

import hashlib
import sys

import numpy as np
import pandas as pd

SEED = "raise-caution-2026-11-18"
WINDOWS, COUNTS = (60, 90, 180, 365), (1, 2, 3)


def half(building: str) -> int:
    return hashlib.sha1((SEED + building).encode()).digest()[0] & 1


c = [
    "listing_id",
    "building",
    "unit_id",
    "first_day",
    "off_day",
    "first_ask",
    "latest_ask",
]
a = pd.read_parquet(sys.argv[1], columns=c).drop_duplicates("listing_id")
a = a[a.first_ask.gt(0) & a.latest_ask.gt(0) & a.first_day.notna() & a.building.notna()]
a = a.reset_index(drop=True)
E = pd.Timestamp("1970-01-01")
a["listing_id"] = a.listing_id.astype(str)
a["d"] = (pd.to_datetime(a.first_day).dt.tz_localize(None) - E).dt.days
a["off"] = (
    (pd.to_datetime(a.off_day).dt.tz_localize(None) - E)
    .dt.days.astype(float)
    .fillna(np.inf)
)
a["up"] = a.latest_ask / a.first_ask - 1 >= 0.15
a["half"] = a.building.map({b: half(b) for b in a.building.unique()})
r = a.loc[a.up, ["building", "d", "off", "unit_id"]]
r = r.rename(columns={"d": "rd", "off": "roff", "unit_id": "ru"})
m = a[["listing_id", "building", "d", "unit_id"]].merge(r, on="building")
m = m[(m.rd < m.d) & (m.roff < m.d) & (m.ru != m.unit_id)]
m["age"] = m.d - m.rd
for w in WINDOWS:
    a[f"k{w}"] = a.listing_id.map(m[m.age <= w].groupby("listing_id").size()).fillna(0)
h = pd.read_parquet(sys.argv[2], columns=["listing_id", "res", "year"])
h["listing_id"] = h.listing_id.astype(str)
h = h.merge(a, on="listing_id")
h["res_first"] = h.res - np.log(h.latest_ask / h.first_ask)
low = h[h.res_first < -0.15]
print(
    "held-out ads",
    len(h),
    "low first asks",
    len(low),
    "raised 15%+",
    round(low.up.mean(), 4),
)
pd.set_option("display.width", 200)
out = []
for hf in (0, 1):
    A, L = a[a.half == hf], low[low.half == hf]
    for w in WINDOWS:
        for k in COUNTS:
            f, g = A[f"k{w}"] >= k, L[f"k{w}"] >= k
            out.append(
                dict(
                    half="AB"[hf],
                    W=w,
                    K=k,
                    ads=f.sum(),
                    ads_up=A.up[f].mean(),
                    rest_up=A.up[~f].mean(),
                    low=g.sum(),
                    low_bld=L.building[g].nunique(),
                    low_up=L.up[g].mean(),
                    low_raised=int(L.up[g].sum()),
                    low_rest_up=L.up[~g].mean(),
                    recall=L.up[g].sum() / max(L.up.sum(), 1),
                )
            )
t = pd.DataFrame(out)
print(t.round(3).to_string(index=False))
ta = t[(t.half == "A") & (t.low_up >= 0.5)].sort_values("low_raised", ascending=False)
print("\nchosen on half A:", ta.head(1)[["W", "K"]].to_dict("records"))
w, k = int(ta.W.iloc[0]), int(ta.K.iloc[0])
print(
    "on half B:",
    t[(t.half == "B") & (t.W == w) & (t.K == k)].round(3).to_dict("records"),
)
B = low[low.half == 1]
print("half B by period:")
print(
    B.assign(f=B[f"k{w}"] >= k, per=pd.cut(B.year, [2000, 2019, 2021, 2023, 2030]))
    .groupby(["per", "f"], observed=True)
    .agg(n=("up", "size"), up=("up", "mean"))
    .round(3)
    .to_string()
)
