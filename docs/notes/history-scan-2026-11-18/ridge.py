"""Ridge of the held-out normal score on text terms: fit on half A, scored on half B."""

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.sparse.linalg import lsqr
from scipy.stats import norm

O = "/data1/apartments/tmp/history-scan"
d = pd.read_parquet(f"{O}/ads.parquet")
X = sparse.load_npz(f"{O}/X.npz").tocsr()
t = pd.read_parquet(f"{O}/terms.parquet")
a = (d.half == 0).to_numpy()
b = ~a
z = d.z.to_numpy()
# Inner split of half A by building, to choose the penalty.
inner = pd.util.hash_pandas_object(d.building, index=False).to_numpy() % 5 == 0
fit, val = a & ~inner, a & inner


def ridge(rows, damp):
    mu = z[rows].mean()
    w = lsqr(X[rows], z[rows] - mu, damp=damp, iter_lim=400)[0]
    return mu, w


def r2(rows, mu, w):
    p = mu + X[rows] @ w
    return 1 - ((z[rows] - p) ** 2).sum() / ((z[rows] - z[rows].mean()) ** 2).sum()


best = None
for damp in (10, 20, 40, 80, 160):
    mu, w = ridge(fit, damp)
    v = r2(val, mu, w)
    print(f"damp {damp}: inner R2 {v:.4f}", flush=True)
    if best is None or v > best[1]:
        best = (damp, v)
mu, w = ridge(a, best[0])
p = mu + X @ w
print(
    f"penalty {best[0]}: R2 on half B {r2(b, mu, w):.4f}, sd of z on B {z[b].std():.3f}, sd of the text score on B {p[b].std():.3f}"
)
print("corr on B", np.corrcoef(p[b], z[b])[0, 1].round(4))
# Tails on B before and after taking the text score off z.
adj = z - (p - p[b].mean())
lowcut = norm.ppf(0.05)
low = z < lowcut
print(
    f"B: asked below the 5% point {low[b].sum()}; of them still below after the text score {(low & (adj < lowcut))[b].sum()}; newly below {(~low & (adj < lowcut))[b].sum()}"
)
q = pd.qcut(p[b], 10, labels=False)
g = (
    pd.DataFrame({"q": q, "z": z[b], "low": low[b], "high": (z > -lowcut)[b]})
    .groupby("q")
    .agg(
        n=("z", "size"),
        mean_z=("z", "mean"),
        low=("low", "mean"),
        high=("high", "mean"),
    )
)
print(g.round(3).to_string())
d["text_score"] = p
d.to_parquet(f"{O}/ads-scored.parquet")
t["w"] = w
t.to_parquet(f"{O}/terms-w.parquet")
