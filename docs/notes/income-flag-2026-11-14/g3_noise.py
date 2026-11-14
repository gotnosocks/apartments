"""S15b, after the screen: the spread search of `g2_tier.py` with m on L1's noise scale
alone, for a module built as D1 is, with the factor on the noise of marked rows and none on
the unit's process.

On the held-out ads the guarded `income_restricted_v2` marks, the script multiplies each
draw's noise scale by m and leaves the sd of the unit's part as drawn, rescoring on the
48-node grid of `common.Draws`. m is picked by halves of the buildings as in `g2_tier.py`,
and the SE is clustered by building over all held-out ads. The script also gives the share
of these ads whose unit has a training row, the mean over the draws of the unit part's
variance and of the noise's squared scale, and the share of draws with nu below 2, where the
noise has no variance. Results go to `OUT/g3_noise.json`.

    systemd-run --user --scope -q -p MemoryMax=3G python g3_noise.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "causal-screens-2026-11-13")
)
import common as c  # noqa: E402

COPY = Path(
    "/data1/apartments/frontier/datasets/"
    "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-textflags"
)
OUT = Path("/data1/apartments/tmp/income-flag-2026-11-14")
SCALES = (1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 2.0, 2.5, 3.0, 3.5, 4.0)


def se_sum(x, b):
    """Building-clustered SE of sum(x), with x demeaned over all its entries."""
    x = np.asarray(x, float)
    t = pd.Series(x - x.mean()).groupby(np.asarray(b)).sum()
    g = len(t)
    return float(np.sqrt(g / (g - 1) * (t**2).sum()))


def lpd_noise(dr, idx, m):
    """Log predictive density of the held-out ads `idx` with each draw's noise scale times
    m and the unit's sd as drawn."""
    s = dr.sig[:, dr.grp[idx]] * dr.fac[:, dr.ph[idx]] * m
    usd = dr.usd[:, idx]
    var = usd[:, :, None] ** 2 + (s.astype(np.float32) ** 2)[:, :, None] * dr.ilam
    dev = (dr.y[idx][None, :] - dr.loc[:, idx])[:, :, None]
    lp = dr.logw - 0.5 * (np.log(var) + dev * dev / var)
    mx = lp.max(axis=2, keepdims=True)
    lp = (mx[:, :, 0] + np.log(np.exp(lp - mx).sum(axis=2))).astype(np.float64)
    return (
        np.logaddexp.reduce(lp, axis=0) - np.log(lp.shape[0]) - 0.5 * np.log(2 * np.pi)
    )


d = pd.read_parquet(
    COPY / "rows.parquet",
    columns=["listing_id", "building", "unit_id", "income_restricted_v2"],
)
d["listing_id"] = d.listing_id.astype(str)
d["held"] = np.load(c.RUN + "pred_scores.npz", allow_pickle=True)["heldout"]
d["ukey"] = np.where(
    d.unit_id.isna(),
    "row:" + d.listing_id,
    d.building.astype(str) + "|" + d.unit_id.astype(str),
)
h = c.heldout(d)
idx = np.flatnonzero(h.income_restricted_v2.to_numpy().astype(bool))
fold = h.fold.to_numpy()[idx]
b_all = h.building.to_numpy()
dr = c.Draws()
base = lpd_noise(dr, idx, 1.0)
gains = {m: lpd_noise(dr, idx, m) - base for m in SCALES}
picked, per = {}, np.zeros(len(idx))
for f in (0, 1):
    tot = {m: float(g[fold != f].sum()) for m, g in gains.items()}
    picked[f] = max(tot, key=tot.get)
    per[fold == f] = gains[picked[f]][fold == f]
x = np.zeros(len(h))
x[idx] = per
tr = d[~d.held.values]
noise = (dr.sig[:, dr.grp[idx]] * dr.fac[:, dr.ph[idx]]) ** 2
res = {
    "ads": len(idx),
    "grid_total": {str(m): float(g.sum()) for m, g in gains.items()},
    "picked": {str(f): picked[f] for f in (0, 1)},
    "gain": float(per.sum()),
    "se": se_sum(x, b_all),
    "unit_has_training_row": float(h.iloc[idx].ukey.isin(tr.ukey).mean()),
    "mean_unit_var": float((dr.usd[:, idx] ** 2).mean()),
    "mean_noise_scale_sq": float(noise.mean()),
    "nu_below_2": float((dr.nu < 2).mean()),
    "nu_median": float(np.median(dr.nu)),
}
print(json.dumps(res, indent=1), flush=True)
json.dump(res, open(OUT / "g3_noise.json", "w"), indent=1)
