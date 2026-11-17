"""Compare the k50 runs of `drift-building-unitkn` and L2 on their shared held-out ads.

    python cmp.py ROOT

ROOT holds `nophase-k50` and `l2-k50`, each with `scores.npz` from
`rentfrontier.drift_score` and the run under `runs/`. The script prints the paired elpd
difference with its SE clustered by building, the median absolute errors, coverage of the
80% interval over all ads and by L2's lease phase, the agreement of the two cdfs, and the
phases of the ads in a single model's lowest tenth.
"""

import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

from rentfrontier.drift_building_phase import PHASES

root = Path(sys.argv[1])
a = np.load(root / "nophase-k50/scores.npz", allow_pickle=True)
b = np.load(root / "l2-k50/scores.npz", allow_pickle=True)
assert np.array_equal(a["y"], b["y"])
post = np.load(root / "l2-k50/runs/l2-k50/posterior.npz", allow_pickle=True)
phase = np.asarray(
    post["kept/pred_phase"] if "kept/pred_phase" in post else post["pred_phase"]
)
phase = phase.reshape(-1, len(a["y"]))[0] if phase.ndim > 1 else phase
d = b["elpd"] - a["elpd"]
_, cl = np.unique(a["building"].astype(str), return_inverse=True)
sums = np.bincount(cl, weights=d - d.mean())
se = float(np.sqrt(len(sums) / (len(sums) - 1) * np.sum(sums**2)))


def cover(s, m):
    q = dict(
        zip((0.025, 0.05, 0.1, 0.25, 0.75, 0.9, 0.95, 0.975), s["q"].T, strict=True)
    )
    return float(np.mean((s["y"][m] >= q[0.1][m]) & (s["y"][m] <= q[0.9][m])))


every = np.ones(len(d), bool)
n = len(d) // 10
lo_a, lo_b = set(np.argsort(a["cdf"])[:n]), set(np.argsort(b["cdf"])[:n])
added, dropped = np.array(sorted(lo_a - lo_b)), np.array(sorted(lo_b - lo_a))
none = PHASES.index("none")
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
    "first_ad_share_added_by_nophase": float(np.mean(phase[added] == none))
    if len(added)
    else None,
    "first_ad_share_dropped_by_nophase": float(np.mean(phase[dropped] == none))
    if len(dropped)
    else None,
    "first_ad_share_all": float(np.mean(phase == none)),
}
print(json.dumps(out, indent=1))
