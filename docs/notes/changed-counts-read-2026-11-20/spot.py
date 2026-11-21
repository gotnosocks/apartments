"""Print 15 coded pairs with both texts for a check by hand (seed 7; both b, 4 a, 3 each c, d, e)."""

import json
from pathlib import Path

import pandas as pd

from build import OUT

d = pd.read_csv(Path(__file__).parent / "codes.csv", dtype={"listing_id": str})
take = {"a": 4, "b": 2, "c": 3, "d": 3, "e": 3}
pick = pd.concat(
    [
        d[d.code == c].sample(min(n, (d.code == c).sum()), random_state=7)
        for c, n in take.items()
    ]
)
ads = {}
for k in range(10):
    for a in json.loads((OUT / f"dossier_{k}.json").read_text()):
        ads[a["ad"]] = a
for r in pick.itertuples():
    a = ads[r.listing_id]
    print("=" * 30, r.listing_id, a["building"], "| reader:", r.code, r.same_apartment)
    print("quote:", r.quote)
    for k in ("ad_1", "ad_2"):
        x = a[k]
        print(f"--- {k}", x["listed"], x["unit_label"], x["coded_bedrooms"], "bd")
        print(x["coded_baths"], "ba", x["coded_square_feet"], "sqft")
        print(x["text"])
