"""Free check: how many text flags changed since the unit's latest earlier ad, on stored l2bt predictions.

The base and scoring of `docs/notes/text-columns-2026-11-21/j2_text.py`. The marks read the
scan's text flags of the latest record's description of this ad and of the unit's ad
priced just before it in l2bt's dataset, never an ask.
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
OTHER = ["dishwasher", "exposed_brick", "high_ceilings", "view", "no_fee"]
FLAGS = "/data1/apartments/tmp/outlier-sprint/qual/flags.parquet"
DATA = (
    "/data1/apartments/frontier/datasets/"
    "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-bedtext/rows.parquet"
)
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
u = pd.read_parquet(DATA, columns=["listing_id", "unit_id", "price_at"])
u["listing_id"] = u.listing_id.astype(str)
FL = [c for c in pq.read_schema(FLAGS).names if c not in ("listing_id", "desc_len")]
print("text flags", len(FL))
w = pd.read_parquet(FLAGS, columns=["listing_id", *FL])
w["listing_id"] = w.listing_id.astype(str)
w = w.drop_duplicates("listing_id")
u = u.merge(w, on="listing_id", how="left", validate="1:1")
print("dataset ads", len(u), "; no flags row:", u.renovated.isna().sum())
u = u.sort_values(["unit_id", "price_at", "listing_id"]).reset_index(drop=True)
has = u.renovated.notna()
F = u[FL].fillna(False).astype(bool)
P = F.groupby(u.unit_id).shift(1)
prev_has = has.groupby(u.unit_id).shift(1).fillna(False).astype(bool)
ok = has & prev_has
u["nflip"] = (F != P.fillna(False).astype(bool)).sum(axis=1).where(ok)
W = F.renovated | F.gut
pW = W.groupby(u.unit_id).shift(1)
u["switch"] = W & pW.notna() & (pW == False)  # noqa: E712
dw = P.dishwasher.fillna(True).astype(bool)
u["dishwasher on"] = F.dishwasher & ~dw & prev_has
rv = u[["listing_id", "nflip", "switch", "dishwasher on"]]
for t in (fl, dup, mk, rv):
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
print("held-out ads with no flag count:", h.nflip.isna().sum())
print(
    h.nflip.fillna(-1).clip(upper=6).value_counts(normalize=True).sort_index().round(4)
)
T = pd.DataFrame(
    {
        "1 flag changed": h.nflip == 1,
        "2 changed": h.nflip == 2,
        "3+ changed": h.nflip >= 3,
        "switch": h.switch.fillna(False).astype(bool),
        "dishwasher on": h["dishwasher on"].fillna(False).astype(bool),
    }
).astype(float)
print("ads", len(h), "from", Y0)
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
xc = list(X.columns)
CNT = ["1 flag changed", "2 changed", "3+ changed"]
perb, thb, Zb = crossfit(xc, "base: j1's eight kept terms")


def show(th, cols, k0):
    for i, c in enumerate(cols):
        j = k0 + 1 + i
        print(
            f"    {c:16} scale (fit on A, on B) {np.exp(th[1][j]):.3f} {np.exp(th[0][j]):.3f};"
            f" shift {th[1][len(th[1]) // 2 + j]:+.4f} {th[0][len(th[0]) // 2 + j]:+.4f}"
        )


pc, thc, Zc = crossfit(xc + CNT, "base + count marks")
over(pc, perb, "count marks")
show(thc, CNT, len(xc))
for extra in (["switch"], ["switch", "dishwasher on"]):
    pe, the, _ = crossfit(xc + CNT + extra, f"base + count marks + {extra}")
    over(pe, pc, f"{extra} over the count marks")
    show(the, CNT + extra, len(xc))


def cdf(th, Z):
    c = np.empty(len(h))
    kk = Z.shape[1]
    for f in (0, 1):
        te = half == f
        m, d = np.exp(Z[te] @ th[f][:kk]), Z[te] @ th[f][kk:]
        c[te] = student.cdf((res[te] - d) / (S[te] * m), DF)
    return c


low0, low1 = cdf(thb, Zb) < 0.05, cdf(thc, Zc) < 0.05
print(
    f"\nlow tail (below 5%), base {low0.sum()}, base + counts {low1.sum()}, "
    f"left {(low0 & ~low1).sum()}, joined {(~low0 & low1).sum()}"
)
for c in CNT:
    on = T[c].to_numpy() > 0
    print(f"  {c:16} marked {on.sum():6}  low {low0[on].sum():5} -> {low1[on].sum():5}")
