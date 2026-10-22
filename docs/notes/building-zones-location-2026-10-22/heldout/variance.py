"""Row-weighted variance of the map, the building effects, the location columns' contribution
and the residual on a run's training ads, from posterior medians.

    python variance.py MODULE RUN OUT.json
"""

import importlib
import json
import sys

import numpy as np

from rentfrontier import b0
from rentfrontier import building_zones as bz

RUNS = "/data1/apartments/frontier/runs/"
DATASET = (
    "/data1/apartments/frontier/datasets/b0-edc83b49f9bacd8c-alldata-v36-dense-nyc"
)
LOC = (
    "bld:log_station_km",
    "bld:log1p_routes",
    "bld:log_park_km",
    "bld:log_big_park_km",
    "bld:log_water_km",
    "bld:log1p_noise",
)
mod = importlib.import_module("rentfrontier." + sys.argv[1])
run, out = sys.argv[2], sys.argv[3]
frame = b0.load_frame(DATASET)
z = np.load(RUNS + run + "/posterior.npz")
held = z["heldout"]
full = mod.design(frame)
t = mod.subset(full, ~held)
del full


def med(s):
    v = z["kept/" + s]
    return np.median(v.reshape(-1, *v.shape[2:]).astype(float), 0)


beta, L, w, bld = med("beta"), med("L"), med("gp_w"), med("bld")
B, _ = bz.wave_matrix(t)
F = (B @ w)[t.site]
del B
b = bld[t.site]
names = list(t.names)
loc = [n for n in LOC if n in names]
xb = t.x @ beta
lc = {n: t.x[:, names.index(n)] * beta[names.index(n)] for n in loc}
lt = sum(lc.values()) if loc else np.zeros(len(t.y))
lin = (1 - t.frac) * L[t.week] + t.frac * L[t.week + 1]
resid = t.y - xb - lin - F - b
zone = np.asarray(t.zone) if hasattr(t, "zone") else None
res = {
    "rows": int(len(t.y)),
    "var_y": float(t.y.var()),
    "var_map": float(F.var()),
    "var_building": float(b.var()),
    "var_resid": float(resid.var()),
    "var_location": float(lt.var()),
    "var_map_plus_location": float((F + lt).var()),
    "location_terms": {
        n: {
            "beta_x100": float(beta[names.index(n)] * 100),
            "contrib_sd_x100": float(v.std() * 100),
            "contrib_p10_p90_x100": float(
                (np.quantile(v, 0.9) - np.quantile(v, 0.1)) * 100
            ),
            "corr_with_map": float(np.corrcoef(v, F)[0, 1]),
        }
        for n, v in lc.items()
    },
}
json.dump(res, open(out, "w"), indent=1)
print(json.dumps(res, indent=1))
