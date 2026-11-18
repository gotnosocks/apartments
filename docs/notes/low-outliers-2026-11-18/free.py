"""Free check of the layout columns, coded by the module, on b9's held-out ads."""

import sys, json
import numpy as np, pandas as pd
from scipy.stats import norm, t as T
from rentfrontier import drift_building_bedtext_layout as M

OUT = "/data1/apartments/tmp/low-outliers-2026-11-18/"
RUN = "/data1/apartments/frontier/runs/drift-building-b0-latest-67d14e17-b9"
ROWS = "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc/rows.parquet"
d = np.load(RUN + "/pred_scores.npz", allow_pickle=True)
frame = pd.read_parquet(
    ROWS,
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
x = M.changes(frame, ~held)
print(
    "all rows marked",
    dict(zip(M.COLUMNS, x.sum(0).astype(int))),
    "train",
    (~held).sum(),
    "held",
    held.sum(),
)
h = frame[held].reset_index(drop=True)
assert (h.listing_id.to_numpy() == d["listing"]).all()
xh = x[held]
qs = list(d["quantiles"])
h["scale"] = (d["q"][:, qs.index(0.75)] - d["q"][:, qs.index(0.25)]) / (
    2 * norm.ppf(0.75)
)
h["gap"] = d["y"] - d["pred"]
h["cdf"] = d["cdf"]
h["z"] = h.gap / h.scale
half = pd.read_parquet(OUT + "held_b9.parquet", columns=["listing_id", "half"])
half["listing_id"] = half.listing_id.astype(h.listing_id.dtype)
h = h.merge(half, on="listing_id", how="left", validate="1:1")
keep = ~h.income_restricted.fillna(False).to_numpy(bool)
rng = np.random.default_rng(20261118)
FOLDS = 5


def cv_r2(z, X, fold):
    pred = np.empty_like(z)
    for k in range(FOLDS):
        tr = fold != k
        A = np.c_[np.ones(tr.sum()), X[tr]]
        b = np.linalg.lstsq(A, z[tr], rcond=None)[0]
        pred[~tr] = np.c_[np.ones((~tr).sum()), X[~tr]] @ b
    return 1 - ((z - pred) ** 2).sum() / ((z - z.mean()) ** 2).sum()


res = {}
for name in ["read", "unread"]:
    m = keep & (h.half == name).to_numpy()
    u, X = h[m].reset_index(drop=True), xh[m]
    blds = u.building.unique()
    fold = u.building.map(
        dict(zip(blds, rng.permutation(np.arange(len(blds)) % FOLDS)))
    ).to_numpy()
    z = np.clip(u.z.to_numpy(), -6, 6)
    S = {
        "below": u.cdf < 0.01,
        "ctl": (u.cdf > 0.25) & (u.cdf < 0.75),
        "above": u.cdf > 0.99,
    }
    print(name, len(u), {k: int(v.sum()) for k, v in S.items()})
    r = {}
    for j, c in enumerate(M.COLUMNS):
        f = X[:, j] > 0
        e = cv_r2(z, X[:, [j]], fold)
        null = [cv_r2(z, rng.permutation(X[:, [j]]), fold) for _ in range(200)]
        r[c] = dict(
            n=int(f.sum()),
            below=float(f[S["below"]].mean()),
            ctl=float(f[S["ctl"]].mean()),
            above=float(f[S["above"]].mean()),
            gap=float(u.gap[f].mean()),
            gap_other=float(u.gap[~f].mean()),
            explained=float(e),
            null_95=float(np.quantile(null, 0.95)),
        )
        print(
            f"  {c:20s} n {f.sum():5d} below {r[c]['below']:.3f} ctl {r[c]['ctl']:.3f} above {r[c]['above']:.3f} gap {r[c]['gap']:+.4f} other {r[c]['gap_other']:+.4f} expl {e:.5f} null95 {r[c]['null_95']:.5f} {'pass' if e > max(0, r[c]['null_95']) else 'fail'}"
        )
    e = cv_r2(z, X, fold)
    null = [cv_r2(z, X[rng.permutation(len(X))], fold) for _ in range(200)]
    print(f"  all four: explained {e:.5f} null95 {np.quantile(null, 0.95):.5f}")
    r["all"] = dict(explained=float(e), null_95=float(np.quantile(null, 0.95)))
    res[name] = r
# shifts fitted on one half, scored on the other with a Student-t (4 df) of the ad's own scale
for a, b in (("read", "unread"), ("unread", "read")):
    ma, mb = keep & (h.half == a).to_numpy(), keep & (h.half == b).to_numpy()
    beta = np.linalg.lstsq(
        np.c_[np.ones(ma.sum()), xh[ma]], h.gap[ma].to_numpy(), rcond=None
    )[0]
    te = h[mb]
    shift = xh[mb] @ beta[1:]
    dl = pd.Series(
        T.logpdf((te.gap - shift) / te.scale, 4) - T.logpdf(te.gap / te.scale, 4)
    )
    bl = dl.groupby(te.building.to_numpy()).sum()
    print(
        a,
        "->",
        b,
        "coef",
        np.round(beta[1:], 4),
        "delta elpd",
        round(dl.sum(), 1),
        "se",
        round(bl.std() * np.sqrt(len(bl)), 1),
        "marked",
        int((xh[mb].sum(1) > 0).sum()),
        "of",
        int(mb.sum()),
    )
    res[f"{a}_to_{b}"] = dict(
        coef=beta[1:].tolist(),
        delta_elpd=float(dl.sum()),
        se=float(bl.std() * np.sqrt(len(bl))),
    )
json.dump(res, open(OUT + "free.json", "w"), indent=1)
