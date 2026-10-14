import duckdb, numpy as np, pandas as pd, re

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
    f"SELECT DISTINCT cast(event_listing_id as varchar) lid, cast(event_date as varchar) d, coalesce(status,'PRICE_CHANGE') status FROM read_parquet('{base}{d}/event_mentions/*.parquet') WHERE event_category='rental'"
    for d in dss
)
ev = db.execute(
    f"SELECT lid, count(DISTINCT d) nd, list(DISTINCT status ORDER BY status) st FROM ({union}) GROUP BY lid"
).df()
f = pd.read_parquet("/data1/apartments/tmp/suspect/lowrent/screen2.parquet")
f = f.merge(ev, on="lid", how="left")
f["only_delisted_day"] = (f.nd == 1) & f.st.apply(
    lambda s: isinstance(s, (list, np.ndarray)) and list(s) == ["ACTIVE", "DELISTED"]
)
f["only_withdrawn_day"] = (f.nd == 1) & f.st.apply(
    lambda s: (
        isinstance(s, (list, np.ndarray))
        and set(s) - {"ACTIVE"} != set()
        and set(s)
        <= {"ACTIVE", "DELISTED", "NO_LONGER_AVAILABLE", "TEMPORARILY_OFF_MARKET"}
    )
)
d = pd.read_parquet(
    "/data1/apartments/tmp/suspect/size/frame.parquet",
    columns=["audit_id", "description"],
)
f = f.merge(d, on="audit_id")


def junk(t):
    if t is None or t != t:
        return False
    letters = re.sub(r"[^a-z]", "", t.lower())
    return len(letters) > 0 and (len(set(letters)) <= 2 or len(t.split()) <= 1)


f["junk_text"] = f.description.apply(junk)
for name in ["only_delisted_day", "only_withdrawn_day", "junk_text"]:
    m = f[name]
    g = f[m & f.oth.notna()]
    print(
        f"{name:20s} n={int(m.sum()):5d} with_other={len(g):5d} far={g.far.mean():.4f} n_far={int(g.far.sum())}"
    )
print(f[f.junk_text].description.value_counts().head(15))
f.to_parquet("/data1/apartments/tmp/suspect/lowrent/screen3.parquet")
