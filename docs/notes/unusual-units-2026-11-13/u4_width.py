"""S14, part 4: how wide L1's own 80% interval already is for each mark's held-out ads.

For the marks of `u2_scatter.py` the script reads, against the same rest:

1. the mean width of L1's 80% interval, on and off the mark;
2. the clipped squared gap over the squared width, ad by ad, so that a mark whose ads scatter
   wider only where L1's interval is already wider comes out near the rest. The difference
   has an SE clustered by building."""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "causal-screens-2026-11-13")
)
import common as c  # noqa: E402

OUT = c.OUT + "unusual-units/"

tx = pd.read_parquet(
    OUT + "u1_text.parquet", columns=["listing_id", "pen", "gar", "town", "pen_text"]
)
dup = pd.read_parquet(c.OUT + "s7_text.parquet", columns=["listing_id", "dup_unit"])
dup["listing_id"] = dup.listing_id.astype(str)
d = c.rows()
d["listing_id"] = d.listing_id.astype(str)
d = d.merge(tx, on="listing_id", how="left").merge(dup, on="listing_id", how="left")
d = d.rename(columns={"dup_unit": "dup"})
for k in ("pen", "gar", "town", "pen_text", "dup"):
    d[k] = d[k].fillna(False).astype(bool)
h = c.heldout(d)
w = (h.hi - h.lo).to_numpy()
rel = h.gap.clip(-0.4, 0.4).to_numpy() ** 2 / w**2
b = h.building.to_numpy()
mk = {k: h[k].to_numpy() for k in ("pen", "gar", "town", "pen_text", "dup")}
nodup = ~mk["dup"]
groups = {k: (mk[k], ~mk[k]) for k in ("pen", "gar", "town", "dup")}
for k in ("pen", "gar", "town"):
    groups[k + "_nodup"] = (mk[k] & nodup, ~mk[k] & nodup)
groups["pen_text_nodup"] = (mk["pen_text"] & nodup, ~mk["pen"] & nodup)
groups["dup_nopen"] = (mk["dup"] & ~mk["pen"], ~mk["dup"] & ~mk["pen"])
res = {}
for k, (on, rest) in groups.items():
    m = on | rest
    o = on[m]
    res[k] = {
        "n_on": int(o.sum()),
        "width_on": float(w[m][o].mean()),
        "width_off": float(w[m][~o].mean()),
        "rel_on": float(rel[m][o].mean()),
        "rel_off": float(rel[m][~o].mean()),
        "rel_diff": c.cluster_mean_diff(rel[m], o, b[m]),
    }
    print(k, json.dumps(res[k]), flush=True)
json.dump(res, open(OUT + "u4_width.json", "w"), indent=1)
