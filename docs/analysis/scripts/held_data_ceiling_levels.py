"""Scores the as-of columns of held_data_ceiling.py on the old level target, the
static target and their difference (WLS, lot folds), run after its `static` step.
"""

import sys, numpy as np, pandas as pd

sys.path.insert(0, "docs/analysis/scripts")
import held_data_ceiling as h

t, tr, fam, rows, w_rows, n_b, lots = h._static_setup()
folds, groups = h.lot_folds(t["buildings"], lots, np.random.default_rng(h.SEED))
bidx = rows.bidx.to_numpy()
cols = [c for c, f in fam.items() if f in h.AS_OF]
x = h.building_table(tr, bidx, w_rows, n_b, cols)
for name, y, sd2 in (
    ("level", t["level_mean"], t["level_var"]),
    ("static", t["static_mean"], t["static_var"]),
    ("static-minus-level", t["static_mean"] - t["level_mean"], t["static_var"]),
):
    p = h.wls_oof(y, sd2, x, folds)
    print(
        name,
        "sd",
        y.std().round(4),
        "wls as-of explained",
        round(100 * h.r2(y, sd2, p), 2),
    )
for fname in ("coded", "pluto", "predsize"):
    xc = h.building_table(
        tr, bidx, w_rows, n_b, [c for c, f in fam.items() if f == fname]
    )
    for name, y, sd2 in (
        ("level", t["level_mean"], t["level_var"]),
        ("static", t["static_mean"], t["static_var"]),
    ):
        print(fname, name, round(100 * h.r2(y, sd2, h.wls_oof(y, sd2, xc, folds)), 2))
# share of building part varying with time inside buildings
b = rows.assign(bm=t["static_mean"][bidx])
print(
    "row bpart var",
    rows.bpart_mean.var().round(4),
    "within-building var",
    (rows.bpart_mean - b.bm).var().round(4),
)
