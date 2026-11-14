"""Sample history pairs for reading and write a dossier for each: 60 pairs v17's history layer
joins and v18 keeps apart, and 40 it joins whose labels agree up to spelling."""

import json
import os
import re

import duckdb
import numpy as np
import pandas as pd

S = "/data1/apartments/tmp/sprint-20261113/label-join"
D = "/data1/apartments/pipeline/datasets"
OUT = f"{S}/dossiers"
os.makedirs(OUT, exist_ok=True)
rng = np.random.default_rng(20261113)
pr = pd.read_parquet(f"{S}/pairs_classified.parquet")
pages = pd.read_parquet(
    f"{S}/pages.parquet", columns=["unit_id", "building"]
).set_index("unit_id")
pr["building_a"] = pages.building.reindex(pr.unit_id).to_numpy()
pr["building_b"] = pages.building.reindex(pr.other_unit_id).to_numpy()
split = pr[pr.joined17 & pr.apart18]
kept_hist = pr[pr.joined17 & pr.agree]
print("split", len(split), "kept_hist", len(kept_hist))
pick = pd.concat(
    [
        split.iloc[rng.choice(len(split), 60, replace=False)].assign(group="split"),
        kept_hist.iloc[rng.choice(len(kept_hist), 40, replace=False)].assign(
            group="kept"
        ),
    ]
)
pick = pick.iloc[rng.permutation(len(pick))].reset_index(drop=True)
pick["pid"] = np.arange(1, len(pick) + 1)
pick.to_parquet(f"{S}/sample.parquet")

c = duckdb.connect()
c.execute(
    "set memory_limit='2000MB'; set threads=3; set preserve_insertion_order=false;"
    f"set temp_directory='{S}/duck'"
)
units = pd.DataFrame(
    {
        "pid": np.r_[pick.pid, pick.pid],
        "side": ["A"] * len(pick) + ["B"] * len(pick),
        "page_unit": np.r_[pick.unit_id, pick.other_unit_id],
    }
)
c.register("units", units)
ads = c.execute(f"""
    SELECT u.pid, u.side, a.listing_id::VARCHAR AS listing_id, a.page, a.building, a.first_day,
        a.latest_ask, a.bedrooms, a.full_baths, a.half_baths, a.square_feet, a.in_rows,
        a.label_fate, a.fate
    FROM read_parquet('{D}/ads-3775f6d9b3e028ca.parquet') a
    JOIN units u ON u.page_unit = regexp_replace(a.unit_id, '~review-.*$', '')
""").df()
c.register("ids", pd.DataFrame({"listing_id": ads.listing_id.unique()}))
rec = (
    c.execute(f"""
    SELECT listing_id::VARCHAR AS listing_id,
        arg_max(raw_listing_json, last_collected_at) AS j
    FROM read_parquet('{D}/records-086e22e48969b098.parquet')
    WHERE listing_id::VARCHAR IN (SELECT listing_id FROM ids)
    GROUP BY 1
""")
    .df()
    .set_index("listing_id")
)
print("ads", len(ads), "records", len(rec))


def get(d, *path):
    for p in path:
        if not isinstance(d, dict):
            return None
        d = d.get(p)
    return d


def fmt(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return ""
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v)


for _, p in pick.iterrows():
    a = ads[ads.pid == p.pid].sort_values(["first_day", "listing_id"])
    lines = [
        f"# Pair {p.pid}",
        "",
        f"- Side A: unit page(s) {', '.join(sorted(set(a.page[a.side == 'A'].str.replace('https://streeteasy.com/building/', ''))))}",
        f"- Side B: unit page(s) {', '.join(sorted(set(a.page[a.side == 'B'].str.replace('https://streeteasy.com/building/', ''))))}",
        f"- Link: the unit history in the record of ad {p.listing_id} lists ad {p.listed_id}"
        f" ({p.links} such links between the two sides).",
        "",
        "## The ads of both sides, oldest first",
        "",
        "| side | ad | page label | record unit | record street | property id | first day | ask | beds | full baths | half baths | rooms | stated sq ft | lister |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    texts = []
    for _, x in a.iterrows():
        j = rec.j.get(x.listing_id)
        d = json.loads(j) if isinstance(j, str) else {}
        prop = get(d, "propertyDetails", "address", "displayUnit")
        street = get(d, "propertyDetails", "address", "street")
        lines.append(
            f"| {x.side} | {x.listing_id} | {x.page.rsplit('/', 1)[-1]} | {fmt(prop)} | "
            f"{fmt(street)} | {fmt(d.get('propertyId'))} | {str(x.first_day)[:10]} | "
            f"{fmt(x.latest_ask)} | {fmt(get(d, 'propertyDetails', 'bedroomCount'))} | "
            f"{fmt(get(d, 'propertyDetails', 'fullBathroomCount'))} | "
            f"{fmt(get(d, 'propertyDetails', 'halfBathroomCount'))} | "
            f"{fmt(get(d, 'propertyDetails', 'roomCount'))} | "
            f"{fmt(get(d, 'propertyDetails', 'livingAreaSize'))} | "
            f"{fmt(get(d, 'legacy', 'sourceGroupLabel'))[:30]} |"
        )
        text = re.sub(r"\s+", " ", d.get("description") or "").strip()[:600]
        texts.append(
            f"### Ad {x.listing_id} (side {x.side}, {str(x.first_day)[:10]})\n\n{text or '(no text)'}\n"
        )
    lines += ["", "## Each ad's text (first 600 characters)", "", *texts]
    open(f"{OUT}/{p.pid}.md", "w").write("\n".join(lines) + "\n")
for k in range(5):
    ids = pick.pid[pick.pid % 5 == k]
    open(f"{S}/batch{k}.txt", "w").write("\n".join(f"{OUT}/{i}.md" for i in ids) + "\n")
print(pick.group.value_counts().to_dict())
