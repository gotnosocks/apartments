"""History: ads whose counts differ from the unit's last training ad, after a level per kind.

The latest-split runs carry no count marks, so their errors by kind of change mix a level
(the model adds the whole step for a room the unit gained or lost) with a spread. The Deals
model has the level. This script removes it here: each kind's mean error on one half of the
buildings is subtracted on the other half, the place of each ask is recomputed under the
Student-t approximation of `calib2.py`, and the tail shares that remain are printed. Ads
with the counts of the last training ad are the control for the approximation.
"""

import sys

import numpy as np
import pandas as pd
from scipy.stats import norm
from scipy.stats import t as student

DS = "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc/rows.parquet"
DF = 7
run, tag, y0 = sys.argv[1], sys.argv[2], int(sys.argv[3])
h = pd.read_parquet(f"baths-{tag}.parquet")
h = h[h.year >= y0].copy()
p = np.load(f"/data1/apartments/frontier/runs/{run}/pred_scores.npz", allow_pickle=True)
q = p["q"].astype(float)
h = h.merge(
    pd.DataFrame({"listing_id": p["listing"], "iqr": q[:, 4] - q[:, 3]}),
    on="listing_id",
    validate="1:1",
)
r = pd.read_parquet(
    DS,
    columns=["unit_id", "building", "price_at", "bedrooms", "full_baths", "half_baths"],
)
r["held"] = p["heldout"]
r["apt"] = r.unit_id.str.replace(r"~\d+$", "", regex=True)
r["baths"] = r.full_baths + 0.5 * r.half_baths.fillna(0)
t = r[~r.held & r.apt.notna()].sort_values("price_at")
last = t.groupby(["building", "apt"]).agg(
    last_bed=("bedrooms", "last"), last_bath=("baths", "last")
)
h = h.merge(last, left_on=["building", "apt"], right_index=True, how="left")
h = h[h.last_bed.notna() & h.last_bath.notna()].copy()
dbed, dbath = h.bedrooms - h.last_bed, h.baths - h.last_bath
h["kind"] = np.select(
    [
        (dbed == 0) & (dbath == 0),
        (dbed > 0) & (dbath == 0),
        (dbed < 0) & (dbath == 0),
        (dbed == 0) & (dbath > 0),
        (dbed == 0) & (dbath < 0),
        (dbed > 0) & (dbath > 0),
        (dbed < 0) & (dbath < 0),
    ],
    [
        "same as the last ad",
        "bed up",
        "bed down",
        "bath up",
        "bath down",
        "both up",
        "both down",
    ],
    "mixed",
)
s = h.iqr / (2 * student.ppf(0.75, DF))
h["d"] = 0.0
for k, g in h.groupby("kind"):
    for f in (0, 1):
        h.loc[(h.kind == k) & (h.half == f), "d"] = g.res[g.half != f].mean()
h["place"] = student.cdf((h.res - h.d) / s, DF)
h["place0"] = student.cdf(h.res / s, DF)
h["z"] = norm.ppf(h.place.clip(1e-6, 1 - 1e-6))
pd.set_option("display.width", 220)


def tab(name, d, key):
    g = d.groupby(key, observed=True).agg(
        n=("res", "size"),
        bld=("building", "nunique"),
        res=("res", "mean"),
        level=("d", "mean"),
        low_stored=("cdf", lambda x: (x < 0.05).mean()),
        low_approx=("place0", lambda x: (x < 0.05).mean()),
        low=("place", lambda x: (x < 0.05).mean()),
        high=("place", lambda x: (x > 0.95).mean()),
        sdz=("z", "std"),
    )
    print(f"\n{name}")
    print(g.round(4).to_string())


print(run, "from", y0, "ads with a last training ad of the unit", len(h))
tab("by kind, after the kind's level from the other half", h, "kind")
tab("by kind and half", h, ["kind", "half"])
h["down"] = h.kind.isin(["bed down", "bath down", "both down"])
h["up"] = h.kind.isin(["bed up", "bath up", "both up"])
h["cls"] = np.select(
    [h.up, h.down, h.kind == "mixed"],
    ["more rooms than the last ad", "fewer rooms than the last ad", "mixed"],
    "same as the last ad",
)
tab("by class and half", h, ["cls", "half"])
tab("fewer rooms: by year", h[h.down], "year")
tab("more rooms: by year", h[h.up], "year")
