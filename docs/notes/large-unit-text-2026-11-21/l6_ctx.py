import re, pandas as pd, pyarrow.parquet as pq

D = "/data1/apartments/tmp/any-unit/"
m = pd.read_parquet("l3_marks.parquet")
ids = sorted(m.listing_id)
t = (
    pq.read_table(
        D + "texts.parquet",
        columns=["listing_id", "description"],
        filters=[("listing_id", "in", ids)],
    )
    .to_pandas()
    .drop_duplicates("listing_id")
)
R = re.compile(
    r"\bmarble\b|\bchef'?s kitchen\b|\bsub[- ]?zero\b|\bmiele\b|\bwine (?:fridge|cooler|refrigerator)\b|\bviking\b|\bwolf (?:range|stove)\b|\bbosch\b"
)
s = t.description.fillna("").str.lower().str.replace(r"\s+", " ", regex=True)
hits = [(i, v) for i, v in zip(t.listing_id, s) if R.search(v)]
import random

random.seed(7)
for i, v in random.sample(hits, 30):
    mm = R.search(v)
    print(i, "|", v[max(0, mm.start() - 45) : mm.end() + 25])
