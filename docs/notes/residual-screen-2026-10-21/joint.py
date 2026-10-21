import pandas as pd, numpy as np, sys

MODE = sys.argv[1]
PRES = {
    "source type",
    "license type",
    "broker (business name)",
    "source group",
    "premium page",
    "MLS number",
    "photos",
    "video",
    "3D tour",
    "description length",
    "fees listed",
    "no fee in text",
    "text: no fee",
    "floor plans",
    "records per ad",
    "from_text",
    "lease term",
    "months free stated",
}
j = pd.read_parquet("joined.parquet")
DROP = {
    "outdoor private (any)",
    "views (any)",
    "relabelled unit (relist/label/split differ)",
    "sqft per bedroom band",
    "square feet stated",
    "outdoor shared (any)",
    "floor x elevator",
    "floor_status",
    "posted speed, faced",
    "identity_reasons",
    "exclusion_reasons",
    "fate",
    "label_fate",
    "gross rent stated",
}
fields = [
    c
    for c in j.columns
    if c not in {"listing_id", "building", "zone", "T", "cell500", "taxblock"}
    and c not in DROP
    and (MODE == "all" or c not in PRES)
]
rng = np.random.default_rng(0)
j = j.iloc[np.sort(rng.choice(len(j), 600_000, replace=False))].reset_index(drop=True)
MIN = 200
TOPK = 40
cols = {}
for c in fields:
    lev = j[c].astype(str)
    vc = lev.value_counts()
    keep = vc[vc >= MIN].index[:TOPK]
    lev = lev.where(lev.isin(keep), "(other)")
    base = lev.value_counts().index[0]
    for l in lev.unique():
        if l != base:
            cols[f"{c} = {l}"] = (lev == l).to_numpy(np.float32)
X = pd.DataFrame(cols)
print("columns", X.shape, flush=True)


def fit(m, cell):
    y = j["T"][m].astype(np.float64)
    Xm = X[m]
    if cell is None:
        y = y - y.mean()
        Xm = Xm - Xm.mean()
    else:
        c = j[cell][m].fillna("?")
        y = y - y.groupby(c).transform("mean")
        Xm = Xm - Xm.groupby(c).transform("mean")
    A = Xm.to_numpy(np.float64)
    keep = A.std(0) > 0
    A = A[:, keep]
    b, *_ = np.linalg.lstsq(A, y.to_numpy(), rcond=None)
    e = 1 - ((y.to_numpy() - A @ b) ** 2).sum() / (y.to_numpy() ** 2).sum()
    k = A.shape[1]
    n = len(y)
    return e - k / (n - k - 1) * (1 - e), pd.Series(b, index=Xm.columns[keep])


out = {}
coefs = {}
for nm, m, cell in (
    ("all", j.zone >= 0, None),
    ("Manhattan", j.zone == 0, None),
    ("BK+Q", j.zone == 1, None),
    ("within 500 m", j.zone >= 0, "cell500"),
    ("within tax block", j.zone >= 0, "taxblock"),
):
    out[nm], coefs[nm] = fit(m.to_numpy(), cell)
    print(nm, round(100 * out[nm], 2), flush=True)
C = pd.DataFrame(coefs)
C["n"] = X.sum().reindex(C.index)
C["contrib"] = C["all"] ** 2 * C.n / len(j) * (1 - C.n / len(j))
C.sort_values("contrib", ascending=False).to_parquet(f"joint_coefs_{MODE}.parquet")
pd.Series(out).to_frame("r2").to_parquet(f"joint_r2_{MODE}.parquet")
print(C.sort_values("contrib", ascending=False).head(30).round(4).to_string())
