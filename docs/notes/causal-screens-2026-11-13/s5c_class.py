"""S5, part C: are j9's new units in buildings with few training ads condos and co-ops?

`s5b_j9level.py` found j9's held-out new units 5% to 9% over its mean location where the
building has under 5 training ads. A condo or co-op apartment is rented by its owner, one at
a time, so its building rarely shows many ads, and j9 carries a condo flag but no co-op flag.
The script splits the gap by PLUTO's building class (condo, co-op, rental, other) and the building's
count of j9 training ads."""

import json

import numpy as np
import pandas as pd

import common as c

J9 = "/data1/apartments/frontier/runs/drift-building-b0-market-67d14e17-j9/"
COOP = ("C6", "C8", "D0", "D4")
z9 = np.load(J9 + "posterior.npz")
r9 = json.load(open(J9 + "result.json"))
d9 = pd.read_parquet(
    r9["dataset"] + "/rows.parquet", columns=["listing_id", "building", "latest_ask"]
)
reg = pd.read_parquet(c.REG, columns=["building", "bbl"]).drop_duplicates("building")
d9 = d9.merge(reg, on="building", how="left")
d9["bbl"] = d9.bbl.astype("string")
plu = pd.read_parquet(
    c.PLUTO, columns=["bbl", "bldgclass", "unitsres"]
).drop_duplicates("bbl")
plu["bbl"] = plu.bbl.astype("string")
d9 = d9.merge(plu, on="bbl", how="left")
held9 = z9["heldout"]
d9["n_train"] = (
    (~pd.Series(held9)).groupby(d9.building.to_numpy()).transform("sum").to_numpy()
)
h9 = d9[held9].reset_index(drop=True)
y9 = z9["kept/pred_y"]
assert np.allclose(np.log(h9.latest_ask.to_numpy(float)), y9, atol=1e-6)
h9["gap"] = y9 - z9["kept/pred_loc"].reshape(-1, len(y9)).mean(axis=0)
cls = h9.bldgclass.astype(str)
h9["class"] = np.where(
    cls.str.startswith("R"),
    "condo",
    np.where(
        cls.isin(COOP),
        "co-op",
        np.where(cls.str[0].isin(list("ABCDS")), "rental", "other"),
    ),
)
h9["count"] = pd.cut(
    h9.n_train, [-1, 4, 19, 99, 10**7], labels=["0-4", "5-19", "20-99", "100+"]
).astype(str)
out = []
for k, v in h9.groupby(["count", "class"]):
    out.append(
        {
            "key": str(k),
            "n": len(v),
            "buildings": int(v.building.nunique()),
            "share_of_count": len(v) / int((h9["count"] == k[0]).sum()),
            "gap": float(v.gap.mean()),
            "se": c.cluster_se(v.gap.to_numpy(), v.building.to_numpy()) / len(v),
        }
    )
print(pd.DataFrame(out).round(4).to_string(), flush=True)
json.dump({"n": len(h9), "count_class": out}, open(c.OUT + "s5c.json", "w"), indent=1)
