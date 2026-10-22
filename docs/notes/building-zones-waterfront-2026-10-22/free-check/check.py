"""Free check: the location fit's building effects against waterfront frontage (water_km under
a cut, from the building-parks snapshot)."""

import json
import numpy as np
import pandas as pd
from rentfrontier import b0, building_zones_location as bzl, splits

DATASET = (
    "/data1/apartments/frontier/datasets/b0-edc83b49f9bacd8c-alldata-v36-dense-nyc"
)
RUN = "/data1/apartments/frontier/runs/building-zones-location-b0-latest-732b36ec-dense-w1000"
frame = b0.load_frame(DATASET)
held = splits.SPLITS["latest"](frame)
d = bzl.design(frame)
t = pd.read_parquet(
    "/data1/apartments/external/building-parks/20261022-ec936683/parks.parquet"
)
e = 1000 * t.drop_duplicates("building").set_index("building").water_km
e = e.reindex(frame.building.astype(str)).to_numpy(float)
z = np.load(RUN + "/posterior.npz")
bld = np.median(z["kept/bld"].reshape(-1, z["kept/bld"].shape[-1]), 0)
names = [str(n) for n in z["names"]]
S = d.site.max() + 1
first = np.full(S, -1)
first[d.site[::-1]] = np.arange(len(d.site))[::-1]
tr = ~held
n_tr = np.bincount(d.site[tr], minlength=S)
es = e[first]
dz = np.load("/data1/apartments/tmp/sim-location/design.npz")
sx, sy, zone = dz["site_x"], dz["site_y"], dz["site_zone"]
out = {"rows_train": int(tr.sum())}
for cut in (100.0, 150.0, 250.0):
    front = np.isfinite(es) & (np.nan_to_num(es, nan=1e9) < cut)
    near = np.isfinite(es) & (es >= cut) & (es < 500)
    r = {
        "rows": int((front[d.site] & tr).sum()),
        "buildings": int((front & (n_tr > 0)).sum()),
    }
    for name, g in (("front", front), ("near_500m", near)):
        wt = n_tr * g
        r["bld_mean_" + name] = float(100 * (bld * wt).sum() / wt.sum())
    for cell in (0.3, 0.15):
        key = np.floor(sx / cell).astype(np.int64) * 100000 + np.floor(
            sy / cell
        ).astype(np.int64)
        keep = (n_tr > 0) & np.isfinite(es)
        df = pd.DataFrame({"k": key[keep], "f": front[keep], "b": 100 * bld[keep]})
        both = df.groupby("k").f.agg(["min", "max"])
        ok = both.index[(both["min"] == 0) & (both["max"] == 1)]
        g = df[df.k.isin(ok)].groupby(["k", "f"]).b.mean().unstack()
        diff = g[True] - g[False]
        r[f"cell{int(cell * 1000)}m"] = {
            "cells": int(len(ok)),
            "gap_mean": float(diff.mean()),
            "gap_se": float(diff.std() / np.sqrt(len(diff))),
            "gap_median": float(diff.median()),
        }
    out[f"under_{int(cut)}m"] = r
json.dump(out, open("/data1/apartments/tmp/waterfront/check.json", "w"), indent=1)
print(json.dumps(out, indent=1))
