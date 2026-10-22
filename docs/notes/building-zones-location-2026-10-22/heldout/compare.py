"""Paired held-out elpd of each run against the floor run on the latest split's ads, overall and
by building (the SE from per-building sums, since ads of a building share its effect)."""

import json
import sys

import numpy as np
import pandas as pd

import os

os.chdir("/data1/apartments/tmp/locheld")
base = np.load("floor.npz", allow_pickle=True)
out = {}
for tag in sys.argv[1:]:
    z = np.load(tag + ".npz", allow_pickle=True)
    assert (z["y"] == base["y"]).all()
    d = z["elpd"] - base["elpd"]
    g = pd.Series(d).groupby(z["building"]).sum()
    out[tag] = {
        "ads": int(len(d)),
        "elpd_diff": round(float(d.sum()), 1),
        "se_ads": round(float(d.std() * np.sqrt(len(d))), 1),
        "se_buildings": round(float(g.std() * np.sqrt(len(g))), 1),
        "rmse": round(float(np.sqrt(((z["y"] - z["pred"]) ** 2).mean())) * 100, 3),
        "rmse_floor": round(
            float(np.sqrt(((base["y"] - base["pred"]) ** 2).mean())) * 100, 3
        ),
        "cover90": round(float(z["in90"].mean()), 4),
        "cover90_floor": round(float(base["in90"].mean()), 4),
    }
    print(tag, out[tag])
json.dump(out, open("compare.json", "w"), indent=1)

# The same on held-out ads in buildings with no training ads, where the building effect is
# its prior and the location columns carry the building's level.
from rentfrontier import b0, splits

frame = b0.load_frame(
    "/data1/apartments/frontier/datasets/b0-edc83b49f9bacd8c-alldata-v36-dense-nyc"
)
held = splits.SPLITS["latest"](frame)
counts = frame[~held].building.astype(str).value_counts()
n_train = counts.reindex(base["building"].astype(str)).to_numpy()
for tag in sys.argv[1:]:
    z = np.load(tag + ".npz", allow_pickle=True)
    out[tag]["by_training_ads"] = {}
    for lo, hi in ((1, 2), (3, 5), (6, 20), (21, 10**9)):
        m = (n_train >= lo) & (n_train <= hi)
        d = (z["elpd"] - base["elpd"])[m]
        g = pd.Series(d).groupby(z["building"][m]).sum()
        out[tag]["by_training_ads"][f"{lo}-{hi}"] = {
            "ads": int(m.sum()),
            "buildings": int(len(g)),
            "elpd_diff": round(float(d.sum()), 1),
            "se_buildings": round(float(g.std() * np.sqrt(len(g))), 1),
        }
    print(tag, out[tag]["by_training_ads"])
json.dump(out, open("compare.json", "w"), indent=1)
