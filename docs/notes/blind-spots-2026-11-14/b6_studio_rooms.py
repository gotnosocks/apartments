"""S16, part 6, written after the precision reads: split `studio_rooms` by the coded room count.

The precision reader found 4 of 30 `studio_rooms` matches to be units with a bedroom, and all 30
had 4 or 5 coded rooms, while 11 of the 12 overpriced bedrooms-too-low reads it catches have 5
to 8. So I count L1's studio rows by coded room count (4, 5, 6, 7 and 8 to 20) and give, for the
held-out ads of each, L1's mean gap with a building-clustered SE and the share inside its 80%
interval, next to the data-error reads of the draw that fall in each. This split is post hoc and
has no precision read of its own.

The draw picked its 400 ads by their gap, and 12 of the held-out ads in these buckets are its
bedrooms-too-low reads. So I leave all 400 out of the held-out figures (`held`) and keep the
figures with them beside (`held_with_drawn`), for each bucket and for 5 to 20 rooms together."""

import json

import numpy as np
import pandas as pd

OUT = "/data1/apartments/tmp/blind-spots-2026-11-14/"
RUN = "/data1/apartments/frontier/runs/drift-building-phase-b0-latest-9a7830fb-l1/"
DATA = (
    "/data1/apartments/frontier/datasets/"
    "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise/rows.parquet"
)
CODES = "/data1/apartments/external/listing-codes/20261023-ks/listing-codes.parquet"

d = pd.read_parquet(DATA, columns=["listing_id", "building", "bedrooms"])
a = np.load(RUN + "pred_scores.npz", allow_pickle=True)
d["held"] = a["heldout"]
assert (d.listing_id[d.held].to_numpy() == a["listing"]).all()
qs = list(a["quantiles"])
d["gap"], d["in80"] = np.nan, False
d.loc[d.held, "gap"] = a["y"] - a["pred"]
d.loc[d.held, "in80"] = (a["y"] >= a["q"][:, qs.index(0.1)]) & (
    a["y"] <= a["q"][:, qs.index(0.9)]
)
d["drawn"] = d.listing_id.isin(set(pd.read_parquet(OUT + "draw.parquet").listing_id))
d = d.merge(
    pd.read_parquet(CODES, columns=["listing_id", "rooms"]), on="listing_id", how="left"
)
s = d[(d.bedrooms == 0) & d.rooms.between(4, 20)].copy()
s["bucket"] = pd.cut(s.rooms, [3, 4, 5, 6, 7, 20], labels=["4", "5", "6", "7", "8-20"])

reads = (
    pd.read_parquet(OUT + "labels.parquet")
    .merge(pd.read_parquet(OUT + "key.parquet"), on="read_id")
    .merge(pd.read_parquet(OUT + "draw.parquet")[["listing_id", "group"]])
)
reads = reads[reads.subtype == "beds_low"].merge(
    s[["listing_id", "bucket"]], on="listing_id"
)


def cluster_mean_se(v, b):
    v = np.asarray(v, float)
    t = pd.Series(v - v.mean()).groupby(np.asarray(b)).sum()
    return float(np.sqrt(len(t) / (len(t) - 1) * (t**2).sum()) / len(v))


def held_stats(h):
    return {
        "ads": len(h),
        "mean_gap": float(h.gap.mean()) if len(h) else None,
        "mean_gap_se": cluster_mean_se(h.gap, h.building) if len(h) > 1 else None,
        "in80": float(h.in80.mean()) if len(h) else None,
    }


buckets = {str(k): g for k, g in s.groupby("bucket", observed=True)}
buckets["5-20"] = s[s.rooms >= 5]
res = {}
for k, g in buckets.items():
    on = reads.bucket.astype(str).isin(["5", "6", "7", "8-20"] if k == "5-20" else [k])
    res[k] = {
        "rows": len(g),
        "buildings": int(g.building.nunique()),
        "held": held_stats(g[g.held & ~g.drawn]),
        "held_with_drawn": held_stats(g[g.held]),
        "drawn_held": int((g.held & g.drawn).sum()),
        "beds_low_reads": reads[on].group.value_counts().to_dict(),
    }
    print(k, json.dumps(res[k]))
json.dump(res, open(OUT + "studio_rooms_split.json", "w"), indent=1)
