"""S12, part B: which building and ad facts carry the negative sums of S11's codes?

On L1's held-out ads the script adds each code's own contribution back into L1's gap, with
the code's own and unit-mean terms at their posterior medians, and regresses the result on
the code and its unit mean, first alone and then with candidate causes beside them: the era
by zone, the full building class, the description's renovation and old-detail wording, and
the count of other premium codes the ad states. It writes the sums, the wording's rates and
a frame of the held-out ads for drawing the ads to read."""

import json
import os
import re
import sys

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "causal-screens-2026-11-13"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "frontier", "src"))
import common as c  # noqa: E402
from rentfrontier.building_zones_floor_asof3_unitmean import unit_groups  # noqa: E402
from rentfrontier.building_zones_kitchen_sink import past_means, past_sums  # noqa: E402

CODES = {
    "ad:private_outdoor_roof_rights": "private_outdoor:ROOF_RIGHTS",
    "ad:feat_hardwood_floors": "feat:HARDWOOD_FLOORS",
    "ad:fireplace_decorative": "fireplace:DECORATIVE",
    "ad:views_city": "views:CITY",
    "ad:private_outdoor_balcony": "private_outdoor:BALCONY",
    "ad:views_park": "views:PARK",
}
SUPER = "bld:amen_live_in_super"
OUTDOOR = [
    "feat:PRIVATE_OUTDOOR_SPACE",
    "private_outdoor:BALCONY",
    "private_outdoor:GARDEN",
    "private_outdoor:PATIO",
    "private_outdoor:PRIVATE_ROOF_DECK",
    "private_outdoor:ROOF_RIGHTS",
    "private_outdoor:TERRACE",
]
OTHER_VIEWS = ["views:GARDEN", "views:PARK", "views:SKYLINE", "views:WATER"]
FIREPLACE = [
    "feat:FIREPLACE",
    "fireplace:DECORATIVE",
    "fireplace:GAS",
    "fireplace:WOOD",
]
SINGLE = [
    "feat:DISHWASHER",
    "feat:WASHER_DRYER",
    "feat:CENTRAL_AC",
    "amen:DOORMAN",
    "amen:ELEVATOR",
    "amen:GYM",
]
WORDS = {
    "renovated": r"\brenovat\w*|\bremodel\w*",
    "gut": r"\bgut[\s-]*(?:renovat|rehab|remodel)\w*",
    "new_kitchen_bath": (
        r"\b(?:new|brand[\s-]new|updated|renovated|modern|chef'?s)\s+(?:\w+\s+){0,2}"
        r"(?:kitchen|bath|bathroom)s?\b"
    ),
    "old_detail": (
        r"\b(?:original|pre-?war|vintage|period|classic)\s+(?:\w+\s+){0,2}"
        r"(?:details?|charm|moldings?|mouldings?|mantels?|floors?|features?)\b"
        r"|\bmouldings?\b|\bmoldings?\b|\bwainscot\w*|\btin ceilings?\b"
    ),
}
ERA = [0, 1899, 1939, 1979, 1999, 2009, 3000]


def ols(y, X, names, cluster):
    """Least squares of y on the columns of X, with the covariance clustered by
    `cluster`."""
    A = X.T @ X
    Ai = np.linalg.pinv(A)
    b = Ai @ (X.T @ y)
    e = y - X @ b
    g = pd.factorize(cluster)[0]
    S = np.zeros((g.max() + 1, X.shape[1]))
    np.add.at(S, g, X * e[:, None])
    n, k, m = len(y), np.linalg.matrix_rank(A), S.shape[0]
    V = Ai @ (S.T @ S) @ Ai * (m / (m - 1) * (n - 1) / (n - k))
    return pd.Series(b, index=names), pd.DataFrame(V, index=names, columns=names)


def cells(v, prefix, min_rows=300):
    """0/1 columns for each value of `v` with at least `min_rows` rows, against the
    most common value and the rare ones together."""
    v = pd.Series(np.asarray(v)).astype(str)
    counts = v.value_counts()
    keep = [u for u in counts.index[1:] if counts[u] >= min_rows]
    return pd.DataFrame({f"{prefix}{u}": (v == u).to_numpy(float) for u in keep})


def term(b, V, cols):
    """The sum of the coefficients `cols`, in percent, with its SE."""
    return [
        round(100 * b[cols].sum(), 3),
        round(100 * np.sqrt(V.loc[cols, cols].sum().sum()), 3),
    ]


d = c.rows()
d = d[
    [
        "listing_id",
        "building",
        "unit_id",
        "price_at",
        "held",
        "bbl",
        "manhattan",
        "bedrooms",
    ]
]
d = d.reset_index(drop=True)
ids = pd.Index(d.listing_id.astype(str))
need = sorted(
    {*CODES.values(), "amen:LIVE_IN_SUPER", *OUTDOOR, *OTHER_VIEWS, *FIREPLACE, *SINGLE}
)
t = pd.read_parquet(
    "/data1/apartments/external/listing-codes/20261023-ks/listing-codes.parquet",
    columns=["listing_id", "states_amenities", "states_features", *need],
)
t["row"] = ids.get_indexer(t.listing_id.astype(str))
t = t[t.row >= 0].drop(columns="listing_id").drop_duplicates("row")
t = t.set_index("row").reindex(np.arange(len(d))).reset_index(drop=True)
for k in need:
    t[k] = t[k].fillna(0).astype(np.float32)
train = ~d.held.to_numpy()

# The unit means as L1 builds them, and the building's live-in super as its past majority.
x = t[list(CODES.values())].to_numpy(float)
m = past_means(x, unit_groups(d), d.price_at, train)
stating = t.states_amenities.fillna(0).to_numpy(float) > 0
sx = (t["amen:LIVE_IN_SUPER"].to_numpy(float) * stating)[:, None]
site = pd.factorize(d.building)[0].astype(np.int64)
s, n = past_sums(sx, (train & stating).astype(float), site, d.price_at)
s, n = s[:, 0] + sx[:, 0], n + stating
super_ = ((s >= 0.5 * n) & (n > 0)).astype(float)

prem = t[SINGLE].sum(axis=1).to_numpy().copy()
prem += t[OUTDOOR].max(axis=1).to_numpy()
prem += t[OTHER_VIEWS].max(axis=1).to_numpy()
prem += t[FIREPLACE].max(axis=1).to_numpy()
frame = pd.DataFrame(x, columns=list(CODES))
frame[["umean:" + k for k in CODES]] = m
frame[SUPER] = super_
frame["premium"] = prem
frame["states_features"] = t.states_features.fillna(0).to_numpy(float)
del t, x, m
d = pd.concat([d, frame], axis=1)
del frame

h = c.heldout(d)
a = np.load(c.RUN + "pred_scores.npz", allow_pickle=True)
qs = list(a["quantiles"])
h["q25"], h["q75"] = a["q"][:, qs.index(0.25)], a["q"][:, qs.index(0.75)]
del d, a

plu = pd.read_parquet(c.PLUTO, columns=["bbl", "version", "yearbuilt", "bldgclass"])
plu = plu.sort_values("version").drop_duplicates("bbl", keep="last")
plu["bbl"] = plu.bbl.astype("string")
plu = plu.set_index("bbl")
bbl = h.bbl.astype("string")
year = pd.to_numeric(plu.yearbuilt.reindex(bbl), errors="coerce").to_numpy()
year = np.where(year > 0, year, np.nan)
era = pd.cut(year, ERA, labels=False)
h["era"] = np.where(np.isnan(era), "na", np.nan_to_num(era).astype(int).astype(str))
h["zone"] = np.where(h.manhattan.fillna(False), "mn", "out")
h["era_zone"] = h.era + "|" + h.zone
h["bldgclass"] = plu.bldgclass.reindex(bbl).fillna("na").astype(str).to_numpy()
del plu

# The description's wording, from the stored pages' records, for the held-out ads.
want = set(h.listing_id.astype(str))
pat = {k: re.compile(v, re.I) for k, v in WORDS.items()}
found = {}
f = pq.ParquetFile(c.RECS)
for i in range(f.metadata.num_row_groups):
    g = f.read_row_group(i, columns=["listing_id", "description"]).to_pandas()
    g = g[g.listing_id.astype(str).isin(want) & g.description.notna()]
    for lid, text in zip(g.listing_id.astype(str), g.description):
        if lid not in found or len(text) > found[lid][0]:
            found[lid] = (len(text), [bool(p.search(text)) for p in pat.values()])
lid = h.listing_id.astype(str)
h["described"] = lid.isin(found).astype(float)
for j, k in enumerate(WORDS):
    h["w:" + k] = [float(found[v][1][j]) if v in found else 0.0 for v in lid]
del found
print("described", float(h.described.mean()), flush=True)

z = np.load(c.RUN + "posterior.npz")
names = [str(v) for v in z["names"]]
beta = z["kept/beta"].reshape(-1, len(names))
med = {k: float(np.median(beta[:, names.index(k)])) for k in [*CODES, SUPER]}
med.update(
    {"umean:" + k: float(np.median(beta[:, names.index("umean:" + k)])) for k in CODES}
)
del beta, z

blocks = {
    "era_zone": cells(h.era_zone, "ez:"),
    "class": cells(h.bldgclass, "cls:"),
    "words": h[["described", *["w:" + k for k in WORDS]]].reset_index(drop=True),
    "premium": cells(np.minimum(h.premium, 6).astype(int), "prem:"),
}
cluster = h.building.astype(str).to_numpy()
out = {"heldout": len(h), "medians": {k: round(100 * v, 3) for k, v in med.items()}}
for k in [*CODES, SUPER]:
    own = [k] if k == SUPER else [k, "umean:" + k]
    r = h.gap.to_numpy() + sum(med[v] * h[v].to_numpy() for v in own)
    base = pd.DataFrame({"const": 1.0, **{v: h[v].to_numpy() for v in own}})
    res = {"stating": int((h[k] > 0).sum())}
    for name, extra in [
        ("none", []),
        *[(b, [b]) for b in blocks],
        ("all", list(blocks)),
    ]:
        X = pd.concat([base, *[blocks[b] for b in extra]], axis=1)
        b, V = ols(r, X.to_numpy(float), list(X.columns), cluster)
        res[name] = term(b, V, own)
        if k != SUPER:
            res[name + "_own"] = term(b, V, [k])
    out[k] = res
    print(k, res, flush=True)

# Advertising what you have: the terms among ads stating few and many other premium codes.
for k in ("ad:feat_hardwood_floors", "ad:views_city"):
    other = h.premium - (h[k] if k == "ad:views_city" else 0)
    for name, rows in (("low", other <= 1), ("high", other >= 3)):
        g = h[rows.to_numpy() & (h.states_features > 0).to_numpy()]
        own = [k, "umean:" + k]
        r = g.gap.to_numpy() + sum(med[v] * g[v].to_numpy() for v in own)
        X = pd.DataFrame({"const": 1.0, **{v: g[v].to_numpy() for v in own}})
        b, V = ols(
            r, X.to_numpy(float), list(X.columns), g.building.astype(str).to_numpy()
        )
        out[f"{k}|{name}"] = {
            "ads": len(g),
            "sum": term(b, V, own),
            "own": term(b, V, [k]),
        }
        print(k, name, out[f"{k}|{name}"], flush=True)

# How often each wording comes with each code, against ads without it that state features.
rates = {}
told = h[(h.described > 0) & (h.states_features > 0)]
for k in [*CODES, SUPER]:
    on = told[k] > 0
    rates[k] = {
        w: [
            round(float(told.loc[on, "w:" + w].mean()), 4),
            round(float(told.loc[~on, "w:" + w].mean()), 4),
        ]
        for w in WORDS
    }
out["word_rates"] = rates
json.dump(out, open(c.OUT + "s12b.json", "w"), indent=1)
keep = [
    "listing_id",
    "building",
    "zone",
    "bedrooms",
    "y",
    "pred",
    "lo",
    "hi",
    "q25",
    "q75",
]
h[
    [
        *keep,
        "gap",
        *CODES,
        *["umean:" + k for k in CODES],
        SUPER,
        "states_features",
        "premium",
        "era_zone",
        "bldgclass",
        *["w:" + k for k in WORDS],
    ]
].to_parquet(c.OUT + "s12b_heldout.parquet")
