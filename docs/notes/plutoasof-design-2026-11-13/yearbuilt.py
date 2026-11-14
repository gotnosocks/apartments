"""Split the rows whose year built P1 changes by cause, from `count.py`'s outputs.

I read `reads.parquet` and the two lot tables that `count.py reads OUT` wrote, and the
`moved-*.npz` parts of `count.py columns`. I sort each row whose yearbuilt differs between
its release and 26v2 into one cause, then split the revisions across 1900 by direction and
count which rows of a missing lot move the condo, lot_unknown and two era columns.

    python yearbuilt.py OUT
"""

import sys

import numpy as np
import pandas as pd

OUT = sys.argv[1]
cols = ["held", "release", "status", "key", "key26", "field:yearbuilt"]
cols += ["field:bldgclass", "field:unitsres", "field:numfloors", "field:yearalter1"]
k = pd.read_parquet(f"{OUT}/reads.parquet", columns=cols)
t = pd.read_parquet(f"{OUT}/table.parquet", columns=["key", "yearbuilt"]).set_index(
    "key"
)
t26 = pd.read_parquet(f"{OUT}/table26.parquet", columns=["key", "yearbuilt"]).set_index(
    "key"
)
a = pd.to_numeric(t.yearbuilt.reindex(k.key), errors="coerce").to_numpy()
b = pd.to_numeric(t26.yearbuilt.reindex(k.key26), errors="coerce").to_numpy()
year = 2000 + k.release.str[:2].replace("", "0").astype(int).to_numpy()
d = k["field:yearbuilt"].to_numpy()
missing = (k.status == "lot not in release").to_numpy()
held = k.held.to_numpy()
ok_a, ok_b = a >= 1800, b >= 1800
both = d & ~missing & ok_a & ok_b
revision = both & (b < year)
cases = {
    "lot not in release": d & missing,
    "release blank or 0, 26v2 a year": d & ~missing & ~ok_a & ok_b,
    "26v2 year in or after the release's year (new building)": both & (b >= year),
    "both years before the release's (revision)": revision,
    "26v2 blank or 0": d & ~missing & ~ok_b,
}
for c, m in cases.items():
    print(f"{c:56s} {int(m.sum()):>8,} {int((m & held).sum()):>7,}")
gap = np.abs(a[revision] - b[revision])
print("revision gap quantiles", np.quantile(gap, [0.25, 0.5, 0.75, 0.9]))
up = revision & (a < 1900) & (b >= 1900)
down = revision & (a >= 1900) & (b < 1900)
print("release before 1900, 26v2 1900 on", int(up.sum()), int((up & held).sum()))
print("release 1900 on, 26v2 before 1900", int(down.sum()), int((down & held).sum()))
print("their release years", pd.Series(a[down]).value_counts().head(5).to_dict())
print("their 26v2 years", pd.Series(b[down]).value_counts().head(5).to_dict())
print("their releases", pd.Series(k.release.to_numpy()[down]).value_counts().to_dict())
moved = {}
for p in range(4):
    z = np.load(f"{OUT}/moved-{p}.npz")
    names = list(z["names"])
    for c in ["bld:condo", "bld:lot_unknown", "bld:built_pre1900", "bld:built_2010_on"]:
        m = moved.setdefault(c, np.zeros(len(k), bool))
        m[z["index"]] = z["moved"][:, names.index(c)]
for c, m in moved.items():
    print(c, "missing lot", int((m & missing).sum()), "read", int((m & ~missing).sum()))
for f in ["field:bldgclass", "field:unitsres", "field:numfloors", "field:yearalter1"]:
    m = k[f].to_numpy()
    print(
        f,
        "lot not in release",
        int((m & missing).sum()),
        "read",
        int((m & ~missing).sum()),
    )
