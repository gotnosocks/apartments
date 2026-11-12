"""Rank units by how far their training asks sit from the other units of their building with
the same bedroom count in the same year, after a repeat-ad month index. This stands in for
u2a's unit levels, which the run did not save."""

import numpy as np, pandas as pd, json

h = pd.read_parquet("/data1/apartments/site/diagnostics/history.parquet")
a = pd.read_parquet(
    "/data1/apartments/site/diagnostics/ads.parquet",
    columns=["listing_id", "building", "unit_id"],
)
h = h[(~h.heldout) & (h.ask > 0)].copy()
h["ly"] = np.log(h.ask.astype(float))
d = pd.to_datetime(h.day)
h["mon"] = d.dt.year * 12 + d.dt.month
h["yr"] = d.dt.year
h["apt"] = h.building + "|" + h.unit_id
dev = h.ly - h.groupby("apt").ly.transform("mean")
idx = dev.groupby(h.mon).mean()
idx = idx.reindex(range(h.mon.min(), h.mon.max() + 1)).interpolate().bfill().ffill()
h["adj"] = h.ly - idx.reindex(h.mon).values
g = ["building", "bedrooms", "yr"]
G = h.groupby(g).adj.agg(["sum", "size"])
U = (
    h.groupby(["apt", *g])
    .adj.agg(["sum", "size"])
    .reset_index()
    .join(G, on=g, rsuffix="_g")
)
U["on"] = U.size_g - U["size"]
U = U[U.on >= 3]
U["other"] = (U.sum_g - U["sum"]) / U.on
U["dev"] = U["sum"] / U["size"] - U.other
w = U.groupby("apt").apply(
    lambda x: pd.Series(
        {
            "dev": np.average(x.dev, weights=x["size"]),
            "n": x["size"].sum(),
            "others": x.on.sum(),
        }
    ),
    include_groups=False,
)
w["score"] = w.dev * w.n / (w.n + 1)
ss, nu = 0.0412, 2.19
w["kap"] = (nu + 1) / (nu + (w.score / ss) ** 2)
a["apt"] = a.building + "|" + a.unit_id
tgt = a.drop_duplicates("apt", keep="last").set_index("apt").listing_id
w = w.join(tgt, how="inner")
w = w.reindex(w.score.abs().sort_values(ascending=False).index)
w["rank"] = np.arange(1, len(w) + 1)
w.to_parquet("ranked.parquet")
print(len(w), "units ranked")
print(w.score.abs().quantile([0.5, 0.9, 0.99, 0.999]).round(3).to_dict())
print(
    "top200 |score| range",
    w.score.abs().iloc[[0, 199, 1999]].round(3).tolist(),
    "over/under in top200",
    (w.score.iloc[:200] > 0).sum(),
)
rng = np.random.default_rng(20261112)
pick = pd.concat(
    [
        w.iloc[:200].assign(stratum="top200"),
        w.iloc[200:2000]
        .iloc[np.sort(rng.choice(1800, 100, replace=False))]
        .assign(stratum="rank201_2000"),
    ]
)
pick.to_parquet("pick.parquet")
print(pick.stratum.value_counts().to_dict())
