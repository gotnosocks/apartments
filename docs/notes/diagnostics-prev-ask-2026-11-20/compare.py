"""Rows whose previous ad changes, and the group whose time-adjusted previous ask sits over
0.3 above the model. Old columns: `old-prev.parquet` (saved from the published table).
New table: the scratch rebuild named in the note."""

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
NEW = "/data1/apartments/tmp/diag-prev/new/ads.parquet"
# The outlier sprint's repeat-ad index by quarter, Manhattan ("mn") and the rest ("ob").
I = pd.read_parquet(HERE / "repeat-index.parquet")
old = pd.read_parquet(HERE / "old-prev.parquet").set_index("listing_id")
cols = ["listing_id", "source", "building", "day", "model_median"]
cols += ["prev_ask", "prev_day", "flags"]
new = pd.read_parquet(NEW, columns=cols).set_index("listing_id")
assert old.index.equals(new.index), "rows differ"


def idx(day, zone):
    q = pd.PeriodIndex(pd.to_datetime(day), freq="Q").astype(str)
    out = np.full(len(q), np.nan)
    for z in ("mn", "ob"):
        m = (zone == z).to_numpy()
        out[m] = I[z].reindex(q[m]).to_numpy()
    return out


def adjusted(prev_ask, prev_day, median):
    zone = pd.Series(np.where(new.building.str.endswith("-new_york"), "mn", "ob"))
    zone.index = new.index
    ok = prev_day.notna()
    ip = np.full(len(new), np.nan)
    ip[ok.to_numpy()] = idx(prev_day[ok], zone[ok])
    return np.log(prev_ask / median) + idx(new.day, zone) - ip


o, n = old.prev_ask, new.prev_ask
same = (o.isna() & n.isna()) | np.isclose(o, n)
dayeq = old.prev_day.fillna("") == new.prev_day.fillna("")
ch = ~same | ~dayeq
print(
    "rows", len(old), "old with prev", o.notna().sum(), "new with prev", n.notna().sum()
)
print("prev_ask or prev_day changes", ch.sum())
print(
    " lost prev",
    (o.notna() & n.isna()).sum(),
    "gained",
    (o.isna() & n.notna()).sum(),
    "other ask",
    (o.notna() & n.notna() & ~np.isclose(o, n)).sum(),
    "same ask other day",
    (same & ~dayeq & o.notna()).sum(),
)
print(" by source", ch.groupby(new.source).sum().to_dict())
# Each table against its own median: since #1484 the market rows' quantiles are exact,
# which moves 6,461 market medians by up to 1.1%.
ao = adjusted(o, old.prev_day, old.model_median)
an = adjusted(n, new.prev_day, new.model_median)
g = ao > 0.3
print(
    "adjusted >0.3 old",
    g.sum(),
    "share",
    round(g.mean(), 4),
    "| keep a prev",
    n[g].notna().sum(),
    "| keep the same prev",
    (g & same & dayeq).sum(),
    "| still >0.3",
    (g & (an > 0.3)).sum(),
)
print("adjusted >0.3 new", (an > 0.3).sum(), "share", round((an > 0.3).mean(), 4))
codes = new["flags"].apply(list)
for f in ("beds_jump", "ask_jump"):
    k = codes.apply(lambda v, f=f: f in v).sum()
    print(f, "old", old[f].sum(), "new", k, "share new", round(k / len(new), 4))
