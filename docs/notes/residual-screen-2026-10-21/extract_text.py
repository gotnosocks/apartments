import pyarrow.parquet as pq, pandas as pd, re

try:
    import orjson as js
except ImportError:
    import json as js
ids = set(
    pd.read_parquet("resid.parquet", columns=["listing_id"]).listing_id.astype(str)
)
P = {
    "text: gut renovated": r"gut[- ]renovat",
    "text: renovated": r"renovat",
    "text: brand new / new construction": r"brand[- ]new|new construction|newly built|never lived",
    "text: luxury": r"luxury",
    "text: dishwasher": r"dish ?washer",
    "text: washer/dryer in unit": r"washer[ /&-]*(and )?dryer in|in[- ]unit (laundry|washer|w/d)|w/d in",
    "text: no fee": r"no[- ]fee|no broker",
    "text: sunny/bright": r"sunny|sun[- ]drenched|bright",
    "text: quiet": r"\bquiet\b",
    "text: noise/street": r"\bnoisy|traffic|street noise",
    "text: exposed brick": r"exposed brick",
    "text: walk-up": r"walk[- ]?up",
    "text: floor-through": r"floor[- ]?thr(ough|u)",
    "text: private outdoor": r"private (terrace|balcony|patio|garden|roof|outdoor)",
    "text: roof deck": r"roof ?(deck|top|terrace)",
    "text: gym/fitness": r"\bgym\b|fitness",
    "text: pool": r"\bpool\b",
    "text: parking/garage": r"parking|garage",
    "text: storage": r"storage",
    "text: views": r"\bviews?\b",
}
C = {k: re.compile(v, re.I) for k, v in P.items()}
pf = pq.ParquetFile(
    "/data1/apartments/pipeline/datasets/records-086e22e48969b098.parquet"
)
out = {}
for i in range(pf.num_row_groups):
    t = pf.read_row_group(
        i, columns=["listing_id", "collected_at", "raw_listing_json"]
    ).to_pandas()
    t["listing_id"] = t.listing_id.astype(str)
    t = t[t.listing_id.isin(ids)]
    for lid, ca, s in zip(t.listing_id, t.collected_at, t.raw_listing_json):
        if lid in out and out[lid][0] >= ca:
            continue
        try:
            d = js.loads(s).get("description") or ""
        except Exception:
            continue
        out[lid] = (ca, [bool(c.search(d)) for c in C.values()])
    print(i, flush=True)
df = pd.DataFrame(
    [v[1] for v in out.values()],
    columns=list(P),
    index=pd.Index(list(out), name="listing_id"),
).astype(str)
df.reset_index().to_parquet("text_fields.parquet")
print("done", len(df))
