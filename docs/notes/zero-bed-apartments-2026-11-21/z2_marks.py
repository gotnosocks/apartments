"""Question 2: every ad coded 0 bed in the live build, with the evidence for a count of 2 or more.

Universe: the live build's ads file (`ads-417bbdf5ed03f5d3`, every ad the pipeline saw). For
each ad coded 0 bed I record:
- `train`: a training row of the live Deals run (in its rows, not one of its 6,502 open ads);
- `in_ledger`: an active ledger entry (exclude or set, from `pipeline/ledger` on master) names
  the listing;
- the unit's other ads (same `unit_id`, any fate) whose bedrooms are typed, that is not set by
  an active ledger entry: `u2` coded 2 or more, `u1` coded 1, `u0` coded 0, the same within
  730 days of the ad's first day (`u2_near`, `ulo_near` for under 2), and the distinct counts
  of 2 or more (`u2_kinds`, `u2_min`);
- the text columns of `rentfrontier.b0bedtext` from the live dataset (`bed_text`,
  `bed_text_more`), its strict reader of the size a description states for its own unit;
- `half`: the building's half by the commercial sweep's hash.
Only counts, dates and units are read. No ask enters any column.
"""

import hashlib
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
WT = HERE.parents[2]
sys.path.insert(0, str(WT / "pipeline"))
from models.ledger import entries  # noqa: E402

OUT = Path("/data1/apartments/tmp/zero-bed")
ADS = "/data1/apartments/pipeline/datasets/ads-417bbdf5ed03f5d3.parquet"
RUNS = Path("/data1/apartments/frontier/runs")
LIVE = RUNS / "drift-building-bedtext-layout-range-b0-market-6cd1f12b-range-m3"
LIVE_ROWS = Path(
    "/data1/apartments/frontier/datasets/"
    "b0-4f487ef77bb6ca61-alldata-dense-nyc-market-bedtext/rows.parquet"
)
SEED = "commercial-sweep-2026-11-20"


def half(b: str) -> str:
    return "AB"[hashlib.sha1((SEED + b).encode()).digest()[0] & 1]


rows = entries.read(sorted((WT / "pipeline" / "ledger").glob("*.ndjson")))
gone = {r["retracts"] for r in rows if r["change"] == "retract"}
act = [r for r in rows if r["change"] != "retract" and r["entry"] not in gone]
named = {str(r["listing_id"]) for r in act if r["change"] in ("exclude", "set")}
bedset = {
    str(r["listing_id"])
    for r in act
    if r["change"] == "set" and r.get("bedrooms") is not None
}
print(
    "active ledger entries",
    len(act),
    "listings named",
    len(named),
    "bedroom sets",
    len(bedset),
)

c = duckdb.connect()
c.execute("set memory_limit='2GB'")
c.execute("set threads=2")
c.execute("set temp_directory='/data1/apartments/tmp/zero-bed/duck'")
c.register("bedset", pd.DataFrame({"listing_id": sorted(bedset)}))
c.execute(f"""create table a as select listing_id, unit_id, building, page, bedrooms,
  first_day, in_rows, fate from '{ADS}'""")
c.execute("""create table o as select a.* from a
  where bedrooms is not null and listing_id not in (select listing_id from bedset)""")
Z = c.execute("""
  select z.listing_id, z.unit_id, z.building, z.page, z.first_day, z.in_rows, z.fate,
    count(o.listing_id) u_n,
    coalesce(sum((o.bedrooms >= 2)::int), 0) u2,
    coalesce(sum((o.bedrooms = 1)::int), 0) u1,
    coalesce(sum((o.bedrooms = 0)::int), 0) u0,
    coalesce(sum((o.bedrooms >= 2 and abs(date_diff('day', z.first_day, o.first_day)) <= 730)::int), 0) u2_near,
    coalesce(sum((o.bedrooms < 2 and abs(date_diff('day', z.first_day, o.first_day)) <= 730)::int), 0) ulo_near,
    count(distinct case when o.bedrooms >= 2 then o.bedrooms end) u2_kinds,
    min(case when o.bedrooms >= 2 then o.bedrooms end) u2_min
  from (select * from a where bedrooms = 0) z
  left join o on o.unit_id = z.unit_id and o.listing_id <> z.listing_id
  group by all""").df()
print("ads coded 0 bed", len(Z))
lr = pd.read_parquet(
    LIVE_ROWS, columns=["listing_id", "bedrooms", "bed_text", "bed_text_more"]
)
lr["listing_id"] = lr.listing_id.astype(str)
lr["live_open"] = np.load(LIVE / "posterior.npz")["heldout"]
Z = Z.merge(lr.rename(columns={"bedrooms": "row_bed"}), on="listing_id", how="left")
Z["in_ledger"] = Z.listing_id.isin(named)
Z["in_live"] = Z.row_bed.notna()
Z["train"] = Z.in_live & ~Z.live_open.fillna(False).astype(bool) & (Z.row_bed == 0)
Z["bed_text_more"] = Z.bed_text_more.fillna(False).astype(bool)
Z["half"] = Z.building.fillna("").map(half)
Z["T"] = Z.bed_text_more & (Z.bed_text >= 2)
Z["U_any"] = Z.u2 > 0
Z["U_clean"] = (Z.u2 > 0) & (Z.u1 == 0)
Z["U_near"] = (Z.u2_near > 0) & (Z.ulo_near == 0)
Z.drop(columns=["row_bed"]).to_parquet(OUT / "zeros.parquet")
print(
    "in live rows coded 0",
    int((Z.in_live).sum()),
    "training",
    int(Z.train.sum()),
    "training not in ledger",
    int((Z.train & ~Z.in_ledger).sum()),
)
print("ledger-named among coded 0", int(Z.in_ledger.sum()))
