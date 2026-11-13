"""S7, part E: what would a period-specific premium for private outdoor space gain on L1?

Part B found held-out ads with the private outdoor flag over L1's median where the held-out
ad or the unit's previous ad ran before 2021, and close to it where both ran from 2021 on. The script
takes the cross-fitted shrunk mean gap of each pair of periods, then of each pair of periods
and the flag, rescores L1's predictive with each as a shift and compares the two."""

import json

import numpy as np
import pandas as pd

import common as c

fl = pd.read_parquet(
    "/data1/apartments/tmp/outlier-sprint/qual/flags.parquet",
    columns=["listing_id", "private_outdoor"],
)
fl["listing_id"] = fl.listing_id.astype(str)
d = c.rows()
d["listing_id"] = d.listing_id.astype(str)
d = d.merge(fl, on="listing_id", how="left")
d = d.sort_values(["ukey", "priced", "listing_id"])
d["prev_day"] = d.groupby("ukey").day.shift(1)
d = d.sort_index()
h = c.heldout(d)
del d


def period(t):
    return np.where(
        t < pd.Timestamp("2020-01-01"),
        "to 2019",
        np.where(t < pd.Timestamp("2021-01-01"), "2020", "2021+"),
    )


pair = pd.Series(period(h.prev_day)) + "|" + pd.Series(period(h.day))
out = h.private_outdoor.fillna(False).astype(bool)
gap = h.gap.clip(-0.4, 0.4).to_numpy()
fold, sub = h.fold.to_numpy(), c.subfold(h.building)
b = h.building.to_numpy()
idx = np.arange(len(h))
dr = c.Draws()
res = {"n": len(h)}
gains = {}
for name, key in (("pair", pair), ("pair_outdoor", pair + "|" + out.astype(str))):
    shift, k = c.crossfit_shift(gap, key.to_numpy(), fold, sub)
    gains[name] = dr.gain(idx, delta=shift)
    res[name] = {
        "gain": float(gains[name].sum()),
        "se": c.cluster_se(gains[name], b),
        "k": k,
    }
diff = gains["pair_outdoor"] - gains["pair"]
res["outdoor_over_pair"] = [float(diff.sum()), c.cluster_se(diff, b)]
print(json.dumps(res, indent=1), flush=True)
json.dump(res, open(c.OUT + "s7e.json", "w"), indent=1)
