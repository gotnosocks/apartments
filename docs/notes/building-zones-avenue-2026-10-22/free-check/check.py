"""Free check: the location fit's building effects against the mid-block avenue flag."""

import json
import numpy as np
import pandas as pd
from rentfrontier import (
    b0,
    building_zones_front,
    building_zones_location as bzl,
    splits,
)

DATASET = (
    "/data1/apartments/frontier/datasets/b0-edc83b49f9bacd8c-alldata-v36-dense-nyc"
)
RUN = "/data1/apartments/frontier/runs/building-zones-location-b0-latest-732b36ec-dense-w1000"
frame = b0.load_frame(DATASET)
held = splits.SPLITS["latest"](frame)
d = bzl.design(frame)
fr = pd.read_parquet(building_zones_front.FRONTAGE)
f = (
    fr.drop_duplicates("building")
    .set_index("building")
    .reindex(frame.building.astype(str))
)
w = f.front_width_ft.to_numpy(float)
c = f.corner.to_numpy(float)
z = np.load(RUN + "/posterior.npz")
bld = np.median(z["kept/bld"].reshape(-1, z["kept/bld"].shape[-1]), 0)
names = [str(n) for n in z["names"]]
truck = d.x[:, names.index("bld:truck_through")]
S = d.site.max() + 1
first = np.full(S, -1)
first[d.site[::-1]] = np.arange(len(d.site))[::-1]
tr = ~held
n_tr = np.bincount(d.site[tr], minlength=S)
ws, cs = w[first], c[first]
wide = np.isfinite(ws) & (np.nan_to_num(ws) > 60)
side = np.isfinite(ws) & (np.nan_to_num(ws) <= 40)
mid = wide & (cs == 0)
cor = wide & (cs == 1)
dz = np.load("/data1/apartments/tmp/sim-location/design.npz")
assert len(dz["site_x"]) == S
sx, sy, zone = dz["site_x"], dz["site_y"], dz["site_zone"]
out = {
    "rows_train": int(tr.sum()),
    "rows_mid": int((mid[d.site] & tr).sum()),
    "rows_corner_wide": int((cor[d.site] & tr).sum()),
    "bld_mid": int((mid & (n_tr > 0)).sum()),
    "bld_total": int((n_tr > 0).sum()),
    "truck_among_mid_rows": float(truck[tr & mid[d.site]].mean()),
}
# Row-weighted mean building effect by group, in log points x100.
for name, g in (("mid", mid), ("corner_wide", cor), ("side", side)):
    wt = n_tr * g
    out["bld_mean_" + name] = float(100 * (bld * wt).sum() / wt.sum())
# Within a 300 m cell: mid-block avenue against side-street buildings in the same cell.
out["xy_span"] = [float(np.ptp(sx[n_tr > 0])), float(np.ptp(sy[n_tr > 0]))]
for cell in (0.3, 0.15):
    key = np.floor(sx / cell).astype(np.int64) * 100000 + np.floor(sy / cell).astype(
        np.int64
    )
    keep = (n_tr > 0) & (mid | side)
    df = pd.DataFrame(
        {"k": key[keep], "mid": mid[keep], "b": 100 * bld[keep], "n": n_tr[keep]}
    )
    both = df.groupby("k").mid.agg(["min", "max"])
    ok = both.index[(both["min"] == 0) & (both["max"] == 1)]
    df = df[df.k.isin(ok)]
    df["bc"] = df.b - df.groupby("k").b.transform("mean")
    gap = df.groupby(["k", "mid"]).b.mean().unstack()
    diff = gap[True] - gap[False]
    out[f"cell{int(cell * 1000)}m"] = {
        "cells": int(len(ok)),
        "mid_buildings": int(df.mid.sum()),
        "gap_mean": float(diff.mean()),
        "gap_se": float(diff.std() / np.sqrt(len(diff))),
        "gap_median": float(diff.median()),
    }
json.dump(out, open("/data1/apartments/tmp/avenue/check.json", "w"), indent=1)
print(json.dumps(out, indent=1))
