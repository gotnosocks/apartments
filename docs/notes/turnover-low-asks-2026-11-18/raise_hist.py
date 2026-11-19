"""The raise flag over the whole ads table, with no model: for each ad, the building's other
ads that opened in the 365 days before it, closed before it opened, and ended 15% or more
above their first ask. Outcome: the ad itself ends 15% or more above its first ask.
Usage: raise_hist.py ADS"""

import sys
import numpy as np, pandas as pd

c = [
    "listing_id",
    "building",
    "unit_id",
    "first_day",
    "off_day",
    "first_ask",
    "latest_ask",
    "in_rows",
]
a = pd.read_parquet(sys.argv[1], columns=c).drop_duplicates("listing_id")
a = a[
    a.first_ask.gt(0) & a.latest_ask.gt(0) & a.first_day.notna() & a.building.notna()
].reset_index(drop=True)
E = pd.Timestamp("1970-01-01")
a["d"] = (pd.to_datetime(a.first_day).dt.tz_localize(None) - E).dt.days
a["off"] = (
    (pd.to_datetime(a.off_day).dt.tz_localize(None) - E)
    .dt.days.astype(float)
    .fillna(np.inf)
)
a["rise"] = a.latest_ask / a.first_ask - 1
a["up"] = a.rise >= 0.15
a["year"] = pd.to_datetime(a.first_day).dt.year
print("ads", len(a), "raised 15%+", a.up.mean().round(4))
r = a.loc[a.up, ["building", "d", "off", "listing_id", "unit_id"]].rename(
    columns={"d": "rd", "off": "roff", "listing_id": "rl", "unit_id": "ru"}
)
m = a[["listing_id", "building", "d", "unit_id"]].merge(r, on="building")
m = m[
    (m.rd < m.d)
    & (m.rd >= m.d - 365)
    & (m.roff < m.d)
    & (m.rl != m.listing_id)
    & (m.ru != m.unit_id)
]
a["k"] = a.listing_id.map(m.groupby("listing_id").size()).fillna(0)
n = (
    a[["listing_id", "building", "d"]].merge(
        a[["building", "d", "off"]].rename(columns={"d": "rd", "off": "roff"}),
        on="building",
    )
    if False
    else None
)
pd.set_option("display.width", 200)
a["flag"] = np.select([a.k >= 2, a.k == 1], ["2+", "1"], "0")
print("\nby flag: ads, buildings, share raised 15%+, share raised 8%+, share cut 5%+")
print(
    a.groupby("flag")
    .agg(
        n=("up", "size"),
        bld=("building", "nunique"),
        up15=("up", "mean"),
        up8=("rise", lambda x: (x >= 0.08).mean()),
        cut5=("rise", lambda x: (x <= -0.05).mean()),
    )
    .round(4)
    .to_string()
)
print("\nby year and flag: share raised 15%+ (ads)")
t = (
    a[a.year >= 2015]
    .groupby(["year", "flag"])
    .agg(n=("up", "size"), up15=("up", "mean"))
    .round(4)
    .unstack()
)
print(t.to_string())
print(
    "\nflag 2+: median size of the raise among raised",
    a[(a.flag == "2+") & a.up].rise.median().round(3),
    "; rest",
    a[(a.flag == "0") & a.up].rise.median().round(3),
)
a[["listing_id", "k"]].to_parquet("raise-flag-all.parquet")
