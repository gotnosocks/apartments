"""Held-out elpd of the combined location fit against the floor fit, on the latest split's
held-out ads in the bottom and top fifth of each location column, with SE from per-building
sums.

    python byfeature.py OUT.json
"""

import json
import sys

import numpy as np
import pandas as pd

from rentfrontier import b0, splits
from rentfrontier import building_zones_location as loc

DATASET = (
    "/data1/apartments/frontier/datasets/b0-edc83b49f9bacd8c-alldata-v36-dense-nyc"
)
D = "/data1/apartments/tmp/locheld/"
frame = b0.load_frame(DATASET)
held = splits.SPLITS["latest"](frame)
h = frame[held]
cols = []
for module, key, snap, file in loc.PARTS:
    cols.append(module.columns(h, pd.read_parquet(getattr(module, snap) / file)))
x = np.hstack(cols)
base = np.load(D + "floor.npz", allow_pickle=True)
z = np.load(D + "location.npz", allow_pickle=True)
assert (base["y"] == h.y.to_numpy()).all() if "y" in h else True
d = z["elpd"] - base["elpd"]
bld = z["building"].astype(str)
out = {}
for j, name in enumerate(loc.COLUMNS):
    lo, hi = np.quantile(x[:, j], [0.2, 0.8])
    out[name] = {}
    for tag, m in (("bottom_fifth", x[:, j] <= lo), ("top_fifth", x[:, j] >= hi)):
        g = pd.Series(d[m]).groupby(bld[m]).sum()
        out[name][tag] = {
            "ads": int(m.sum()),
            "elpd_diff": round(float(d[m].sum()), 1),
            "se_buildings": round(float(g.std() * np.sqrt(len(g))), 1),
            "rmse_change": round(
                float(
                    np.sqrt(((z["y"][m] - z["pred"][m]) ** 2).mean())
                    - np.sqrt(((base["y"][m] - base["pred"][m]) ** 2).mean())
                )
                * 100,
                3,
            ),
        }
    print(name, out[name])
json.dump(out, open(sys.argv[1], "w"), indent=1)
