"""S12, part B's lister check: does the sum of each code's two terms move toward zero with a
fixed effect for the lister, the building, or the building and lister together?

The script reads `b_between.py`'s held-out ads, takes each ad's lister from its last stored
record, adds each code's contribution back into L1's gap as `b_between.py` does, and
regresses that on the code and its unit mean after demeaning within each group, with SEs
clustered by building."""

import json
import os
import sys

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import scipy.sparse as sp

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "causal-screens-2026-11-13"))
import common as c  # noqa: E402

CODES = [
    "ad:private_outdoor_roof_rights",
    "ad:feat_hardwood_floors",
    "ad:fireplace_decorative",
    "ad:views_city",
    "ad:private_outdoor_balcony",
    "ad:views_park",
]
SUPER = "bld:amen_live_in_super"


def ols(y, X, cluster):
    """Least squares of y on X with no intercept, and the covariance clustered by
    `cluster`."""
    Ai = np.linalg.pinv(X.T @ X)
    b = Ai @ (X.T @ y)
    e = y - X @ b
    g = pd.factorize(cluster)[0]
    S = pd.DataFrame(X * e[:, None]).groupby(g).sum().to_numpy()
    n, k, m = len(y), X.shape[1], S.shape[0]
    V = Ai @ (S.T @ S) @ Ai * m / (m - 1) * (n - 1) / (n - k)
    return b, V


def demean(A, key):
    """Each column of A less its mean within each value of `key`."""
    g = pd.factorize(key)[0]
    G = sp.csr_matrix((np.ones(len(g)), (g, np.arange(len(g)))))
    n = np.asarray(G.sum(axis=1)).ravel()
    return A - (G @ A / n[:, None])[g]


h = pd.read_parquet(c.OUT + "s12b_heldout.parquet")
want = set(h.listing_id.astype(str))
last = {}
f = pq.ParquetFile(c.RECS)
for i in range(f.metadata.num_row_groups):
    g = f.read_row_group(i, columns=["listing_id", "last_collected_at", "lister"])
    g = g.to_pandas()
    g = g[g.listing_id.astype(str).isin(want)]
    for lid, t, who in zip(g.listing_id.astype(str), g.last_collected_at, g.lister):
        if lid not in last or t > last[lid][0]:
            last[lid] = (t, who)
lister = h.listing_id.astype(str).map(lambda v: last.get(v, (0, None))[1])
h["lister"] = lister.fillna("na").astype(str).to_numpy()
del last
med = {k: v / 100 for k, v in json.load(open(c.OUT + "s12b.json"))["medians"].items()}
groups = {
    "none": np.zeros(len(h)),
    "lister": h.lister.to_numpy(),
    "building": h.building.astype(str).to_numpy(),
    "building_lister": (h.building.astype(str) + "|" + h.lister).to_numpy(),
}
cluster = h.building.astype(str).to_numpy()
out = {
    "heldout": len(h),
    "listers": int(h.lister.nunique()),
    "no_lister": round(float((h.lister == "na").mean()), 4),
}
for k in [*CODES, SUPER]:
    own = [k] if k == SUPER else [k, "umean:" + k]
    r = h.gap.to_numpy() + sum(med[v] * h[v].to_numpy() for v in own)
    X = h[own].to_numpy(float)
    res = {}
    for name, key in groups.items():
        if k == SUPER and name != "none" and name != "lister":
            continue
        A = demean(np.column_stack([r, X]), key)
        b, V = ols(A[:, 0], A[:, 1:], cluster)
        res[name] = [round(100 * b.sum(), 3), round(100 * np.sqrt(V.sum()), 3)]
    out[k] = res
    print(k, res, flush=True)
json.dump(out, open(c.OUT + "s12f.json", "w"), indent=1)
h[["listing_id", "lister"]].to_parquet(c.OUT + "s12f_lister.parquet")
