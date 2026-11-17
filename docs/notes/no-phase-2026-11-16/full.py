"""Compare the short fits of `drift-building-unitkn` and L2 on the latest split.

    python full.py NOPHASE_RUN L2_RUN

Each run directory holds `pred_scores.npz` from `rentfrontier.drift_score`, and L2's holds
`posterior.npz` with each held-out row's lease phase. The script prints the paired elpd
difference with its SE clustered by building, the median absolute errors, coverage of the
80% interval over all ads and by L2's phase, and the agreement of the two cdfs.
"""

import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

from rentfrontier.drift_building_phase import PHASES

new, old = (Path(p) for p in sys.argv[1:])
a = np.load(new / "pred_scores.npz", allow_pickle=True)
b = np.load(old / "pred_scores.npz", allow_pickle=True)
assert np.array_equal(a["y"], b["y"])
post = np.load(old / "posterior.npz", allow_pickle=True)
phase = np.asarray(post["kept/pred_phase"]).reshape(-1, len(a["y"]))[0]
d = b["elpd"] - a["elpd"]
_, cl = np.unique(a["building"].astype(str), return_inverse=True)
sums = np.bincount(cl, weights=d - d.mean())
se = float(np.sqrt(len(sums) / (len(sums) - 1) * np.sum(sums**2)))


def cover(s, m):
    return float(np.mean((s["cdf"][m] >= 0.1) & (s["cdf"][m] <= 0.9)))


every = np.ones(len(d), bool)
n = len(d) // 10
lo_a, lo_b = set(np.argsort(a["cdf"])[:n]), set(np.argsort(b["cdf"])[:n])
out = {
    "ads": len(d),
    "elpd_nophase": float(a["elpd"].sum()),
    "elpd_l2": float(b["elpd"].sum()),
    "l2_minus_nophase": float(d.sum()),
    "se_by_building": se,
    "mae_nophase": float(np.median(np.abs(a["y"] - a["pred"]))),
    "mae_l2": float(np.median(np.abs(b["y"] - b["pred"]))),
    "cover80": {"all": [cover(a, every), cover(b, every)]}
    | {
        p: [
            int((phase == i).sum()),
            cover(a, phase == i),
            cover(b, phase == i),
            float(d[phase == i].sum()),
        ]
        for i, p in enumerate(PHASES)
        if (phase == i).any()
    },
    "spearman_cdf": float(spearmanr(a["cdf"], b["cdf"]).statistic),
    "lowest_tenth": n,
    "shared_lowest_tenth": len(lo_a & lo_b),
    "lowest_hundredth": n // 10,
    "shared_lowest_hundredth": len(
        set(np.argsort(a["cdf"])[: n // 10]) & set(np.argsort(b["cdf"])[: n // 10])
    ),
}
print(json.dumps(out, indent=1))
