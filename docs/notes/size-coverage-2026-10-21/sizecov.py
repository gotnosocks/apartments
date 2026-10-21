import pandas as pd, numpy as np, re, json

P = "/data1/apartments/pipeline/datasets/rows-edc83b49f9bacd8c.parquet"
p = (
    pd.read_parquet(
        P,
        columns=[
            "listing_id",
            "building",
            "page",
            "bedrooms",
            "square_feet",
            "building_floor_count",
        ],
    )
    .drop_duplicates("listing_id")
    .reset_index(drop=True)
)
p["sq"] = p.square_feet.where((p.square_feet > 100) & (p.square_feet < 10000))
lab = p.page.astype(str).str.extract(r"/([^/?#]+)/?$")[0].str.upper().fillna("")
lab = lab.str.replace(r"^(APT|UNIT|NO)[-_.]?", "", regex=True).str.replace(
    r"[^0-9A-Z]", "", regex=True
)
p["label"] = lab
p["bkey"] = p.building.astype(str)
special = lab.str.contains(
    r"PH|PENT|GARDEN|GDN|PARLOR|BSMT|BASEMENT|CELLAR|LOWER"
) | lab.str.fullmatch(r"GF?|LL\d*")


def parse(s):
    m = re.fullmatch(r"(\d{1,2})([A-Z]{1,2})", s)
    if m:
        return int(m.group(1)), "L" + m.group(2)
    m = re.fullmatch(r"(\d{1,2})(\d{2})", s)
    if m:
        return int(m.group(1)), "D" + m.group(2)
    m = re.fullmatch(r"([A-Z]{1,2})(\d{1,2})", s)
    if m:
        return int(m.group(2)), "L" + m.group(1)
    return None, None


u = pd.Series(lab.unique())
pm = dict(zip(u, u.map(parse)))
p["floor"] = lab.map(lambda s: pm[s][0])
p["line"] = lab.map(lambda s: pm[s][1])
top = p.floor >= p.building_floor_count - 1
p["line_ok"] = p.line.notna() & ~special & ~top.fillna(False) & (lab != "")
p["ukey"] = np.where(lab != "", p.bkey + "|" + lab, None)
# unit medians over every listing date
um = p[p.sq.notna() & p.ukey.notna()].groupby("ukey").sq.median()
p["sq_unit"] = p.ukey.map(um)
# line: median over other units of same building, line and beds
p["lkey"] = np.where(
    p.line_ok, p.bkey + "|" + p.line.astype(str) + "|" + p.bedrooms.astype(str), None
)
uu = (
    p[p.lkey.notna() & p.sq.notna()].groupby(["lkey", "ukey"]).sq.median().reset_index()
)


def loo_med(df, gcol, vcol, idcol):
    """median of vcol over other ids in each group, per id"""
    out = {}
    for g, d in df.groupby(gcol, sort=False):
        ids = d[idcol].to_numpy()
        v = d[vcol].to_numpy()
        if len(v) == 1:
            continue
        for i in range(len(v)):
            out[(g, ids[i])] = np.median(np.delete(v, i))
    return out


lm = uu.groupby("lkey").sq.median()
p["sq_line_any"] = p.lkey.map(lm)
L = loo_med(uu, "lkey", "sq", "ukey")
# for a unit that itself has a size, the line value excluding it; for a unit without, the line median
p["sq_line"] = [
    L.get((l, k), np.nan)
    if (l is not None and k in um.index)
    else (lm.get(l, np.nan) if l is not None else np.nan)
    for l, k in zip(p.lkey, p.ukey)
]
# training rows
r = pd.read_parquet("resid.parquet", columns=["listing_id", "r", "bld", "F", "zone"])
r["T"] = r.r + r.bld + r.F
r["T"] -= r.groupby("zone")["T"].transform("mean")
f = r.merge(p, on="listing_id", how="left")
f["beds"] = f.bedrooms.clip(upper=4).astype("Int64").astype(str).replace({"4": "4+"})
a = f.sq.notna()
b = a | f.sq_unit.notna()
c = b | f.sq_line.notna()
f["layer"] = np.select([a, b, c], ["a stated", "b same unit", "c same line"], "none")
res = {}


def cov(df, w):
    g = lambda m: float(np.average(m, weights=w))
    return {
        "a": g(df.layer == "a stated"),
        "b": g(df.layer.isin(["a stated", "b same unit"])),
        "c": g(df.layer != "none"),
        "n": int(len(df)),
    }


U = f.drop_duplicates("ukey").copy()
U = U[U.ukey.notna()]
for nm, df in [("ads", f), ("units", U)]:
    t = {"all": cov(df, np.ones(len(df)))}
    for z, zn in [(0, "Manhattan"), (1, "Brooklyn + Queens")]:
        d = df[df.zone == z]
        t[zn] = cov(d, np.ones(len(d)))
    for bd in ["0", "1", "2", "3", "4+"]:
        d = df[df.beds == bd]
        t[bd + " bed"] = cov(d, np.ones(len(d)))
    res[nm] = t
# holdout among ads that state a size
h = f[a].copy()
# (b): other listings of the same unit, excluding this one
s = p[p.sq.notna() & p.ukey.notna()][["ukey", "listing_id", "sq"]]
B = loo_med(s, "ukey", "sq", "listing_id")
h["imp_b"] = [B.get((k, l), np.nan) for k, l in zip(h.ukey, h.listing_id)]
h["imp_c"] = h.sq_line
h["imp"] = h.imp_b.fillna(h.imp_c)


def err(x, y):
    e = np.abs(np.log(x / y))
    e = e[np.isfinite(e)]
    return {
        "n": int(len(e)),
        "median": float(np.median(e)),
        "p90": float(np.quantile(e, 0.9)),
        "within10": float((e < np.log(1.1)).mean()),
    }


res["holdout"] = {
    "b": err(h.imp_b, h.sq),
    "c only (no other listing)": err(h.imp_c[h.imp_b.isna()], h.sq[h.imp_b.isna()]),
    "c all": err(h.imp_c, h.sq),
    "b then c": err(h.imp, h.sq),
}
# skew: stated vs not
sk = {}
for nm, m in [
    ("state a size", a),
    ("no size", ~a),
    ("no size, filled by b or c", (~a) & (f.layer != "none")),
    ("still missing", f.layer == "none"),
]:
    d = f[m.to_numpy()]
    sk[nm] = {
        "n": int(len(d)),
        "T mean": float(d["T"].mean()),
        "T median": float(d["T"].median()),
        "Manhattan share": float((d.zone == 0).mean()),
        "beds": d.beds.value_counts(normalize=True)
        .reindex(["0", "1", "2", "3", "4+"])
        .fillna(0)
        .round(4)
        .to_dict(),
    }
res["skew"] = sk
# within-building skew: T of stated minus not-stated in the same building
f["bT"] = f["T"] - f.groupby("building")["T"].transform("mean")
res["within building gap"] = float(f.bT[a].mean() - f.bT[~a].mean())
res["line exclusions"] = {
    "special labels": int(special.sum()),
    "top two floors": int(top.fillna(False).sum()),
    "no parsable line": int(p.line.isna().sum()),
    "rows": int(len(p)),
}
json.dump(res, open("sizecov.json", "w"), indent=1)
print(json.dumps(res, indent=1))
