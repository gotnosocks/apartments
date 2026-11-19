"""The term scan again on another run's held-out errors and a span of years, from the saved matrix."""

import sys

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.stats import norm

from scan import stats

O = "/data1/apartments/tmp/history-scan"
run, y0, y1, tag = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
d = pd.read_parquet(f"{O}/ads.parquet")
X = sparse.load_npz(f"{O}/X.npz").tocsr()
vocab = pd.read_parquet(f"{O}/terms.parquet", columns=["term"]).term
s = np.load(f"/data1/apartments/frontier/runs/{run}/pred_scores.npz", allow_pickle=True)
sc = pd.DataFrame({"listing_id": s["listing"], "cdf2": s["cdf"]})
f = pd.read_parquet(
    "/data1/apartments/pipeline/datasets/ads-14f9e88d75290a0f.parquet",
    columns=["listing_id", "first_day"],
)
d = d.merge(sc, on="listing_id", how="left").merge(f, on="listing_id", how="left")
assert d.cdf2.notna().all()
d["z"] = norm.ppf(d.cdf2.clip(1e-4, 1 - 1e-4))
yr = pd.to_datetime(d.first_day).dt.year
span = yr.between(y0, y1).to_numpy()
out = pd.DataFrame({"term": vocab})
for h, name in ((0, "a"), (1, "b")):
    k = ((d.half == h).to_numpy()) & span
    bld = pd.factorize(d.building[k])[0]
    n, nb, m, tt, lo = stats(
        X[k].tocsc(), d.z[k].to_numpy(), (d.cdf2[k] < 0.05).to_numpy(), bld
    )
    for c, v in (("n", n), ("bld", nb), ("dz", m), ("t", tt), ("low", lo)):
        out[f"{c}_{name}"] = v
    print(f"half {name}: ads {k.sum()}, low share {(d.cdf2[k] < 0.05).mean():.4f}")
out.to_parquet(f"{O}/terms-{tag}.parquet")
ok = out[(out.bld_a >= 40) & (out.bld_b >= 40)]
print(
    "terms with 40 buildings in both halves",
    len(ok),
    "corr of t",
    np.corrcoef(ok.t_a, ok.t_b)[0, 1].round(3),
)
pd.set_option("display.width", 200)
lo_ = ok[(ok.t_a < -3) & (ok.t_b < -2)].sort_values("t_a")
hi_ = ok[(ok.t_a > 3) & (ok.t_b > 2)].sort_values("t_a", ascending=False)
print(f"\n== asked below, replicated: {len(lo_)} of {(ok.t_a < -3).sum()}")
print(lo_.round(3).head(70).to_string(index=False))
print(f"\n== asked above, replicated: {len(hi_)} of {(ok.t_a > 3).sum()}")
print(
    hi_.round(3)
    .head(int(sys.argv[5]) if len(sys.argv) > 5 else 70)
    .to_string(index=False)
)
