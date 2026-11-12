"""Screen for a line level under L1: shift each held-out ad by a shrunk mean of the
held-out residuals of other units in its group, and re-score L1's predictive."""

import json, sys
import numpy as np, pandas as pd

sys.path.insert(0, "/data1/apartments/serve/master/frontier/src")
from rentfrontier import drift_score as ds

R = "/data1/apartments/frontier/runs/drift-building-phase-b0-latest-9a7830fb-l1/"
D = "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise/rows.parquet"
a = np.load(R + "pred_scores.npz", allow_pickle=True)
held = a["heldout"]
d = pd.read_parquet(
    D,
    columns=[
        "listing_id",
        "building",
        "unit_id",
        "bedrooms",
        "full_baths",
        "latest_ask",
        "latest_day",
    ],
)
assert (d.listing_id.astype(str).values[held] == a["listing"]).all()
h = d[held].reset_index(drop=True)
h["y"], h["pred"], h["elpd0"] = a["y"], a["pred"], a["elpd"]
qs = list(a["quantiles"])
h["lo"], h["hi"] = a["q"][:, qs.index(0.1)], a["q"][:, qs.index(0.9)]
h["r"] = h.y - h.pred
h["fb"] = h.full_baths.fillna(-1)
dd = pd.to_datetime(h.latest_day)
h["mon"] = dd.dt.year * 12 + dd.dt.month


# other units' residual mean in the group: (group sum - unit sum) / (group n - unit n)
def loo(keys):
    # earlier only: other units' residuals in the group with latest_day strictly before this ad's
    day = pd.to_datetime(h.latest_day).values.astype("datetime64[D]").astype(int)

    def prior(ks):
        f = h[ks].copy()
        f["day"] = day
        f["r"] = h.r.values
        f["one"] = 1.0
        f = f.reset_index().sort_values(ks + ["day"])
        g = f.groupby(ks, sort=False)
        cn = g.one.cumsum()
        same = f.groupby(ks + ["day"], sort=False)
        # cumsum through the last row of the day, minus the day's total, is the sum before the day
        last_s = (
            f.assign(c=g.r.cumsum())
            .groupby(ks + ["day"], sort=False)
            .c.transform("last")
        )
        last_n = f.assign(c=cn).groupby(ks + ["day"], sort=False).c.transform("last")
        ps = last_s - same.r.transform("sum")
        pn = last_n - same.one.transform("sum")
        out_s, out_n = np.empty(len(h)), np.empty(len(h))
        out_s[f["index"].values], out_n[f["index"].values] = ps.values, pn.values
        return out_s, out_n

    gs, gn = prior(keys)
    us, un = prior(keys + ["unit_id"])
    return gs - us, gn - un


groups = {
    "building": ["building"],
    "bld_bed": ["building", "bedrooms"],
    "line": ["building", "bedrooms", "fb"],
}
# folds by building hash for choosing the shrinkage k on one half, scoring the other
fold = (pd.util.hash_array(h.building.astype(str).to_numpy()) % 2).astype(int)
z = np.load(R + "posterior.npz")
flat = lambda k: z["kept/" + k].reshape(-1, *z["kept/" + k].shape[2:])
loc, usd, sig, nu, fac = (
    flat("pred_loc"),
    flat("pred_unit_sd"),
    flat("sigma"),
    flat("nu"),
    flat("phase_scale"),
)
grp, ph, y = z["kept/pred_group"], z["kept/pred_phase"], z["kept/pred_y"]
assert np.allclose(y, h.y)
lam, logw = ds.mixture(nu)


def elpd_shift(delta, idx):
    out = np.empty(len(idx))
    for a0 in range(0, len(idx), 500):
        sl = idx[a0 : a0 + 500]
        s = sig[:, grp[sl]] * fac[:, ph[sl]]
        pd_, _ = ds._density(
            y[sl],
            loc[:, sl].astype(float) + delta[sl][None, :],
            usd[:, sl].astype(float),
            s,
            lam,
            logw,
        )
        out[a0 : a0 + 500] = np.logaddexp.reduce(pd_, axis=0) - np.log(loc.shape[0])
    return out


def cluster_se(x, b):
    t = pd.Series(x).groupby(b.values).sum()
    return float(np.sqrt(len(t) * t.var(ddof=1)))


res = {}
sub = (
    np.load("/data1/apartments/tmp/sprint-20261112/line-check/pricier.npy")
    if len(sys.argv) > 1
    else None
)
for name, keys in groups.items():
    s, n = loo(keys)
    mean = np.where(n > 0, s / np.maximum(n, 1), 0.0)
    best = {}
    for f in (0, 1):
        tr = np.flatnonzero((fold != f) & (n > 0))
        tr = tr[np.random.default_rng(0).permutation(len(tr))[:30000]]
        sc = {}
        for k in (1, 3, 10, 30, 100):
            dl = np.where(n > 0, n / (n + k) * mean, 0.0)
            sc[k] = float((elpd_shift(dl, tr) - h.elpd0.values[tr]).sum())
        best[f] = max(sc, key=sc.get)
    dl = np.zeros(len(h))
    for f in (0, 1):
        m = fold == f
        k = best[f]
        dl[m] = np.where(n[m] > 0, n[m] / (n[m] + k) * mean[m], 0.0)
    idx = np.flatnonzero(n > 0)
    e = np.zeros(len(h))
    e[idx] = elpd_shift(dl, idx) - h.elpd0.values[idx]
    y_, p1 = h.y.values, h.pred.values + dl
    cov = (y_ >= h.lo + dl) & (y_ <= h.hi + dl)
    r = dict(
        k=best,
        n_with=int((n > 0).sum()),
        gain=float(e.sum()),
        se=cluster_se(e, h.building),
        mae0=float(np.median(np.abs(h.r))),
        mae1=float(np.median(np.abs(y_ - p1))),
        cov0=float(((y_ >= h.lo) & (y_ <= h.hi)).mean()),
        cov1=float(cov.mean()),
    )
    h["e_" + name], h["d_" + name], h["c_" + name] = e, dl, cov
    res[name] = r
    print(name, json.dumps(r), flush=True)
h.drop(columns=["latest_day"]).to_parquet(
    "/data1/apartments/tmp/sprint-20261112/line-check/h_time.parquet"
)
json.dump(
    res,
    open("/data1/apartments/tmp/sprint-20261112/line-check/res_time.json", "w"),
    indent=1,
)
