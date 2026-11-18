"""Free check: each unit and ad column of the served design, gained or lost against the
apartment's previous training ad. Rows with a layout mark or the income flag are left out."""

import json, numpy as np, pandas as pd
from scipy.stats import norm
from rentfrontier import drift_building_bedtext_layout as M

OUT = "/data1/apartments/tmp/low-outliers-2026-11-18/"
d = np.load(
    "/data1/apartments/frontier/runs/drift-building-b0-latest-67d14e17-b9/pred_scores.npz",
    allow_pickle=True,
)
fr = pd.read_parquet(
    "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-bedtext/rows.parquet",
    columns=[
        "listing_id",
        "building",
        "unit_id",
        "price_at",
        "bedrooms",
        "full_baths",
        "half_baths",
        "income_restricted",
    ],
)
held = d["heldout"]
assert (fr.listing_id[held].to_numpy() == d["listing"]).all()
X = np.load(OUT + "design_b9_x.npy", mmap_mode="r")
names = json.load(open(OUT + "design_b9_names.json"))
lay = (M.changes(fr, ~held).sum(1) > 0)[held]
prev = M.previous(
    fr.assign(bedrooms=np.arange(len(fr), dtype=float)), ~held
).prev_beds.to_numpy()[held]
has = ~np.isnan(prev)
pi = np.where(has, prev, 0).astype(int)
Xh = np.asarray(X[np.flatnonzero(held)])
Xp = np.asarray(X[pi])
cols = {}
floor = [
    i
    for i, n in enumerate(names)
    if n.startswith(("unit:elev_f", "unit:walkup_f")) and n[-1].isdigit()
]
for label, v, p, tol in [("floor", Xh[:, floor].sum(1), Xp[:, floor].sum(1), 0.5)] + [
    (
        n,
        Xh[:, i],
        Xp[:, i],
        0.15 if n in ("unit:log_size_rel", "ad:log1p_photos") else 0.25,
    )
    for i, n in enumerate(names)
    if i not in floor
]:
    cols[label + " up"] = has & (v > p + tol)
    cols[label + " down"] = has & (v < p - tol)
qs = list(d["quantiles"])
h = fr[held].reset_index(drop=True)
h["gap"] = d["y"] - d["pred"]
h["cdf"] = d["cdf"]
h["z"] = np.clip(
    h.gap
    / ((d["q"][:, qs.index(0.75)] - d["q"][:, qs.index(0.25)]) / (2 * norm.ppf(0.75))),
    -6,
    6,
)
half = pd.read_parquet(OUT + "held_b9.parquet", columns=["listing_id", "half"])
half["listing_id"] = half.listing_id.astype(h.listing_id.dtype)
h = h.merge(half, on="listing_id", how="left", validate="1:1")
keep = ~h.income_restricted.fillna(False).to_numpy(bool) & ~lay
rng = np.random.default_rng(20261118)


def cv(z, x, fold):
    pred = np.empty_like(z)
    for k in range(5):
        tr = fold != k
        m1, m0 = (
            z[tr][x[tr] > 0].mean() if (x[tr] > 0).any() else z[tr].mean(),
            z[tr][x[tr] == 0].mean(),
        )
        pred[~tr] = np.where(x[~tr] > 0, m1, m0)
    return 1 - ((z - pred) ** 2).sum() / ((z - z.mean()) ** 2).sum()


res = {}
for name in ("read", "unread"):
    m = keep & (h.half == name).to_numpy()
    u = h[m].reset_index(drop=True)
    b = u.building.unique()
    fold = u.building.map(
        dict(zip(b, rng.permutation(np.arange(len(b)) % 5)))
    ).to_numpy()
    z = u.z.to_numpy()
    lo = (u.cdf < 0.01).to_numpy()
    print(name, len(u), "with a previous ad", int(has[m].sum()))
    for k, v in cols.items():
        f = v[m]
        if f.sum() < 150:
            continue
        x = f.astype(float)
        e = cv(z, x, fold)
        n95 = np.quantile([cv(z, rng.permutation(x), fold) for _ in range(40)], 0.95)
        res[(k, name)] = (int(f.sum()), 100 * f[lo].mean(), u.gap[f].mean(), e, n95)
T = pd.DataFrame(res, index=["n", "below%", "gap", "expl", "null95"]).T.unstack()
T.columns = [f"{a}_{b}" for a, b in T.columns]
T["both"] = (T.expl_read > T.null95_read.clip(lower=0)) & (
    T.expl_unread > T.null95_unread.clip(lower=0)
)
T = T.sort_values("expl_unread", ascending=False)
pd.set_option(
    "display.width",
    250,
    "display.max_rows",
    300,
    "display.float_format",
    lambda v: f"{v:.4f}",
)
print(
    T[
        [
            "n_unread",
            "below%_unread",
            "gap_read",
            "gap_unread",
            "expl_read",
            "expl_unread",
            "null95_unread",
            "both",
        ]
    ].to_string()
)
T.to_csv(OUT + "featchg.csv")
