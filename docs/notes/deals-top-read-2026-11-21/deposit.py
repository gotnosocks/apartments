"""A flat security deposit above the page price, over every ad of the live Deals table.

New York caps a security deposit at one month's rent (2019), so a deposit above the price
the page shows says the lease rent is the deposit and the page shows a net rent with no free
months coded. Reads each ad's record from the pipeline records file the publish reads for
texts (`api_records.records_file`), chosen as `descriptions.record_descriptions` chooses it:
the ACTIVE record fetched last, else the record fetched last. Takes the deposit and the page
price, and no model output. Writes deposit.csv to scratch and prints counts by place in the
default Deals view."""

import json
import sys
from pathlib import Path

import pandas as pd

from apartments.site import deals
from rentfrontier import api_records

S = Path(sys.argv[1])
data = deals.load(Path("/data1/apartments/site"))
rows = data["rows"]
view = {r["listing_id"]: i + 1 for i, r in enumerate(deals.choose(rows))}
wanted = {str(r["listing_id"]) for r in rows}
records = api_records.records_file()
print("records file", records["path"])
latest, active = {}, {}
columns = ["listing_id", "collected_at", "snapshot_id", "raw_listing_json"]
for r in api_records.captures(records, columns):
    lid = str(r["listing_id"])
    if lid not in wanted:
        continue
    key = (r["collected_at"], r["snapshot_id"])
    j = (json.loads(r["raw_listing_json"]) or {}) if r["raw_listing_json"] else {}
    if lid not in latest or key >= latest[lid][0]:
        latest[lid] = (key, j)
    if j.get("status") == "ACTIVE" and (lid not in active or key >= active[lid][0]):
        active[lid] = (key, j)
rec = {lid: (active.get(lid) or latest[lid])[1] for lid in latest}


def deposit(j: dict):
    for f in (j.get("pricing") or {}).get("moveInFees") or []:
        calc = f.get("calculation") or {}
        if (
            f.get("typeLabel") == "Security deposit"
            and calc.get("calculationType") == "FLAT_FEE"
        ):
            return calc.get("feeQuantifier")
    return None


out = []
for r in rows:
    j = rec.get(str(r["listing_id"]), {})
    pr = j.get("pricing") or {}
    out.append(
        {
            "listing_id": r["listing_id"],
            "price": pr.get("price"),
            "months_free": pr.get("monthsFree"),
            "deposit": deposit(j),
            "cautioned": bool(r["cautions"]),
            "place": view.get(r["listing_id"]),
        }
    )
df = pd.DataFrame(out)
df["ratio"] = df.deposit / df.price
df["over"] = df.ratio > 1.02
df.to_csv(S / "deposit.csv", index=False)
coded = df.months_free.fillna(0) > 0
print("ads", len(df), "with flat deposit", df.deposit.notna().sum())
print(
    "deposit over price by 2%+",
    df.over.sum(),
    "of which months free coded",
    (df.over & coded).sum(),
)
print("uncoded and over", (df.over & ~coded).sum())
for lo, hi in [(1, 60), (1, 300), (301, 2000), (2001, 4067)]:
    s = df[(df.place >= lo) & (df.place <= hi)]
    print(
        f"view places {lo}-{hi}: {len(s)} ads, {(s.over & (s.months_free.fillna(0) == 0)).sum()} uncoded over"
    )
print("cautioned rows over uncoded", (df.over & ~coded & df.cautioned).sum())
print(df[df.over & ~coded].ratio.describe())
print(df[df.over & ~coded].sort_values("place").head(25).to_string())
