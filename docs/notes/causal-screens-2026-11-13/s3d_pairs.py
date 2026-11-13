"""S3, part D: does the drop after a quick relist show among L1's training ads too?

A level per phase in L2's mean would be learned from training ads, and each of those has a
later ad of its unit, while each held-out ad has none. So the script pairs every ad with its unit's
previous ad, sort the pairs into L1's phases with `drift_building_phase.phase_index`, and take
the change in log latest ask from the previous ad. The script reports it by phase for pairs whose later
ad L1 trained on and pairs whose later ad it held out. Then the script takes off the mean change of all
pairs with the same quarters for the two ads, which removes the market's move, and compare the
held-out pairs with the training pairs of the same phase."""

import json

import numpy as np
import pandas as pd

import common as c
from rentfrontier import drift_building_phase as dbp

d = pd.read_parquet(
    c.DATA,
    columns=["listing_id", "building", "unit_id", "price_at", "latest_ask", "audit_id"],
)
d["held"] = np.load(c.RUN + "pred_scores.npz", allow_pickle=True)["heldout"]
d["phase"] = np.asarray(dbp.PHASES)[dbp.phase_index(d)]
ph9 = np.load(c.RUN + "posterior.npz")["kept/pred_phase"]
agree = float((d.phase[d.held].to_numpy() == np.asarray(dbp.PHASES)[ph9]).mean())
d["t"] = pd.to_datetime(d.price_at, utc=True).dt.tz_convert(None)
d = d[d.unit_id.notna()].sort_values(
    ["building", "unit_id", "t", "audit_id"], kind="stable"
)
grp = d.groupby(["building", "unit_id"], sort=False)
d["chg"] = np.log(d.latest_ask) - np.log(grp.latest_ask.shift(1))
d["q0"] = grp.t.shift(1).dt.to_period("Q").astype(str)
d["q1"] = d.t.dt.to_period("Q").astype(str)
p = d[d.chg.notna() & (d.phase != "none")].copy()
p["chg"] = p.chg.clip(-0.4, 0.4)
p["adj"] = p.chg - p.groupby(["q0", "q1"]).chg.transform("mean")
res = {
    "pairs": len(p),
    "phase_agrees_with_L1": agree,
    "held_minus_train_same_quarters": c.cluster_mean_diff(
        p.adj.to_numpy(), p.held.to_numpy(), p.building.to_numpy()
    ),
    "by_phase": {},
}
for ph, v in p.groupby("phase"):
    b = v.building.to_numpy()
    held = v.held.to_numpy()
    r = {}
    for name, m in (("train", ~held), ("held", held)):
        r[name] = {
            "n": int(m.sum()),
            "mean_chg": float(v.chg[m].mean()),
            "se": c.cluster_se(v.chg.to_numpy()[m], b[m]) / max(m.sum(), 1),
            "median_chg": float(v.chg[m].median()),
        }
    r["held_minus_train_same_quarters"] = c.cluster_mean_diff(v.adj.to_numpy(), held, b)
    res["by_phase"][ph] = r
print(json.dumps(res, indent=1), flush=True)
json.dump(res, open(c.OUT + "s3d.json", "w"), indent=1)
