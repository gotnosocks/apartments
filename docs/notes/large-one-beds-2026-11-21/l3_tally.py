"""Tally the readers' kinds by miss direction (low, high, inside) from key.parquet."""

import pandas as pd

T = "/data1/apartments/tmp/big-small/"
r = pd.concat([pd.read_csv(T + f"read_{i}.csv", dtype=str) for i in (1, 2, 3)])
r["ad"] = r.ad.astype(int)
x = pd.read_parquet(T + "key.parquet").rename(columns={"kind": "dir"})
x = x.merge(r, on="ad", how="left")
print("rows read:", int(x.kind.notna().sum()), "of", len(x))
x["miss"] = x.dir.isin(["low", "high"])
t = pd.crosstab(x.kind, x.dir)
t["misses"] = t.get("low", 0) + t.get("high", 0)
t["miss/inside"] = (t.misses / 60) / (t.inside / 60).where(t.inside > 0)
print(t.to_string())
fl = x["flags"].fillna("").str.replace(" ", "").str.split(",").explode()
f = pd.crosstab(fl.to_numpy(), x.loc[fl.index, "dir"].to_numpy()).drop(
    index="", errors="ignore"
)
print("\nflags (any):")
print(f.to_string())
x.drop(columns="miss").to_csv(T + "reads_keyed.csv", index=False)
s = pd.read_parquet(T + "sample.parquet")[["listing_id", "sqft", "size_source"]]
s["listing_id"] = s.listing_id.astype(str)
x = x.merge(s, on="listing_id", how="left")
ts = pd.to_numeric(x.text_sqft, errors="coerce")
x["text_off"] = (ts.notna()) & ((ts - x.sqft).abs() > 0.15 * x.sqft)
tb = pd.to_numeric(x.text_bedrooms, errors="coerce")
print("\ntext size more than 15% from the size used, by direction:")
print(x.groupby("dir").text_off.agg(["sum", "count"]).to_string())
print("text bedrooms above 1, by direction:")
print((tb > 1).groupby(x.dir).sum().to_string())
print("size source by direction:")
print(pd.crosstab(x.size_source, x.dir).to_string())
print("\nmismatch and text-off ads:")
for r in x[(x.kind == "mismatch") | x.text_off].itertuples():
    print(
        f"  {r.dir:6} {r.kind:9} used {r.sqft:5.0f} ({r.size_source}) text {r.text_sqft}: {r.reason}"
    )
