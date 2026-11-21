"""Reader input for the sample of l1_read.py: full ad text and coded fields, no price.

Dollar amounts and amounts per month are blanked so a reader names the apartment's kind
without the ask. The ads are shuffled and the file holds no miss direction; the key that
says which ad is low, high or inside stays in key.parquet for scoring.
"""

import re

import pandas as pd
import pyarrow.parquet as pq

T = "/data1/apartments/tmp/big-small/"
ADS = "/data1/apartments/pipeline/datasets/ads-417bbdf5ed03f5d3.parquet"
TEXTS = "/data1/apartments/tmp/any-unit/texts.parquet"
s = pd.read_parquet(T + "sample.parquet")
s["listing_id"] = s.listing_id.astype(str)
ids = sorted(set(s.listing_id))


def table(path, cols):
    t = pq.read_table(
        path, columns=cols, filters=[("listing_id", "in", ids)]
    ).to_pandas()
    t["listing_id"] = t.listing_id.astype(str)
    return t.drop_duplicates("listing_id")


a = table(
    ADS, ["listing_id", "bedrooms", "bathrooms", "square_feet", "advertised_floor"]
)
t = table(TEXTS, ["listing_id", "description"])
x = s.merge(a, on="listing_id", how="left").merge(t, on="listing_id", how="left")
MONEY = re.compile(
    r"\$\s?\d[\d,.]*k?|\b\d[\d,.]*\s?(?:/\s?mo(?:nth)?|per month|a month|dollars)\b",
    re.I,
)
x["text"] = x.description.fillna("").map(lambda d: MONEY.sub("[amount]", d))
x = x.sample(frac=1, random_state=7).reset_index(drop=True)
x["ad"] = range(1, len(x) + 1)
x[["ad", "listing_id", "kind"]].to_parquet(T + "key.parquet")
with open(T + "ads.txt", "w") as f:
    for r in x.itertuples():
        f.write(
            f"=== AD {r.ad}\ncoded: {r.bedrooms} bedrooms, {r.bathrooms} baths, "
            f"square_feet field {r.square_feet}, size used {r.sqft:.0f} ({r.size_source}), "
            f"floor {r.advertised_floor}, building {r.building}, unit {r.unit_id}\n"
            f"text: {r.text.strip()}\n\n"
        )
print(len(x), "ads; texts missing:", int(x.description.isna().sum()))
print("amount blanks:", int(x.text.str.count(r"\[amount\]").sum()))
