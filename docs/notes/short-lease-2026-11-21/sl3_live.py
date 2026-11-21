"""The short-lease mark on the live Deals table: ads marked, and where they rank in the
default view (cautioned ads hidden) as it stood before the mark."""

import json, re
import pandas as pd
from pathlib import Path
from apartments.site import deals

N = r"(?:[1-9]|1[01]|one|two|three|four|five|six|seven|eight|nine|ten|eleven)"
R = re.compile(
    rf"(?<![\d.-])\b{N}[- ]?(?:month|mo)s?[- ](?:lease|term|rental|stay|sublet)"
)
T = pd.read_parquet(
    "/data1/apartments/tmp/deals-refresh/drift-building-bedtext-layout-range-b0-market-6cd1f12b-range-m3/texts.parquet"
)
print(T.columns.tolist(), len(T))
col = "description" if "description" in T else T.columns[1]
T["m"] = [
    bool(R.search(re.sub(r"\s+", " ", x.lower()))) if isinstance(x, str) else False
    for x in T[col]
]
marked = set(T.listing_id[T.m].astype(str))
rows = deals.load(Path("/data1/apartments/site"))["rows"]
view = [str(r["listing_id"]) for r in deals.choose(rows)]
allc = {str(r["listing_id"]): r.get("cautions") or [] for r in rows}
print("marked live", len(marked & set(allc)), "of", len(allc))
print("already cautioned", sum(1 for l in marked & set(allc) if allc[l]))
ranks = [i + 1 for i, l in enumerate(view) if l in marked]
print("in default view", len(ranks), "ranks", ranks[:20])
for l in [v for v in view if v in marked][:8]:
    x = re.sub(r"\s+", " ", T.loc[T.listing_id.astype(str) == l, col].iloc[0].lower())
    mm = R.search(x)
    print(
        l, "|", re.sub(r"\$\s?[\d,]+", "$N", x[max(0, mm.start() - 80) : mm.end() + 60])
    )
