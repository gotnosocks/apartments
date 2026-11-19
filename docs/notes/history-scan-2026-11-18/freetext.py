"""Free months stated only in the text against held-out errors of the bed-text model (l2bt)."""

import hashlib

import numpy as np
import pandas as pd
from scipy.stats import norm

O = "/data1/apartments/tmp/history-scan"
DS = "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-freetext/rows.parquet"
ADS = "/data1/apartments/pipeline/datasets/ads-14f9e88d75290a0f.parquet"
RUN = "/data1/apartments/frontier/runs/drift-building-phase-unitkn-level-bedtext-b0-latest-c1ffaefd-l2bt/pred_scores.npz"
r = pd.read_parquet(
    DS,
    columns=[
        "listing_id",
        "building",
        "price_at",
        "months_free_text",
        "free_lease_months",
        "free_text_kind",
        "ask_basis_text",
    ],
)
f = pd.read_parquet(ADS, columns=["listing_id", "months_free"])
r = r.merge(f, on="listing_id", how="left")
s = np.load(RUN, allow_pickle=True)
assert len(s["heldout"]) == len(r)
r["held"] = s["heldout"]
sc = pd.DataFrame(
    {"listing_id": s["listing"], "cdf": s["cdf"], "res": s["y"] - s["pred"]}
)
h = r[r.held].merge(sc, on="listing_id")
assert len(h) == len(sc), (len(h), len(sc))
h["z"] = norm.ppf(h.cdf.clip(1e-6, 1 - 1e-6))
h["half"] = [
    hashlib.sha1(("history-scan-2026-11-18" + str(b)).encode()).digest()[0] % 2
    for b in h.building
]
LOW = norm.ppf(0.05)
coded = h.months_free.fillna(0) > 0
text = h.months_free_text.fillna(0) > 0
h["year"] = pd.to_datetime(h.price_at).dt.year
print(
    "held-out",
    len(h),
    "coded",
    coded.sum(),
    "text months",
    text.sum(),
    "text only",
    (text & ~coded).sum(),
)


def row(g, base):
    if len(g) < 30:
        return dict(n=len(g))
    bm = g.groupby("building").z.agg(["sum", "size"])
    dz = g.z.mean() - base.z.mean()
    se = np.sqrt(((bm["sum"] - bm["size"] * g.z.mean()) ** 2).sum()) / len(g)
    return dict(
        n=len(g),
        bld=len(bm),
        dz=dz,
        t=dz / se,
        res=g.res.mean() - base.res.mean(),
        low=(g.z < LOW).mean(),
        high=(g.z > -LOW).mean(),
    )


def table(masks):
    out = []
    for name, m in masks.items():
        a, b = (row(h[m & (h.half == k)], h[h.half == k]) for k in (0, 1))
        out.append(
            {
                "group": name,
                **{k + "_a": v for k, v in a.items()},
                **{k + "_b": v for k, v in b.items()},
            }
        )
    print(pd.DataFrame(out).set_index("group").round(3).to_string())


pd.set_option("display.width", 250)
to = text & ~coded
m = h.months_free_text
print("\ntext-only free months, by months and by the text's word on the price")
table(
    {
        "text only, all": to,
        "text only, under 1 month": to & (m < 1),
        "text only, 1 month": to & (m == 1),
        "text only, over 1 to 2": to & (m > 1) & (m <= 2),
        "text only, over 2": to & (m > 2),
        "text only, price called net": to & (h.ask_basis_text == "net"),
        "text only, price called gross": to & (h.ask_basis_text == "gross"),
        "text only, basis unstated": to & h.ask_basis_text.isna(),
        "text only, exact": to & (h.free_text_kind == "exact"),
        "text only, up_to": to & (h.free_text_kind == "up_to"),
        "text only, conditional": to & (h.free_text_kind == "conditional"),
        "text only, before 2020": to & (h.year < 2020),
        "text only, 2020-21": to & h.year.isin([2020, 2021]),
        "text only, 2022 on": to & (h.year >= 2022),
        "coded": coded,
        "kind unstated (net or free words, no count)": (h.free_text_kind == "unstated")
        & ~coded,
    }
)
print(h.ask_basis_text.value_counts(dropna=False).to_string())

# The indirect channel: a building whose training ads were net asks with no coded months
# has a level pulled down, so its ads with no offer should be asked above prediction.
t = r[~r.held]
tcoded = t.months_free.fillna(0) > 0
ttext = (t.months_free_text.fillna(0) > 0) & ~tcoded
b = pd.DataFrame(
    {
        "n": t.groupby("building").size(),
        "share": ttext.groupby(t.building).mean(),
        "months": (t.months_free_text.where(ttext, 0)).groupby(t.building).mean(),
    }
)
h = h.merge(b, left_on="building", right_index=True, how="left")
none = ~coded & ~text & ~(h.free_text_kind == "unstated").fillna(False).astype(bool)
print(
    "\nheld-out ads with no offer, by the building's share of training ads with text-only free months"
)
bins = [-1, 0, 0.05, 0.15, 0.3, 0.5, 1]
h["bin"] = pd.cut(h.share.fillna(0), bins)
for k in (0, 1):
    g = h[none & (h.half == k)]
    base = h[h.half == k]
    print("half", "AB"[k])
    print(
        g.groupby("bin", observed=True)
        .agg(
            n=("z", "size"),
            bld=("building", "nunique"),
            dz=("z", lambda s: s.mean() - base.z.mean()),
            res=("res", lambda s: s.mean() - base.res.mean()),
            low=("z", lambda s: (s < LOW).mean()),
            high=("z", lambda s: (s > -LOW).mean()),
        )
        .round(3)
        .to_string()
    )
h["bin"] = h.bin.astype(str)
h.to_parquet(f"{O}/freetext-held.parquet")
# The same by era of the held-out ad, and with the share as a slope.
for lo, hi in ((2014, 2019), (2020, 2021), (2022, 2026)):
    g = h[none & h.year.between(lo, hi) & (h.n >= 20)]
    for k in (0, 1):
        q = g[g.half == k]
        bm = q.groupby("building").agg(
            z=("z", "mean"),
            res=("res", "mean"),
            share=("share", "first"),
            w=("z", "size"),
        )
        x = bm.share - np.average(bm.share, weights=bm.w)
        slope = (bm.w * x * bm.res).sum() / (bm.w * x * x).sum()
        e = bm.res - np.average(bm.res, weights=bm.w) - slope * x
        se = np.sqrt(((bm.w * x * e) ** 2).sum()) / (bm.w * x * x).sum()
        print(
            f"{lo}-{hi} half {'AB'[k]}: ads {len(q)}, buildings {len(bm)}, slope of log residual on share {slope:.4f} (se {se:.4f}), ads in buildings with share over 0.15: {(q.share > 0.15).sum()}"
        )
