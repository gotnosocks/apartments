"""Per-building posterior mean and variance of d, map value F and training ad count for the age run."""

import numpy as np, pandas as pd
from common import RUNS, DATASET, AGE
from rentfrontier import b0, splits, building_zones as bz, building_zones_age as bzs

frame = b0.load_frame(DATASET)
held = splits.SPLITS["latest"](frame)
z = np.load(RUNS + AGE + "/posterior.npz")
t = bzs.subset(bzs.design(frame), ~held)
bld = z["kept/bld"]
bld = bld.reshape(-1, bld.shape[-1])
w = z["kept/gp_w"]
w = w.reshape(-1, w.shape[-1]).mean(0)
B, _ = bz.wave_matrix(t)
F = B @ w
tr = frame[~held].reset_index(drop=True)
sb = pd.DataFrame({"site": t.site, "building": tr.building.astype(str)})
n = np.bincount(t.site, minlength=bld.shape[1])
first = sb.drop_duplicates("site").set_index("site").building
out = pd.DataFrame(
    {
        "site": np.arange(bld.shape[1]),
        "d": bld.mean(0),
        "d_var": bld.var(0),
        "F": F,
        "zone": bz.site_zone(t),
        "n_train": n,
    }
)
out["building"] = out.site.map(first)
out = out[out.n_train > 0]
out.to_parquet("sites_age.parquet")
print(len(out), out.d.describe().to_dict())
