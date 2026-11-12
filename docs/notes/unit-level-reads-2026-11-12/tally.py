"""Tally the readers' classes and codes by stratum and by direction."""

import glob
import json

import pandas as pd

rows = [
    json.loads(line)
    for f in sorted(glob.glob("reads/*.jsonl"))
    for line in open(f)
    if line.strip()
]
r = pd.DataFrame(rows)
t = pd.read_parquet("targets.parquet")
t["listing_id"] = t["listing_id"].astype(str)
d = r.merge(t, on="listing_id", how="left", validate="one_to_one")
assert len(d) == 300 and d["stratum"].notna().all()
d["dir"] = d["score"].gt(0).map({True: "over", False: "under"})
pd.set_option("display.width", 200)
print(pd.crosstab(d["class"], d["stratum"], margins=True))
print(pd.crosstab([d["class"], d["code"]], [d["stratum"]], margins=True))
print(pd.crosstab(d["class"], d["dir"], margins=True))
print(pd.crosstab(d["code"], d["dir"]))
print(pd.crosstab(d["action"], d["stratum"]))
print(d["confidence"].value_counts())
# Do the codes line up with what the model already has?
ro = d["class"].eq("real_outlier")
for code, col in [
    ("penthouse_top", "penthouse"),
    ("penthouse_top", "top_floor"),
    ("outdoor_space", "private_outdoor"),
    ("view", "view"),
]:
    s = d[d["code"].eq(code)]
    print(code, col, s[col].value_counts(dropna=False).to_dict())
s = d[d["code"].eq("layout_size")]
print(
    "layout_size sqft known",
    s["square_feet"].notna().mean(),
    "model_sqft",
    s["model_sqft"].notna().mean(),
    s["size_source"].value_counts().to_dict(),
)
print("all sqft known", d["square_feet"].notna().mean())
print(d.groupby("class")["score"].agg(["count", "median", lambda x: x.abs().median()]))
cols = [
    "listing_id",
    "code",
    "action",
    "value",
    "backing",
    "confidence",
    "stratum",
    "bedrooms",
]
print(d[d["action"].ne("none")][cols].to_string())
d.drop(columns=["value", "images"]).to_parquet("tally.parquet")
