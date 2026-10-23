"""Fit 4's held-out ads against fit 8's, split by whether the ad's unit has training rows.

    python unit_heldout.py DIR A B

DIR holds A-latest.npz and B-latest.npz from score.py, and B carries `unit_seen`. For each
group I print the ads, the summed elpd change B minus A, the RMSE of each run's median
prediction, the 90% coverage and the median 90% interval width. `compare.py` gives the standard errors
of the elpd change.
"""

import sys

import numpy as np

a, b = (np.load(f"{sys.argv[1]}/{n}-latest.npz") for n in sys.argv[2:4])
assert (a["listing"] == b["listing"]).all()
d = b["elpd"] - a["elpd"]
bld = b["building"]
y = b["y"]


def stats(z, m):
    lo, hi = z["q"][m, 1], z["q"][m, 6]
    return (
        np.sqrt(np.mean((y[m] - z["pred"][m]) ** 2)),
        np.mean((y[m] >= lo) & (y[m] <= hi)),
        np.median(hi - lo),
    )


seen = b["unit_seen"]
for lab, m in (
    ("unit has training rows", seen == 1),
    ("unit_id, no training row", seen == 0),
    ("no unit_id", seen == -1),
    ("all", np.ones(len(d), bool)),
):
    if not m.any():
        print(lab, 0)
        continue
    ra, ca, wa = stats(a, m)
    rb, cb, wb = stats(b, m)
    print(
        f"{lab:26s} ads {m.sum():7d} buildings {len(np.unique(bld[m])):6d}"
        f" elpd {d[m].sum():+9.0f}"
        f"  RMSE {ra:.4f} -> {rb:.4f}  cover90 {ca:.3f} -> {cb:.3f}"
        f"  width90 {wa:.4f} -> {wb:.4f} ({wb / wa - 1:+.1%})"
    )
