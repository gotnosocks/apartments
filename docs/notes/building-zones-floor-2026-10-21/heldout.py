"""Held-out elpd, RMSE and coverage on the latest split, floor run against age run at the same
draw count, overall and by floor band and flag."""

import json, numpy as np, pandas as pd
from scipy.special import gammaln, logsumexp
from rentfrontier import (
    b0,
    splits,
    building_zones as bz,
    building_zones_age,
    building_zones_floor,
)
from common import RUNS, DATASET, FLOOR, AGE, bands

frame = b0.load_frame(DATASET)
held = splits.SPLITS["latest"](frame)
DRAWS = 100  # per chain, spread evenly, the same for both runs
out = {}
for tag, run, mod in (
    ("age", AGE, building_zones_age),
    ("floor", FLOOR, building_zones_floor),
):
    z = np.load(RUNS + run + "/posterior.npz")
    assert (z["heldout"] == held).all()
    full = mod.design(frame)
    assert list(full.names) == [str(n) for n in z["names"]], tag
    t = mod.subset(full, ~held)
    h = mod.subset(full, held)
    idx = np.linspace(0, z["kept/sigma"].shape[1] - 1, DRAWS).round().astype(int)
    k = lambda s: (
        z["kept/" + s][:, idx].reshape(-1, *z["kept/" + s].shape[2:]).astype(float)
    )
    beta, L, w, bld, sig, nu = (
        k("beta"),
        k("L"),
        k("gp_w"),
        k("bld"),
        k("sigma"),
        k("nu"),
    )
    B, _ = bz.wave_matrix(t)
    Bw = B[h.site] @ w.T
    del t, full
    rows = []
    rng = np.random.default_rng(0)
    for a0 in range(0, len(h.y), 20000):
        sl = slice(a0, a0 + 20000)
        site, week, frac = h.site[sl], h.week[sl], h.frac[sl]
        mu = h.x[sl] @ beta.T
        mu += (1 - frac)[:, None] * L[:, week].T + frac[:, None] * L[:, week + 1].T
        mu += Bw[sl] + bld[:, site].T
        s = sig[:, h.group[sl]].T
        r = (h.y[sl, None] - mu) / s
        lp = (
            gammaln((nu + 1) / 2)
            - gammaln(nu / 2)
            - 0.5 * np.log(nu * np.pi)
            - np.log(s)
            - (nu + 1) / 2 * np.log1p(r * r / nu)
        )
        elpd = logsumexp(lp, axis=1) - np.log(lp.shape[1])
        yrep = mu + s * rng.standard_t(nu, size=mu.shape)
        lo, hi = np.quantile(yrep, [0.05, 0.95], axis=1)
        med = np.median(mu, 1)
        rows.append(
            pd.DataFrame(
                {
                    "elpd": elpd,
                    "err": h.y[sl] - med,
                    "pred": med,
                    "in90": (h.y[sl] >= lo) & (h.y[sl] <= hi),
                }
            )
        )
    out[tag] = pd.concat(rows, ignore_index=True)
    if tag == "floor":
        info = bands(
            frame[held].reset_index(drop=True), h.x[:, h.names.index("bld:elevator")]
        )
    print(tag, len(h.y), beta.shape[0], flush=True)
    del h, B, Bw, beta, bld
f, a = out["floor"], out["age"]
res = {"draws_each": DRAWS * 4}


def summ(m, label):
    d = f.elpd[m] - a.elpd[m]
    res[label] = {
        "rows": int(m.sum()),
        "elpd_diff": float(d.sum()),
        "se": float(d.std() * np.sqrt(m.sum())),
        "elpd_diff_per_ad": float(d.mean()),
    }
    for tag, x in out.items():
        res[label][tag] = {
            "rmse": float(np.sqrt((x.err[m] ** 2).mean())),
            "cover90": float(x.in90[m].mean()),
            "bias_median": float(x.err[m].median()),
        }


summ(np.ones(len(f), bool), "all")
summ(info.band.to_numpy() != "unknown", "floor known")
for g in ("elev", "walkup"):
    for b in ("1", "2", "3-5", "6-9", "10-19", "20-39", "40+", "unknown"):
        m = (info.group == g).to_numpy() & (info.band == b).to_numpy()
        if m.sum() >= 30:
            summ(m, f"{g} {b}")
    for fl in ("top", "penthouse", "garden", "lower"):
        m = (info.group == g).to_numpy() & info[fl].to_numpy()
        if m.sum() >= 30:
            summ(m, f"{g} {fl}")
json.dump(res, open("heldout.json", "w"), indent=1)
for k_, v in res.items():
    print(k_, json.dumps(v))
