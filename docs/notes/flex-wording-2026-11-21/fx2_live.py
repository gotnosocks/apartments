"""Bedroom wording on ten live Deals ads the reader codes with fewer bedrooms in the text."""

import re

import pandas as pd

from rentfrontier import b0bedtext as b

IDS = "5114922 5111490 5205822 5142075 5201322 5203130 5139517 5181377 5181704 5148536".split()
RUN = "drift-building-bedtext-layout-range-b0-market-6cd1f12b-range-m3"
t = pd.read_parquet(
    f"/data1/apartments/tmp/deals-refresh/{RUN}/texts.parquet",
    columns=["listing_id", "description"],
)
for r in t[t.listing_id.isin(IDS)].itertuples():
    s = re.sub(r"[$][\d,]+", "$X", b.plain(r.description))
    hits = [m.start() for m in re.finditer(r"studio|bed|br\b|bdr", s)][:3]
    print(
        r.listing_id,
        b.read(r.description)[:2],
        " | ".join(s[max(0, i - 60) : i + 40] for i in hits),
    )
