"""Live Deals ads the reader codes as a studio in the text while the listing gives 1 or more
bedrooms, with each "studio" in the text and the words before it."""

import json
import re

import pandas as pd

from rentfrontier import b0bedtext as b

RUN = "drift-building-bedtext-layout-range-b0-market-6cd1f12b-range-m3"
d = pd.DataFrame(json.load(open("/data1/apartments/site/deals/deals.json")))
d["place"] = range(1, len(d) + 1)
t = pd.read_parquet(
    f"/data1/apartments/tmp/deals-refresh/{RUN}/texts.parquet",
    columns=["listing_id", "description"],
)
x = d.merge(t, on="listing_id", how="left")
for r in x.itertuples():
    s = r.description if isinstance(r.description, str) else ""
    if len(s) < 40 or not r.bedrooms >= 1:
        continue
    c = b.code(*b.read(s), r.bedrooms)
    if not (c["bed_text_fewer"] and c["bed_text"] == 0):
        continue
    p = b.plain(s)
    ctx = [p[max(0, m.start() - 30) : m.end() + 15] for m in re.finditer(r"studio", p)][
        :4
    ]
    print(r.place, r.listing_id, r.bedrooms, r.cautions, " | ".join(ctx))
