"""Held-out elpd change of fit 8 (asof3-cap64) against the asof2 fit by elevator floor band, with
building-clustered standard errors, from the per-ad scores of score.py.

    python floor_bands.py

Each ad's floor comes from the unit floor snapshot. Floors at 48 and up also get their 90%
coverage and median residual in each run.
"""

import numpy as np, pandas as pd

D = "/data1/apartments/tmp/conference-followups/"
a, b = np.load(D + "asof2-latest.npz"), np.load(D + "cap64-latest.npz")
assert (a["listing"] == b["listing"]).all()
fl = pd.read_parquet(
    "/data1/apartments/external/unit-floor/20261021-d84914c0/floor.parquet",
    columns=["listing_id", "floor"],
)
fl = (
    fl.assign(listing_id=fl.listing_id.astype(str))
    .drop_duplicates("listing_id")
    .set_index("listing_id")
    .floor
)
f = pd.Series(a["listing"].astype(str)).map(fl).to_numpy(dtype=float)
d = b["elpd"] - a["elpd"]


def se(m):
    s = pd.Series(d[m]).groupby(b["building"][m]).sum()
    return (
        np.sqrt(len(s) / (len(s) - 1) * ((s - s.mean()) ** 2).sum())
        if len(s) > 1
        else np.nan
    )


for lab, m in (
    ("floor unknown", np.isnan(f)),
    ("floor < 30", f < 30),
    ("30 to 46", (f >= 30) & (f <= 46)),
    ("47", f == 47),
    ("48 and up", f >= 48),
    ("48 to 63", (f >= 48) & (f < 64)),
    ("64 and up", f >= 64),
):
    print(
        f"{lab:14s} ads {m.sum():7d} buildings {len(np.unique(b['building'][m])):5d} elpd change {d[m].sum():+7.1f} SE bld {se(m):5.1f}"
    )
m = f >= 48
for k, z in (("asof2", a), ("cap64", b)):
    lo, hi = z["q"][m, 1], z["q"][m, 6]
    print(
        k,
        "floor>=48 90% cover",
        np.mean((z["y"][m] >= lo) & (z["y"][m] <= hi)).round(3),
        "median resid x100",
        np.median(z["y"][m] - z["pred"][m]).round(4) * 100,
    )
