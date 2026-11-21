"""Step 1: every mismatched pair of the zero-bed note's unit mark, and what joined it.

Rows: the training rows of the live Deals run coded 0 bed with no active ledger entry
(`zero-bed-apartments-2026-11-21/z2_marks.py`, `zeros.parquet`). `U_any`: some other ad of the
unit codes 2 or more; `U_strict`: the unit's other typed ads all code 2 or more (`z3_size.py`).
A pair is the 0-bed row and one other ad of its unit coded 2 or more, with bedrooms not set by
an active ledger entry, as z2 counts them.

For each pair I record whether the two ads share the page (the StreetEasy unit URL), whether
they share the page unit (the unit ID less a `~review-` suffix of the unit ledger), and the
units of both ads in the live build's rows file (`label_unit`, after `analysis.label_units`)
and in the live run's dataset (`unit_id`, the fit's unit, after `unit-splits-v4`). Only units,
pages, counts and dates are read. No ask enters any column.
"""

import sys
from pathlib import Path

import duckdb
import pandas as pd

HERE = Path(__file__).resolve().parent
WT = HERE.parents[2]
sys.path.insert(0, str(WT / "pipeline"))
from models.ledger import entries  # noqa: E402

ZB = Path("/data1/apartments/tmp/zero-bed")
OUT = Path("/data1/apartments/tmp/label-reuse")
D = "/data1/apartments/pipeline/datasets"
ADS = f"{D}/ads-417bbdf5ed03f5d3.parquet"
ROWS = f"{D}/rows-4f487ef77bb6ca61.parquet"
LIVE_ROWS = (
    "/data1/apartments/frontier/datasets/"
    "b0-4f487ef77bb6ca61-alldata-dense-nyc-market-bedtext/rows.parquet"
)

rows = entries.read(sorted((WT / "pipeline" / "ledger").glob("*.ndjson")))
gone = {r["retracts"] for r in rows if r["change"] == "retract"}
bedset = sorted(
    str(r["listing_id"])
    for r in rows
    if r["change"] == "set" and r["entry"] not in gone and r.get("bedrooms") is not None
)

Z = pd.read_parquet(ZB / "zeros.parquet")
t = Z[Z.train & ~Z.in_ledger].copy()
t["U_strict"] = (t.u2 > 0) & (t.u1 == 0) & (t.u0 == 0)
u = t[t.U_any][["listing_id", "unit_id", "U_strict"]]
print("U_any rows", len(u), "units", u.unit_id.nunique())
print("U_strict rows", int(u.U_strict.sum()), "units", u[u.U_strict].unit_id.nunique())

c = duckdb.connect()
c.execute("set memory_limit='2GB'; set threads=2")
c.execute(f"set temp_directory='{OUT}/duck'")
c.register("u", u)
c.register("bedset", pd.DataFrame({"listing_id": bedset}))
c.execute(f"""create table a as select listing_id, unit_id,
    regexp_replace(unit_id, '~review-.*$', '') page_unit, building, page,
    regexp_extract(page, '[^/]+$') AS "label", bedrooms, first_day, on_day, off_day, fate, in_rows
  from '{ADS}'""")
c.execute(f"""create table r as select r.listing_id, r.label_unit, r.split_unit, d.unit_id fit_unit
  from '{ROWS}' r left join '{LIVE_ROWS}' d using (listing_id)""")
P = c.execute("""
  select u.listing_id z_id, u.U_strict, z.unit_id, z.page z_page, z.page_unit z_page_unit,
    z."label" z_label, z.building, z.first_day z_first, z.on_day z_on, z.off_day z_off,
    o.listing_id o_id, o.page o_page, o.page_unit o_page_unit, o."label" o_label,
    o.bedrooms o_bed, o.first_day o_first, o.on_day o_on, o.off_day o_off, o.fate o_fate,
    o.in_rows o_in_rows,
    rz.label_unit z_label_unit, rz.split_unit z_split, rz.fit_unit z_fit,
    ro.label_unit o_label_unit, ro.split_unit o_split, ro.fit_unit o_fit
  from u join a z on z.listing_id = u.listing_id
  join a o on o.unit_id = z.unit_id and o.listing_id <> z.listing_id
  left join r rz on rz.listing_id = z.listing_id
  left join r ro on ro.listing_id = o.listing_id
  where o.bedrooms >= 2 and o.listing_id not in (select listing_id from bedset)
""").df()
P["same_page"] = P.z_page == P.o_page
P["same_page_unit"] = P.z_page_unit == P.o_page_unit
P["o_in_fit"] = P.o_fit.notna()
P["same_fit_unit"] = P.z_fit == P.o_fit
P["same_label_unit"] = P.z_label_unit == P.o_label_unit
P.to_parquet(OUT / "mark_pairs.parquet")
print("pairs", len(P), "rows", P.z_id.nunique(), "units", P.unit_id.nunique())


def tally(g: pd.DataFrame, name: str) -> None:
    print(
        f"\n== {name}: pairs {len(g)}, rows {g.z_id.nunique()}, units {g.unit_id.nunique()}"
    )
    for col in ["same_page", "same_page_unit", "o_in_fit", "same_label_unit"]:
        print(col, g[col].value_counts(dropna=False).to_dict())
    print(
        "2+ ad also a row of the live run, same fit unit:",
        g[g.o_in_fit].same_fit_unit.value_counts().to_dict(),
    )
    print("o_fate", g.o_fate.value_counts(dropna=False).to_dict())
    rowwise = g.groupby("z_id").agg(
        any_other_page=("same_page", lambda s: (~s).any()),
        all_same_page=("same_page", "all"),
    )
    print(
        "rows with every pair on one page",
        int(rowwise.all_same_page.sum()),
        "rows with some pair on another page",
        int(rowwise.any_other_page.sum()),
    )


tally(P, "U_any")
tally(P[P.U_strict], "U_strict")
print("\npairs on two pages:")
print(
    P[~P.same_page][
        ["unit_id", "z_page", "o_page", "z_bed" if "z_bed" in P else "o_bed"]
    ]
    .drop_duplicates("unit_id")
    .head(20)
    .to_string()
)
