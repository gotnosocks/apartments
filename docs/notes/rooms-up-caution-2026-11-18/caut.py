"""The rooms_up caution on the backtest (later cuts) and on the market run (the top of the table)."""

import importlib.util, sys
from pathlib import Path
import numpy as np
from rentfrontier import drift_deals

W = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "place", W / "docs/notes/bedtext-base-2026-11-17/place.py"
)
place = importlib.util.module_from_spec(spec)
spec.loader.exec_module(place)
ADS = Path("/data1/apartments/pipeline/datasets/ads-14f9e88d75290a0f.parquet")
R = Path("/data1/apartments/frontier/runs")
J, Mk = (
    R / "drift-building-bedtext-b0-market-f288a423-heldbed-j",
    R / "drift-building-bedtext-b0-market-f288a423-heldbed-m",
)
t = drift_deals.deals(J, ADS)
lid, p, ok, days, change = place.places(J, ADS)
c = t.set_index("listing_id").cautions.reindex(lid)
up = c.map(lambda v: "rooms_up" in v).to_numpy()
other = c.map(lambda v: bool(set(v) - {"rooms_up"})).to_numpy()
low = ok & (p < 0.1)
print(
    "backtest open ads",
    ok.sum(),
    "rooms_up",
    (up & ok).sum(),
    "of them with another caution",
    (up & other & ok).sum(),
)
for name, m in {
    "rooms_up, no other caution": up & ~other,
    "no caution": ~up & ~other,
    "other caution": other,
}.items():
    k = low & m
    print(
        f"  {name:28s} ads {(m & ok).sum():5d} lowest tenth {k.sum():4d} ({100 * k.sum() / (m & ok).sum():.1f}%) cut {100 * (change[k] < -0.001).mean():.1f}% raised {100 * (change[k] > 0.001).mean():.1f}% median days {np.median(days[k]):.0f}"
    )
import sys

texts = sys.argv[1] if len(sys.argv) > 1 else None
try:
    m = drift_deals.deals(Mk, ADS, texts=Path(texts) if texts else None)
except SystemExit as e:
    print("texts not for this run:", e)
    m = drift_deals.deals(Mk, ADS)
up = m.cautions.map(lambda v: "rooms_up" in v)
other = m.cautions.map(lambda v: bool(set(v) - {"rooms_up"}))
print(
    "market ads",
    len(m),
    "rooms_up",
    up.sum(),
    "with no other caution",
    (up & ~other).sum(),
)
free = m[~other].reset_index(drop=True)
u = free.cautions.map(bool)
for n in (20, 60, 100, 200):
    print(f"  first {n} with no other caution: rooms_up {u[:n].sum()}")
print(
    "  share among below_share 0.25 to 0.75:",
    round(100 * u[(free.below_share > 0.25) & (free.below_share < 0.75)].mean(), 1),
)
