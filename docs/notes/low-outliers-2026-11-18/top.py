"""The top of a staged Deals table against the live one, with the range marks of each ad."""

import json
import sys
from pathlib import Path

import pandas as pd

from rentfrontier import drift_building_bedtext_layout_range as M
from rentfrontier import drift_deals

run, staged, live = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
frame, h, held = drift_deals._held_frame(run)
x = pd.DataFrame(M.marks(frame, ~held)[held], columns=M.COLUMNS)
x["listing_id"] = h.listing_id.astype(str).to_numpy()
x["more"] = (x["ad:beds_above_low"] + x["ad:baths_above_low"]) > 0
x["fewer"] = (x["ad:beds_below_high"] + x["ad:baths_below_high"]) > 0
x = x.set_index("listing_id")


def table(path):
    t = pd.DataFrame(json.loads((path / "deals.json").read_text()))
    t = t[~t.cautions.map(bool)].reset_index(drop=True)
    return t.join(x[["more", "fewer"]], on="listing_id")


s, v = table(staged), table(live)
print("uncautioned ads", len(s), len(v))
print(
    f"  more rooms than the lowest earlier count {s.more.sum()}, fewer than the highest {s.fewer.sum()}"
)
for n in (20, 60, 100, 200):
    both = len(set(s.listing_id[:n]) & set(v.listing_id[:n]))
    print(
        f"first {n}: in both {both}; fewer rooms staged {s.fewer[:n].sum()} live {v.fewer[:n].sum()};"
        f" more rooms staged {s.more[:n].sum()} live {v.more[:n].sum()}"
    )
m = s.merge(v[["listing_id", "below_share"]], on="listing_id", suffixes=("", "_live"))
d = m.below_share - m.below_share_live
print(
    "below_share staged minus live: all",
    round(d.mean(), 4),
    "fewer",
    round(d[m.fewer].mean(), 4),
    "more",
    round(d[m.more].mean(), 4),
)
print("ads moving by more than 0.1:", int((d.abs() > 0.1).sum()), "of", len(m))
