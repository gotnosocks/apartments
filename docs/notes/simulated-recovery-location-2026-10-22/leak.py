"""Map leakage in the simulated recovery of the location fit: the row-weighted mean error of the
fitted map F (posterior median less the truth) over buildings with training rows, by fifths of
each location column, and the row-weighted slope of the error on the planted location
contribution.

    python leak.py SIM_RUN ROOT OUT.json
"""

import json
import sys

import numpy as np

from rentfrontier import simulate

run, root, out = sys.argv[1:4]
dz = np.load(root + "/design.npz")
t = np.load(root + "/fitted/truth.npz")
z = np.load(f"/data1/apartments/frontier/runs/{run}/posterior.npz")
w = np.asarray(z["kept/gp_w"])
w = w.reshape(-1, w.shape[-1])
basis = [dz[f"basis_{k}"].astype(float) for k in range(len(dz["basis_sizes"]))]
err = np.median(simulate.surface(basis, dz["share"], w), axis=0) - t["F"]
rows = dz["site_rows"].astype(int)
on = rows > 0
cols = [str(c) for c in dz["bld_cols"]]
names = [str(n) for n in dz["names"]]
loc = [c for c in cols if c in simulate.SPECS["building-zones-location"].COLUMNS]
X = dz["site_bldx"][:, [cols.index(c) for c in loc]]
contrib = X @ t["beta"][[names.index(c) for c in loc]]
res = {"by_column": {}}
for j, c in enumerate(loc):
    x = X[on, j]
    lo, hi = np.quantile(np.repeat(x, rows[on]), [0.2, 0.8])
    res["by_column"][c] = {
        tag: {
            "sites": int(m.sum()),
            "rows": int(rows[on][m].sum()),
            "mean_error_x100": round(
                float(np.average(err[on][m], weights=rows[on][m])) * 100, 3
            ),
        }
        for tag, m in (
            ("nearest_or_lowest_fifth", x <= lo),
            ("farthest_or_highest_fifth", x >= hi),
        )
    }
    print(c, res["by_column"][c])
for k, zname in enumerate(dz["zone_names"]):
    m = on & (dz["site_zone"] == k)
    wt = rows[m]
    pc = contrib[m] - np.average(contrib[m], weights=wt)
    e = err[m] - np.average(err[m], weights=wt)
    res[str(zname)] = {
        "slope_of_map_error_on_planted_contribution": round(
            float((wt * pc * e).sum() / (wt * pc * pc).sum()), 4
        ),
        "planted_contribution_sd_x100": round(
            float(np.sqrt(np.average(pc * pc, weights=wt))) * 100, 2
        ),
        "map_error_sd_x100": round(
            float(np.sqrt(np.average(e * e, weights=wt))) * 100, 3
        ),
    }
    print(zname, res[str(zname)])
json.dump(res, open(out, "w"), indent=1)
