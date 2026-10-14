import duckdb, numpy as np, pandas as pd

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
    f"SELECT DISTINCT cast(event_listing_id as varchar) lid, cast(event_date as varchar) d, price, status FROM read_parquet('{base}{d}/event_mentions/*.parquet') WHERE event_category='rental' AND status IS NULL"
    for d in dss
)
pc = db.execute(
    f"SELECT lid, d, list(DISTINCT price) prices FROM ({union}) GROUP BY lid, d"
).df()
f = pd.read_parquet(
    "screen.parquet", columns=["audit_id", "lid", "d", "asking_rent", "revised"]
)
m = f[f.revised].merge(pc, on=["lid", "d"])
# biggest same-day move from the initial ask
m["lr"] = m.apply(
    lambda r: max(abs(np.log(p / r.asking_rent)) for p in r.prices), axis=1
)
print(len(m), m.lr.describe(percentiles=[0.5, 0.9, 0.99]).round(3).to_string())
for t in [0.05, 0.2, np.log(2)]:
    print(f">{t:.3f}", int((m.lr > t).sum()))
