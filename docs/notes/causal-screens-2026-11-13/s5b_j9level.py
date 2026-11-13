"""S5, part B: do j9's new units ask more in buildings new to the data, or in buildings with few ads?

S5 found j9's new units asking 3% to 5% over j9's mean location in the first months after their
building's first ad, in old buildings as much as in new ones. A building new to the data also
has few training ads, so j9 sets its level close to what its attributes and place predict. To
pull the two apart the script crosses the building's count of j9 training ads with the months since its
first ad and splits the gap by PLUTO's latest alteration year as well."""

import json

import numpy as np
import pandas as pd

import common as c

J9 = "/data1/apartments/frontier/runs/drift-building-b0-market-67d14e17-j9/"
BINS = [-1, 6, 12, 24, 48, 10_000]
LABELS = ["0-6", "6-12", "12-24", "24-48", "48+"]


def opened(d):
    """As in `s5_leaseup.py`: the day each ad opened, from the raw status history."""
    p = pd.read_parquet(
        "/data1/apartments/tmp/outlier-sprint/s2/H/proc.parquet",
        columns=["listing_id", "t_on"],
    ).drop_duplicates("listing_id")
    p["t_on"] = p.t_on.dt.tz_convert(None)
    d = d.merge(p, on="listing_id", how="left")
    d["opened"] = d.t_on.where(d.t_on.notna() & (d.t_on <= d.priced), d.priced)
    return d


def tag(d, plu):
    """As in `s5_leaseup.py`: the building's age group and the months since its first ad."""
    first = d.groupby("building").opened.min().rename("first_open")
    d = d.merge(first, on="building", how="left")
    d = d.merge(plu, on="bbl", how="left")
    yb = d.yearbuilt.where(d.yearbuilt > 1800)
    new = (yb >= 2014) & (d.first_open.dt.year <= yb + 2)
    d["age_group"] = np.where(new, "new", np.where(yb < 2010, "old", "other"))
    months = (d.opened - d.first_open).dt.days / 30.44
    d["months"] = pd.cut(months, BINS, labels=LABELS).astype(str)
    return d


z9 = np.load(J9 + "posterior.npz")
r9 = json.load(open(J9 + "result.json"))
d9 = pd.read_parquet(
    r9["dataset"] + "/rows.parquet",
    columns=["listing_id", "building", "unit_id", "price_at", "latest_ask"],
)
d9["priced"] = d9.price_at.dt.tz_convert(None)
reg = pd.read_parquet(c.REG, columns=["building", "bbl"]).drop_duplicates("building")
d9 = d9.merge(reg, on="building", how="left")
d9["bbl"] = d9.bbl.astype("string")
plu = pd.read_parquet(
    c.PLUTO, columns=["bbl", "yearbuilt", "yearalter1", "yearalter2"]
).drop_duplicates("bbl")
for col in ("yearbuilt", "yearalter1", "yearalter2"):
    plu[col] = pd.to_numeric(plu[col], errors="coerce")
plu["bbl"] = plu.bbl.astype("string")
held9 = z9["heldout"]
d9 = tag(opened(d9), plu)
d9["n_train"] = (
    (~pd.Series(held9)).groupby(d9.building.to_numpy()).transform("sum").to_numpy()
)
h9 = d9[held9].reset_index(drop=True)
y9 = z9["kept/pred_y"]
assert np.allclose(np.log(h9.latest_ask.to_numpy(float)), y9, atol=1e-6)
h9["gap"] = y9 - z9["kept/pred_loc"].reshape(-1, len(y9)).mean(axis=0)
h9["count"] = pd.cut(
    h9.n_train, [-1, 0, 4, 19, 99, 10**7], labels=["0", "1-4", "5-19", "20-99", "100+"]
).astype(str)
h9["first_year"] = np.where(h9.months.isin(["0-6", "6-12"]), "first year", "later")
alter = h9[["yearalter1", "yearalter2"]].max(axis=1)
h9["era"] = np.where(
    h9.yearbuilt >= 2010,
    "built 2010+",
    np.where(alter >= 2010, "altered 2010+", "older, unaltered since 2010"),
)


def table(by):
    out = []
    for k, v in h9.groupby(by):
        out.append(
            {
                "key": str(k),
                "n": len(v),
                "buildings": int(v.building.nunique()),
                "gap": float(v.gap.mean()),
                "se": c.cluster_se(v.gap.to_numpy(), v.building.to_numpy()) / len(v),
            }
        )
    return out


res = {
    "n": len(h9),
    "count": table("count"),
    "count_first_year": table(["count", "first_year"]),
    "era_first_year": table(["era", "first_year"]),
}
for k, v in res.items():
    if k != "n":
        print(k, pd.DataFrame(v).round(4).to_string(), sep="\n", flush=True)
json.dump(res, open(c.OUT + "s5b.json", "w"), indent=1)
