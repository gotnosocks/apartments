"""The raise flag with windows of one year, two years and the building's whole record, over the
ads table, and against the held-out errors of the latest-split run (all years).
Usage: raise_all.py ADS HELD_FRAME"""
import sys
import numpy as np, pandas as pd
c = ["listing_id", "building", "unit_id", "first_day", "off_day", "first_ask", "latest_ask"]
a = pd.read_parquet(sys.argv[1], columns=c).drop_duplicates("listing_id")
a = a[a.first_ask.gt(0) & a.latest_ask.gt(0) & a.first_day.notna() & a.building.notna()].reset_index(drop=True)
E = pd.Timestamp("1970-01-01")
a["listing_id"] = a.listing_id.astype(str)
a["d"] = (pd.to_datetime(a.first_day).dt.tz_localize(None) - E).dt.days
a["off"] = (pd.to_datetime(a.off_day).dt.tz_localize(None) - E).dt.days.astype(float).fillna(np.inf)
a["rise"] = a.latest_ask / a.first_ask - 1
a["up"] = a.rise >= 0.15
a["year"] = pd.to_datetime(a.first_day).dt.year
r = a.loc[a.up, ["building", "d", "off", "listing_id", "unit_id"]].rename(columns={"d": "rd", "off": "roff", "listing_id": "rl", "unit_id": "ru"})
m = a[["listing_id", "building", "d", "unit_id"]].merge(r, on="building")
m = m[(m.rd < m.d) & (m.roff < m.d) & (m.ru != m.unit_id)]
m["age"] = m.d - m.rd
W = {"1y": 365, "2y": 730, "5y": 1825, "all": 10**6}
for w, days in W.items():
    a[f"k_{w}"] = a.listing_id.map(m[m.age <= days].groupby("listing_id").size()).fillna(0)
# Closed earlier ads of other units of the building, for a share over the whole record.
a = a.sort_values(["building", "d"]).reset_index(drop=True)
pd.set_option("display.width", 220)
def flag(k):
    return np.select([k >= 5, k >= 2, k == 1], ["5+", "2-4", "1"], "0")
print("ADS TABLE: share ending 15%+ above the first ask, by window and count of earlier raised ads")
for w in W:
    f = flag(a[f"k_{w}"])
    print(w, a.groupby(f).agg(n=("up", "size"), bld=("building", "nunique"), up15=("up", "mean")).round(4).T.to_string().replace("\n", "\n   "))
print("\nrecency inside the whole-record flag (2+ ever): by years since the building's newest earlier raised ad")
last = m.groupby("listing_id").age.min()
a["since"] = a.listing_id.map(last)
b = a[a.k_all >= 2]
print(b.groupby(pd.cut(b.since, [0, 90, 365, 730, 1825, 10**5])).agg(n=("up", "size"), up15=("up", "mean")).round(4).to_string())
print("\n2024 on, whole record 2+ but none in the past year:", a[(a.year >= 2024) & (a.k_all >= 2) & (a.k_1y == 0)].up.agg(["size", "mean"]).round(4).to_dict(),
      "; 1y 2+:", a[(a.year >= 2024) & (a.k_1y >= 2)].up.agg(["size", "mean"]).round(4).to_dict())
h = pd.read_parquet(sys.argv[2], columns=["listing_id", "building", "cdf", "res", "z", "half", "year"])
h["listing_id"] = h.listing_id.astype(str)
h = h.merge(a[["listing_id", "first_ask", "latest_ask", "rise", "up", "k_1y", "k_2y", "k_5y", "k_all"]], on="listing_id")
h["res_first"] = h.res - np.log(h.latest_ask / h.first_ask)
print("\nHELD-OUT HISTORY (latest split):", len(h), "ads")
for w in W:
    f = flag(h[f"k_{w}"])
    g = h.groupby(f).agg(n=("res", "size"), bld=("building", "nunique"), gap_first=("res_first", "mean"), first_15_under=("res_first", lambda x: (x < -0.15).mean()),
                         gap_latest=("res", "mean"), low_latest=("cdf", lambda x: (x < 0.05).mean()), up15=("up", "mean"))
    print(w, g.round(4).to_string().replace("\n", "\n   "))
f = h.k_all >= 2
print("\nwhole record 2+, by half and by period")
print(h.assign(f=f).groupby(["half", "f"]).agg(n=("res", "size"), gap_first=("res_first", "mean"), first_15_under=("res_first", lambda x: (x < -0.15).mean()), up15=("up", "mean")).round(4).to_string())
print(h.assign(f=f, per=pd.cut(h.year, [2000, 2019, 2021, 2023, 2030])).groupby(["per", "f"], observed=True).agg(n=("res", "size"), gap_first=("res_first", "mean"), first_15_under=("res_first", lambda x: (x < -0.15).mean()), up15=("up", "mean")).round(4).to_string())
