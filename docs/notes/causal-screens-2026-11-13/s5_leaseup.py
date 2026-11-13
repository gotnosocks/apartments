"""S5: do new buildings price their first units differently while they lease up?

A building counts as new where PLUTO's year built is 2014 or later and its first ad in
L1's dataset opened within two years of the year built. For each held-out ad the script takes the
months since its building's first ad opened and reads the gap by those months for new
buildings beside older ones (built before 2010). L1 saves no quarterly building paths, so the
check reads the gap alone. Then the script moves
each held-out ad by the cross-fitted mean gap of its cell and rescores. Last, the same table
on the new units of the backtest j9 (`drift-building-b0-market-67d14e17-j9`), with the gap taken against the mean of its draws' locations."""

import json

import numpy as np
import pandas as pd

import common as c

BINS = [-1, 6, 12, 24, 48, 10_000]
LABELS = ["0-6", "6-12", "12-24", "24-48", "48+"]


def opened(d):
    p = pd.read_parquet(
        "/data1/apartments/tmp/outlier-sprint/s2/H/proc.parquet",
        columns=["listing_id", "t_on"],
    ).drop_duplicates("listing_id")
    p["t_on"] = p.t_on.dt.tz_convert(None)
    d = d.merge(p, on="listing_id", how="left")
    d["opened"] = d.t_on.where(d.t_on.notna() & (d.t_on <= d.priced), d.priced)
    return d


def tag(d, plu):
    first = d.groupby("building").opened.min().rename("first_open")
    d = d.merge(first, on="building", how="left")
    d = d.merge(plu, on="bbl", how="left")
    yb = d.yearbuilt.where(d.yearbuilt > 1800)
    new = (yb >= 2014) & (d.first_open.dt.year <= yb + 2)
    old = yb < 2010
    d["age_group"] = np.where(new, "new", np.where(old, "old", "other"))
    months = (d.opened - d.first_open).dt.days / 30.44
    d["months"] = pd.cut(months, BINS, labels=LABELS).astype(str)
    return d


plu = pd.read_parquet(c.PLUTO, columns=["bbl", "yearbuilt"]).drop_duplicates("bbl")
plu["yearbuilt"] = pd.to_numeric(plu.yearbuilt, errors="coerce")
plu["bbl"] = plu.bbl.astype("string")
d = c.rows()
d["bbl"] = d.bbl.astype("string")
d = tag(opened(d), plu)
h = c.heldout(d)
dr = c.Draws()
assert len(h) == len(dr.ph)
res = {"n": len(h), "groups": h.age_group.value_counts().to_dict()}
print(res, flush=True)


def table(x, gapcol="gap"):
    rows = []
    for (ag, mo), g in x[x.age_group != "other"].groupby(["age_group", "months"]):
        rows.append(
            {
                "age_group": ag,
                "months": mo,
                "n": len(g),
                "buildings": g.building.nunique(),
                "gap": float(g[gapcol].mean()),
                "se": c.cluster_se(g[gapcol].to_numpy(), g.building.to_numpy())
                / len(g),
            }
        )
    return pd.DataFrame(rows)


t = table(h)
t.to_csv(c.OUT + "s5_l1.csv", index=False)
print(t.to_string(), flush=True)
res["l1"] = t.to_dict("records")

key = (h.age_group + "|" + h.months).to_numpy()
fold = h.fold.to_numpy()
sub = c.subfold(h.building)
dl, k = c.crossfit_shift(h.gap.to_numpy(), key, fold, sub)
e = dr.gain(np.arange(len(h)), delta=dl)
res["shift"] = {
    "elpd_gain": float(e.sum()),
    "se": c.cluster_se(e, h.building.to_numpy()),
    "k": k,
}
# the same over a constant shift fitted the same way
e0 = dr.gain(
    np.arange(len(h)),
    delta=c.crossfit_shift(h.gap.to_numpy(), np.zeros(len(h)), fold, sub)[0],
)
inc = e - e0
res["shift"]["over_constant"] = [
    float(inc.sum()),
    c.cluster_se(inc, h.building.to_numpy()),
]
new = (h.age_group == "new").to_numpy()
res["shift"]["gain_new"] = float(inc[new].sum())
res["shift"]["gain_new_se"] = c.cluster_se(inc[new], h.building.to_numpy()[new])
print(json.dumps(res["shift"]), flush=True)
del dr

# the backtest j9's new units
J9 = "/data1/apartments/frontier/runs/drift-building-b0-market-67d14e17-j9/"
r9 = json.load(open(J9 + "result.json"))
z9 = np.load(J9 + "posterior.npz")
d9 = pd.read_parquet(
    r9["dataset"] + "/rows.parquet",
    columns=["listing_id", "building", "unit_id", "price_at", "latest_ask"],
)
d9["priced"] = d9.price_at.dt.tz_convert(None)
reg = pd.read_parquet(c.REG, columns=["building", "bbl"]).drop_duplicates("building")
d9 = d9.merge(reg, on="building", how="left")
d9["bbl"] = d9.bbl.astype("string")
held9 = z9["heldout"]
d9 = tag(opened(d9), plu)
h9 = d9[held9].reset_index(drop=True)
y9 = z9["kept/pred_y"]
assert np.allclose(np.log(h9.latest_ask.to_numpy(float)), y9, atol=1e-6)
h9["gap"] = y9 - z9["kept/pred_loc"].reshape(-1, len(y9)).mean(axis=0)
t9 = table(h9)
t9.to_csv(c.OUT + "s5_j9.csv", index=False)
print(t9.to_string(), flush=True)
res["j9"] = t9.to_dict("records")
res["j9_groups"] = h9.age_group.value_counts().to_dict()
json.dump(res, open(c.OUT + "s5.json", "w"), indent=1)
