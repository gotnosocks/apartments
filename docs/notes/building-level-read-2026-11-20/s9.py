import pandas as pd, numpy as np, json
from scipy.stats import norm

pd.set_option("display.width", 250)
pd.set_option("display.max_rows", 300)
L = pd.read_parquet("levels_live.parquet").set_index("building")
D = pd.DataFrame(json.load(open("/data1/apartments/site/deals/deals.json")))
D["rank"] = np.arange(1, len(D) + 1)
unc = D[D.cautions.map(len) == 0].copy()
unc["urank"] = np.arange(1, len(unc) + 1)
D = D.merge(unc[["listing_id", "urank"]], how="left", on="listing_id")
print(len(D), len(unc), D.below_share.is_monotonic_increasing)
D["level"] = D.building.map(L.level)
D["lsd"] = D.building.map(L.level_sd)
D["ntr"] = D.building.map(L.n_train)
D["rhat"] = D.building.map(L.rhat)
print("deals ads w/o level", D.level.isna().sum())
s = (np.log(D.model_hi80) - np.log(D.model_lo80)) / 2 / 1.2816
D["z"] = (np.log(D.ask) - np.log(D.model_median)) / s
D["bs0"] = norm.cdf(D.z + D.level / s)  # level removed
D["bs_n"] = norm.cdf(D.z)
bs = D.below_share.values
D["rank0"] = [int(np.searchsorted(bs, v)) + 1 for v in D.bs0]
P = pd.read_parquet("packet.parquet")
print(P.columns.tolist())
for nm, m in (("HI>0.5", D.level > 0.5), ("LO<-0.3", D.level < -0.3)):
    x = D[m]
    print(
        nm,
        len(x),
        x.building.nunique(),
        "in top300",
        (x["rank"] <= 300).sum(),
        "unc top300",
        (x.urank <= 300).sum(),
    )
    print(
        x[
            [
                "listing_id",
                "building",
                "unit",
                "bedrooms",
                "ask",
                "model_median",
                "below_share",
                "bs_n",
                "bs0",
                "rank",
                "urank",
                "rank0",
                "level",
                "lsd",
                "ntr",
                "unit_ads",
                "cautions",
            ]
        ]
        .round(3)
        .to_string(index=False)
    )
# top300 level distribution
t = D[D["rank"] <= 300]
print(t.level.describe().round(3))
print(
    (t.level > 0.3).sum(),
    (t.level > 0.2).sum(),
    (D.level > 0.3).sum(),
    (D.level > 0.2).sum(),
)
print(
    t[t.level > 0.25][
        [
            "listing_id",
            "building",
            "ask",
            "model_median",
            "below_share",
            "rank",
            "urank",
            "rank0",
            "level",
            "ntr",
            "rhat",
            "cautions",
        ]
    ]
    .round(3)
    .to_string(index=False)
)
# thin high-level buildings among deals
print(
    "thin: level>0.3 & ntr<=5",
    ((D.level > 0.3) & (D.ntr <= 5)).sum(),
    "in top300",
    ((D.level > 0.3) & (D.ntr <= 5) & (D["rank"] <= 300)).sum(),
)
print(
    D[(D.level > 0.3) & (D.ntr <= 5)][
        [
            "listing_id",
            "building",
            "ask",
            "model_median",
            "below_share",
            "rank",
            "urank",
            "rank0",
            "level",
            "ntr",
            "cautions",
        ]
    ]
    .round(3)
    .to_string(index=False)
)
# training summary for hi buildings
h = P[P.grp == "hi"] if "grp" in P else P
g = h.groupby("building").agg(
    n=("ratio", "size"),
    med=("ratio", "median"),
    q25=("ratio", lambda v: v.quantile(0.25)),
    mn=("ratio", "min"),
    mx=("ratio", "max"),
    y0=("year", "min"),
    y1=("year", "max"),
)
print(g.round(2).to_string())
