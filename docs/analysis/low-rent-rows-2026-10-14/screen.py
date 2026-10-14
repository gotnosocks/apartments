import json
import duckdb
import pandas as pd

base = "/data1/apartments/archive/datasets/"
dss = [
    "chelsea-granular-20260917-canonical-url-v1",
    "west-village-granular-20260930-canonical-url-v1",
    "greenwich-village-granular-20261005-canonical-url-v1",
    "flatiron-gramercy-park-granular-20261007-canonical-url-v1",
    "stuyvesant-town-pcv-granular-20261008-canonical-url-v1",
    "nomad-granular-20261009-canonical-url-v1",
    "east-village-granular-20261010-canonical-url-v1",
]
db = duckdb.connect(config={"memory_limit": "1500MB", "threads": "2"})
union = " UNION ".join(
    f"SELECT DISTINCT cast(event_listing_id as varchar) lid, cast(event_date as varchar) d, status, price, percent_change FROM read_parquet('{base}{d}/event_mentions/*.parquet') WHERE event_category='rental'"
    for d in dss
)
ev = db.execute(f"SELECT DISTINCT * FROM ({union})").df()
print("events", len(ev))
f = pd.read_parquet(
    "/data1/apartments/tmp/suspect/size/frame.parquet",
    columns=[
        "audit_id",
        "source_listing_id",
        "price_at",
        "asking_rent",
        "bedrooms",
        "neighbourhood",
        "heldout",
        "canonical_unit_url",
    ],
)
f["lid"] = f.source_listing_id.astype(str)
f["d"] = pd.to_datetime(f.price_at).dt.strftime("%Y-%m-%d")
same = f.merge(ev, on=["lid", "d"], how="inner")
same["status"] = same.status.fillna("PRICE_CHANGE")
agg = same.groupby("audit_id").status.agg(lambda s: sorted(set(s))).rename("same_day")
f = f.join(agg, on="audit_id")
f["revised"] = f.same_day.apply(lambda s: isinstance(s, list) and "PRICE_CHANGE" in s)
f["withdrawn"] = f.same_day.apply(
    lambda s: (
        isinstance(s, list)
        and bool({"DELISTED", "TEMPORARILY_OFF_MARKET", "NO_LONGER_AVAILABLE"} & set(s))
    )
)
f["rented"] = f.same_day.apply(lambda s: isinstance(s, list) and "RENTED" in s)
print(pd.Series([tuple(x) for x in f.same_day.dropna()]).value_counts().head(20))
for k in ["revised", "withdrawn", "rented"]:
    print(k, int(f[k].sum()))
print("either", int((f.revised | f.withdrawn).sum()), "of", len(f))
f.drop(columns=["same_day"]).assign(
    same_day=f.same_day.apply(lambda s: json.dumps(s) if isinstance(s, list) else None)
).to_parquet("/data1/apartments/tmp/suspect/lowrent/screen.parquet")
