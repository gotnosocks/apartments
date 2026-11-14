"""Market disagreement, part 5: the pattern for the flagged cause, `duplex_multilevel`.

The pattern is S7's unit-level duplex match (`dup_unit` of `causal-screens-2026-11-13/
s7_text.py`): `duplex` or `triplex` in the listing's latest description, unless the text calls
the building a duplex. I count the rows of L1's dataset it marks, and on the held-out ads
outside the 400 drawn I take L1's gap (mean with a building-clustered SE, median), the spread
of the gap (median absolute deviation) against all other held-out ads, and the share inside
L1's 80% interval. On the kept ads of part 1 I add the pattern's days, cuts and score D, over
all tenths of z and in the lowest and highest tenth."""

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "causal-screens-2026-11-13")
)
import common as cm  # noqa: E402

OUT = "/data1/apartments/tmp/market-disagreement-2026-11-14/"
S7 = "/data1/apartments/tmp/sprint-20261113/s7_text.parquet"


def mad(x):
    return float(np.median(np.abs(x - np.median(x))))


def clustered(x, b):
    x = np.asarray(x, float)
    t = pd.Series(x - x.mean()).groupby(np.asarray(b)).sum()
    return float(x.mean()), float(
        np.sqrt(len(t) / (len(t) - 1) * (t**2).sum()) / len(x)
    )


d = cm.rows()
d["listing_id"] = d.listing_id.astype(str)
s7 = pd.read_parquet(S7, columns=["listing_id", "dup_unit"])
s7["listing_id"] = s7.listing_id.astype(str)
d = d.merge(s7.drop_duplicates("listing_id"), on="listing_id", how="left")
d["dup"] = d.dup_unit.fillna(False).astype(bool)
h = cm.heldout(d)
drawn = set(
    pd.read_parquet(OUT + "draw.parquet", columns=["listing_id"]).listing_id.astype(str)
)
out = {
    "rows": int(d.dup.sum()),
    "train_rows": int((d.dup & ~d.held).sum()),
    "held_rows": int((d.dup & d.held).sum()),
    "units": int(d.ukey[d.dup].nunique()),
    "buildings": int(d.building[d.dup].nunique()),
}
h = h[~h.listing_id.astype(str).isin(drawn)]
on, off = h[h.dup], h[~h.dup]
m, se = clustered(on.gap, on.building)
out["held_outside_draw"] = {
    "ads": len(on),
    "gap_mean": m,
    "gap_se": se,
    "gap_median": float(on.gap.median()),
    "spread_ratio": mad(on.gap.to_numpy()) / mad(off.gap.to_numpy()),
    "in80": float(on.in80.mean()),
    "in80_others": float(off.in80.mean()),
}
o = pd.read_parquet(OUT + "outcomes.parquet")
o = o[~o.listing_id.isin(drawn)].merge(
    d[["listing_id", "dup"]], on="listing_id", how="left"
)
market = {}
for name, part in (
    ("all", o),
    ("lowest_tenth", o[o.tenth == 1]),
    ("highest_tenth", o[o.tenth == 10]),
):
    a, b = part[part.dup], part[~part.dup]
    dm, dse = clustered(a.D, a.building)
    market[name] = {
        "ads": len(a),
        "days_median": float(a.days.median()),
        "days_median_others": float(b.days.median()),
        "cut": float(a.cut.mean()),
        "cut_others": float(b.cut.mean()),
        "gone_7": float((a.days <= 7).mean()),
        "gone_7_others": float((b.days <= 7).mean()),
        "D_mean": dm,
        "D_se": dse,
        "r_days_mean": float(a.r_days.mean()),
        "r_cut_mean": float(a.r_cut.mean()),
    }
out["market"] = market
out["share_by_tenth"] = o.groupby("tenth").dup.mean().round(4).to_dict()
json.dump(out, open(OUT + "pattern.json", "w"), indent=1)
print(json.dumps(out, indent=1))
