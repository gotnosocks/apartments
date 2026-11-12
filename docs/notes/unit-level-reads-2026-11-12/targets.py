import pandas as pd, json

p = pd.read_parquet("pick.parquet")
a = pd.read_parquet("/data1/apartments/site/diagnostics/ads.parquet")
h = pd.read_parquet("/data1/apartments/site/diagnostics/history.parquet")
t = a[a.listing_id.isin(p.listing_id)].copy()
t = t.drop_duplicates("listing_id")
t = t.merge(
    p.reset_index()[
        ["listing_id", "dev", "n", "others", "score", "kap", "rank", "stratum"]
    ],
    on="listing_id",
)
t["tail"] = (t.score > 0).map({True: "over", False: "under"})
t["apt"] = t.building + "|" + t.unit_id.str.replace(r"~\d+$", "", regex=True)
h["apt"] = h.building + "|" + h.unit_id.str.replace(r"~\d+$", "", regex=True)
hh = h[h.apt.isin(t.apt)]
ids = sorted(set(t.listing_id.astype(str)) | set(hh.listing_id.astype(str)))
t.to_parquet("targets.parquet")
hh.to_parquet("targets_hist.parquet")
json.dump(ids, open("ids.json", "w"))
print(len(t), len(hh), len(ids))
