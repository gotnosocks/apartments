"""Changed-count ads by the kind of change, and by whether the counts equal the unit's last training ad."""

import sys

import numpy as np
import pandas as pd

DS = "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc/rows.parquet"
run, tag, y0 = sys.argv[1], sys.argv[2], int(sys.argv[3])
h = pd.read_parquet(f"baths-{tag}.parquet")
h = h[h.year >= y0].copy()
r = pd.read_parquet(
    DS,
    columns=[
        "listing_id",
        "unit_id",
        "building",
        "price_at",
        "bedrooms",
        "full_baths",
        "half_baths",
    ],
)
s = np.load(f"/data1/apartments/frontier/runs/{run}/pred_scores.npz", allow_pickle=True)
r["held"] = s["heldout"]
r["apt"] = r.unit_id.str.replace(r"~\d+$", "", regex=True)
r["baths"] = r.full_baths + 0.5 * r.half_baths.fillna(0)
t = r[~r.held & r.apt.notna()].sort_values("price_at")
last = t.groupby(["building", "apt"]).agg(
    last_bed=("bedrooms", "last"),
    last_bath=("baths", "last"),
    last_day=("price_at", "last"),
    n_layouts=("bedrooms", lambda b: 0),
)
lay = (
    t.drop_duplicates(["building", "apt", "bedrooms", "baths"])
    .groupby(["building", "apt"])
    .size()
    .rename("layouts")
)
h = h.merge(
    last.drop(columns="n_layouts"),
    left_on=["building", "apt"],
    right_index=True,
    how="left",
).merge(lay, left_on=["building", "apt"], right_index=True, how="left")
h["low"], h["high"] = h.cdf < 0.05, h.cdf > 0.95
h["dbed"] = h.bedrooms - h.last_bed
h["dbath"] = h.baths - h.last_bath
pd.set_option("display.width", 220)


def tab(name, d, key):
    g = d.groupby(key, observed=True).agg(
        n=("z", "size"),
        bld=("building", "nunique"),
        res=("res", "mean"),
        sdz=("z", "std"),
        low=("low", "mean"),
        high=("high", "mean"),
        absres=("res", lambda x: x.abs().median()),
    )
    print(f"\n{name}")
    print(g[g.n >= 40].round(4).to_string())


c = h[~h.same].copy()
print("changed-count ads", len(c), "of", len(h))
c["vs_last"] = np.where(
    (c.dbed == 0) & (c.dbath == 0),
    "same as the last training ad",
    "differs from the last training ad",
)
tab("by whether the counts equal the unit's last training ad", c, ["vs_last", "half"])
tab(
    "same as last: by layouts seen in training",
    c[c.vs_last.str.startswith("same")],
    c.layouts.clip(upper=4),
)
d = c[c.vs_last.str.startswith("differs")].copy()
d["kind"] = np.select(
    [
        (d.dbed == 1) & (d.dbath == 0),
        (d.dbed == -1) & (d.dbath == 0),
        (d.dbed >= 2),
        (d.dbed <= -2),
        (d.dbed == 0) & (d.dbath > 0),
        (d.dbed == 0) & (d.dbath < 0),
        (d.dbed > 0) & (d.dbath > 0),
        (d.dbed < 0) & (d.dbath < 0),
    ],
    [
        "bed +1",
        "bed -1",
        "bed +2 or more",
        "bed -2 or more",
        "bath up",
        "bath down",
        "both up",
        "both down",
    ],
    "mixed",
)
tab("differs from last: kind of change", d, "kind")
tab("differs from last: kind of change by half", d, ["kind", "half"])
d["gap"] = pd.cut(
    (
        pd.to_datetime(d.day).dt.tz_localize(None)
        - pd.to_datetime(d.last_day).dt.tz_localize(None)
    ).dt.days
    / 365.25,
    [-1, 0.5, 2, 5, 50],
)
tab("differs from last: years since the last training ad", d, "gap")
tab("differs from last: bedrooms of the ad", d, "bd")
tab(
    "differs from last: baths were whole before and half now, or the reverse",
    d,
    [
        (d.baths % 1 != 0).rename("half bath now"),
        (d.last_bath % 1 != 0).rename("half bath before"),
    ],
)
