"""S3, part B: how much of a level by lease phase (candidate L2) is a common offset?

L1 puts the lease phase in the noise scale only. The script fits two cross-fitted shifts the same way
as `s3_ending.py`, a constant and a mean by phase, rescores L1's predictive with each and
takes the gain of the phase shift over the constant. The script also prints each phase's mean gap and
median gap with SEs clustered by building."""

import json

import numpy as np
import pandas as pd

import common as c

PHASES = ("10-13", "none", "0-2", "3-9", "14-21", "22-25", "26+")
h = c.heldout(c.rows())
dr = c.Draws()
assert len(h) == len(dr.ph)
ph = np.asarray(PHASES)[dr.ph]
gap, fold, sub, b = (
    h.gap.to_numpy(),
    h.fold.to_numpy(),
    c.subfold(h.building),
    h.building.to_numpy(),
)
idx = np.arange(len(h))
e0 = dr.gain(idx, delta=c.crossfit_shift(gap, np.zeros(len(h)), fold, sub)[0])
dl, k = c.crossfit_shift(gap, ph, fold, sub)
e1 = dr.gain(idx, delta=dl)
inc = e1 - e0
res = {
    "n": len(h),
    "constant": [float(e0.sum()), c.cluster_se(e0, b)],
    "phase": [float(e1.sum()), c.cluster_se(e1, b)],
    "phase_over_constant": [float(inc.sum()), c.cluster_se(inc, b)],
    "k": k,
    "mean_gap": [float(gap.mean()), c.cluster_se(gap, b) / len(h)],
    "median_gap": float(np.median(gap)),
    "by_phase": {},
}
for p in PHASES:
    m = ph == p
    if m.sum() == 0:
        continue
    res["by_phase"][p] = {
        "n": int(m.sum()),
        "mean_gap": float(gap[m].mean()),
        "se": c.cluster_se(gap[m], b[m]) / m.sum(),
        "median_gap": float(np.median(gap[m])),
        "gain_over_constant": float(inc[m].sum()),
    }
print(json.dumps(res, indent=1), flush=True)
json.dump(res, open(c.OUT + "s3b.json", "w"), indent=1)
pd.DataFrame(
    {"listing_id": h.listing_id.to_numpy(), "e_const": e0, "e_phase": e1}
).to_parquet(c.OUT + "s3b_gains.parquet")
