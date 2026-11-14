"""Each segment's training rows and its hat weight at each quarter start, on a dataset.

The script reads five columns of DATASET/rows.parquet, so the full data fit in 3 GB. It
marks the held-out rows with SPLIT (`latest` on the full data, `carried` on a subsample of
`rehearsals-2026-11-14/subsample.py`), gives each training row its segment as the segment
model does (the borough digit of the building's registry BBL, 1 for Manhattan, and the
bedroom count capped at 3), and sums the rows' hat weights at each calendar quarter start
from the first row's quarter to the quarter after the last row's. It prints, for each
segment: its training rows, its least and median weight over the quarter starts, and the
number of quarter starts under 20 and under 100.

    python docs/notes/unitkn-rehearsals-2026-11-14/segments.py DATASET SPLIT
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "frontier" / "src"))
from rentfrontier import b0_4, splits  # noqa: E402
from rentfrontier import drift_building_phase_segment as segment  # noqa: E402

DATASET, SPLIT = Path(sys.argv[1]), sys.argv[2]
columns = ["audit_id", "building", "unit_id", "price_at", "bedrooms", "latest_day"]
if SPLIT == "carried":
    columns.append("carried_heldout")
frame = pd.read_parquet(DATASET / "rows.parquet", columns=columns)
held = splits.SPLITS[SPLIT](frame)
boro = frame.building.map(b0_4.sites_of(frame).boro)
zone = np.where(boro.to_numpy() == "1", 0, 1)
beds = np.minimum(np.clip(np.round(frame.bedrooms.to_numpy(float)), 0, None), 3)
seg = zone * len(segment.BEDS) + beds.astype(int)
day = pd.to_datetime(frame.latest_day)
first = day.min().to_period("Q").start_time
q = pd.date_range(first, (day.max().to_period("Q") + 1).start_time, freq="QS")
knots = np.asarray((q - first).days, float)
t = (day - first).dt.days.to_numpy(float)
out = {
    "rows": len(frame),
    "training_rows": int((~held).sum()),
    "quarter_starts": len(q),
    "first": str(q[0].date()),
    "last": str(q[-1].date()),
    "segments": {},
}
for k, zone_name in enumerate(("manhattan", "outer")):
    for b, bed_name in enumerate(segment.BEDS):
        on = ~held & (seg == k * len(segment.BEDS) + b)
        weight = segment.hat_weights(t[on], knots).sum(axis=0)
        out["segments"][f"{zone_name}:{bed_name}"] = {
            "training_rows": int(on.sum()),
            "least_weight": round(float(weight.min()), 1),
            "median_weight": round(float(np.median(weight)), 1),
            "quarters_under_20": int((weight < 20).sum()),
            "quarters_under_100": int((weight < 100).sum()),
        }
print(json.dumps(out, indent=1))
