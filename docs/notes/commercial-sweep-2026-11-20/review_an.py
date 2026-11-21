import numpy as np, pandas as pd

OUT = "/data1/apartments/tmp/commercial-sweep/"
TL = "/data1/apartments/tmp/po-thinlevel/"
M = pd.read_parquet(
    OUT + "marks.parquet",
    columns=[
        "listing_id",
        "building",
        "bed",
        "ask",
        "nb",
        "year",
        "nb_median",
        "nb_n",
        "ratio",
        "in_live",
        "l2bt_held",
        "live_held",
        "m_ratio",
        "m_text",
        "half",
        "status",
        "unit_id",
    ],
)
M["listing_id"] = M.listing_id.astype(str)
# leak-free median: drop l2bt held-out and live held rows from the median
L = M[
    M.in_live
    & ~M.l2bt_held.fillna(False).astype(bool)
    & ~M.live_held.fillna(False).astype(bool)
]
med2 = L.groupby(["nb", "year", "bed"]).ask.median().rename("med2").reset_index()
M = M.merge(med2, on=["nb", "year", "bed"], how="left")
M["m_ratio2"] = M.bed.isin([0, 1]) & (M.ask / M.med2 > 3)
H = pd.read_parquet(TL + "l2_ads.parquet")
H["listing_id"] = H.listing_id.astype(str)
S = pd.read_parquet(TL + "l2_rows_slim.parquet")
S["listing_id"] = S.listing_id.astype(str)
Tr = S[~S.heldout].merge(M, on=["listing_id"], how="left", suffixes=("", "_m"))
for c in ["m_ratio", "m_text", "m_ratio2"]:
    Tr[c] = Tr[c].fillna(False).astype(bool)
Hm = H.merge(
    M[["listing_id", "m_ratio", "m_text", "m_ratio2", "half", "bed"]].rename(
        columns={"half": "h2"}
    ),
    on="listing_id",
    how="left",
)
for c in ["m_ratio", "m_text", "m_ratio2"]:
    Hm[c] = Hm[c].fillna(False).astype(bool)
Hm["low"] = (Hm.cdf < 0.05).astype(float)
Hm["high"] = (Hm.cdf > 0.95).astype(float)
Hm["pp"] = Hm.pred.rank(pct=True)
Hm["band"] = pd.cut(
    Hm.n_bld, [-1, 4, 19, 99, 1e9], labels=["0-4", "5-19", "20-99", "100+"]
)
Hm["dec"] = np.minimum((Hm.pp * 20).astype(int), 19)
Hm["cell"] = Hm.dec.astype(str) + "_" + Hm.band.astype(str)
base = Hm.groupby("cell")[["low", "high"]].mean()
print(
    "changed ratio training rows: orig",
    int(Tr.m_ratio.sum()),
    "leakfree",
    int(Tr.m_ratio2.sum()),
    "both",
    int((Tr.m_ratio & Tr.m_ratio2).sum()),
)


def clse(x, col):
    g = x.groupby("building")[col].agg(["sum", "size"])
    p = g["sum"].sum() / g["size"].sum()
    k = len(g)
    r = g["sum"] - p * g["size"]
    se = np.sqrt(k / (k - 1) * (r**2).sum()) / g["size"].sum()
    return p, se


def rep(name, bset, own):
    sel = Hm.building.isin(bset) & ~Hm[own]
    x = Hm[sel]
    exp = base.loc[x.cell].mean()
    p, se = clse(x, "low")
    ph, seh = clse(x, "high")
    print(
        f"\n{name}: bld {len(bset)} ads {len(x)} blds-with-heldout {x.building.nunique()} low {p:.3f} (cl SE {se:.3f}) exp-matched {exp.low:.3f} | high {ph:.3f} (SE {seh:.3f}) exp {exp.high:.3f}"
    )
    for h in "AB":
        y = x[x.h2 == h]
        p, se = clse(y, "low")
        e = base.loc[y.cell].low.mean()
        print(
            f"  half {h}: n {len(y)} blds {y.building.nunique()} low {p:.3f} SE {se:.3f} matched exp {e:.3f}"
        )
    print(
        "  top3% pred share",
        round((x.pp >= 0.97).mean(), 3),
        "all 0.03; top10%",
        round((x.pp >= 0.9).mean(), 3),
        "median pp",
        round(x.pp.median(), 3),
    )
    for lab, y in [
        ("pp>=.97", x[x.pp >= 0.97]),
        ("pp<.97", x[x.pp < 0.97]),
        ("bed01", x[x.bed.isin([0, 1])]),
        ("bed2+", x[~x.bed.isin([0, 1])]),
    ]:
        if len(y):
            print(
                f"  {lab}: n {len(y)} low {y.low.mean():.3f} exp {base.loc[y.cell].low.mean():.3f} high {y.high.mean():.3f}"
            )
    # concentration: top buildings by low count
    g = (
        x.groupby("building")
        .low.agg(["sum", "size"])
        .sort_values("sum", ascending=False)
    )
    print(
        "  low misses",
        int(g["sum"].sum()),
        "in",
        int((g["sum"] > 0).sum()),
        "buildings; top5",
        g.head(5).to_dict("index"),
    )
    print(
        "  median level", round(x.level.median(), 3), "all", round(Hm.level.median(), 3)
    )
    return x


b_rt = set(Tr.building[Tr.m_ratio & Tr.m_text])
b_r = set(Tr.building[Tr.m_ratio])
b_rt2 = set(Tr.building[Tr.m_ratio2 & Tr.m_text])
x = rep("ratio+text", b_rt, "m_ratio")
# note excludes only ratio_text-marked ads; reproduce note's set too
sel = Hm.building.isin(b_rt) & ~(Hm.m_ratio & Hm.m_text)
print("note set n", int(sel.sum()), "low", round(Hm.low[sel].mean(), 3))
rep("ratio+text leakfree median", b_rt2, "m_ratio2")
rep("ratio", b_r, "m_ratio")
# own marked held-out ratio+text / ratio ads: are low misses in marked rows?
for m in ["m_ratio"]:
    y = Hm[Hm[m] & Hm.building.isin(b_rt)]
    print(
        "\nmarked held-out ratio ads in those blds",
        len(y),
        "low",
        y.low.sum(),
        "high",
        y.high.sum(),
    )
# matched comparison: buildings with ratio row but no text word
b_ro = b_r - b_rt
rep("ratio only (no text) blds", b_ro, "m_ratio")
print("\n--- extra")
sel = Hm.building.isin(b_rt) & ~Hm.m_ratio
x = Hm[sel]
y = x[x.building != "the-archive"]
p, se = clse(y, "low")
print(
    "no archive n",
    len(y),
    "blds",
    y.building.nunique(),
    "low",
    round(p, 3),
    "SE",
    round(se, 3),
    "exp",
    round(base.loc[y.cell].low.mean(), 3),
    "high",
    round(y.high.mean(), 3),
    "exp",
    round(base.loc[y.cell].high.mean(), 3),
)
for h in "AB":
    z = y[y.h2 == h]
    print(
        "  half",
        h,
        len(z),
        round(z.low.mean(), 3),
        round(base.loc[z.cell].low.mean(), 3),
    )
print(
    "archive half",
    x[x.building == "the-archive"].h2.unique(),
    "archive train rows",
    int((Tr.building == "the-archive").sum()),
    "ratio rows",
    int((Tr.m_ratio & (Tr.building == "the-archive")).sum()),
)
for k in ["0-4", "5-19", "20-99", "100+"]:
    z = x[x.band == k]
    if len(z):
        print(
            " band",
            k,
            len(z),
            "low",
            round(z.low.mean(), 3),
            "exp",
            round(base.loc[z.cell].low.mean(), 3),
            "high",
            round(z.high.mean(), 3),
        )
