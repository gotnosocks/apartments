"""Explained share of building effects by the building gym flag, against a permutation null, on the unit and attrs runs."""

import json
import numpy as np, pandas as pd
from rentfrontier import b0, splits, building_zones_gym as bzy
from rentfrontier.explained import screen, building_means
from common import RUNS, DATASET, UNIT, ATTRS

frame = b0.load_frame(DATASET)
held = splits.SPLITS["latest"](frame)
t = bzy.subset(bzy.design(frame), ~held)
nm = list(t.names)
S = int(t.site.max()) + 1
x = building_means(t.x[:, [nm.index("bld:gym")]], t.site, S)
out = {}
for tag, run in (("unit", UNIT), ("attrs", ATTRS)):
    z = np.load(RUNS + run + "/posterior.npz")
    bld = z["kept/bld"].reshape(-1, z["kept/bld"].shape[-1])
    assert bld.shape[1] == S
    level, sd2 = bld.mean(0), bld.var(0)
    keep = np.bincount(t.site, minlength=S) > 0
    out[tag] = screen(level[keep], sd2[keep], x[keep], np.random.default_rng(0))
    out[tag]["beats_null"] = bool(out[tag]["explained"] > max(0, out[tag]["null_95"]))
    print(tag, out[tag], flush=True)
json.dump(out, open("screen.json", "w"), indent=1)
