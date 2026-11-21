"""Tally the readers' kinds by miss direction (low, high, inside) from key.parquet."""

import pandas as pd

T = "/data1/apartments/tmp/big-small/"
r = pd.concat([pd.read_csv(T + f"read_{i}.csv", dtype=str) for i in (1, 2, 3)])
r["ad"] = r.ad.astype(int)
x = pd.read_parquet(T + "key.parquet").merge(r, on="ad", how="left")
print("rows read:", int(x.kind.notna().sum()), "of", len(x))
x["miss"] = x.kind_x.isin(["low", "high"])
t = pd.crosstab(x.kind_y, x.kind_x)
t["misses"] = t.get("low", 0) + t.get("high", 0)
t["miss/inside"] = (t.misses / 60) / (t.inside / 60).where(t.inside > 0)
print(t.to_string())
fl = x.flags.fillna("").str.replace(" ", "").str.split(",").explode()
f = pd.crosstab(fl, x.loc[fl.index, "kind_x"]).drop(index="", errors="ignore")
print("\nflags (any):")
print(f.to_string())
x.drop(columns="miss").to_csv(T + "reads_keyed.csv", index=False)
