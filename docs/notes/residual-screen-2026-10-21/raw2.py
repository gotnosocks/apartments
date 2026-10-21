import pandas as pd, numpy as np

f = pd.read_parquet("raw_fields.parquet")
o = pd.DataFrame({"listing_id": f.listing_id})
o["source type"] = f.source_type.fillna("none").astype(str)
o["license type"] = f.license_type.fillna("none").astype(str)
o["broker (business name)"] = f.business.fillna("none").astype(str)
o["source group"] = f.source_group.fillna("none").astype(str)
o["premium page"] = f.premium.astype(str)
o["MLS number"] = f.mls.astype(str)
o["room count"] = f.rooms.fillna(-1).clip(upper=8).astype(int).astype(str)
o["photos"] = pd.cut(
    f.photos,
    [-2, -0.5, 0, 4, 9, 14, 19, 500],
    labels=["no media", "0", "1-4", "5-9", "10-14", "15-19", "20+"],
).astype(str)
o["video"] = f.video.astype(str)
o["3D tour"] = f.tour3d.astype(str)
o["description length"] = pd.cut(
    f.desc_len, [-1, 0, 300, 600, 1000, 1500, 2500, 1e6]
).astype(str)
o["fees listed"] = f.n_fees.clip(upper=3).astype(str)
o["no fee in text"] = f.nofee_text.astype(str)
for c in [
    "outdoor_private",
    "outdoor_shared",
    "parking",
    "fireplace",
    "views",
    "storage",
]:
    o[c.replace("_", " ") + " (any)"] = (f[c].fillna("") != "").astype(str)
for c, pre in [
    ("amen", "amenity"),
    ("feat", "feature"),
    ("outdoor_private", "private outdoor"),
    ("outdoor_shared", "shared outdoor"),
]:
    s = f[c].fillna("").str.split("|")
    codes = pd.Series([x for l in s for x in l if x]).value_counts()
    for k in codes[codes >= 2000].index:
        o[f"{pre}: {k}"] = (
            f[c].fillna("").str.split("|").map(lambda l, k=k: k in l).astype(str)
        )
o.to_parquet("raw_screen_fields.parquet")
print(o.shape)
