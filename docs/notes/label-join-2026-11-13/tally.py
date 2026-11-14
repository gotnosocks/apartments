"""Tally the readers' verdicts by sample group, with the labels of each pair."""

import json

import pandas as pd

S = "/data1/apartments/tmp/sprint-20261113/label-join"
lines = []
for k in range(5):
    for line in open(f"{S}/read{k}.jsonl"):
        if line.strip():
            lines.append(json.loads(line))
read = pd.DataFrame(lines)
print("lines", len(read), "distinct pids", read.pid.nunique())
pick = pd.read_parquet(f"{S}/sample.parquet")
both = pick.merge(read, on="pid", how="left")
print(pd.crosstab(both.group, both.verdict, margins=True))
print(pd.crosstab([both.group, both.verdict], both.confidence))
spencer = both.building_a.astype(str).str.contains("175-spencer")
print("175 spencer in sample", int(spencer.sum()))
print(pd.crosstab(both.group[~spencer], both.verdict[~spencer], margins=True))
pr = pd.read_parquet(f"{S}/pairs_classified.parquet")
pages = pd.read_parquet(
    f"{S}/pages.parquet", columns=["unit_id", "building"]
).set_index("unit_id")
pr["building_a"] = pages.building.reindex(pr.unit_id).to_numpy()
split = pr[pr.joined17 & pr.apart18]
print(
    "split pairs",
    len(split),
    "at 175 spencer",
    int(split.building_a.astype(str).str.contains("175-spencer").sum()),
)
print("split pairs by building, top 10")
print(split.building_a.value_counts().head(10))
for _, r in both.sort_values(["group", "verdict"]).iterrows():
    print(r.group, r.pid, r.verdict, r.confidence, list(r.a_labels), list(r.b_labels))
