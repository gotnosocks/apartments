"""Outcomes of backtest ads coding fewer rooms than the apartment's previous ad.

The method of docs/notes/rooms-up-caution-2026-11-18/caut.py on the Deals model's backtest:
among open ads whose first ask is in the lowest tenth of its predictive, the share the
landlord later cut or raised, and the median days on the market, by the model's
previous-ad marks.
"""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from rentfrontier import drift_building_bedtext_layout as lay
from rentfrontier import drift_deals

W = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location(
    "place", W / "docs/notes/bedtext-base-2026-11-17/place.py"
)
place = importlib.util.module_from_spec(spec)
spec.loader.exec_module(place)
ADS = Path("/data1/apartments/pipeline/datasets/ads-14f9e88d75290a0f.parquet")
J = Path("/data1/apartments/frontier/runs") / sys.argv[2]
t = drift_deals.deals(J, ADS)
lid, p, ok, days, change = place.places(J, ADS)
frame, h, held = drift_deals._held_frame(J)
held = np.asarray(held, bool)
m = pd.DataFrame(
    lay.changes(frame, ~held)[held],
    columns=["bed_up", "bed_down", "bath_up", "bath_down"],
).astype(bool)
m.index = h.listing_id.to_numpy()
m = m.reindex(lid)
c = t.set_index("listing_id").cautions.reindex(lid)
caut = c.map(bool).to_numpy()
up = c.map(lambda v: "rooms_up" in v).to_numpy()
other = c.map(lambda v: bool(set(v) - {"rooms_up"})).to_numpy()
down = (m.bed_down | m.bath_down).to_numpy()
print(
    "backtest open ads",
    int(ok.sum()),
    "fewer rooms",
    int((down & ok).sum()),
    "of them cautioned already",
    int((down & caut & ok).sum()),
)
groups = {
    "fewer rooms, no caution": down & ~caut,
    "fewer bedrooms, no caution": m.bed_down.to_numpy() & ~caut,
    "fewer baths, no caution": m.bath_down.to_numpy() & ~caut,
    "rooms_up, no other caution": up & ~other,
    "no caution, counts as previous": ~caut & ~down,
    "another caution": other,
}
for cut in (0.05, 0.1, 0.2):
    print(f"\nfirst ask below the {cut:.0%} point")
    for name, g in groups.items():
        k = ok & g & (p < cut)
        n = int((g & ok).sum())
        print(
            f"  {name:32s} ads {n:5d} low {int(k.sum()):4d} ({100 * k.sum() / n:4.1f}%) cut {100 * (change[k] < -0.001).mean():5.1f}% raised {100 * (change[k] > 0.001).mean():5.1f}% median days {np.median(days[k]):.0f}"
        )
print("\nall places")
for name, g in groups.items():
    k = ok & g
    print(
        f"  {name:32s} cut {100 * (change[k] < -0.001).mean():5.1f}% raised {100 * (change[k] > 0.001).mean():5.1f}% median days {np.median(days[k]):.0f}"
    )
