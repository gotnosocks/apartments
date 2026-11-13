"""S7, part D: how much would a wider predictive for duplex ads gain on L1?

Part C found duplex ads with about twice the squared gap of other ads, whatever the
building's size and whether or not the previous ad matched. Here I multiply L1's noise scale
and unit sd for duplex ads by m, for m on a grid, and rescore its predictive with
`common.Draws`. I pick m on one half of the buildings and score the other half, both ways. A
control runs the same search on 10,000 other held-out ads drawn at random."""

import json

import numpy as np
import pandas as pd

import common as c

GRID = (1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 2.0)
tx = pd.read_parquet(c.OUT + "s7_text.parquet", columns=["listing_id", "dup_unit"])
tx["listing_id"] = tx.listing_id.astype(str)
h = c.heldout()
h["listing_id"] = h.listing_id.astype(str)
h = h.merge(tx, on="listing_id", how="left")
dup = h.dup_unit.fillna(False).astype(bool).to_numpy()
rng = np.random.default_rng(20261113)
groups = {
    "duplex": np.flatnonzero(dup),
    "control": np.sort(rng.choice(np.flatnonzero(~dup), 10_000, replace=False)),
}
dr = c.Draws()
res = {}
for name, idx in groups.items():
    gains = {}
    for m in GRID:
        scale = np.ones(len(h), dtype=np.float32)
        scale[idx] = m
        gains[m] = dr.gain(idx, scale=scale)
    fold = h.fold.to_numpy()[idx]
    b = h.building.to_numpy()[idx]
    picked, per_ad = {}, np.zeros(len(idx))
    for f in (0, 1):
        tot = {m: float(g[fold != f].sum()) for m, g in gains.items()}
        picked[f] = max(tot, key=tot.get)
        per_ad[fold == f] = gains[picked[f]][fold == f]
    res[name] = {
        "n": len(idx),
        "grid_total": {str(m): float(g.sum()) for m, g in gains.items()},
        "picked": picked,
        "crossfit_gain": float(per_ad.sum()),
        "se": float(c.cluster_se(per_ad, b)),
    }
    print(name, json.dumps(res[name]), flush=True)
json.dump(res, open(c.OUT + "s7d.json", "w"), indent=1)
