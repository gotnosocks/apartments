"""Join the broker reads of the top 60, the blind trait codes of all 120 picked ads, the
coded fields and the deposit marks; write reads.csv and codes.csv into the note's folder and
print the tables of the note. Field traits come from the ads file and the stored record;
text traits from the blind codes, which saw no ask, no model and no group."""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

S = Path(sys.argv[1])
NOTE = Path(__file__).resolve().parent
SCORING_DAY = pd.Timestamp("2026-11-20")

reads = pd.DataFrame(
    [json.loads(x) for p in sorted((S / "reads").glob("*.jsonl")) for x in p.open()]
)
codes = pd.DataFrame(
    [json.loads(x) for p in sorted((S / "codes").glob("*.jsonl")) for x in p.open()]
)
key = pd.read_csv(S / "blind_key.csv", dtype={"listing_id": str})
fields = pd.read_csv(S / "fields.csv", dtype={"listing_id": str})
dep = pd.read_csv(S / "deposit_kinds.csv", dtype={"listing_id": str})

fields["T"] = np.where(
    fields.group == "top", "T" + fields["rank"].astype(str).str.zfill(2), ""
)
reads = reads.rename(columns={"key": "T"}).merge(
    fields[["T", "listing_id", "rank"]], on="T", how="left"
)
reads["reasons"] = reads.reasons.apply(lambda r: ";".join(r or []))
reads.to_csv(NOTE / "reads.csv", index=False)

c = codes.merge(key, on="key").merge(fields, on=["listing_id", "group"])
c["coded_months_free"] = c.months_free.fillna(0) > 0
c["deposit_net"] = c.listing_id.isin(dep[dep.kind == "net fit"].listing_id)
c["stale_available"] = pd.to_datetime(
    c.available, errors="coerce"
) < SCORING_DAY - pd.Timedelta(days=30)
c["few_photos"] = c.photos < 8
c["elevator_field_true"] = c.elevator.astype(str) == "True"
c["owner_feed"] = c.source_type.isin(["OWNER"])
c["landlord_feed"] = c.source_type.isin(["FEED"])
text = [
    "walkup",
    "low_floor",
    "high_walkup",
    "owner_or_small_landlord",
    "condo_coop_owner_rental",
    "thin_ad",
    "railroad_or_odd_layout",
    "flex_or_unbuilt_bedroom",
    "busy_street_or_elevated",
    "small_for_rooms",
    "renovated",
    "utilities_beyond_heat",
    "doorman",
    "new_development",
]
field = [
    "coded_months_free",
    "deposit_net",
    "stale_available",
    "few_photos",
    "elevator_field_true",
    "owner_feed",
    "landlord_feed",
]
c = c.rename(columns={"floor_x": "coded_floor"})
keep = ["key", "listing_id", "group", "rank", "coded_floor"]
c[keep + text + field + ["quote"]].to_csv(NOTE / "codes.csv", index=False)

rows = []
for t in text:
    top = (c[c.group == "top"][t] == "yes").sum()
    mid = (c[c.group == "middle"][t] == "yes").sum()
    rows.append((t, "text", top, mid))
for t in field:
    rows.append(
        (
            t,
            "field",
            int(c[c.group == "top"][t].sum()),
            int(c[c.group == "middle"][t].sum()),
        )
    )
tab = pd.DataFrame(rows, columns=["trait", "from", "top", "middle"])
tab["diff"] = (tab.top - tab.middle) / 60
tab["se"] = np.sqrt(
    (tab.top / 60 * (1 - tab.top / 60) + tab.middle / 60 * (1 - tab.middle / 60)) / 60
)
tab["z"] = tab["diff"] / tab.se.replace(0, np.nan)
print(tab.round(3).to_string(index=False))

print(
    "\nreads:",
    reads.one_apartment.value_counts().to_dict(),
    reads.problem.value_counts().to_dict(),
)
print("real_deal:", reads.real_deal.value_counts().to_dict())
r = reads[reads.one_apartment == "yes"]
cr = c[c.group == "top"].set_index("listing_id")
for t in ["walkup", "low_floor", "owner_or_small_landlord"]:
    print(
        t,
        "among real_deal no/unclear/yes:",
        {
            v: int((cr.loc[r[r.real_deal == v].listing_id, t] == "yes").sum())
            for v in ["no", "unclear", "yes"]
        },
        "of",
        r.real_deal.value_counts().to_dict(),
    )
