"""I1's starting point: L1's scores on its held-out ads of the latest split, on all of them
and on the 265 that the guarded `income_restricted_v2` marks, and on those 265 the coverage
and median's error L1's draws give with each draw's noise scale multiplied by k.

The script reads L1's `pred_scores.npz` and scores it as `drift_score.summary` does: the sum
of elpd, the median absolute gap from the predictive median, and the coverage of the central
50%, 80% and 95% intervals. For each k on KS it then rebuilds the predictive of each marked
ad from L1's 272 kept draws on the 48-node grid of `common.Draws`, with the unit's sd and
the location as drawn:

- the predictive cdf at the ask, whose value between 0.1 and 0.9 puts the ask inside the
  central 80% interval (likewise for 50% and 95%);
- the predictive median, by bisection on that cdf.

`docs/notes/income-flag-2026-11-14/g3_noise.py` gives the elpd gain for each k.

A fit moves the locations and unit sds as well, so these numbers only bound what k alone
does to the marked ads. Results go to `OUT/baseline.json`.

    systemd-run --user --scope -q -p MemoryMax=3G python baseline.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import ndtr

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "causal-screens-2026-11-13")
)
import common as c  # noqa: E402

COPY = Path(
    "/data1/apartments/frontier/datasets/"
    "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-textflags"
)
OUT = Path("/data1/apartments/tmp/income-flag-2026-11-14")
KS = (1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0)
LEVELS = {"50": (0.25, 0.75), "80": (0.1, 0.9), "95": (0.025, 0.975)}


def summary(y, q, pred, elpd):
    """`drift_score.summary`'s scores of the ads given."""
    cover = {
        "50": float(np.mean((y >= q[:, 3]) & (y <= q[:, 4]))),
        "80": float(np.mean((y >= q[:, 2]) & (y <= q[:, 5]))),
        "95": float(np.mean((y >= q[:, 0]) & (y <= q[:, 7]))),
    }
    return {
        "ads": int(len(y)),
        "elpd": float(elpd.sum()),
        "median_abs_error": float(np.median(np.abs(y - pred))),
        "coverage": cover,
    }


def cdf(dr, idx, x, k):
    """The predictive cdf of the ads `idx` at `x`, with each draw's noise scale times k."""
    s = (dr.sig[:, dr.grp[idx]] * dr.fac[:, dr.ph[idx]] * k).astype(np.float32)
    sd = np.sqrt(dr.usd[:, idx, None] ** 2 + s[:, :, None] ** 2 * dr.ilam)
    z = (x[None, :, None] - dr.loc[:, idx, None]) / sd
    return (np.exp(dr.logw) * ndtr(z)).sum(axis=2).mean(axis=0)


def median(dr, idx, k, steps=40):
    """The predictive median of the ads `idx` by bisection."""
    lo = dr.loc[:, idx].min(axis=0) - 2.0
    hi = dr.loc[:, idx].max(axis=0) + 2.0
    for _ in range(steps):
        mid = (lo + hi) / 2
        below = cdf(dr, idx, mid, k) < 0.5
        lo, hi = np.where(below, mid, lo), np.where(below, hi, mid)
    return (lo + hi) / 2


a = np.load(c.RUN + "pred_scores.npz", allow_pickle=True)
d = pd.read_parquet(
    COPY / "rows.parquet", columns=["listing_id", "income_restricted_v2"]
)
held = a["heldout"]
assert (d.listing_id.astype(str).to_numpy()[held] == a["listing"]).all()
marked = d.income_restricted_v2.to_numpy(bool)[held]
idx = np.flatnonzero(marked)
res = {
    "all": summary(a["y"], a["q"], a["pred"], a["elpd"]),
    "marked": summary(a["y"][idx], a["q"][idx], a["pred"][idx], a["elpd"][idx]),
    "unmarked": summary(
        a["y"][~marked], a["q"][~marked], a["pred"][~marked], a["elpd"][~marked]
    ),
}
dr = c.Draws()
assert np.allclose(dr.y[idx], a["y"][idx])
res["by_k"] = {}
for k in KS:
    pit = cdf(dr, idx, dr.y[idx].astype(np.float32), k)
    med = median(dr, idx, k)
    res["by_k"][str(k)] = {
        "coverage": {
            lv: float(np.mean((pit >= lo) & (pit <= hi)))
            for lv, (lo, hi) in LEVELS.items()
        },
        "median_abs_error": float(np.median(np.abs(dr.y[idx] - med))),
        "mean_pit": float(pit.mean()),
    }
    print(k, json.dumps(res["by_k"][str(k)]), flush=True)
print(json.dumps({p: res[p] for p in ("all", "marked", "unmarked")}, indent=1))
json.dump(res, open(OUT / "baseline.json", "w"), indent=1)
