"""Paired held-out scores of the location fit against the floor fit on the whole-building split,
and the explained-share test of the location contribution against a within-zone permutation null.

    python compare_buildings.py FLOOR.npz LOCATION.npz OUT.json
"""

import json
import sys

import numpy as np
import pandas as pd

base = np.load(sys.argv[1])
z = np.load(sys.argv[2])
assert (z["y"] == base["y"]).all() and (z["building"] == base["building"]).all()
d = z["elpd"] - base["elpd"]
bld = z["building"]


def paired(m):
    g = pd.Series(d[m]).groupby(bld[m]).sum()
    rmse = lambda r: float(np.sqrt(((r["y"][m] - r["pred"][m]) ** 2).mean())) * 100
    return {
        "ads": int(m.sum()),
        "buildings": int(len(g)),
        "elpd_diff": round(float(d[m].sum()), 1),
        "se_buildings": round(float(g.std() * np.sqrt(len(g))), 1),
        "rmse": round(rmse(z), 3),
        "rmse_floor": round(rmse(base), 3),
        "cover90": round(float(z["in90"][m].mean()), 4),
        "cover90_floor": round(float(base["in90"][m].mean()), 4),
    }


out = {"all": paired(np.ones(len(d), bool)), "by_column": {}}
print("all", out["all"])
for j, name in enumerate(z["loc_names"]):
    x = z["loc_x"][:, j]
    lo, hi = np.quantile(x, [0.2, 0.8])
    out["by_column"][name] = {
        "bottom_fifth": paired(x <= lo),
        "middle": paired((x > lo) & (x < hi)),
        "top_fifth": paired(x >= hi),
    }
    print(
        name,
        {
            k: (v["elpd_diff"], v["se_buildings"])
            for k, v in out["by_column"][name].items()
        },
    )

# Per held-out building: the floor fit's mean residual and the location contribution, weighted by
# ads. Explained share = 1 - SS(residual - centred contribution) / SS(residual), each about its
# weighted mean. The null shuffles the contribution across buildings within each zone.
f = (
    pd.DataFrame(
        {
            "b": bld,
            "r": base["y"] - base["pred"],
            "c": z["loc_contrib"],
            "delta": z["pred"] - base["pred"],
            "map_change": z["map"] - base["map"],
            "zone": z["zone"],
        }
    )
    .groupby("b")
    .agg(
        r=("r", "mean"),
        c=("c", "mean"),
        delta=("delta", "mean"),
        map_change=("map_change", "mean"),
        zone=("zone", "first"),
        n=("r", "size"),
    )
)
w = f.n.to_numpy(float)
r = f.r.to_numpy()
r = r - np.average(r, weights=w)
ss = np.sum(w * r * r)


def share(c):
    c = c - np.average(c, weights=w)
    return 1 - np.sum(w * (r - c) ** 2) / ss


zones = f.zone.to_numpy()


def test(c, seed=0):
    rng = np.random.default_rng(seed)
    null = []
    for _ in range(1000):
        p = c.copy()
        for k in np.unique(zones):
            i = np.flatnonzero(zones == k)
            p[i] = c[rng.permutation(i)]
        null.append(share(p))
    null = np.array(null)
    cc = c - np.average(c, weights=w)
    return {
        "explained": round(float(share(c)), 5),
        "null_mean": round(float(null.mean()), 5),
        "null_95": round(float(np.quantile(null, 0.95)), 5),
        "beats_null": bool(share(c) > max(0.0, np.quantile(null, 0.95))),
        "sd_x100": round(float(np.sqrt(np.average(cc**2, weights=w))) * 100, 2),
        "slope_of_residual": round(float(np.sum(w * r * cc) / np.sum(w * cc**2)), 3),
    }


mc = f.map_change.to_numpy() - np.average(f.map_change.to_numpy(), weights=w)
cc0 = f.c.to_numpy() - np.average(f.c.to_numpy(), weights=w)
out["explained_share"] = {
    "buildings": int(len(f)),
    "residual_sd_x100": round(float(np.sqrt(ss / w.sum())) * 100, 2),
    "location_contribution": test(f.c.to_numpy()),
    "prediction_change": test(f.delta.to_numpy()),
    "corr_contribution_map_change": round(float(np.corrcoef(cc0, mc)[0, 1]), 3),
}
print("explained", out["explained_share"])
json.dump(out, open(sys.argv[3], "w"), indent=1)
