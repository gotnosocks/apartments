"""Free check: five text columns beside the queued base-refit terms, on stored l2bt predictions.

The method and base of `docs/notes/joint-terms-2026-11-21/j1_joint.py`: each held-out
predictive is a Student-t on its median with the scale from its quartiles, every ad's scale
multiplied by exp(a . x) and its centre moved by b . x, a and b fitted on one half of the
buildings and scored on the other. The base is j1's eight kept terms. Each text mark reads
the latest record's description and the coded fields, never the ask.
"""

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.optimize import minimize
from scipy.stats import t as student

HS = "/data1/apartments/tmp/history-scan/baths-l2bt.parquet"
RUN = "drift-building-phase-unitkn-level-bedtext-b0-latest-c1ffaefd-l2bt"
SNAP = "/data1/apartments/external/unit-floor/20261021-d84914c0/floor.parquet"
DUP = (
    "/data1/apartments/frontier/datasets/"
    "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-duplex-penthouse/rows.parquet"
)
MARKS = "/data1/apartments/tmp/large-units/l8_marks.parquet"
FLAGS = "/data1/apartments/tmp/outlier-sprint/qual/flags.parquet"
CODES = "/data1/apartments/external/listing-codes/20261023-ks/listing-codes.parquet"
TEXT = ["private_outdoor", "dishwasher", "furnished", "penthouse", "full_floor"]
CODED = ["feat:PRIVATE_OUTDOOR_SPACE", "feat:DISHWASHER", "feat:FURNISHED"]
Y0 = 2022

h = pd.read_parquet(HS)
h["listing_id"] = h.listing_id.astype(str)
p = np.load(f"/data1/apartments/frontier/runs/{RUN}/pred_scores.npz", allow_pickle=True)
q = p["q"].astype(float)
sc = pd.DataFrame(
    {
        "listing_id": p["listing"].astype(str),
        "elpd": p["elpd"],
        "pred": p["pred"],
        "iqr": q[:, 4] - q[:, 3],
    }
)
h = h.merge(sc, on="listing_id", validate="1:1")
ids = sorted(set(h.listing_id))


def table(path, cols=None):
    t = pq.read_table(
        path, columns=cols, filters=[("listing_id", "in", ids)]
    ).to_pandas()
    t["listing_id"] = t.listing_id.astype(str)
    return t


fl = table(SNAP).drop_duplicates("listing_id")[["listing_id", "floor"]]
dup = (
    table(DUP, ["listing_id", "duplex"])
    .groupby("listing_id", as_index=False)
    .duplex.max()
)
mk = pd.read_parquet(MARKS)[["listing_id", "spec"]]
mk["listing_id"] = mk.listing_id.astype(str)
tx = table(FLAGS, ["listing_id", *TEXT]).drop_duplicates("listing_id")
cd = table(CODES, ["listing_id", *CODED]).groupby("listing_id", as_index=False).max()
for t in (fl, dup, mk, tx, cd):
    h = h.merge(t, on="listing_id", how="left")
g = h.groupby("building").spec
n, s = g.transform("size"), g.transform(lambda v: v.fillna(False).astype(int).sum())
h["share"] = ((s - h.spec.fillna(False).astype(int)) / (n - 1)).where(n >= 4)
h["tier"] = h.groupby("year").pred.transform(lambda x: x.rank(pct=True))
h = h[h.year >= Y0].reset_index(drop=True)

big = h.bd >= 3
X = pd.DataFrame(
    {
        "changed counts": ~h.same,
        "changed, 2 baths": ~h.same & (h.fb == 2),
        "3+ baths": h.fb >= 3,
        "2 baths": h.fb == 2,
        "top 3% predicted": h.tier > 0.97,
        "floor 1": h.floor == 1,
        "duplex": h.duplex.fillna(False).astype(bool),
        "3+ bed, finish share": big * h.share.fillna(0),
    }
).astype(float)
txt = {c: h[c].fillna(False).astype(bool) for c in TEXT}
code = {c: h[c].fillna(0).astype(int) == 1 for c in CODED}
T = pd.DataFrame(
    {
        "outdoor, uncoded": txt["private_outdoor"]
        & ~code["feat:PRIVATE_OUTDOOR_SPACE"],
        "dishwasher, uncoded": txt["dishwasher"] & ~code["feat:DISHWASHER"],
        "furnished, uncoded": txt["furnished"] & ~code["feat:FURNISHED"],
        "penthouse": txt["penthouse"],
        "full floor": txt["full_floor"],
    }
).astype(float)
print("ads", len(h), "from", Y0, "; no text flags row:", h.private_outdoor.isna().sum())
print("no listing-codes row:", h[CODED[0]].isna().sum())
for c in TEXT:
    print(f"  text {c:16} {txt[c].mean():.4f}")
for c in CODED:
    print(f"  coded {c:27} {code[c].mean():.4f}")
print("marked shares:")
print(T.mean().round(4).to_string())

best = None
for dfree in (2, 2.5, 3, 4, 5, 7, 10, 30):
    s0 = h.iqr / (2 * student.ppf(0.75, dfree))
    lp0 = student.logpdf(h.res / s0, dfree) - np.log(s0)
    if best is None or abs(lp0.mean() - h.elpd.mean()) < best[0]:
        best = (abs(lp0.mean() - h.elpd.mean()), dfree, s0.to_numpy())
_, DF, S = best
print("t df", DF)
res, half, bld = h.res.to_numpy(), h.half.to_numpy(), h.building.to_numpy()
base = student.logpdf(res / S, DF) - np.log(S)
ALL = pd.concat([X, T], axis=1)


def lp(theta, Z, idx):
    k = Z.shape[1]
    m = np.exp(Z[idx] @ theta[:k])
    d = Z[idx] @ theta[k:]
    return student.logpdf((res[idx] - d) / (S[idx] * m), DF) - np.log(S[idx] * m)


def cluster_se(x):
    g = pd.Series(x).groupby(bld).sum()
    return float(np.sqrt(len(g) / (len(g) - 1) * ((g - g.mean()) ** 2).sum()))


def crossfit(cols, label):
    Z = np.column_stack([np.ones(len(h))] + [ALL[c].to_numpy() for c in cols])
    per, thetas = np.zeros(len(h)), {}
    for f in (0, 1):
        tr, te = np.flatnonzero(half != f), np.flatnonzero(half == f)
        r = minimize(
            lambda t: -lp(t, Z, tr).sum(), np.zeros(2 * Z.shape[1]), method="L-BFGS-B"
        )
        thetas[f] = r.x
        per[te] = lp(r.x, Z, te) - base[te]
    print(f"\n{label}: cross-fit gain {per.sum():8.1f} (SE {cluster_se(per):5.1f})")
    return per, thetas, Z


def over(per, ref, label):
    d = per - ref
    by = [round(d[half == f].sum(), 1) for f in (0, 1)]
    print(
        f"  {label} over the base: {d.sum():7.1f} (SE {cluster_se(d):5.1f}); by half",
        by,
    )


# thetas[f] is fitted on half != f: thetas[1] on half A (0), thetas[0] on half B (1)
xc, tc = list(X.columns), list(T.columns)
perb, thb, Zb = crossfit(xc, "base: j1's eight kept terms")
for c in tc:
    pc, thc, _ = crossfit(xc + [c], f"base + {c}")
    over(pc, perb, c)
    print(
        f"    scale (fit on A, on B) {np.exp(thc[1][len(xc) + 1]):.3f} "
        f"{np.exp(thc[0][len(xc) + 1]):.3f}; shift {thc[1][-1]:+.4f} {thc[0][-1]:+.4f}"
    )
per5, th5, Z5 = crossfit(xc + tc, "base + all five")
over(per5, perb, "all five")
k = Z5.shape[1]
tab = pd.DataFrame(
    {
        "scale x (fit on A)": np.exp(th5[1][:k]),
        "scale x (fit on B)": np.exp(th5[0][:k]),
        "shift (fit on A)": th5[1][k:],
        "shift (fit on B)": th5[0][k:],
    },
    index=["intercept"] + xc + tc,
).round(4)
print(tab.to_string())


# the low tail, each ad placed under the fit of the other half
def cdf(th, Z):
    c = np.empty(len(h))
    kk = Z.shape[1]
    for f in (0, 1):
        te = half == f
        m, d = np.exp(Z[te] @ th[f][:kk]), Z[te] @ th[f][kk:]
        c[te] = student.cdf((res[te] - d) / (S[te] * m), DF)
    return c


low0, low1 = cdf(thb, Zb) < 0.05, cdf(th5, Z5) < 0.05
print(
    f"\nlow tail (below 5%), base {low0.sum()}, base + five {low1.sum()}, "
    f"left {(low0 & ~low1).sum()}, joined {(~low0 & low1).sum()}"
)
for c in tc:
    on = T[c].to_numpy() > 0
    print(
        f"  {c:20} marked {on.sum():6}  low {low0[on].sum():5} -> {low1[on].sum():5}"
        f"  ({100 * low0[on].mean():4.1f}% -> {100 * low1[on].mean():4.1f}%)"
    )
