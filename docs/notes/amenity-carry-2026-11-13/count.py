"""Counts for the note on carrying unit codes from a unit's earlier ads: the rows gaining
each code, overall and among L1's held-out ads, the gains that rest on an earlier ad still
listed when the row's ad opened, the codes by a row's count of earlier ads, and L1's held-out
gap for the rows gaining a code.

Run from the repo root inside a memory scope:

    systemd-run --user --scope -q -p MemoryMax=3G env JAX_PLATFORMS=cpu \
        /data1/apartments/venvs/nj-frontier/bin/python docs/notes/amenity-carry-2026-11-13/count.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "frontier/src"))
from rentfrontier import b0amenitycarry as ac  # noqa: E402

DS = Path("/data1/apartments/frontier/datasets")
OUT = DS / "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-amenitycarry"
L1 = Path("/data1/apartments/frontier/runs/drift-building-phase-b0-latest-9a7830fb-l1")
SAVE = Path("/data1/apartments/tmp/sprint-20261113/amenitycarry-count.json")
SHOW = (
    "feat:HARDWOOD_FLOORS",
    "feat:CENTRAL_AC",
    "feat:PRIVATE_OUTDOOR_SPACE",
    "feat:VIEW",
    "fireplace:WOOD",
    "private_outdoor:PATIO",
    "views:WATER",
)
BINS = [-1, 0, 1, 2, 3, 5, 1000]
LABELS = ["0", "1", "2", "3", "4-5", "6+"]


def cluster_se(x, b):
    """SE of the sum of `x`, clustered by `b`."""
    t = pd.Series(np.asarray(x)).groupby(np.asarray(b)).sum()
    return float(np.sqrt(len(t) * t.var(ddof=1)))


def bit(m, k):
    return (m >> k) & 1 == 1


entry = json.loads((OUT / "manifest.json").read_text())["amenity_carry"]
names = entry["codes_carried"]
codes = names[:-1]
d = pd.read_parquet(
    OUT / "rows.parquet",
    columns=[
        "listing_id",
        "audit_id",
        "building",
        "unit_id",
        "price_at",
        *[ac.PREFIX + n for n in names],
        "carry:earlier_ads",
    ],
)
ids = set(d.listing_id.astype(str))
table, read = ac.read_codes(Path(entry["codes"]["path"]), ids)
assert read == codes
own = ac.masks(d, table, codes)
del table
union = np.zeros(len(d), np.int64)
for k, n in enumerate(names):
    union |= d[ac.PREFIX + n].to_numpy().astype(np.int64) << k
d = d.drop(columns=[ac.PREFIX + n for n in names])
gain = union & ~own
earlier = d["carry:earlier_ads"].to_numpy()
res = {"rows": len(d), "rows_with_earlier_ads": int((earlier > 0).sum())}

# The ads file: opening days, closing days and the fetch times of the records.
t = pq.read_table(
    entry["ads"]["path"], columns=["listing_id", "on_day", "off_day", "fetched"]
)
t = t.filter(
    pc.is_in(
        t["listing_id"], value_set=pa.array(sorted(ids)).cast(t["listing_id"].type)
    )
)
a = t.to_pandas().set_index("listing_id").reindex(d.listing_id.astype(str))
del t
on = pd.to_datetime(a.on_day).to_numpy().astype("datetime64[D]")
off = pd.to_datetime(a.off_day).to_numpy().astype("datetime64[D]")
price_day = ac.days(d.price_at)
on_n = np.where(np.isnat(on), np.nan, on.astype(np.int64))
opened = ac.opening_days(d, pd.Series(on_n, index=d.listing_id.astype(str).to_numpy()))
fetched = pd.to_datetime(a.fetched, utc=True)
del a
res["ads"] = {
    "rows_without_on_day": int(np.isnat(on).sum()),
    "rows_on_day_after_price_day": int((on_n > price_day).sum()),
    "rows_on_day_before_price_day": int((on_n < price_day).sum()),
    "fetched_min": str(fetched.min()),
    "fetched_max": str(fetched.max()),
}

# Gains that rest on an earlier ad still listed when the row's ad opened: off_day missing or
# on or after the row's opening day.
order, group = ac.unit_order(d)
r, e, dropped = ac.earlier_pairs(group, opened[order])
r, e = order[r], order[e]
off_n = np.where(np.isnat(off), np.inf, off.astype(np.int64))
closed = off_n[e] < opened[r]
shut = own.copy()
np.bitwise_or.at(shut, r[closed], own[e[closed]])
res["pairs"] = {
    "read": len(r),
    "opened_same_day_or_later": dropped,
    "earlier_ad_still_listed": int((~closed).sum()),
}
open_only = gain & ~shut
res["rows_gaining_only_from_a_listed_ad"] = int((open_only != 0).sum())

# L1's held-out ads, in the same row order.
s = np.load(L1 / "pred_scores.npz", allow_pickle=True)
held = s["heldout"]
assert (d.listing_id.astype(str).to_numpy()[held] == s["listing"]).all()
is_held = np.zeros(len(d), bool)
is_held[held] = True
states = bit(own, len(codes))

# L1's `umean:` columns average each code over the row and the unit's training rows priced on
# earlier days, so a positive unit mean marks the union over the earlier training ads. Rows
# where the union over every earlier ad differs from that one read a held-out earlier ad.
train = ~is_held[e]
seen = own.copy()
np.bitwise_or.at(seen, r[train], own[e[train]])
res["union_differs_from_training_union"] = {
    "heldout": int((seen != union)[is_held].sum()),
    "training": int((seen != union)[~is_held].sum()),
}
res["codes"] = {
    n: {
        "own": int(bit(own, k).sum()),
        "carried": int(bit(union, k).sum()),
        "gaining": int(bit(gain, k).sum()),
        "gaining_on_ads_stating_no_features": int((bit(gain, k) & ~states).sum()),
        "gaining_only_from_a_listed_ad": int(bit(open_only, k).sum()),
        "heldout_own": int(bit(own, k)[is_held].sum()),
        "heldout_gaining": int(bit(gain, k)[is_held].sum()),
    }
    for k, n in enumerate(names)
}
res["heldout"] = {
    "rows": int(is_held.sum()),
    "gaining_any": int((gain[is_held] != 0).sum()),
    "with_earlier_ads": int((earlier[is_held] > 0).sum()),
}
res["rows_gaining_any"] = int((gain != 0).sum())
res["gaining_any_on_ads_stating_no_features"] = int(((gain != 0) & ~states).sum())

# Codes by the row's count of earlier ads: the share of rows with each code, own and carried,
# and the mean count of the 20 codes.
band = np.asarray(pd.cut(earlier, BINS, labels=LABELS)).astype(str)
n_own = sum(bit(own, k).astype(int) for k in range(len(codes)))
n_carry = sum(bit(union, k).astype(int) for k in range(len(codes)))
by = {}
for b in LABELS:
    m = band == b
    by[b] = {
        "rows": int(m.sum()),
        "states_features_own": float(states[m].mean()),
        "states_features_carried": float(bit(union, len(codes))[m].mean()),
        "codes_own": float(n_own[m].mean()),
        "codes_carried": float(n_carry[m].mean()),
        **{
            f"{n} own/carried": [
                float(bit(own, names.index(n))[m].mean()),
                float(bit(union, names.index(n))[m].mean()),
            ]
            for n in SHOW
        },
    }
res["by_earlier_ads"] = by

# Own codes switching between a unit's consecutive ads, against the carried codes, which only
# switch on.
first = np.r_[True, group[1:] != group[:-1]] | (group < 0)
cur, prev = order[1:][~first[1:]], order[:-1][~first[1:]]
res["consecutive_pairs"] = {
    "pairs": len(cur),
    **{
        n: {
            "own_on": int((bit(own, k)[cur] & ~bit(own, k)[prev]).sum()),
            "own_off": int((~bit(own, k)[cur] & bit(own, k)[prev]).sum()),
            "carried_on": int((bit(union, k)[cur] & ~bit(union, k)[prev]).sum()),
            "carried_off": int((~bit(union, k)[cur] & bit(union, k)[prev]).sum()),
        }
        for k, n in enumerate(names)
        if n in SHOW
    },
}

# L1's held-out gap (log ask less the median) for rows gaining a code against the rest,
# within bands of earlier ads, with SEs clustered by building.
gap = s["y"] - s["pred"]
hb = band[held]
bld = d.building.to_numpy()[held]
gaps = {}
for label, g in (
    ("any", gain[held] != 0),
    ("feat:HARDWOOD_FLOORS", bit(gain, names.index("feat:HARDWOOD_FLOORS"))[held]),
    ("states_features", bit(gain, len(codes))[held]),
):
    rows = {}
    for b in ["all", *LABELS[1:]]:
        inb = np.ones(len(gap), bool) if b == "all" else hb == b
        for side, m in (("gaining", inb & g), ("not", inb & ~g)):
            if m.sum() < 30:
                continue
            rows[f"{b} {side}"] = {
                "n": int(m.sum()),
                "gap_pct": 100 * float(gap[m].mean()),
                "se_pct": 100 * cluster_se(gap[m], bld[m]) / int(m.sum()),
            }
    gaps[label] = rows
res["l1_heldout_gap"] = gaps
print(json.dumps(res, indent=1))
SAVE.write_text(json.dumps(res, indent=1))
