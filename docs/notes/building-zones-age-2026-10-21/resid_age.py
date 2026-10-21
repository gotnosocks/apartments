import os, numpy as np, pandas as pd

os.environ.setdefault("JAX_PLATFORMS", "cpu")
from rentfrontier import b0, splits, building_zones_age as bzf, building_zones as bz

R = "/data1/apartments/frontier/runs/building-zones-age-b0-latest-f023987f-dense-w1000"
frame = b0.load_frame(
    "/data1/apartments/frontier/datasets/b0-edc83b49f9bacd8c-alldata-v36-dense-nyc"
)
held = splits.SPLITS["latest"](frame)
z = np.load(f"{R}/posterior.npz")
assert (held == z["heldout"]).all()
d = bzf.design(frame)
assert list(d.names) == [str(n) for n in z["names"]]
t = bzf.subset(d, ~held)
m = lambda k: z["kept/" + k].reshape(-1, *z["kept/" + k].shape[2:]).mean(0)
beta, L, w, bld = m("beta"), m("L"), m("gp_w"), m("bld")
B, _ = bz.wave_matrix(t)
F = B @ w
mu = t.x @ beta + (1 - t.frac) * L[t.week] + t.frac * L[t.week + 1] + (F + bld)[t.site]
tr = frame[~held].reset_index(drop=True)
out = pd.DataFrame(
    {
        "listing_id": tr.listing_id,
        "building": tr.building,
        "unit_id": tr.unit_id,
        "y": t.y,
        "mu": mu,
        "r": t.y - mu,
        "bld": bld[t.site],
        "F": F[t.site],
        "zone": bz.site_zone(t)[t.site],
        "group": t.group,
    }
)
print(len(out), out.r.describe(), out.groupby("zone").r.agg(["mean", "std"]), sep="\n")
print("mad", np.median(np.abs(out.r)))
out.to_parquet("resid_age.parquet")
