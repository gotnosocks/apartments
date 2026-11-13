"""S12, part A's follow-up: which difference between L1 and a first difference of a unit's
ads turns the sign of the six own terms?

The script reads L1's training ads of units with a `unit_id`, takes the market's move out of
each log ask with quarter effects from M0's pairs, and estimates each code's coefficient five
ways (E1 to E5 in the note): every consecutive pair, long differences against the unit's
first ad, a fixed effect for each unit with the code alone and with L1's past mean beside
it, and a fixed effect for each building with the code and the past mean. E6 to E8 add a
trend in years for each unit, then a slope common to every unit, then the ad's number."""

import json
import os
import sys

import numpy as np
import pandas as pd
import scipy.sparse as sp

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "causal-screens-2026-11-13"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "frontier", "src"))
import common as c  # noqa: E402
from rentfrontier.building_zones_kitchen_sink import past_means  # noqa: E402

CODES = {
    "ad:fireplace_wood": "fireplace:WOOD",
    "ad:private_outdoor_patio": "private_outdoor:PATIO",
    "ad:feat_fireplace": "feat:FIREPLACE",
    "ad:views_water": "views:WATER",
    "ad:feat_private_outdoor_space": "feat:PRIVATE_OUTDOOR_SPACE",
    "ad:feat_hardwood_floors": "feat:HARDWOOD_FLOORS",
}
AD = ["unstated", "feed", "owner", "photos_l", "plan"]


def ols(y, X, names, cluster):
    """Least squares of y on the columns of X (dense or sparse), with SEs clustered by
    `cluster`."""
    A = X.T @ X
    A = A.toarray() if sp.issparse(A) else A
    Ai = np.linalg.pinv(A)
    b = Ai @ (X.T @ y)
    e = y - X @ b
    g = pd.factorize(cluster)[0]
    G = sp.csr_matrix((np.ones(len(g)), (g, np.arange(len(g)))))
    Xe = X.multiply(e[:, None]) if sp.issparse(X) else X * e[:, None]
    S = G @ Xe
    S = S.toarray() if sp.issparse(S) else S
    n, k, m = len(y), np.linalg.matrix_rank(A), G.shape[0]
    adj = m / (m - 1) * (n - 1) / (n - k)
    se = np.sqrt(np.diag(Ai @ (S.T @ S) @ Ai) * adj)
    return pd.DataFrame({"b": b, "se": se}, index=names)


def demean(A, g):
    """Each column of A less its mean over the rows of each group in `g`."""
    G = sp.csr_matrix((np.ones(len(g)), (g, np.arange(len(g)))))
    n = np.asarray(G.sum(axis=1)).ravel()
    return A - (G @ A / n[:, None])[g]


def cells(v, prefix):
    """0/1 columns for each value of `v` but its most common."""
    v = pd.Series(np.asarray(v))
    ref = v.mode().iloc[0]
    return pd.DataFrame(
        {
            f"{prefix}{u}": (v == u).to_numpy(float)
            for u in sorted(v.unique())
            if u != ref
        }
    )


def report(res, extra=()):
    return {
        k: [round(100 * res.b[k], 3), round(100 * res.se[k], 3)]
        for k in [*CODES, *extra]
        if k in res.index
    }


d = c.rows()
d = d[~d.held & d.unit_id.notna()]
d = d[
    [
        "listing_id",
        "building",
        "ukey",
        "priced",
        "price_at",
        "latest_ask",
        "bedrooms",
        "full_baths",
    ]
].reset_index(drop=True)
ids = pd.Index(d.listing_id.astype(str))
t = pd.read_parquet(
    "/data1/apartments/external/listing-codes/20261023-ks/listing-codes.parquet",
    columns=[
        "listing_id",
        "source_type",
        "photos",
        "floorplans",
        "states_features",
        *CODES.values(),
    ],
)
t["row"] = ids.get_indexer(t.listing_id.astype(str))
t = t[t.row >= 0].drop(columns="listing_id").drop_duplicates("row")
t = t.set_index("row").reindex(np.arange(len(d))).reset_index(drop=True)
d = pd.concat([d, t], axis=1)
del t
for col, code in CODES.items():
    d[col] = d[code].fillna(0).astype(float)
d = d.drop(columns=list(CODES.values()))
src = d.source_type.astype(object)
d["unstated"] = 1.0 - d.states_features.fillna(0).astype(float)
d["feed"] = (src == "FEED").astype(float)
d["owner"] = (src == "OWNER").astype(float)
d["photos_l"] = np.log1p(d.photos.fillna(0).astype(float))
d["plan"] = (d.floorplans.fillna(0) > 0).astype(float)
d["y"] = np.log(d.latest_ask.astype(float))
d["quarter"] = d.priced.dt.to_period("Q").astype(str)
d["beds"] = np.minimum(d.bedrooms.fillna(-1), 5).astype(int).astype(str)
d["baths"] = np.minimum(d.full_baths.fillna(-1), 3).astype(int).astype(str)

# L1's past mean: over the ad itself and its unit's training ads priced on earlier days.
group = pd.factorize(d.ukey)[0].astype(np.int64)
x = d[list(CODES)].to_numpy(float)
past = past_means(x, group, d.price_at, np.ones(len(d), bool))
MEANS = ["umean:" + k for k in CODES]
d[MEANS] = past
d = d.sort_values(["ukey", "priced", "listing_id"]).reset_index(drop=True)
group = pd.factorize(d.ukey)[0].astype(np.int64)
bgroup = pd.factorize(d.building)[0].astype(np.int64)
cluster = d.building.astype(str).to_numpy()

# The market's move: quarter effects from M0's pairs, as in `a_within.py`.
same = d.ukey.eq(d.ukey.shift()) & d.bedrooms.eq(d.bedrooms.shift())
same &= d.full_baths.eq(d.full_baths.shift())
prev = d.shift()
quarters = sorted(d.quarter.unique())
qi = {q: i for i, q in enumerate(quarters)}
li = d.quarter.map(qi).to_numpy()
ei = prev.quarter.map(qi).to_numpy()
ok = same.to_numpy()
n_ok = int(ok.sum())
Q = sp.csr_matrix(
    (
        np.r_[np.ones(n_ok), -np.ones(n_ok)],
        (
            np.r_[np.arange(n_ok), np.arange(n_ok)],
            np.r_[li[ok], ei[ok].astype(int)],
        ),
    ),
    shape=(n_ok, len(quarters)),
)[:, 1:]
diff = (
    d.loc[ok, [*CODES, *AD]].to_numpy() - prev.loc[ok, [*CODES, *AD]].to_numpy()
).astype(float)
X = sp.hstack([sp.csr_matrix(np.ones((n_ok, 1))), sp.csr_matrix(diff), Q]).tocsr()
names = ["const", *CODES, *AD, *quarters[1:]]
m0 = ols((d.y - prev.y).to_numpy()[ok], X, names, cluster[ok])
index = np.r_[0.0, m0.b[quarters[1:]].to_numpy()]
d["ya"] = d.y - index[d.quarter.map(qi).to_numpy()]
out = {"M0": report(m0), "ads": len(d), "units": int(group.max() + 1)}
print("M0", out["M0"], flush=True)

# E1: every consecutive pair of a unit's ads, with indicators for a change of layout.
pair = d.ukey.eq(d.ukey.shift()).to_numpy()
prev = d.shift()
D1 = pd.DataFrame(
    d.loc[pair, [*CODES, *AD]].to_numpy() - prev.loc[pair, [*CODES, *AD]].to_numpy(),
    columns=[*CODES, *AD],
)
D1["beds_changed"] = d.bedrooms.ne(prev.bedrooms)[pair].to_numpy(float)
D1["baths_changed"] = d.full_baths.ne(prev.full_baths)[pair].to_numpy(float)
D1.insert(0, "const", 1.0)
e1 = ols(
    (d.ya - prev.ya).to_numpy()[pair], D1.to_numpy(), list(D1.columns), cluster[pair]
)
out["E1"] = report(e1, ["beds_changed", "baths_changed"])
out["E1_pairs"] = int(pair.sum())
print("E1", out["E1"], flush=True)

# E2: each ad against the first ad of its unit with the same bedrooms and full baths.
chain = d.ukey + "|" + d.beds + "|" + d.baths
later = chain.duplicated().to_numpy()
start = pd.Series(np.arange(len(d))).groupby(chain.to_numpy()).transform("first")
start = start.to_numpy()
cols = [*CODES, *AD]
D2 = pd.DataFrame(
    d[cols].to_numpy()[later] - d[cols].to_numpy()[start[later]], columns=cols
)
D2.insert(0, "const", 1.0)
e2 = ols(
    (d.ya.to_numpy()[later] - d.ya.to_numpy()[start[later]]),
    D2.to_numpy(),
    list(D2.columns),
    cluster[later],
)
out["E2"] = report(e2)
out["E2_pairs"] = int(later.sum())
print("E2", out["E2"], flush=True)

# E3 to E5: fixed effects by unit, then by building.
lay = pd.concat([cells(d.beds, "beds:"), cells(d.baths, "baths:")], axis=1)
base = pd.concat([d[[*CODES, *AD]].reset_index(drop=True), lay], axis=1)
multi = np.bincount(group)[group] > 1
for key, frame, g, rows in (
    ("E3", base, group, multi),
    ("E4", pd.concat([base, d[MEANS].reset_index(drop=True)], axis=1), group, multi),
    (
        "E5",
        pd.concat([base, d[MEANS].reset_index(drop=True)], axis=1),
        bgroup,
        np.ones(len(d), bool),
    ),
):
    gr = pd.factorize(g[rows])[0]
    A = demean(frame.to_numpy(float)[rows], gr)
    yv = demean(d.ya.to_numpy()[rows, None], gr).ravel()
    res = ols(yv, A, list(frame.columns), cluster[rows])
    out[key] = report(res, MEANS)
    if key != "E3":
        out[key + "_sum"] = {
            k: round(100 * (res.b[k] + res.b["umean:" + k]), 3) for k in CODES
        }
    print(key, out[key], flush=True)


def detrend(A, g, t):
    """Each column of A less its least-squares line in `t` over the rows of each group in
    `g`, or less its mean where the group's `t` does not vary."""
    G = sp.csr_matrix((np.ones(len(g)), (g, np.arange(len(g)))))
    n = np.asarray(G.sum(axis=1)).ravel()
    st, stt = G @ t, G @ (t * t)
    sa, sta = G @ A, G @ (A * t[:, None])
    den = stt - st**2 / n
    slope = np.where(
        (den > 1e-9)[:, None], (sta - st[:, None] * sa / n[:, None]) / den[:, None], 0.0
    )
    level = (sa - slope * st[:, None]) / n[:, None]
    return A - level[g] - slope[g] * t[:, None]


# E3 by the unit's number of ads.
count = np.bincount(group)[group]
for name, rows in (
    ("E3_n2", count == 2),
    ("E3_n3_4", (count >= 3) & (count <= 4)),
    ("E3_n5", count >= 5),
):
    gr = pd.factorize(group[rows])[0]
    A = demean(base.to_numpy(float)[rows], gr)
    yv = demean(d.ya.to_numpy()[rows, None], gr).ravel()
    out[name] = report(ols(yv, A, list(base.columns), cluster[rows]))
    out[name + "_ads"] = int(rows.sum())
    print(name, out[name], flush=True)

# E6: E3 with a linear trend in years for each unit.
years = (
    d.priced - d.groupby("ukey").priced.transform("min")
).dt.days.to_numpy() / 365.25
gr = pd.factorize(group[multi])[0]
A = detrend(base.to_numpy(float)[multi], gr, years[multi])
yv = detrend(d.ya.to_numpy()[multi, None], gr, years[multi]).ravel()
out["E6"] = report(ols(yv, A, list(base.columns), cluster[multi]))
print("E6", out["E6"], flush=True)

# E7 and E8: E3 with a slope in years common to every unit, then with the ad's number too.
number = d.groupby("ukey").cumcount().to_numpy(float)
for key, extra in (
    ("E7", {"years": years}),
    ("E8", {"years": years, "ad_number": number}),
):
    frame = pd.concat([base, pd.DataFrame(extra)], axis=1)
    A = demean(frame.to_numpy(float)[multi], gr)
    yv = demean(d.ya.to_numpy()[multi, None], gr).ravel()
    res = ols(yv, A, list(frame.columns), cluster[multi])
    out[key] = report(res, list(extra))
    print(key, out[key], flush=True)
json.dump(out, open(c.OUT + "s12a2.json", "w"), indent=1)
