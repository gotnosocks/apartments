"""Free check: ads whose page price looks net of uncoded free months, on the backtest.

For the open ads of the Deals backtest (`range-j`) with no other caution it prints, for the ads
`cautions.net_ask` marks and for three comparison groups, the count, the share in the
lowest tenth of places and what the ask did before the ad closed. The place is of the
first ask, as in `drift_deals validate`.

Run from the repo root with PYTHONPATH=frontier/src: python docs/notes/net-ask-caution-2026-11-18/backtest.py
"""

import importlib.util, sys
from pathlib import Path
import numpy as np, pandas as pd
from rentfrontier import cautions, drift_deals

W = Path.cwd()
spec = importlib.util.spec_from_file_location(
    "place", W / "docs/notes/bedtext-base-2026-11-17/place.py"
)
place = importlib.util.module_from_spec(spec)
spec.loader.exec_module(place)
ADS = Path("/data1/apartments/pipeline/datasets/ads-14f9e88d75290a0f.parquet")
J = next(
    Path("/data1/apartments/frontier/runs").glob(
        "drift-building-bedtext-layout-range-b0-market-*-range-j"
    )
)
lid, p, ok, days, change = place.places(J, ADS)
ids = pd.Index([str(x) for x in lid])
a = pd.read_parquet(
    ADS, columns=["listing_id", "first_ask", "page_price", "months_free"]
)
a["listing_id"] = a.listing_id.astype(str)
a = a.drop_duplicates("listing_id").set_index("listing_id").reindex(ids)
t = drift_deals.deals(J, ADS)
c = t.assign(listing_id=t.listing_id.astype(str)).set_index("listing_id").cautions
plain = ~c.reindex(ids).map(
    lambda v: (
        any(code != "net_ask" for code in v)
        if isinstance(v, (list, tuple, np.ndarray))
        else False
    )
).to_numpy(bool)
first, page = a.first_ask.to_numpy(float), a.page_price.to_numpy(float)
nofree = ~(np.nan_to_num(a.months_free.to_numpy(float)) > 0)
rnd = np.abs(first - np.round(first / 25) * 25) < 0.01
odd = ~np.isin(np.round(page) % 10, (0, 5, 9))
cut = first > page
hit = cautions.net_ask(first, page, a.months_free.to_numpy(float))
groups = {
    "simple: odd page below round first, no free": nofree & rnd & odd & cut,
    "net_ask": hit,
    "cut to a round price, no free": nofree & rnd & ~odd & cut,
    "no cut, no free": nofree & ~cut,
}
base = ok & plain
print("open uncautioned", base.sum())
for name, m in groups.items():
    b = base & m
    k = b & (p < 0.1)
    print(
        f"{name:45s} ads {b.sum():5d} lowest tenth {k.sum():4d} ({100 * k.sum() / max(b.sum(), 1):.1f}%) median place {np.median(p[b]) if b.any() else np.nan:.3f} "
        f"| all: cut {100 * (change[b] < -0.001).mean():.1f}% raised {100 * (change[b] > 0.001).mean():.1f}% median days {np.median(days[b]):.0f}"
    )
