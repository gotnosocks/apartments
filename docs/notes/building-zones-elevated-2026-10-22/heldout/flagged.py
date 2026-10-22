"""Paired held-out elpd, RMSE and coverage on the ads a 0/1 column flags, and on the rest.

python flagged.py BASE.npz NEW.npz OUT.json
"""

import json
import sys

import numpy as np
import pandas as pd

base, z = np.load(sys.argv[1]), np.load(sys.argv[2])
assert (z["y"] == base["y"]).all() and (z["building"] == base["building"]).all()
d = z["elpd"] - base["elpd"]
x = z["loc_x"][:, -1]
out = {"column": str(z["loc_names"][-1])}
for k, m in (("flagged", x == 1), ("rest", x == 0)):
    s = pd.Series(d[m]).groupby(z["building"][m]).sum()
    out[k] = {
        "ads": int(m.sum()),
        "buildings": int(len(s)),
        "elpd_diff": round(float(d[m].sum()), 1),
        "se_buildings": round(float(np.sqrt(len(s)) * s.std()), 1),
        "rmse": round(
            float(np.sqrt(((z["y"][m] - z["pred"][m]) ** 2).mean()) * 100), 3
        ),
        "rmse_base": round(
            float(np.sqrt(((base["y"][m] - base["pred"][m]) ** 2).mean()) * 100), 3
        ),
        "mean_resid_base": round(
            float((base["y"][m] - base["pred"][m]).mean() * 100), 2
        ),
        "mean_resid_new": round(float((z["y"][m] - z["pred"][m]).mean() * 100), 2),
        "cover90": round(float(z["in90"][m].mean()), 4),
        "cover90_base": round(float(base["in90"][m].mean()), 4),
    }
json.dump(out, open(sys.argv[3], "w"), indent=1)
print(out)
