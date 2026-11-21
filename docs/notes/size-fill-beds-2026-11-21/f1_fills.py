"""Size fills across bedroom counts: the current fill against one matched on bedrooms.

Reads the rows `unit_features.main` reads (bedrooms, labels, stated sizes; no rent),
reruns `sizes`, checks it against the snapshot, and builds a fill matched on bedroom count.
"""

import numpy as np
import pandas as pd
from rentfrontier import unit_features as uf

SNAP = "/data1/apartments/external/unit-features/20261021-16cea7c/unit_features.parquet"
OUT = "/data1/apartments/tmp/size-fill-beds/fills.parquet"
cols = [
    "listing_id",
    "building",
    "page",
    "bedrooms",
    "square_feet",
    "building_floor_count",
]
rows = pd.read_parquet(uf.ROWS, columns=cols)
cur = uf.sizes(rows)
snap = pd.read_parquet(SNAP, columns=["listing_id", "sqft", "size_source"])
snap["listing_id"] = snap.listing_id.astype(str)
m = cur.merge(snap, on="listing_id", suffixes=("", "_snap"))
same = (m.size_source == m.size_source_snap) & (
    np.isclose(m.sqft, m.sqft_snap) | (m.sqft.isna() & m.sqft_snap.isna())
)
print(
    f"rerun vs snapshot: {len(cur)} listings, {len(m)} in both, {same.mean():.4f} same"
)

# The same pieces as uf.sizes, kept for the matched fill.
r = rows.drop_duplicates("listing_id").reset_index(drop=True)
lo, hi = uf.SQFT_RANGE
sq = r.square_feet.where((r.square_feet >= lo) & (r.square_feet <= hi))
lab = uf.unit_label(r.page)
parsed = {s: uf.floor_and_line(s) for s in lab.unique()}
floor = lab.map(lambda s: parsed[s][0]).astype(float)
line = lab.map(lambda s: parsed[s][1])
top = (floor >= r.building_floor_count - 1).fillna(False)
special = lab.str.contains(uf.SPECIAL)
building = r.building.astype(str)
unit = pd.Series(np.where(lab != "", building + "|" + lab, None), index=r.index)
beds = r.bedrooms.clip(upper=4)
bs = beds.astype(str)
on_line = line.notna() & ~special & ~top & (lab != "")
key = pd.Series(
    np.where(on_line, building + "|" + line.astype(str) + "|" + bs, None), index=r.index
)
assert (r.listing_id.astype(str) == cur.listing_id).all()

# Which units hold stated sizes from more than one bedroom count, and from which.
st = pd.DataFrame({"unit": unit, "beds": beds})[sq.notna() & unit.notna()]
unit_beds = st.groupby("unit").beds.agg(lambda b: frozenset(b))
ub = unit.map(unit_beds)
src = cur.size_source.to_numpy()
# A unit fill draws on another bedroom count when any of the unit's stated sizes comes
# from a bedroom count other than the listing's own.
cross_unit = (src == "unit") & np.array(
    [isinstance(u, frozenset) and not (u <= {b}) for u, b in zip(ub, beds)]
)
# A line fill draws on another bedroom count when a unit filed under its key has stated
# sizes from a bedroom count other than the key's.
unit_sq = unit.map(sq[unit.notna()].groupby(unit[unit.notna()]).median())
units = pd.DataFrame({"key": key, "unit": unit, "sq": unit_sq, "beds": beds}).dropna()
units = units.drop_duplicates("unit")
units["mixed"] = [
    not (unit_beds.get(u, frozenset()) <= {b}) for u, b in zip(units.unit, units.beds)
]
key_mixed = units.groupby("key").mixed.any()
cross_line = (src == "line") & key.map(key_mixed).fillna(False).to_numpy().astype(bool)

# The matched fill: unit and line layers on the same bedroom count.
ukey = pd.Series(np.where(unit.notna(), unit + "|" + bs, None), index=r.index)
unit_m = ukey.map(sq[ukey.notna()].groupby(ukey[ukey.notna()]).median())
um = pd.DataFrame({"key": key, "ukey": ukey, "sq": unit_m}).dropna()
line_m = key.map(um.drop_duplicates("ukey").groupby("key").sq.median())
sqft_m = sq.fillna(unit_m).fillna(line_m)
src_m = np.select(
    [sq.notna(), unit_m.notna(), line_m.notna()], ["stated", "unit", "line"], "none"
)
f = pd.DataFrame(
    {
        "listing_id": cur.listing_id,
        "beds": beds.to_numpy(),
        "source": src,
        "sqft": cur.sqft.to_numpy(),
        "cross": cross_unit | cross_line,
        "source_m": src_m,
        "sqft_m": sqft_m.to_numpy(),
    }
)
f.to_parquet(OUT)

print("\n1. filled listings whose fill draws on another bedroom count")
for s in ("unit", "line"):
    k = f[f.source == s]
    by = k.groupby(k.beds.clip(upper=3)).cross.agg(["mean", "size"]).round(3)
    print(f"  {s}: {k.cross.mean():.3f} of {len(k)}; by bedrooms (3 = 3+):")
    print("   ", by.to_dict("index"))

print("\n2. 0-1-bedroom listings over 1,000 sq ft")
s01 = f[f.beds <= 1]
for name, k, col in [
    ("stated", s01.source == "stated", "sqft"),
    ("current fills", s01.source.isin(["unit", "line"]), "sqft"),
    ("matched fills", pd.Series(s01.source_m).isin(["unit", "line"]), "sqft_m"),
]:
    print(f"  {name:13}: {np.mean(s01.loc[k, col] > 1000):.4f} of {int(k.sum())}")
for s in ("unit", "line"):
    k = s01.source == s
    print(
        f"    current {s} fills: {np.mean(s01.loc[k, 'sqft'] > 1000):.4f} of {int(k.sum())}"
    )
big = s01[s01.source.isin(["unit", "line"]) & (s01.sqft > 1000)]
fate = np.select(
    [big.source_m == "none", big.sqft_m > 1000, big.sqft_m <= 1000],
    ["no size", "still over", "under 1,000"],
    "?",
)
print(f"  current fills over 1,000 ({len(big)}) under the matched fill:")
print("   ", pd.Series(fate).value_counts().to_dict())
print("    by layer:", pd.crosstab(big.source.to_numpy(), fate).to_dict("index"))
print("    of those drawing on another bedroom count:", int(big.cross.sum()))

print("\n3. listings that lose a size under the matched fill")
had = f.source != "none"
lose = had & (f.source_m == "none")
print(f"  {lose.sum()} of {had.sum()} ({lose.sum() / had.sum():.4f})")
print("   ", lose.groupby(f.beds.clip(upper=3)).sum().to_dict())
moved = had & (f.source_m != "none") & ~np.isclose(f.sqft, f.sqft_m)
print(f"  size changed but kept: {moved.sum()}")
