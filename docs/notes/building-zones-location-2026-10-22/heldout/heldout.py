"""Per-ad held-out elpd, predictive median and 90% coverage on the latest split for one run.

    python heldout.py MODULE RUN OUT.npz

400 draws per run (100 per chain, spread evenly), Student-t likelihood, chunks of 20,000 ads,
as in docs/notes/building-zones-floor-2026-10-21/heldout.py.
"""

import importlib
import sys

import numpy as np
from scipy.special import gammaln, logsumexp

from rentfrontier import b0, splits
from rentfrontier import building_zones as bz

RUNS = "/data1/apartments/frontier/runs/"
DATASET = (
    "/data1/apartments/frontier/datasets/b0-edc83b49f9bacd8c-alldata-v36-dense-nyc"
)
mod = importlib.import_module("rentfrontier." + sys.argv[1])
run, out = sys.argv[2], sys.argv[3]

frame = b0.load_frame(DATASET)
held = splits.SPLITS["latest"](frame)
z = np.load(RUNS + run + "/posterior.npz")
assert (z["heldout"] == held).all()
full = mod.design(frame)
assert list(full.names) == [str(n) for n in z["names"]]
t = mod.subset(full, ~held)
h = mod.subset(full, held)
DRAWS = 100
idx = np.linspace(0, z["kept/sigma"].shape[1] - 1, DRAWS).round().astype(int)


def k(s):
    return z["kept/" + s][:, idx].reshape(-1, *z["kept/" + s].shape[2:]).astype(float)


beta, L, w, bld, sig, nu = k("beta"), k("L"), k("gp_w"), k("bld"), k("sigma"), k("nu")
B, _ = bz.wave_matrix(t)
Bw = B[h.site] @ w.T
del t, full, B
res = {n: [] for n in ("elpd", "pred", "in90", "map", "bldfx")}
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
    res["elpd"].append(logsumexp(lp, axis=1) - np.log(lp.shape[1]))
    yrep = mu + s * rng.standard_t(nu, size=mu.shape)
    lo, hi = np.quantile(yrep, [0.05, 0.95], axis=1)
    res["pred"].append(np.median(mu, 1))
    res["in90"].append((h.y[sl] >= lo) & (h.y[sl] <= hi))
    res["map"].append(np.median(Bw[sl], 1))
    res["bldfx"].append(np.median(bld[:, site].T, 1))
np.savez_compressed(
    out,
    y=h.y,
    building=frame[held].building.astype(str).to_numpy().astype("U"),
    **{n: np.concatenate(v) for n, v in res.items()},
)
print(run, len(h.y), beta.shape[0], flush=True)
