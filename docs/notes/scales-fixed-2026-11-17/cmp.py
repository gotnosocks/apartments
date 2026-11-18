"""Compare a held-scales run with an ordinary run on their shared held-out ads.

    python cmp.py ROOT HELD ORDINARY

ROOT/HELD and ROOT/ORDINARY each hold `scores.npz` from `rentfrontier.drift_score` and the
run under `runs/`. The script prints both elpds with the paired difference and its SE
clustered by building, the median absolute errors, coverage of the 50%, 80% and 95%
intervals, the mean width of the 80% interval, the agreement of the two cdfs at the ask,
and each run's sweep time and convergence summary.
"""

import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

root = Path(sys.argv[1])
names = sys.argv[2:4]
a, b = (np.load(root / n / "scores.npz", allow_pickle=True) for n in names)
assert np.array_equal(a["y"], b["y"])
d = a["elpd"] - b["elpd"]
_, cl = np.unique(a["building"].astype(str), return_inverse=True)
sums = np.bincount(cl, weights=d - d.mean())
se = float(np.sqrt(len(sums) / (len(sums) - 1) * np.sum(sums**2)))
BANDS = {"50": (0.25, 0.75), "80": (0.1, 0.9), "95": (0.025, 0.975)}


def bands(s):
    q = dict(zip(s["quantiles"].round(3).tolist(), s["q"].T, strict=True))
    cover = {
        k: float(np.mean((s["y"] >= q[lo]) & (s["y"] <= q[hi])))
        for k, (lo, hi) in BANDS.items()
    }
    return cover, float(np.mean(q[0.9] - q[0.1]))


def fit(name):
    r = json.loads((root / name / "runs" / name / "result.json").read_text())
    diag = r["diagnostics"]
    return {
        "seconds_per_sweep": r["gibbs"]["seconds_per_sweep"],
        "seconds": r["seconds"],
        "draws": r["sampler_settings"]["draws"],
        "max_rhat": [diag["max_rhat_name"], diag["max_rhat"]],
        "min_ess": [diag["min_ess_name"], diag["min_ess"]],
        "quantities": len(diag["per_quantity"]),
        "passes": diag["passes"],
    }


n = len(d) // 10
lo_a, lo_b = set(np.argsort(a["cdf"])[:n]), set(np.argsort(b["cdf"])[:n])
out = {
    "ads": len(d),
    "elpd": [float(a["elpd"].sum()), float(b["elpd"].sum())],
    "held_minus_ordinary": float(d.sum()),
    "se_by_building": se,
    "mae": [float(np.median(np.abs(s["y"] - s["pred"]))) for s in (a, b)],
    "cover": [bands(a)[0], bands(b)[0]],
    "width80": [bands(a)[1], bands(b)[1]],
    "spearman_cdf": float(spearmanr(a["cdf"], b["cdf"]).statistic),
    "lowest_tenth": n,
    "shared_lowest_tenth": len(lo_a & lo_b),
    "fit": {name: fit(name) for name in names},
}
print(json.dumps(out, indent=1))
