"""Turnover bands (S13's cuts) against the held-out errors of the latest-split run l2bt."""

import numpy as np, pandas as pd, pyarrow.parquet as pq

h = pd.read_parquet("/data1/apartments/tmp/history-scan/baths-l2bt.parquet")
h["listing_id"] = h.listing_id.astype(str)
D = "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-turnover"
t = pq.read_table(
    D + "/rows.parquet", columns=["listing_id", "bld_opened_730", "res_units_asof"]
).to_pandas()
t["listing_id"] = t.listing_id.astype(str)
t = t.drop_duplicates("listing_id", keep=False)
h = h.merge(t, on="listing_id", how="left")
print("held-out", len(h), "joined", h.bld_opened_730.notna().sum())
n, u = h.bld_opened_730.to_numpy(float), h.res_units_asof.to_numpy(float)
rate = n / np.where(u > 0, u, np.nan) / 2
band = np.select(
    [np.isnan(n), n == 0, ~(u > 0), rate < 0.123, rate < 0.223, rate < 0.417],
    ["no join", "none", "units unknown", "Q1", "Q2", "Q3"],
    "Q4",
)
h["band"] = band


def tab(g, label):
    rows = []
    for b, s in g.groupby("band"):
        k = s.groupby("building").res.agg(["sum", "size"])
        m = s.res.mean()
        se = np.sqrt(((k["sum"] - m * k["size"]) ** 2).sum()) / len(s)
        rows.append(
            dict(
                band=b,
                ads=len(s),
                gap=m,
                se=se,
                low5=(s.cdf < 0.05).mean(),
                high95=(s.cdf > 0.95).mean(),
            )
        )
    print(label)
    print(pd.DataFrame(rows).round(4).to_string(index=False))


tab(h, "all years")
for y0, y1 in ((0, 2019), (2020, 2021), (2022, 2023), (2024, 2030)):
    tab(h[(h.year >= y0) & (h.year <= y1)], f"{y0}-{y1}")
for hf in sorted(h.half.unique()):
    tab(h[h.half == hf], f"half {hf}")
