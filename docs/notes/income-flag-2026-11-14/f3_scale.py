"""S15, part 3 (not in the predictions): a wider predictive for the held-out ads
`income_restricted_v2` marks, as S7 and S14 widened duplexes and penthouses.

L1's 80% interval covers about 0.57 of these ads in `f1_screen.py`. With L1's locations as
they are, the script multiplies L1's noise scale and unit sd for the marked ads by m on a
grid, picks m on one half of the buildings and scores it on the other, both ways, with
`common.Draws`. A null runs the same search on as many held-out ads drawn at random from
those neither flag marks. SEs are clustered by building as in `f1_screen.py`. Results go to
`OUT/f3_scale.json`.

    systemd-run --user --scope -q -p MemoryMax=3G python f3_scale.py
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
GRID = (1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 2.0, 2.5, 3.0)


def se_sum(x, b):
    """Building-clustered SE of sum(x), with x demeaned over all its entries."""
    x = np.asarray(x, float)
    t = pd.Series(x - x.mean()).groupby(np.asarray(b)).sum()
    g = len(t)
    return float(np.sqrt(g / (g - 1) * (t**2).sum()))


d = pd.read_parquet(
    COPY / "rows.parquet",
    columns=["listing_id", "building", "income_restricted", "income_restricted_v2"],
)
d["listing_id"] = d.listing_id.astype(str)
d["held"] = np.load(c.RUN + "pred_scores.npz", allow_pickle=True)["heldout"]
h = c.heldout(d)
new = h.income_restricted_v2.to_numpy().astype(bool)
old = h.income_restricted.to_numpy().astype(bool)
rng = np.random.default_rng(20261114)
groups = {
    "new flag": np.flatnonzero(new),
    "null": np.sort(rng.choice(np.flatnonzero(~new & ~old), new.sum(), replace=False)),
}
dr = c.Draws()
b_all = h.building.to_numpy()
res = {}
for name, idx in groups.items():
    gains = {}
    for m in GRID:
        scale = np.ones(len(h), dtype=np.float32)
        scale[idx] = m
        gains[m] = dr.gain(idx, scale=scale)
    fold = h.fold.to_numpy()[idx]
    picked, per = {}, np.zeros(len(idx))
    for f in (0, 1):
        tot = {m: float(g[fold != f].sum()) for m, g in gains.items()}
        picked[f] = max(tot, key=tot.get)
        per[fold == f] = gains[picked[f]][fold == f]
    x = np.zeros(len(h))
    x[idx] = per
    res[name] = {
        "ads": len(idx),
        "in80": float(h.in80.to_numpy()[idx].mean()),
        "grid_total": {str(m): float(g.sum()) for m, g in gains.items()},
        "picked": picked,
        "gain": float(per.sum()),
        "se": se_sum(x, b_all),
        "se_within": se_sum(per, b_all[idx]),
    }
    if name == "new flag":
        for part, on in (("both", old[idx]), ("new only", ~old[idx])):
            y = np.zeros(len(h))
            y[idx[on]] = per[on]
            res[name][part] = {
                "ads": int(on.sum()),
                "in80": float(h.in80.to_numpy()[idx][on].mean()),
                "gain": float(per[on].sum()),
                "se": se_sum(y, b_all),
            }
    print(name, json.dumps(res[name]), flush=True)
json.dump(res, open(OUT / "f3_scale.json", "w"), indent=1)
