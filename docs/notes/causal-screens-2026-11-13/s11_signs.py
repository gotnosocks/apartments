"""S11: which amenity, feature, view and outdoor columns of L1 come out negative, and why?

Part A reads L1's kept draws: for each column the median and 90% interval of its own
coefficient, of its unit mean's (`umean:`) and of their sum, with split R-hat and bulk ESS
from the run record. A unit mean averages the column over the row and its unit's training
rows priced earlier, so the own coefficient measures the change between a unit's ads and the
sum measures the difference between units.

Part B reads the raw codes behind each column with a negative median
(`/data1/apartments/external/listing-codes/20261023-ks/listing-codes.parquet`) on L1's
training rows:

1. how often a code flips between ads of a unit, and how often an ad disagrees with its
   building's majority;
2. its correlation, over buildings, with the doorman, concierge, valet and elevator codes;
3. its share by borough zone, building era and source type, beside the column's overall
   share."""

import json

import numpy as np
import pandas as pd

import common as c

z = np.load(c.RUN + "posterior.npz")
names = [str(n) for n in z["names"]]
beta = z["kept/beta"].reshape(-1, len(names))
diag = json.load(open(c.RUN + "result.json"))["diagnostics"]["per_quantity"]
EXPECT_POSITIVE = (
    "unit:laundry",
    "unit:dishwasher",
    "bld:elevator",
    "bld:doorman_",
    "bld:gym",
    "ad:feat_",
    "ad:fireplace_",
    "ad:private_outdoor_",
    "ad:views_",
    "bld:amen_",
    "bld:parking_",
    "bld:shared_outdoor_",
    "bld:storage_",
    "unit:penthouse",
)
cols = [n for n in names if n.startswith(EXPECT_POSITIVE)]


def q(v):
    return [float(x) for x in np.percentile(v, [50, 5, 95])]


rows = []
for n in cols:
    j = names.index(n)
    r = {"column": n, "own": q(beta[:, j])}
    um = "umean:" + n
    if um in names:
        k = names.index(um)
        r["umean"] = q(beta[:, k])
        r["sum"] = q(beta[:, j] + beta[:, k])
    d = diag.get(f"beta[{n}]", {})
    r["rhat"], r["ess"] = d.get("rhat"), d.get("ess")
    if um in names:
        d = diag.get(f"beta[{um}]", {})
        r["umean_rhat"], r["umean_ess"] = d.get("rhat"), d.get("ess")
    r["neg_own"] = r["own"][0] < 0
    r["neg_own_90"] = r["own"][2] < 0
    r["neg_sum"] = "sum" in r and r["sum"][0] < 0
    r["neg_sum_90"] = "sum" in r and r["sum"][2] < 0
    rows.append(r)
t = pd.DataFrame(rows)
pd.set_option("display.width", 250)
show = t.assign(
    own=t.own.map(
        lambda v: f"{100 * v[0]:+.2f} [{100 * v[1]:+.2f}, {100 * v[2]:+.2f}]"
    ),
    sum=t["sum"].map(
        lambda v: (
            f"{100 * v[0]:+.2f} [{100 * v[1]:+.2f}, {100 * v[2]:+.2f}]"
            if isinstance(v, list)
            else ""
        )
    ),
)[["column", "own", "sum", "rhat", "ess", "neg_own_90", "neg_sum_90"]]
print(show.to_string(), flush=True)
res = {
    "n_columns": len(t),
    "n_neg_own": int(t.neg_own.sum()),
    "n_neg_own_90": int(t.neg_own_90.sum()),
    "n_neg_sum": int(t.neg_sum.sum()),
    "n_neg_sum_90": int(t.neg_sum_90.sum()),
    "neg_own_diag": t[t.neg_own][["column", "rhat", "ess"]].to_dict("records"),
    "columns": rows,
}
print({k: v for k, v in res.items() if k.startswith("n_")}, flush=True)

# Part B: the raw codes of the flagged columns on L1's training rows
flag = t[t.neg_own | t.neg_sum].column.tolist()
CODE = {}
for n in flag:
    s = n.split(":", 1)[1]
    for pre in (
        "amen_",
        "parking_",
        "shared_outdoor_",
        "storage_",
        "feat_",
        "fireplace_",
        "private_outdoor_",
        "views_",
    ):
        if s.startswith(pre):
            CODE[n] = pre[:-1] + ":" + s[len(pre) :].upper()
RELATED = ["amen:DOORMAN", "amen:CONCIERGE", "amen:VALET_SERVICE", "amen:ELEVATOR"]
codes = pd.read_parquet(
    "/data1/apartments/external/listing-codes/20261023-ks/listing-codes.parquet",
    columns=[
        "listing_id",
        "source_type",
        "states_amenities",
        "states_features",
        *set(CODE.values()) | set(RELATED),
    ],
)
d = c.rows()
d = d[~d.held]
d = d.merge(codes, on="listing_id", how="inner")
plu = pd.read_parquet(c.PLUTO, columns=["bbl", "yearbuilt"]).drop_duplicates("bbl")
plu["yearbuilt"] = pd.to_numeric(plu.yearbuilt, errors="coerce")
plu["bbl"] = plu.bbl.astype("string")
d["bbl"] = d.bbl.astype("string")
d = d.merge(plu, on="bbl", how="left")
d["era"] = pd.cut(
    d.yearbuilt,
    [0, 1899, 1939, 1979, 1999, 2009, 3000],
    labels=["<1900", "1900-39", "1940-79", "1980-99", "2000-09", "2010+"],
).astype(str)
d["zone"] = np.where(d.manhattan, "mn", "out")
d["year"] = d.day.dt.year
bld_codes = d[d.states_amenities > 0].groupby("building")[RELATED].mean() >= 0.5
part_b = {}
for n, code in CODE.items():
    stating = (d.states_amenities if n.startswith("bld:") else d.states_features) > 0
    e = d[stating & d[code].notna()].copy()
    e["v"] = e[code].astype(float)
    out = {"code": code, "rows": len(e), "share_on": float(e.v.mean())}
    g = e.groupby("building").v
    nb = g.transform("size")
    maj = g.transform("mean")
    m3 = nb >= 3
    out["bld_disagree"] = float(np.minimum(maj, 1 - maj)[m3].mean())
    out["bld_mixed_share"] = float(
        ((maj > 0) & (maj < 1))[m3].groupby(e.building[m3]).first().mean()
    )
    u = e[e.unit_id.notna()].groupby("ukey").v
    un = u.transform("size")
    um = u.transform("mean")
    out["unit_flip_share"] = float(
        ((um > 0) & (um < 1))[un >= 2]
        .groupby(e.ukey[e.unit_id.notna()][un >= 2])
        .first()
        .mean()
    )
    bm = (g.mean() >= 0.5).rename("x").to_frame().join(bld_codes, how="inner")
    out["corr_bld"] = {
        r: float(np.corrcoef(bm.x, bm[r])[0, 1]) for r in RELATED if r != code
    }
    out["by_zone"] = e.groupby("zone").v.mean().round(4).to_dict()
    out["by_era"] = e.groupby("era").v.mean().round(4).to_dict()
    out["by_source"] = e.groupby(e.source_type.astype(str)).v.mean().round(4).to_dict()
    out["by_year"] = e.groupby("year").v.mean().round(3).to_dict()
    part_b[n] = out
    print(n, json.dumps(out), flush=True)
res["part_b"] = part_b
json.dump(res, open(c.OUT + "s11.json", "w"), indent=1)
