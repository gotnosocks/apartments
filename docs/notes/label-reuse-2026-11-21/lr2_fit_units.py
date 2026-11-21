"""Step 2: the same check on the units the fit uses.

`lr1_pairs.py` finds every pair of the zero-bed unit mark on one page. Here the unit is the
live build's: for each 0-bed training row of the live run (no active ledger entry), the rows of
its label unit (rows file `label_unit`, after `analysis.label_units` under v17) and of its fit
unit (the live dataset's `unit_id`, after `unit-splits-v4`) coded 2 or more, split by whether
they share the 0-bed row's page. Rows of the label unit on another page were joined by a
label_units layer, and `lr3_layers.py` names it. Bedrooms are the rows file's, before ledger
sets, as in z2. Only units, pages and counts are read.
"""

from pathlib import Path

import duckdb
import pandas as pd

ZB = Path("/data1/apartments/tmp/zero-bed")
OUT = Path("/data1/apartments/tmp/label-reuse")
ROWS = "/data1/apartments/pipeline/datasets/rows-4f487ef77bb6ca61.parquet"
LIVE_ROWS = (
    "/data1/apartments/frontier/datasets/"
    "b0-4f487ef77bb6ca61-alldata-dense-nyc-market-bedtext/rows.parquet"
)

Z = pd.read_parquet(ZB / "zeros.parquet", columns=["listing_id", "train", "in_ledger"])
base = Z[Z.train & ~Z.in_ledger][["listing_id"]]
c = duckdb.connect()
c.execute("set memory_limit='2GB'; set threads=2")
c.execute(f"set temp_directory='{OUT}/duck'")
c.register("base", base)
c.execute(f"""create table r as select r.listing_id, r.unit_id, r.page, r.label_unit,
    r.split_unit, r.bedrooms, d.unit_id fit_unit
  from '{ROWS}' r left join '{LIVE_ROWS}' d using (listing_id)""")
print("0-bed training rows", len(base))
for unit in ("label_unit", "fit_unit"):
    g = c.execute(f"""
      select z.listing_id, max((o.page = z.page)::int) same_page,
        max((o.page <> z.page)::int) other_page
      from base b join r z using (listing_id)
      join r o on o.{unit} = z.{unit} and o.listing_id <> z.listing_id
      where o.bedrooms >= 2 group by 1""").df()
    print(
        unit,
        "rows with a 2+ row in the unit",
        len(g),
        "on the same page",
        int(g.same_page.sum()),
        "on another page",
        int(g.other_page.sum()),
        "only on another page",
        int(((g.other_page == 1) & (g.same_page == 0)).sum()),
    )
    if unit == "label_unit":
        P = c.execute("""
          select z.listing_id z_id, z.unit_id z_unit, z.page z_page, z.label_unit,
            o.listing_id o_id, o.unit_id o_unit, o.page o_page, o.bedrooms o_bed
          from base b join r z using (listing_id)
          join r o on o.label_unit = z.label_unit and o.listing_id <> z.listing_id
          where o.bedrooms >= 2 and o.page <> z.page""").df()
        P.to_parquet(OUT / "label_unit_pairs.parquet")
        print("cross-page pairs", len(P), "label units", P.label_unit.nunique())
