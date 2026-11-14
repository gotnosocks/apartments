"""Counts for the note on the co-op column: the column against the 26v2 tenure that j9 and L1
read, the candidate co-op classes, S5c's co-op held-out ads and L1's held-out co-op ads.

Run from the repo root inside a memory scope:

    systemd-run --user --scope -q -p MemoryMax=3G env JAX_PLATFORMS=cpu \
        /data1/apartments/venvs/nj-frontier/bin/python docs/notes/coop-column-2026-11-13/count.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "frontier/src"))
from rentfrontier import b0coop, building_attrs  # noqa: E402

DS = Path("/data1/apartments/frontier/datasets")
OUT = DS / "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-coop"
L1 = Path("/data1/apartments/frontier/runs/drift-building-phase-b0-latest-9a7830fb-l1")
J9 = Path("/data1/apartments/frontier/runs/drift-building-b0-market-67d14e17-j9")
SAVE = Path("/data1/apartments/tmp/sprint-20261113/coop-count.json")
CANDIDATES = ("C6", "C8", "D0", "D4", "CB", "DB", "R9", "A8")


def cluster_se(x, b):
    """SE of the sum of `x`, clustered by `b`."""
    t = pd.Series(np.asarray(x)).groupby(np.asarray(b)).sum()
    return float(np.sqrt(len(t) * t.var(ddof=1)))


res = {}
d = pd.read_parquet(
    OUT / "rows.parquet",
    columns=["listing_id", "building", "unit_id", "price_at", "coop", "condo"],
)
attrs = pd.read_parquet(building_attrs.ATTRS, columns=["building", "tenure"])
now = d.building.astype(str).map(attrs.set_index("building").tenure).fillna("rental")
res["rows"] = len(d)
res["as_of_vs_26v2"] = {
    f"coop {a} / 26v2 {b}": int(n)
    for (a, b), n in pd.crosstab(d.coop, now).stack().items()
}
res["condo_vs_bld_condo"] = {
    f"condo {a} / bld:condo {b}": int(n)
    for (a, b), n in pd.crosstab(d.condo, now.eq("condo")).stack().items()
}
year = d.price_at.dt.year
res["coop_rows_by_year"] = {
    str(y): [int(g.coop.sum()), int((now[g.index] == "coop").sum())]
    for y, g in d.groupby(year)
}
flips = d.groupby("building").coop.agg(["any", "all"])
res["buildings_coop_some_rows_only"] = int((flips["any"] & ~flips["all"]).sum())

# The candidate classes: lots of the dataset's buildings in 26v2, and their rows.
reg = pd.read_parquet(building_attrs.REGISTRY, columns=["building", "bbl"])
lots = reg.drop_duplicates("building").set_index("building").bbl.astype(str)
table = b0coop.read_releases(b0coop.RELEASES, set(lots[lots.index.isin(d.building)]))
last = table[table.release == "26v2"].set_index("bbl").bldgclass
cls = d.building.astype(str).map(lots).map(last)
found = b0coop.classes(d, lots, table)
for name, m in (
    ("condo_only_in_26v2", ~d.condo & now.eq("condo")),
    ("coop_only_in_26v2", ~d.coop & now.eq("coop")),
    ("coop_only_as_of", d.coop & ~now.eq("coop")),
):
    m = m.to_numpy()
    res[name] = {
        "status": {str(k): int(n) for k, n in found.status[m].value_counts().items()},
        "as_of_class": {
            str(k): int(n) for k, n in found.bldgclass[m].value_counts().head(8).items()
        },
        "buildings": int(d.building[m].nunique()),
        "last_year": {
            str(k): int(n)
            for k, n in d.price_at.dt.year[m].value_counts().sort_index().items()
        },
    }
# For rows whose lot is missing from their release: how long after the row's month the lot
# first appears in a release, and whether 26v2 dates the building to that year or later.
missing = (found.status == "lot not in release").to_numpy()
pub = pd.to_datetime(
    table.dropna(subset=["published"])
    .drop_duplicates("release")
    .set_index("release")
    .published
)
first = (
    table.dropna(subset=["published"])
    .assign(at=lambda t: t.release.map(pub))
    .groupby("bbl")
    .at.min()
)
wait = (
    found.bbl[missing].map(first).to_numpy() - b0coop.months(d.price_at[missing])
) / np.timedelta64(365, "D")
built = pd.to_numeric(
    pd.read_parquet(building_attrs.PLUTO, columns=["bbl", "yearbuilt"])
    .drop_duplicates("bbl")
    .set_index("bbl")
    .yearbuilt,
    errors="coerce",
)
yb = found.bbl[missing].map(built).to_numpy()
res["lot_not_in_release"] = {
    "rows": int(missing.sum()),
    "buildings": int(d.building[missing].nunique()),
    "years_until_lot_appears_quartiles": np.nanquantile(
        wait, [0.25, 0.5, 0.75]
    ).tolist(),
    "rows_built_in_or_after_row_year_minus_1": int(
        (yb >= d.price_at.dt.year[missing].to_numpy() - 1).sum()
    ),
    "rows_26v2_condo": int(now[missing].eq("condo").sum()),
}
res["candidates_26v2"] = {
    k: {
        "buildings": int(d.building[cls == k].nunique()),
        "rows": int((cls == k).sum()),
        "rows_as_of_coop": int(d.coop[cls == k].sum()),
    }
    for k in CANDIDATES
}

# L1's held-out ads.
a = np.load(L1 / "pred_scores.npz", allow_pickle=True)
held = a["heldout"]
assert (d.listing_id.astype(str).to_numpy()[held] == a["listing"]).all()
h = d[held].reset_index(drop=True)
gap = a["y"] - a["pred"]
for name, m in (("coop", h.coop.to_numpy()), ("other", ~h.coop.to_numpy())):
    res[f"l1_heldout_{name}"] = {
        "n": int(m.sum()),
        "buildings": int(h.building[m].nunique()),
        "median_gap": float(gap[m].mean()),
        "se": cluster_se(gap[m], h.building.to_numpy()[m]) / int(m.sum()),
    }

# S5c's co-op held-out ads: j9's held-out ads whose lot is C6, C8, D0 or D4 in 26v2.
r9 = json.loads((J9 / "result.json").read_text())
d9 = pd.read_parquet(
    Path(r9["dataset"]) / "rows.parquet",
    columns=["listing_id", "building", "price_at"],
)
h9 = d9[np.load(J9 / "posterior.npz")["heldout"]].reset_index(drop=True)
del d9
cls9 = h9.building.astype(str).map(lots).map(last).fillna("")
s5c = cls9.isin(building_attrs.COOP_CLASSES).to_numpy()
t9 = b0coop.read_releases(b0coop.RELEASES, set(lots[lots.index.isin(h9.building)]))
found = b0coop.classes(h9, lots, t9)
_, coop9 = b0coop.tenure(found.bldgclass.to_numpy())
in_l1 = h9.listing_id.astype(str).isin(set(d.listing_id.astype(str))).to_numpy()
l1_coop = (
    h9.listing_id.astype(str).map(d.set_index(d.listing_id.astype(str)).coop).eq(True)
)
res["s5c"] = {
    "j9_heldout": len(h9),
    "s5c_coop": int(s5c.sum()),
    "flagged_by_rule_at_j9_price_at": int((s5c & coop9).sum()),
    "s5c_coop_in_l1_dataset": int((s5c & in_l1).sum()),
    "flagged_in_l1_dataset": int((s5c & l1_coop.to_numpy()).sum()),
    "flagged_not_s5c_coop": int((~s5c & coop9).sum()),
    "s5c_coop_missed_by_release": {
        f"{r} {c}": int(n)
        for (r, c), n in found[s5c & ~coop9]
        .assign(release=lambda f: f.release.fillna("none"))
        .groupby(["release", "bldgclass"])
        .size()
        .items()
    },
    "s5c_coop_missed_status": {
        str(k): int(n) for k, n in found.status[s5c & ~coop9].value_counts().items()
    },
}
print(json.dumps(res, indent=1))
SAVE.write_text(json.dumps(res, indent=1))
