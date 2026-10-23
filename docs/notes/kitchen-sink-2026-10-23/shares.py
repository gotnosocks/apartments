"""Variance shares of a building-zones run over its training rows, from 100 kept draws.

    python shares.py MODULE RUN OUT.json SPLIT DATASET

As in rentfrontier.variance, I split each draw's fitted log rent mu into its terms and give
each term Cov(term, mu) / (Var(mu) + Var(r)), with r the observed residual:

    time       the weekly walk and the season columns
    features   every other column of the design
    surface    the neighborhood surface
    building   the building level

The descriptive share is the building share. I print the surface share beside it.
"""

import importlib
import json
import sys

import numpy as np

from rentfrontier import b0, splits
from rentfrontier import building_zones as bz

RUNS = "/data1/apartments/frontier/runs/"
SEASON = ("sin1", "cos1", "sin2", "cos2")
mod = importlib.import_module("rentfrontier." + sys.argv[1])
for m in list(sys.modules.values()):
    if m.__name__.startswith("rentfrontier.") and hasattr(m, "SPLIT"):
        m.SPLIT = sys.argv[4]
run, out = sys.argv[2], sys.argv[3]

frame = b0.load_frame(sys.argv[5])
held = splits.SPLITS[sys.argv[4]](frame)
z = np.load(RUNS + run + "/posterior.npz")
assert (z["heldout"] == held).all()
full = mod.design(frame)
names = [str(n) for n in z["names"]]
assert list(full.names) == names
t = mod.subset(full, ~held)
del full
DRAWS = 100
idx = np.linspace(0, z["kept/sigma"].shape[1] - 1, DRAWS).round().astype(int)


def k(s):
    return z["kept/" + s][:, idx].reshape(-1, *z["kept/" + s].shape[2:]).astype(float)


beta, L, w, bld = k("beta"), k("L"), k("gp_w"), k("bld")
season = np.isin(names, SEASON)
B, _ = bz.wave_matrix(t)
G = ("time", "features", "surface", "building")
n = 0
s_mu = np.zeros(len(beta))
s_mu2 = np.zeros(len(beta))
s_r = np.zeros(len(beta))
s_r2 = np.zeros(len(beta))
s_g = {g: np.zeros(len(beta)) for g in G}
s_gmu = {g: np.zeros(len(beta)) for g in G}
for a0 in range(0, len(t.y), 20000):
    sl = slice(a0, a0 + 20000)
    x, week, frac = t.x[sl], t.week[sl], t.frac[sl]
    terms = {
        "time": x[:, season] @ beta[:, season].T
        + (1 - frac)[:, None] * L[:, week].T
        + frac[:, None] * L[:, week + 1].T,
        "features": x[:, ~season] @ beta[:, ~season].T,
        "surface": B[t.site[sl]] @ w.T,
        "building": bld[:, t.site[sl]].T,
    }
    mu = sum(terms.values())
    r = t.y[sl, None] - mu
    n += len(r)
    s_mu += mu.sum(0)
    s_mu2 += (mu * mu).sum(0)
    s_r += r.sum(0)
    s_r2 += (r * r).sum(0)
    for g, v in terms.items():
        s_g[g] += v.sum(0)
        s_gmu[g] += (v * mu).sum(0)
var_mu = s_mu2 / n - (s_mu / n) ** 2
total = var_mu + s_r2 / n - (s_r / n) ** 2
shares = {g: (s_gmu[g] / n - s_g[g] / n * s_mu / n) / total for g in G}
shares["residual"] = 1 - var_mu / total
rec = {
    g: {
        "median": float(np.median(v)),
        "lower_90": float(np.quantile(v, 0.05)),
        "upper_90": float(np.quantile(v, 0.95)),
    }
    for g, v in shares.items()
}
rec["descriptive"] = rec["building"]
with open(out, "w") as f:
    json.dump({"run": run, "rows": n, "draws": len(beta), "shares": rec}, f, indent=1)
print(json.dumps(rec), flush=True)
