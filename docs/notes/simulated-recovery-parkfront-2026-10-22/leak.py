"""Leakage in the simulated recovery of park frontage: over buildings with training rows, the
row-weighted mean error of the fitted map F and of the fitted building levels (posterior median
less the truth), for park-facing buildings and the others in each zone, and their difference.

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
f_err = np.median(simulate.surface(basis, dz["share"], w), axis=0) - t["F"]
b = np.asarray(z["kept/bld"])
b_err = np.median(b.reshape(-1, b.shape[-1]), axis=0) - t["bld"]
rows = dz["site_rows"].astype(int)
cols = [str(c) for c in dz["bld_cols"]]
park = dz["site_bldx"][:, cols.index("bld:park_front")] == 1
res = {}
for k, zname in enumerate(dz["zone_names"]):
    on = (rows > 0) & (dz["site_zone"] == k)
    r = {}
    for name, e in (("map", f_err), ("building_level", b_err)):
        a = np.average(e[on & park], weights=rows[on & park])
        o = np.average(e[on & ~park], weights=rows[on & ~park])
        r[name] = {
            "park_facing_x100": round(float(a) * 100, 3),
            "others_x100": round(float(o) * 100, 3),
            "difference_x100": round(float(a - o) * 100, 3),
        }
    r["park_facing_sites"] = int((on & park).sum())
    r["park_facing_rows"] = int(rows[on & park].sum())
    a = np.average(f_err[on & park] + b_err[on & park], weights=rows[on & park])
    r["map_plus_level_park_facing_x100"] = round(float(a) * 100, 3)
    res[str(zname)] = r
    print(zname, r)
json.dump(res, open(out, "w"), indent=1)
