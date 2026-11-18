"""Free check: an ad's coded counts against the earlier training ads of its apartment (first, lowest, highest), on ads with and without a mark against the previous ad."""

import numpy as np, pandas as pd, pyarrow.parquet as pq
from scipy.stats import norm
from rentfrontier import drift_building_bedtext_layout as M

OUT = "/data1/apartments/tmp/low-outliers-2026-11-18/"
d = np.load(
    "/data1/apartments/frontier/runs/drift-building-b0-latest-67d14e17-b9/pred_scores.npz",
    allow_pickle=True,
)
fr = pd.read_parquet(
    "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-bedtext/rows.parquet",
    columns=[
        "listing_id",
        "building",
        "unit_id",
        "price_at",
        "bedrooms",
        "full_baths",
        "half_baths",
        "income_restricted",
    ],
)
held = d["heldout"]
assert (fr.listing_id[held].to_numpy() == d["listing"]).all()
marks = M.changes(fr, ~held) > 0
lay = marks.any(1)
c = M.counts(fr)
c["key"] = (
    fr.building.astype(str)
    + "|"
    + fr.unit_id.astype(str).str.replace(M.PIECE, "", regex=True)
).to_numpy()
c["day"] = pd.to_datetime(fr.price_at, utc=True).dt.normalize().to_numpy()
c["row"] = np.arange(len(c))
known = fr.unit_id.notna().to_numpy()
hk = c[held & known]
tr = c[~held & known & c.key.isin(set(hk.key)).to_numpy()]
j = hk.merge(tr, on="key", suffixes=("", "_t"))
j = j[j.day_t < j.day].sort_values("day_t", kind="stable")
g = (
    j.groupby("row")
    .agg(
        first_beds=("beds_t", "first"),
        min_beds=("beds_t", "min"),
        max_beds=("beds_t", "max"),
        first_baths=("baths_t", "first"),
        min_baths=("baths_t", "min"),
        max_baths=("baths_t", "max"),
    )
    .reindex(np.arange(len(c)))
)
beds, baths = c.beds.to_numpy(), c.baths.to_numpy()
raw = {}
with np.errstate(invalid="ignore"):
    for w in ("first", "min", "max"):
        raw[f"beds above {w}"] = beds > g[f"{w}_beds"].to_numpy()
        raw[f"beds below {w}"] = beds < g[f"{w}_beds"].to_numpy()
        raw[f"baths above {w}"] = baths > g[f"{w}_baths"].to_numpy()
        raw[f"baths below {w}"] = baths < g[f"{w}_baths"].to_numpy()
cols = {"marked vs previous": lay}
for k, v in raw.items():
    cols[k + ", all"] = v
    cols[k + ", unmarked"] = v & ~lay
h = fr[held].reset_index(drop=True)
qs = list(d["quantiles"])
h["gap"] = d["y"] - d["pred"]
h["cdf"] = d["cdf"]
h["z"] = np.clip(
    h.gap
    / ((d["q"][:, qs.index(0.75)] - d["q"][:, qs.index(0.25)]) / (2 * norm.ppf(0.75))),
    -6,
    6,
)
half = pd.read_parquet(OUT + "held_b9.parquet", columns=["listing_id", "half"])
half["listing_id"] = half.listing_id.astype(h.listing_id.dtype)
h = h.merge(half, on="listing_id", how="left", validate="1:1")
keep = ~h.income_restricted.fillna(False).to_numpy(bool)
rng = np.random.default_rng(20261118)


def cv(z, x, fold):
    pred = np.empty_like(z)
    for k in range(5):
        tr = fold != k
        A = np.c_[np.ones(tr.sum()), x[tr]]
        b = np.linalg.lstsq(A, z[tr], rcond=None)[0]
        pred[~tr] = b[0] + b[1] * x[~tr]
    return 1 - ((z - pred) ** 2).sum() / ((z - z.mean()) ** 2).sum()


for name in ("read", "unread"):
    m = keep & (h.half == name).to_numpy()
    u = h[m].reset_index(drop=True)
    b = u.building.unique()
    fold = u.building.map(
        dict(zip(b, rng.permutation(np.arange(len(b)) % 5)))
    ).to_numpy()
    z = u.z.to_numpy()
    lo, ct, hi = (
        (u.cdf < 0.01).to_numpy(),
        ((u.cdf > 0.25) & (u.cdf < 0.75)).to_numpy(),
        (u.cdf > 0.99).to_numpy(),
    )
    print(name, len(u))

    def cvm(X):
        pred = np.empty_like(z)
        for k in range(5):
            tr = fold != k
            A = np.c_[np.ones(len(z)), X]
            pred[~tr] = A[~tr] @ np.linalg.lstsq(A[tr], z[tr], rcond=None)[0]
        return 1 - ((z - pred) ** 2).sum() / ((z - z.mean()) ** 2).sum()

    prev = marks[held][m].astype(float)
    ends = np.column_stack(
        [
            raw[k][held][m]
            for k in (
                "beds above min",
                "beds below max",
                "baths above min",
                "baths below max",
            )
        ]
    ).astype(float)
    first = np.column_stack(
        [
            raw[k][held][m]
            for k in (
                "beds above first",
                "beds below first",
                "baths above first",
                "baths below first",
            )
        ]
    ).astype(float)
    for label, X in {
        "previous-ad marks": prev,
        "lowest and highest earlier counts": ends,
        "first earlier counts": first,
        "previous and lowest/highest": np.c_[prev, ends],
    }.items():
        n95 = np.quantile([cvm(X[rng.permutation(len(z))]) for _ in range(40)], 0.95)
        print(f"  joint {label:36s} expl {cvm(X):+.5f} null95 {n95:.5f}")
    for k, v in cols.items():
        f = v[held][m]
        x = f.astype(float)
        if f.sum() < 30:
            print(f"  {k:22s} n {f.sum()}")
            continue
        e = cv(z, x, fold)
        n95 = np.quantile([cv(z, rng.permutation(x), fold) for _ in range(100)], 0.95)
        print(
            f"  {k:22s} n {f.sum():6d} below {100 * f[lo].mean():5.1f} ctl {100 * f[ct].mean():5.1f} above {100 * f[hi].mean():5.1f} gap {u.gap[f].mean():+.4f} other {u.gap[~f].mean():+.4f} expl {e:+.5f} null95 {n95:.5f} {'pass' if e > max(0, n95) else 'fail'}"
        )
