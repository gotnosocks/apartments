"""S12, part A: which change between two ads of a unit travels with a code's switch and
lowers the later ask?

The script pairs each training ad of a unit in L1's dataset with the unit's previous training
ad, where both list the same bedrooms and full baths, and regresses the change in log ask on
the change in each of six codes (`ols`, SEs clustered by building). M0 takes a fixed effect
for each quarter, +1 at the later ad's and -1 at the earlier ad's, and the changes in the
ad columns L1 carries beside the codes. Then it adds the channel, the lister, the earlier
ad's ending, both ads' price paths and the form's (year, source) effects, one family at a
time and all at once, and counts how often a switch on coincides with each."""

import json
import os
import sys

import numpy as np
import pandas as pd
import scipy.linalg
import scipy.sparse as sp

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "causal-screens-2026-11-13")
)
import common as c  # noqa: E402

CODES = {
    "ad:fireplace_wood": "fireplace:WOOD",
    "ad:private_outdoor_patio": "private_outdoor:PATIO",
    "ad:feat_fireplace": "feat:FIREPLACE",
    "ad:views_water": "views:WATER",
    "ad:feat_private_outdoor_space": "feat:PRIVATE_OUTDOOR_SPACE",
    "ad:feat_hardwood_floors": "feat:HARDWOOD_FLOORS",
}
L1_OWN = {
    "ad:fireplace_wood": -0.98,
    "ad:private_outdoor_patio": -0.33,
    "ad:feat_fireplace": -0.31,
    "ad:views_water": -0.27,
    "ad:feat_private_outdoor_space": -0.14,
    "ad:feat_hardwood_floors": -0.12,
}
END = {
    "RENTED": "deal",
    "IN_CONTRACT": "deal",
    "NO_LONGER_AVAILABLE": "nla",
    "DELISTED": "delisted",
    "TEMPORARILY_OFF_MARKET": "paused",
}
SOURCES = ("PARTNER", "FEED", "OWNER")


def ols(y, X, names, cluster):
    """Least squares of y on the sparse columns of X, with SEs clustered by `cluster`,
    through a pseudo-inverse so that collinear fixed effects leave the other coefficients
    defined."""
    A = (X.T @ X).toarray()
    Ai = scipy.linalg.pinvh(A)
    b = Ai @ (X.T @ y)
    e = y - X @ b
    g = pd.factorize(cluster)[0]
    G = sp.csr_matrix((np.ones(len(g)), (g, np.arange(len(g)))))
    S = (G @ sp.csr_matrix(X.multiply(e[:, None]))).toarray()
    n, k, m = len(y), np.linalg.matrix_rank(A), G.shape[0]
    adj = m / (m - 1) * (n - 1) / (n - k)
    se = np.sqrt(np.diag(Ai @ (S.T @ S) @ Ai) * adj)
    return pd.DataFrame({"b": b, "se": se}, index=names)


def block(frame):
    """A frame's columns as a sparse block and their names."""
    return sp.csr_matrix(frame.to_numpy(np.float64)), list(frame.columns)


def pm(later, earlier, prefix, ref=None):
    """+1 at each pair's later value and -1 at its earlier value, as a sparse column for
    each value but `ref`."""
    later, earlier = np.asarray(later), np.asarray(earlier)
    vals = sorted((set(pd.unique(later)) | set(pd.unique(earlier))) - {ref})
    j = {v: i for i, v in enumerate(vals)}
    n = len(later)
    rows_, cols_, data = [], [], []
    for sign, v in ((1.0, later), (-1.0, earlier)):
        k = pd.Series(v).map(j).to_numpy(np.float64)
        ok = ~np.isnan(k)
        rows_.append(np.arange(n)[ok])
        cols_.append(k[ok].astype(int))
        data.append(np.full(ok.sum(), sign))
    M = sp.csr_matrix(
        (np.concatenate(data), (np.concatenate(rows_), np.concatenate(cols_))),
        shape=(n, len(vals)),
    )
    M.eliminate_zeros()
    return M, [f"{prefix}{v}" for v in vals]


def cells(v, prefix, ref):
    """A sparse 0/1 column for each value of `v` but `ref`."""
    v = np.asarray(v)
    vals = sorted(set(pd.unique(v)) - {ref})
    k = pd.Series(v).map({u: i for i, u in enumerate(vals)}).to_numpy(np.float64)
    ok = ~np.isnan(k)
    M = sp.csr_matrix(
        (np.ones(ok.sum()), (np.arange(len(v))[ok], k[ok].astype(int))),
        shape=(len(v), len(vals)),
    )
    return M, [f"{prefix}{u}" for u in vals]


def stack(*blocks):
    return sp.hstack([m for m, _ in blocks]).tocsr(), [
        n for _, ns in blocks for n in ns
    ]


d = c.rows()
d = d[~d.held & d.unit_id.notna()]
d = d[
    ["listing_id", "building", "ukey", "priced", "latest_ask", "bedrooms", "full_baths"]
]
d = d.reset_index(drop=True)
ids = pd.Index(d.listing_id.astype(str))


def joined(path, columns):
    """The table's rows for the listings of `d`, in `d`'s order, without the listing ids."""
    t = pd.read_parquet(path, columns=["listing_id", *columns])
    t["row"] = ids.get_indexer(t.listing_id.astype(str))
    t = t[t.row >= 0].drop(columns="listing_id").drop_duplicates("row")
    return t.set_index("row").reindex(np.arange(len(d))).reset_index(drop=True)


codes = joined(
    "/data1/apartments/external/listing-codes/20261023-ks/listing-codes.parquet",
    ["source_type", "photos", "floorplans", "states_features", *CODES.values()],
)
recs = joined(c.RECS, ["lister"])
proc = joined(
    "/data1/apartments/tmp/outlier-sprint/s2/H/proc.parquet",
    ["end_st", "t_on", "t_off", "run_days", "n_cut", "n_raise"],
)
proc["t_on"] = proc.t_on.dt.tz_convert(None)
proc["t_off"] = proc.t_off.dt.tz_convert(None)
recs["lister"] = recs.lister.astype("category")
d = pd.concat([d, codes, recs, proc], axis=1)
del codes, recs, proc

# The columns as L1's design codes them: a missing code is 0.
for col, code in CODES.items():
    d[col] = d[code].fillna(0).astype(float)
d["unstated"] = 1.0 - d.states_features.fillna(0).astype(float)
d["src"] = d.source_type.astype(object).fillna("none")
d["photos_l"] = np.log1p(d.photos.fillna(0).astype(float))
d["plan"] = (d.floorplans.fillna(0) > 0).astype(float)
d["y"] = np.log(d.latest_ask.astype(float))
d["quarter"] = d.priced.dt.to_period("Q").astype(str)
d["year"] = d.priced.dt.year
d["cuts"] = np.minimum(d.n_cut.fillna(0), 3).astype(int).astype(str)
d["raised"] = (d.n_raise.fillna(0) > 0).astype(float)
d["days"] = np.log1p(d.run_days.fillna(0).clip(lower=0))
d["path_known"] = d.n_cut.notna().astype(float)

d = d.sort_values(["ukey", "priced", "listing_id"]).reset_index(drop=True)
same = d.ukey.eq(d.ukey.shift()) & d.bedrooms.eq(d.bedrooms.shift())
same &= d.full_baths.eq(d.full_baths.shift())
L = d[same].reset_index(drop=True)
E = d.shift()[same].reset_index(drop=True)
print(
    "pairs",
    len(L),
    "units",
    L.ukey.nunique(),
    "buildings",
    L.building.nunique(),
    flush=True,
)

opens = L.t_on.where(L.t_on.notna() & (L.t_on < L.priced), L.priced)
known = E.t_off.notna() & (E.t_off < opens)
ending = np.where(known, E.end_st.map(END).fillna("other"), "unknown")
both_named = L.lister.notna() & E.lister.notna()
lister_new = (both_named & L.lister.ne(E.lister)).astype(float)

dy = (L.y - E.y).to_numpy()
cluster = L.building.astype(str).to_numpy()
base = [pm(L.quarter, E.quarter, "q:", ref=sorted(d.quarter.unique())[0])]
dc = pd.DataFrame({col: L[col] - E[col] for col in CODES})
dcode = block(dc)
ad_cols = block(
    pd.DataFrame(
        {
            "d:unstated": L.unstated - E.unstated,
            "d:photos": L.photos_l - E.photos_l,
            "d:plan": L.plan - E.plan,
        }
    )
)
dsrc = block(
    pd.DataFrame(
        {
            f"d:src_{s}": (L.src == s).astype(float) - (E.src == s).astype(float)
            for s in ("FEED", "OWNER")
        }
    )
)
channel = cells(E.src + ">" + L.src, "ch:", "PARTNER>PARTNER")
lister = block(
    pd.DataFrame(
        {"lister_new": lister_new, "lister_unknown": (~both_named).astype(float)}
    )
)
ends = cells(ending, "end:", "deal")
path = stack(
    cells(L.cuts, "cuts_l:", "0"),
    cells(E.cuts, "cuts_e:", "0"),
    block(
        pd.DataFrame(
            {
                "raised_l": L.raised,
                "raised_e": E.raised,
                "days_l": L.days,
                "days_e": E.days,
                "path_l": L.path_known,
                "path_e": E.path_known,
            }
        )
    ),
)
form = pm(
    L.year.astype(str) + "|" + L.src,
    E.year.astype(str) + "|" + E.src,
    "form:",
    ref=f"{int(d.year.min())}|PARTNER",
)
one = (sp.csr_matrix(np.ones((len(L), 1))), ["const"])
FAMILIES = {
    "channel": channel,
    "lister": lister,
    "ending": ends,
    "path": path,
    "form": form,
}


def fit(parts, rows=None):
    X, names = stack(one, dcode, ad_cols, *base, *parts)
    y, cl = dy, cluster
    if rows is not None:
        X, y, cl = X[rows], dy[rows], cluster[rows]
    nz = np.diff(X.tocsc().indptr) > 0
    X = X[:, np.flatnonzero(nz)]
    return ols(y, X, [n for n, k in zip(names, nz) if k], cl)


def code_rows(res):
    return {
        col: [round(100 * res.b[col], 3), round(100 * res.se[col], 3)] for col in CODES
    }


out = {"pairs": int(len(L)), "units": int(L.ukey.nunique())}
m0 = fit([dsrc])
out["M0"] = code_rows(m0)
print("M0", out["M0"], flush=True)
stated = ((L.unstated == 0) & (E.unstated == 0)).to_numpy()
out["M0_both_stated"] = code_rows(fit([dsrc], stated))
out["both_stated_pairs"] = int(stated.sum())
print("M0 both stated", out["M0_both_stated"], flush=True)
for k, part in FAMILIES.items():
    parts = [part] if k == "channel" else [dsrc, part]
    out[f"M0+{k}"] = code_rows(fit(parts))
    print(k, out[f"M0+{k}"], flush=True)
full = fit(list(FAMILIES.values()))
out["full"] = code_rows(full)
print("full", out["full"], flush=True)
out["full_controls"] = {
    k: [round(100 * full.b[k], 3), round(100 * full.se[k], 3)]
    for k in full.index
    if not k.startswith(("q:", "form:", "d:"))
}
out["share_removed"] = {
    col: {
        k: round(1 - out[k][col][0] / out["M0"][col][0], 3)
        for k in ["full", *[f"M0+{f}" for f in FAMILIES]]
    }
    for col in CODES
}

# How often a switch on coincides with each control, against pairs with no switch.
switch_any = (dc != 0).any(axis=1).to_numpy()
src_new = L.src.ne(E.src).to_numpy()
co = {}
for col in CODES:
    on = (dc[col] > 0).to_numpy()
    co[col] = {
        "switch_on": int(on.sum()),
        "switch_off": int((dc[col] < 0).sum()),
        "src_new": round(float(src_new[on].mean()), 3),
        "src_or_lister_new": round(float((src_new | (lister_new > 0))[on].mean()), 3),
        "later_cut": round(float((L.cuts != "0")[on].mean()), 3),
        "earlier_delisted_or_paused": round(
            float(np.isin(ending, ["delisted", "paused"])[on].mean()), 3
        ),
        "earlier_unstated": round(float((E.unstated == 1)[on].mean()), 3),
    }
co["no_switch"] = {
    "src_new": round(float(src_new[~switch_any].mean()), 3),
    "src_or_lister_new": round(
        float((src_new | (lister_new > 0))[~switch_any].mean()), 3
    ),
    "later_cut": round(float((L.cuts != "0")[~switch_any].mean()), 3),
    "earlier_delisted_or_paused": round(
        float(np.isin(ending, ["delisted", "paused"])[~switch_any].mean()), 3
    ),
    "earlier_unstated": round(float((E.unstated == 1)[~switch_any].mean()), 3),
}
out["coincide"] = co
print(json.dumps(co), flush=True)

# A lister switch after a failed rental: its interaction with the earlier ad's ending.
fail = np.isin(ending, ["delisted", "paused"]).astype(float)
inter = block(
    pd.DataFrame(
        {"lister_new_x_failed": lister_new * fail, "src_new_x_failed": src_new * fail}
    )
)
res = fit([*FAMILIES.values(), inter])
out["switch_after_failed"] = {
    k: [round(100 * res.b[k], 3), round(100 * res.se[k], 3)]
    for k in ("lister_new", "lister_new_x_failed", "src_new_x_failed")
    if k in res.index
}
print("switch after failed", out["switch_after_failed"], flush=True)
out["l1_own"] = L1_OWN
json.dump(out, open(c.OUT + "s12a.json", "w"), indent=1)
