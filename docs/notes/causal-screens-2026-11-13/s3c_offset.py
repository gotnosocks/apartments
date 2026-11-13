"""S3, part C: where do L1's held-out asks sit 0.44% under its median?

`s3b_phase.py` found that a constant shift of every held-out ad gains 582 elpd. Here I break
the held-out gap and that constant's per-ad gain down by the ad's year, by quarter from 2024,
and by phase in two periods. For each month I also count the share of the dataset's ads that
L1 trained on, since the newest months hold mostly held-out ads and leave the citywide walk
there with few training ads."""

import json

import numpy as np
import pandas as pd

import common as c

PHASES = ("10-13", "none", "0-2", "3-9", "14-21", "22-25", "26+")
d = c.rows()
d["month"] = d.day.dt.to_period("M")
train_share = (~d.held).groupby(d.month).mean()
h = c.heldout(d)
dr = c.Draws()
h["phase"] = np.asarray(PHASES)[dr.ph]
del dr
g = pd.read_parquet(c.OUT + "s3b_gains.parquet")
assert (g.listing_id.to_numpy() == h.listing_id.to_numpy()).all()
h["e_const"] = g.e_const.to_numpy()
h["train_share"] = h.month.map(train_share).to_numpy()


def table(by):
    out = []
    for k, v in h.groupby(by):
        b = v.building.to_numpy()
        out.append(
            {
                "key": str(k),
                "n": len(v),
                "gap": float(v.gap.mean()),
                "se": c.cluster_se(v.gap.to_numpy(), b) / len(v),
                "median": float(np.median(v.gap)),
                "in80": float(v.in80.mean()),
                "e_const": float(v.e_const.sum()),
                "train_share": float(v.train_share.mean()),
            }
        )
    return out


res = {"year": table(h.day.dt.year)}
late = h.day >= pd.Timestamp("2024-01-01")
res["quarter_2024on"] = [
    r for r in table(h.day.dt.to_period("Q")) if r["key"] >= "2024Q1"
]
h["period"] = np.where(late, "2024+", "to 2023")
res["phase_period"] = table(["phase", "period"])
for k, v in res.items():
    print(k, pd.DataFrame(v).round(5).to_string(), sep="\n", flush=True)
json.dump(res, open(c.OUT + "s3c.json", "w"), indent=1)
