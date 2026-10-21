"""Posterior-mean residuals of a run on the training rows: python resid.py TAG."""

import sys, numpy as np, pandas as pd
from rentfrontier import (
    b0,
    splits,
    building_zones as bz,
    building_zones_age,
    building_zones_floor,
)
from common import RUNS, DATASET, FLOOR, AGE, bands

tag = sys.argv[1]
run, mod = {"floor": (FLOOR, building_zones_floor), "age": (AGE, building_zones_age)}[
    tag
]
frame = b0.load_frame(DATASET)
held = splits.SPLITS["latest"](frame)
z = np.load(f"{RUNS}{run}/posterior.npz")
assert (held == z["heldout"]).all()
d = mod.design(frame)
assert list(d.names) == [str(n) for n in z["names"]]
t = mod.subset(d, ~held)
m = lambda k: z["kept/" + k].reshape(-1, *z["kept/" + k].shape[2:]).mean(0)
beta, L, w, bld = m("beta"), m("L"), m("gp_w"), m("bld")
B, _ = bz.wave_matrix(t)
F = B @ w
mu = t.x @ beta + (1 - t.frac) * L[t.week] + t.frac * L[t.week + 1] + (F + bld)[t.site]
tr = frame[~held].reset_index(drop=True)
out = pd.DataFrame(
    {
        "listing_id": tr.listing_id.astype(str),
        "building": tr.building.astype(str),
        "site": t.site,
        "y": t.y,
        "mu": mu,
        "r": t.y - mu,
        "bld": bld[t.site],
        "F": F[t.site],
        "zone": bz.site_zone(t)[t.site],
    }
)
out = pd.concat([out, bands(tr, t.x[:, t.names.index("bld:elevator")])], axis=1)
out.to_parquet(f"resid_{tag}.parquet")
if tag == "floor":
    np.save("train_x_names.npy", np.array(t.names))
    pd.DataFrame(
        {"mean": t.x.mean(0), "var": t.x.var(0), "share": (t.x != 0).mean(0)},
        index=t.names,
    ).to_parquet("x_moments.parquet")
print(tag, len(out), "mad", float(np.median(np.abs(out.r))))
