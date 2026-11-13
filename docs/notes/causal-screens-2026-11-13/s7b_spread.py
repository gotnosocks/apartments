"""S7, part B: do duplex asks vary more than others, and did private outdoor space gain value?

`s7_score.py` found duplex ads within 0.5% of L1's median and of j9's mean location. This script
compares the spread instead: 80% coverage and the clipped squared gap on L1, the clipped
squared gap on j9's new units. Then the script takes held-out ads with the private outdoor flag and
compares their gap with other ads of the same pair of periods, the period of the unit's
previous ad and that of the held-out ad, split at 2020 and 2021."""

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
d = c.rows()
d["listing_id"] = d.listing_id.astype(str)
d = d.merge(tx, on="listing_id", how="left").merge(fl, on="listing_id", how="left")
d = d.sort_values(["ukey", "priced", "listing_id"])
d["prev_day"] = d.groupby("ukey").day.shift(1)
d = d.sort_index()
h = c.heldout(d)
h["dup"] = h.dup_unit.fillna(False).astype(bool)
h["out"] = h.private_outdoor.fillna(False).astype(bool)
h["sq"] = h.gap.clip(-0.4, 0.4) ** 2
b = h.building.to_numpy()


def spread(x, on, b):
    return {
        "n_on": int(on.sum()),
        "sq_on": float(x.sq[on].mean()),
        "sq_off": float(x.sq[~on].mean()),
        "sq_diff": c.cluster_mean_diff(x.sq.to_numpy(), on, b),
    }


res = {"n": len(h), "l1_dup": spread(h, h.dup.to_numpy(), b)}
res["l1_dup"]["in80_diff"] = c.cluster_mean_diff(
    h.in80.to_numpy(float), h.dup.to_numpy(), b
)
res["l1_dup"]["in80_on"] = float(h.in80[h.dup].mean())

J9 = "/data1/apartments/frontier/runs/drift-building-b0-market-67d14e17-j9/"
r9 = json.load(open(J9 + "result.json"))
z9 = np.load(J9 + "posterior.npz")
d9 = pd.read_parquet(
    r9["dataset"] + "/rows.parquet", columns=["listing_id", "building", "latest_ask"]
)
h9 = d9[z9["heldout"]].reset_index(drop=True)
y9 = z9["kept/pred_y"]
assert np.allclose(np.log(h9.latest_ask.to_numpy(float)), y9, atol=1e-6)
h9["gap"] = y9 - z9["kept/pred_loc"].reshape(-1, len(y9)).mean(axis=0)
del z9
h9["listing_id"] = h9.listing_id.astype(str)
h9 = h9.merge(tx, on="listing_id", how="left")
h9["sq"] = h9.gap.clip(-0.4, 0.4) ** 2
on9 = h9.dup_unit.fillna(False).astype(bool).to_numpy()
res["j9_dup"] = spread(h9, on9, h9.building.to_numpy())
h9["wsq"] = c.within(h9.gap.clip(-0.4, 0.4), h9.building) ** 2
res["j9_dup"]["within_sq_diff"] = c.cluster_mean_diff(
    h9.wsq.to_numpy(), on9, h9.building.to_numpy()
)


def period(t):
    return np.where(
        t < pd.Timestamp("2020-01-01"),
        "to 2019",
        np.where(t < pd.Timestamp("2021-01-01"), "2020", "2021+"),
    )


h["p0"] = period(h.prev_day)
h["p1"] = period(h.day)
res["outdoor_share"] = float(h.out.mean())
res["outdoor"] = []
for (p0, p1), v in h.groupby(["p0", "p1"]):
    on = v.out.to_numpy()
    if on.sum() < 30:
        continue
    res["outdoor"].append(
        {
            "prev": p0,
            "held": p1,
            "n": len(v),
            "n_out": int(on.sum()),
            "diff": c.cluster_mean_diff(v.gap.to_numpy(), on, v.building.to_numpy()),
        }
    )
print(
    json.dumps({k: v for k, v in res.items() if k != "outdoor"}, indent=1), flush=True
)
print(pd.DataFrame(res["outdoor"]).to_string(), flush=True)
json.dump(res, open(c.OUT + "s7b.json", "w"), indent=1)
