"""S16, part 3: gather the 400 readers' labels and fold the causes into categories, before I
join a single label to its group.

I wrote this mapping after reading every label's cause, note and evidence, with only the read_id
to go on: nothing here touches `key.parquet` or `draw.parquet`. The script writes
`labels.parquet` and `harmonize.json`, which holds the file's SHA-256 and the time, so the note
can show the mapping was fixed before the unblinding in part 4.

The folding runs in three steps:

1. Causes the readers coined go into a seeded category, or into a new one when several reads
   share them:
   - every net-effective or free-month reading goes into `net_effective`, together with the
     three `data_error` reads whose note says the price is net effective;
   - lofts, high ceilings and period details go into `loft_ceilings_period`;
   - lease assignments and a resident-only studio go into `tenancy_terms`;
   - a private elevator landing and an in-unit washer and dryer go into `other_unit_feature`;
   - the rest join the seeded category they describe (blocked windows join `layout_fault`, a
     lobby-level unit joins `garden_basement`, and so on).
2. `renovation` and `utilities_fees_included` split on the reader's direction, since a gut
   renovation and a unit needing work push the ask opposite ways, as do heat included and a
   fee on top.
3. Each `data_error` read gets a subtype from its note, by read_id.
"""

import glob
import hashlib
import json
import time

import pandas as pd

OUT = "/data1/apartments/tmp/blind-spots-2026-11-14/"

COINED = {
    "net_effective_concession": "net_effective",
    "net_effective_free_months": "net_effective",
    "free_rent_concession": "net_effective",
    "loft_high_ceilings": "loft_ceilings_period",
    "loft_open_plan": "loft_ceilings_period",
    "sleep_loft_high_ceilings": "loft_ceilings_period",
    "high_ceilings_parlor_level": "loft_ceilings_period",
    "prewar_period_details": "loft_ceilings_period",
    "lease_assignment": "tenancy_terms",
    "resident_only_eligibility": "tenancy_terms",
    "private_elevator_landing": "other_unit_feature",
    "in_unit_washer_dryer": "other_unit_feature",
    "blocked_windows": "layout_fault",
    "ground_floor_unit": "garden_basement",
    "walkup_annex_mismatch": "data_error",
    "size_includes_terrace": "data_error",
    "walkup_top_floor": "penthouse_top_floor",
    "junior_one_bedroom": "size_mismatch",
}
NET_EFFECTIVE_DATA_ERRORS = {355, 358, 398}
DATA_ERROR_SUBTYPE = {
    "beds_low": [4, 15, 44, 69, 77, 80, 82, 89, 97, 106, 128, 145, 151, 153, 176, 177]
    + [226, 232, 235, 243, 246, 248, 261, 317, 327, 363, 364, 389],
    "beds_high": [41, 146, 271, 388],
    "baths": [191, 216, 234, 265],
    "wrong_unit_or_address": [1, 46, 76, 142, 200, 228, 309],
    "nonresidential": [47, 238, 260, 300, 334, 367, 391],
    "whole_house": [32],
    "size_field": [218, 283],
    "flag_field": [37, 293, 320],
}
SUB = {i: s for s, ids in DATA_ERROR_SUBTYPE.items() for i in ids}

lab = pd.DataFrame(
    [
        json.loads(line)
        for f in sorted(glob.glob(OUT + "read/labels*.jsonl"))
        for line in open(f)
        if line.strip()
    ]
)
assert len(lab) == 400 and set(lab.read_id) == set(range(400))
lab["category"] = lab.cause.map(lambda c: COINED.get(c, c))
lab.loc[lab.read_id.isin(NET_EFFECTIVE_DATA_ERRORS), "category"] = "net_effective"
lab["subtype"] = ""
for cat, up, down in (
    ("renovation", "renovated", "needs_work"),
    ("utilities_fees_included", "utilities_included", "fees_on_top"),
):
    m = lab.category == cat
    lab.loc[m, "subtype"] = (
        lab.loc[m, "direction"].map({"raises": up, "lowers": down}).fillna("unclear")
    )
de = lab.category == "data_error"
lab.loc[de, "subtype"] = lab.loc[de, "read_id"].map(SUB)
assert lab.loc[de, "subtype"].notna().all(), lab.loc[de & lab.subtype.isna(), "read_id"]
assert set(SUB) <= set(lab.read_id[de]), set(SUB) - set(lab.read_id[de])
lab.to_parquet(OUT + "labels.parquet")
sha = hashlib.sha256(open(OUT + "labels.parquet", "rb").read()).hexdigest()
res = {
    "written": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
    "sha256": sha,
    "categories": lab.category.value_counts().to_dict(),
    "subtypes": {
        f"{c}/{s}": int(n)
        for (c, s), n in lab[lab.subtype != ""]
        .groupby(["category", "subtype"])
        .size()
        .items()
    },
}
json.dump(res, open(OUT + "harmonize.json", "w"), indent=1)
print(json.dumps(res, indent=1))
