import pandas as pd, numpy as np

r = pd.read_parquet("resid.parquet", columns=["listing_id", "unit_id"])
p = pd.read_parquet(
    "/data1/apartments/pipeline/datasets/rows-edc83b49f9bacd8c.parquet",
    columns=[
        "listing_id",
        "unit_id",
        "page",
        "square_feet",
        "listed_floor",
        "floor_status",
        "building_floor_count",
        "advertised_floor",
        "elevator",
        "laundry_type",
        "doorman_type",
        "hvac_type",
        "pet_policy",
        "view_exposures",
        "window_exposures",
        "latest_gross",
        "months_free",
        "lease_term",
        "relist_unit",
        "label_unit",
        "split_unit",
    ],
)
p = p[p.listing_id.isin(r.listing_id)].drop_duplicates("listing_id")
a = pd.read_parquet(
    "/data1/apartments/pipeline/datasets/ads-9a533e24ab232a81.parquet",
    columns=[
        "listing_id",
        "identity_reasons",
        "fate",
        "label_fate",
        "from_text",
        "records",
        "floor_plans",
        "exclusion_reasons",
        "conflicts",
    ],
)
a = a[a.listing_id.isin(r.listing_id)].drop_duplicates("listing_id")
f = r.merge(p.drop(columns="unit_id"), on="listing_id", how="left").merge(
    a, on="listing_id", how="left"
)
lab = f.page.astype(str).str.extract(r"/([^/?#]+)/?$")[0].str.upper().fillna("")


def ltype(s):
    import re

    if re.search(r"PH|PENT", s):
        return "penthouse"
    if re.search(r"GARDEN|GDN|^GF|^G$|PARLOR", s):
        return "garden/parlor"
    if re.search(r"BSMT|BASEMENT|^LL|LOWER|CELLAR", s):
        return "basement/lower"
    if re.fullmatch(r"\d{1,2}", s):
        return "bare 1-2 digits"
    if re.fullmatch(r"\d{3,4}", s):
        return "bare 3-4 digits"
    if re.fullmatch(r"(APT-?)?\d{1,2}[A-Z]{1,2}", s):
        return "digits+letter"
    if re.fullmatch(r"[A-Z]{1,2}\d{0,2}", s):
        return "letters first"
    return "other"


u = pd.Series(lab.unique())
m = dict(zip(u, u.map(ltype)))
o = pd.DataFrame({"listing_id": f.listing_id})
o["unit label type"] = lab.map(m)
o["floor_status"] = f.floor_status.fillna("missing")
fl = f.listed_floor
o["floor band"] = (
    pd.cut(
        fl,
        [0, 1, 2, 3, 5, 10, 20, 40, 200],
        labels=["1", "2", "3", "4-5", "6-10", "11-20", "21-40", "41+"],
    )
    .astype(str)
    .replace("nan", "unknown")
)
o["floor / building floors"] = (
    pd.cut(
        fl / f.building_floor_count,
        [0, 0.34, 0.67, 0.99, 10],
        labels=["bottom third", "middle third", "top third below top", "top floor"],
    )
    .astype(str)
    .replace("nan", "unknown")
)
o["building floor count"] = pd.cut(
    f.building_floor_count, [0, 3, 5, 6, 10, 20, 40, 200]
).astype(str)
o["square feet stated"] = f.square_feet.notna().astype(str)
o["sqft per bedroom band"] = pd.qcut(f.square_feet, 10, duplicates="drop").astype(str)
o["identity_reasons"] = f.identity_reasons.map(
    lambda v: "|".join(sorted(v)) if v is not None and len(v) else "none"
)
o["exclusion_reasons"] = f.exclusion_reasons.map(
    lambda v: "|".join(sorted(v)) if v is not None and len(v) else "none"
)
o["fate"] = f.fate.fillna("missing")
o["label_fate"] = f.label_fate.fillna("none")
o["relabelled unit (relist/label/split differ)"] = (
    (f.relist_unit != f.unit_id)
    | (f.label_unit != f.unit_id)
    | (f.split_unit != f.unit_id)
).map({True: "differs", False: "same"})
o["relist_unit differs"] = (f.relist_unit != f.unit_id).astype(str)
o["label_unit differs"] = (f.label_unit != f.unit_id).astype(str)
o["split_unit differs"] = (f.split_unit != f.unit_id).astype(str)
o["from_text"] = f.from_text.map(
    lambda v: "|".join(sorted(v)) if v is not None and len(v) else "none"
)
o["records per ad"] = f.records.clip(upper=4).astype(str)
o["floor plans"] = f.floor_plans.map(
    lambda v: min(len(v), 2) if v is not None else -1
).astype(str)
for c in ["elevator", "laundry_type", "doorman_type", "hvac_type", "pet_policy"]:
    o[c] = f[c].astype(str).replace({"None": "unknown", "nan": "unknown"})
import json

for c, ks in [
    (
        "view_exposures",
        ["city", "courtyard", "garden", "park", "skyline", "street", "water"],
    ),
    ("window_exposures", ["east", "north", "south", "west"]),
]:
    v = f[c].map(lambda s: json.loads(s) if isinstance(s, str) else (s or {}))
    for k in ks:
        o[f"{c.split('_')[0]}: {k}"] = v.map(
            lambda d: str(d.get(k)) if isinstance(d, dict) else "None"
        )
o["gross rent stated"] = f.latest_gross.notna().astype(str)
o["months free stated"] = f.months_free.notna().astype(str)
o["lease term"] = f.lease_term.fillna(-1).clip(upper=25).astype(int).astype(str)
o.to_parquet("pipe_fields.parquet")
print(o.shape)
print(o["unit label type"].value_counts())
