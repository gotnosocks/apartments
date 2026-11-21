"""Live Deals rows whose previous-ask ring changes under the fix. The ring reads
`prev_ask` from the diagnostics table by listing id."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
NEW = "/data1/apartments/tmp/diag-prev/new/ads.parquet"
rows = json.load(open("/data1/apartments/site/deals/deals.json"))
meta = json.load(open("/data1/apartments/site/deals/meta.json"))
print("deals run", meta["run"], "scoring day", meta["scoring_day"])
ids = pd.Index([str(r["listing_id"]) for r in rows])
old = pd.read_parquet(HERE / "old-prev.parquet").set_index("listing_id")
new = pd.read_parquet(NEW, columns=["listing_id", "source", "prev_ask", "prev_day"])
new = new.set_index("listing_id")
o, n = old.prev_ask.reindex(ids), new.prev_ask.reindex(ids)
known = old.index.isin(ids).sum()
print("deals", len(ids), "with a diagnostics row", known, "without", len(ids) - known)
print("their diagnostics source", new.source.reindex(ids).value_counts().to_dict())
ring = o.notna() & (o > 0)
od, nd = old.prev_day.reindex(ids), new.prev_day.reindex(ids)
diff = ring & ~(np.isclose(o, n) & (od == nd))
print(
    "rings",
    ring.sum(),
    "| changed by the fix",
    diff.sum(),
    "| lost",
    (ring & n.isna()).sum(),
)
