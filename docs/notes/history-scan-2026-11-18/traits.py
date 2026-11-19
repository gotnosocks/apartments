"""Coded traits against the held-out normal score of the base model (b9), by half of buildings."""

import re
import sys

import numpy as np
import pandas as pd
from scipy.stats import norm

O = "/data1/apartments/tmp/history-scan"
ADS = "/data1/apartments/pipeline/datasets/ads-14f9e88d75290a0f.parquet"
d = pd.read_parquet(f"{O}/ads.parquet")
RUN = sys.argv[1] if len(sys.argv) > 1 else "drift-building-b0-latest-67d14e17-b9"
sc = np.load(
    f"/data1/apartments/frontier/runs/{RUN}/pred_scores.npz", allow_pickle=True
)
sc = pd.DataFrame(
    {
        "listing_id": sc["listing"],
        "cdf": sc["cdf"],
        "res": sc["y"] - sc["pred"],
        "unit_sd": sc["unit_sd"],
    }
)
d = d.drop(columns=["cdf", "z"]).merge(sc, on="listing_id")
d["z"] = norm.ppf(d.cdf.clip(1e-6, 1 - 1e-6))
print(RUN, len(d))
tx = pd.read_parquet(f"{O}/texts-b9.parquet", columns=["listing_id", "description"])
f = pd.read_parquet(
    ADS,
    columns=[
        "listing_id",
        "months_free",
        "lease_term",
        "first_ask",
        "latest_ask",
        "page_price",
        "physical_floor",
        "elevator",
        "bedrooms",
        "first_day",
        "status",
        "concession",
        "days_on_market",
        "floors_above_ground",
    ],
)
d = d.merge(tx, on="listing_id", how="left").merge(f, on="listing_id", how="left")
d["text"] = d.description.fillna("").str.lower().str.replace(r"\s+", " ", regex=True)
LOW = norm.ppf(0.05)

TRAITS = {
    "net wording": r"\bnet effective\b|\bnet rent\b|\bis net\b|\bnet price\b|\bnet of\b|\bgross rent\b|\bgross price\b|\ba gross\b|\beffective rent\b|\brent advertised\b|\badvertised (?:rent|price) (?:is|reflects)\b|\blisted (?:rent|price) (?:is|reflects)\b",
    "months free": r"\bmonths? free\b|\bfree months?\b|\bmonths? of free\b|\bfree rent\b",
    "junior": r"\bjunior\b|\bjr\.? ?(?:1|one|4|four)\b|\bjr\b",
    "railroad": r"\brailroad\b",
    "flex / convertible": r"\bflex\b|\bconvertible\b|\bconverted\b",
    "asap": r"\basap\b",
    "deal words": r"\bdeal\b|\bpriced to\b|\bwon't last\b|\bwont last\b|\bbelow market\b|\bbargain\b",
    "no fee": r"\bno (?:broker'?s? )?fee\b",
    "parlor": r"\bparlor\b|\bparlour\b",
    "gut renovated": r"\bgut[- ]renovat",
    "primary bedroom": r"\bprimary (?:bedroom|suite|bath)",
    "private garden": r"\bprivate (?:garden|backyard|yard)\b",
    "home office": r"\bhome office\b",
    "ground floor words": r"\bground floor\b|\bground level\b|\bfirst floor\b|\b1st floor\b|\bgarden level\b|\bbasement\b|\blower level\b",
    "sublet / short term": r"\bsublet\b|\bsublease\b|\bshort[- ]term\b",
}


def row(m, half):
    h = d.half == half
    g = d[h & m]
    if len(g) < 30:
        return dict(n=len(g))
    base = d.z[h].mean()
    bm = g.groupby("building").z.agg(["sum", "size"])
    dz = g.z.mean() - base
    # Cluster by building: variance of the mean from building sums of residuals.
    r = bm["sum"] - bm["size"] * g.z.mean()
    se = np.sqrt((r**2).sum()) / len(g)
    return dict(
        n=len(g),
        bld=len(bm),
        dz=dz,
        t=dz / se,
        res=g.res.mean() - d.res[h].mean(),
        low=(g.z < LOW).mean(),
        high=(g.z > -LOW).mean(),
        med_cdf=g.cdf.median(),
    )


def table(masks):
    out = []
    for name, m in masks.items():
        a, b = row(m, 0), row(m, 1)
        out.append(
            {
                "trait": name,
                **{k + "_a": v for k, v in a.items()},
                **{k + "_b": v for k, v in b.items()},
            }
        )
    return pd.DataFrame(out).set_index("trait").round(3)


masks = {k: d.text.str.contains(v, regex=True) for k, v in TRAITS.items()}
pd.set_option("display.width", 250)
print(
    "base low share A, B:", [(d.z[d.half == h] < LOW).mean().round(4) for h in (0, 1)]
)
print(table(masks).to_string())

coded = d.months_free.fillna(0) > 0
net = masks["net wording"] | masks["months free"]
print("\nnet or free-months wording by coded months_free")
print(
    table(
        {
            "wording, coded": net & coded,
            "wording, not coded": net & ~coded,
            "no wording, coded": ~net & coded,
            "net wording only, not coded": masks["net wording"] & ~coded,
            "free-months words only, not coded": masks["months free"]
            & ~masks["net wording"]
            & ~coded,
        }
    ).to_string()
)
d["net"], d["coded"] = net, coded
print("\nshare of held-out ads with wording by year")
d["year"] = pd.to_datetime(d.first_day).dt.year
print(
    d.groupby("year")
    .agg(
        n=("z", "size"),
        wording=("net", "mean"),
        coded=("coded", "mean"),
        low=("z", lambda s: (s < LOW).mean()),
    )
    .round(3)
    .to_string()
)
if len(sys.argv) < 2:
    pd.to_pickle({k: v.to_numpy() for k, v in masks.items()}, f"{O}/trait-masks.pkl")
    d.drop(columns=["description"]).to_parquet(f"{O}/ads-fields.parquet")
