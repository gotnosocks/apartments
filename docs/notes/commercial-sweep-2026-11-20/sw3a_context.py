"""Words around the TODO's terms, to narrow them once before any count or read.

No ask, ratio or gap is loaded here: only texts. For each term, the most common word before
it and after it across the latest records of every listing.
"""

import re
from collections import Counter
from pathlib import Path

import pandas as pd

OUT = Path("/data1/apartments/tmp/commercial-sweep")
P = pd.read_parquet(OUT / "texts.parquet", columns=["desc", "t_office", "t_retail"])
for term, col, rx in (
    ("office", "t_office", r"([a-z'/&-]+)\W+offices?\b\W*([a-z'/&-]*)"),
    ("retail", "t_retail", r"([a-z'/&-]+)\W+retail\b\W*([a-z'/&-]*)"),
):
    before, after = Counter(), Counter()
    for d in P.desc[P[col]]:
        for m in re.finditer(rx, d.lower()):
            before[m.group(1)] += 1
            after[m.group(2)] += 1
    print(term, "texts", int(P[col].sum()))
    print(" before:", before.most_common(45))
    print(" after:", after.most_common(30))
