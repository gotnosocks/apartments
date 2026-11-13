"""S7, part C: do duplex ads miss L1's interval because two ads of a unit describe two apartments?

`s7b_spread.py` found duplex ads with twice the squared gap of other ads. A duplex in a small
building can be the same unit_id as a different floor-through, or a unit that was combined
or split between ads. So for each held-out ad I read the unit's previous ad: whether it also
matches the duplex pattern and whether it lists the same bedrooms. I split the squared gap
and 80% coverage by that, and by the lot's residential units from PLUTO, for duplex ads and
the rest. Last, I split the private outdoor contrast of part B by the years between the two
ads."""

import json

import numpy as np
import pandas as pd

import common as c

tx = pd.read_parquet(c.OUT + "s7_text.parquet", columns=["listing_id", "dup_unit"])
tx["listing_id"] = tx.listing_id.astype(str)
fl = pd.read_parquet(
    "/data1/apartments/tmp/outlier-sprint/qual/flags.parquet",
    columns=["listing_id", "private_outdoor"],
)
fl["listing_id"] = fl.listing_id.astype(str)
plu = pd.read_parquet(c.PLUTO, columns=["bbl", "unitsres"]).drop_duplicates("bbl")
plu["bbl"] = plu.bbl.astype("string")
plu["unitsres"] = pd.to_numeric(plu.unitsres, errors="coerce")
d = c.rows()
d["listing_id"] = d.listing_id.astype(str)
d["bbl"] = d.bbl.astype("string")
d = (
    d.merge(tx, on="listing_id", how="left")
    .merge(fl, on="listing_id", how="left")
    .merge(plu, on="bbl", how="left")
)
d["dup"] = d.dup_unit.fillna(False).astype(bool)
d = d.sort_values(["ukey", "priced", "listing_id"])
g = d.groupby("ukey")
d["prev_dup"] = g.dup.shift(1)
d["prev_beds"] = g.bedrooms.shift(1)
d["prev_day"] = g.day.shift(1)
d = d.sort_index()
h = c.heldout(d)
h["out"] = h.private_outdoor.fillna(False).astype(bool)
h["sq"] = h.gap.clip(-0.4, 0.4) ** 2
h["wsq"] = c.within(h.gap.clip(-0.4, 0.4), h.building) ** 2
h["same_beds"] = h.bedrooms.eq(h.prev_beds)
h["prev"] = np.where(
    h.prev_dup.fillna(False).astype(bool),
    "previous ad duplex",
    "previous ad not duplex",
)
h["beds"] = np.where(h.same_beds, "same bedrooms", "other bedrooms")
h["lot_units"] = pd.cut(
    h.unitsres, [-1, 5, 19, 99, 10**6], labels=["1-5", "6-19", "20-99", "100+"]
).astype(str)
b = h.building.to_numpy()


def cells(x, by):
    out = []
    for k, v in x.groupby(by):
        out.append(
            {
                "key": str(k),
                "n": len(v),
                "share": len(v) / len(x),
                "sq": float(v.sq.mean()),
                "in80": float(v.in80.mean()),
                "gap": float(v.gap.mean()),
            }
        )
    return out


dup = h[h.dup]
res = {
    "n": len(h),
    "within_sq_diff": c.cluster_mean_diff(h.wsq.to_numpy(), h.dup.to_numpy(), b),
    "sq_diff": c.cluster_mean_diff(h.sq.to_numpy(), h.dup.to_numpy(), b),
    "dup_by_previous": cells(dup, ["prev", "beds"]),
    "rest_by_beds": cells(h[~h.dup], "beds"),
    "dup_by_lot_units": cells(dup, "lot_units"),
    "rest_by_lot_units": cells(h[~h.dup], "lot_units"),
}
h["years"] = pd.cut(
    (h.day - h.prev_day).dt.days / 365.25,
    [-1, 1, 2, 4, 100],
    labels=["0-1", "1-2", "2-4", "4+"],
).astype(str)
res["outdoor_by_years"] = []
for k, v in h.groupby("years"):
    on = v.out.to_numpy()
    res["outdoor_by_years"].append(
        {
            "years": k,
            "n": len(v),
            "n_out": int(on.sum()),
            "diff": c.cluster_mean_diff(v.gap.to_numpy(), on, v.building.to_numpy()),
        }
    )
for k, v in res.items():
    if isinstance(v, list):
        print(k, pd.DataFrame(v).round(4).to_string(), sep="\n", flush=True)
    else:
        print(k, v, flush=True)
json.dump(res, open(c.OUT + "s7c.json", "w"), indent=1)
