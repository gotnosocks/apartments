import pandas as pd, numpy as np, sys, glob

r = pd.read_parquet(
    "resid.parquet", columns=["listing_id", "building", "r", "bld", "F", "zone"]
)
r["T"] = r.r + r.bld + r.F
r["T"] -= r.groupby("zone")["T"].transform("mean")
geo = pd.read_parquet(
    "bld_fields.parquet", columns=["listing_id", "cell500", "taxblock"]
)
r = r.merge(geo, on="listing_id", how="left")
fields = []
for src in sys.argv[1:]:
    f = pd.read_parquet(src)
    f["listing_id"] = f.listing_id.astype(r.listing_id.dtype)
    f = (
        f.drop(columns=[c for c in ("cell500", "taxblock") if c in f.columns])
        .drop_duplicates("listing_id")
        .set_index("listing_id")
        .reindex(r.listing_id)
    )
    for c in f.columns:
        r[c] = pd.Categorical(f[c].astype(str).to_numpy())
        fields.append(c)
    del f
MIN = 200
TOPK = 40


def levels(c):
    lev = r[c].astype(str)
    vc = lev.value_counts()
    keep = vc[vc >= MIN].index[:TOPK]
    return lev.where(lev.isin(keep), "(other)")


def r2_within(y, lev, cell, mask):
    """share of y's variance (within cell if cell given) explained by lev's dummies"""
    y = y[mask]
    lev = lev[mask]
    D = pd.get_dummies(lev, drop_first=True, dtype=float)
    if D.shape[1] == 0:
        return 0.0
    if cell is not None:
        c = cell[mask]
        y = y - y.groupby(c).transform("mean")
        D = D - D.groupby(c).transform("mean")
    else:
        y = y - y.mean()
        D = D - D.mean()
    Y = y.to_numpy()
    X = D.to_numpy()
    b, *_ = np.linalg.lstsq(X, Y, rcond=None)
    res = Y - X @ b
    k = X.shape[1]
    n = len(Y)
    e = 1 - res @ res / (Y @ Y)
    return e - (k) / (n - k - 1) * (1 - e)


rows = []
L = {}
bmean = r.groupby("building").agg(
    T=("T", "mean"),
    n=("T", "size"),
    zone=("zone", "first"),
    cell=("cell500", "first"),
    tb=("taxblock", "first"),
)
for c in fields:
    lev = levels(c)
    res = {"field": c, "levels": lev.nunique()}
    for zn, m in (
        ("all", r.zone >= 0),
        ("Manhattan", r.zone == 0),
        ("BK+Q", r.zone == 1),
    ):
        res[f"ad {zn}"] = r2_within(r["T"], lev, None, m)
    res["ad within 500 m"] = r2_within(r["T"], lev, r.cell500, r.zone >= 0)
    res["ad within tax block"] = r2_within(r["T"], lev, r.taxblock, r.zone >= 0)
    g = (
        pd.DataFrame({"l": lev, "T": r["T"], "z": r.zone})
        .groupby(["l"])
        .agg(n=("T", "size"), mean=("T", "mean"))
    )
    gz = (
        pd.DataFrame({"l": lev, "T": r["T"], "z": r.zone})
        .groupby(["z", "l"])
        .agg(n=("T", "size"), mean=("T", "mean"))
    )
    L[c] = (g, gz)
    cnt = (
        pd.DataFrame({"b": r.building, "l": lev})
        .value_counts()
        .reset_index()
        .drop_duplicates("b")
    )
    bl = cnt.set_index("b").l.reindex(bmean.index)
    # building view: weighted by ads, on building-mean target
    w = bmean.n.to_numpy(float)
    for zn, m in (
        ("all", bmean.zone >= 0),
        ("Manhattan", bmean.zone == 0),
        ("BK+Q", bmean.zone == 1),
    ):
        yy = bmean["T"][m]
        ww = w[m.to_numpy()]
        D = pd.get_dummies(bl[m], drop_first=True, dtype=float)
        mu = np.average(yy, weights=ww)
        Y = (yy - mu).to_numpy() * np.sqrt(ww)
        X = (
            (D - np.average(D, axis=0, weights=ww)).to_numpy() * np.sqrt(ww)[:, None]
            if D.shape[1]
            else np.zeros((len(yy), 0))
        )
        if X.shape[1] == 0:
            res[f"bld {zn}"] = 0.0
            continue
        b, *_ = np.linalg.lstsq(X, Y, rcond=None)
        e = 1 - ((Y - X @ b) ** 2).sum() / (Y @ Y)
        k = X.shape[1]
        n = len(Y)
        res[f"bld {zn}"] = e - k / (n - k - 1) * (1 - e)
    rows.append(res)
    import time

    print(
        time.strftime("%X"),
        c,
        {
            k: (round(100 * v, 2) if isinstance(v, float) else v)
            for k, v in res.items()
            if k != "field"
        },
        flush=True,
    )
o = pd.DataFrame(rows)
o.to_parquet("screen2.parquet")
pd.to_pickle(L, "levels2.pkl")
print("target var", r["T"].var(), "by zone", r.groupby("zone")["T"].var().to_dict())
r[["listing_id", "building", "zone", "T", "cell500", "taxblock"] + fields].to_parquet(
    "joined.parquet"
)
