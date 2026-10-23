"""Within-unit change counts on Sol's audited endpoints, before any rent is read.

    PYTHONPATH=frontier/src python counts.py [OUT_DIR]

I rebuild fit 4's as-of tables (`rentfrontier.building_zones_floor_asof3_unit`) from the model
dataset's training rows under the latest split, as `b0.main_run` does, and run the floor design
on the 123,828 endpoint ads in `season_exploratory_endpoints.parquet`. For each design column I count the
units whose two endpoints take different values, and for 0/1 columns which way they move. I
also record the endpoints' dates and gaps.

I write to OUT_DIR (default /data1/apartments/tmp/conference-followups/unit-fe):

- counts.json, the counts and dates;
- endpoint_design.parquet, the endpoint rows' ids, dates and design columns, for unit_fe.py.

Neither file holds an ask. The design's `y` stays in memory and I drop it unread.

    systemd-run --user --scope -q -p MemoryMax=3G env PYTHONPATH=frontier/src python counts.py

It ran in 80 s under that 3 GB cap; the full 1.9M-row design did not fit in it.
"""

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

T0 = time.time()
OUT = Path(
    sys.argv[1]
    if len(sys.argv) > 1
    else "/data1/apartments/tmp/conference-followups/unit-fe"
)
DATASET = Path(
    "/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc"
)
SOL = Path("/data1/apartments/research-group/members/sol61/checks")
os.environ.setdefault("FRONTIER_DATASET", str(DATASET))

from rentfrontier import (  # noqa: E402
    b0,
    building_zones_floor,
    building_zones_floor_asof,
    building_zones_floor_asof3,
    building_zones_unit,
    splits,
)
from rentfrontier import building_zones_floor_asof3_unit as fit4  # noqa: E402

# Columns that fit 4 holds fixed within a pair by design or that the month effects absorb.
SKIP_PREFIX = ("alpha", "bed>=", "full>=", "half>=", "bath_unknown", "sin", "cos")

ends = pd.read_parquet(SOL / "season_exploratory_endpoints.parquet")
core = pd.read_parquet(SOL / "season_exploratory_core_ids.parquet")
assert ends.listing_id.is_unique and len(ends) == 2 * ends.unit_id.nunique()

frame = b0.load_frame(DATASET)
held = splits.SPLITS["latest"](frame)
lid = frame.listing_id.astype(str).to_numpy()
assert pd.Index(lid).is_unique
pos = pd.Index(lid).get_indexer(ends.listing_id.astype(str))
assert (pos >= 0).all(), f"{(pos < 0).sum()} endpoint ads missing from the model rows"
same = (frame.building.astype(str).to_numpy()[pos] == ends.building.to_numpy()) & (
    frame.unit_id.astype(str).to_numpy()[pos] == ends.unit_id.to_numpy()
)
unit_number = fit4.unit_index(frame, held)[0][pos]
held_end = held[pos]
start = pd.to_datetime(frame.latest_day).min()
# The full design of 1.9M rows does not fit in 3 GB. Every unit and flag column joins a row's
# own listing or building to a table, so I rebuild the as-of tables from the whole frame's
# training rows, as fit 4's design does, and run the floor design on the endpoint rows only.
tables = building_zones_floor_asof.tables_for(
    frame,
    held,
    building_zones_floor_asof3.read_ads(),
    pd.read_parquet(building_zones_floor_asof.AMENITIES / "amenities.parquet"),
    building_zones_floor_asof.load_lots(),
    pd.read_parquet(building_zones_unit.SNAPSHOT / "unit_features.parquet"),
)
sub = frame.iloc[pos].reset_index(drop=True)
del frame
d = building_zones_floor.design(sub, start, **tables)
print(f"design {d.x.shape} {time.time() - T0:.0f}s", flush=True)
cols = [j for j, n in enumerate(d.names) if not n.startswith(SKIP_PREFIX)]
names = [d.names[j] for j in cols]
X = pd.DataFrame(d.x[:, cols], columns=names)
del d, tables

E = ends.reset_index(drop=True).assign(fit4_unit=unit_number, fit4_held_out=held_end)
E = pd.concat([E, X], axis=1).sort_values(["unit_id", "endpoint"])
E.to_parquet(OUT / "endpoint_design.parquet", index=False)

a = E[E.endpoint == 0].set_index("unit_id")[names]
b = E[E.endpoint == 1].set_index("unit_id")[names].reindex(a.index)
diff = b - a
terms = {}
for n in names:
    dv = diff[n].to_numpy()
    binary = set(np.unique(E[n])) <= {0.0, 1.0}
    t = dict(
        units_changing=int((np.abs(dv) > 1e-9).sum()),
        share_at_1_or_mean=round(float(E[n].mean()), 4),
    )
    if binary:
        t |= dict(on=int((dv > 0.5).sum()), off=int((dv < -0.5).sum()))
    else:
        t |= dict(
            units_changing_over_0_05=int((np.abs(dv) > 0.05).sum()),
            sd_change=round(float(dv.std()), 4),
        )
    terms[n] = t

day = pd.to_datetime(E.latest_day)
month = day.dt.to_period("M").astype(str)
iso = day.dt.isocalendar()
week = iso.year.astype(str) + "-" + iso.week.astype(str)
gap = core.gap
out = dict(
    inputs=dict(
        dataset=str(DATASET),
        endpoints=str(SOL / "season_exploratory_endpoints.parquet"),
        core=str(SOL / "season_exploratory_core_ids.parquet"),
        model="building-zones-floor-asof3-unit",
        split="latest",
    ),
    endpoints=int(len(E)),
    units=int(E.unit_id.nunique()),
    buildings=int(E.building.nunique()),
    endpoints_matching_unit_and_building=int(same.sum()),
    endpoints_held_out_by_fit4_split=int(held_end.sum()),
    units_with_fit4_unit_effect=int(E[E.fit4_unit >= 0].unit_id.nunique()),
    strict_pairs=int(core.strict.fillna(False).sum()),
    dates=dict(
        endpoint0=[
            str(day[E.endpoint == 0].min().date()),
            str(day[E.endpoint == 0].max().date()),
        ],
        endpoint1=[
            str(day[E.endpoint == 1].min().date()),
            str(day[E.endpoint == 1].max().date()),
        ],
        months=int(month.nunique()),
        weeks=int(week.nunique()),
        gap_days_quantiles={
            str(q): int(gap.quantile(q)) for q in (0, 0.1, 0.25, 0.5, 0.75, 0.9, 1)
        },
        endpoints_by_year={
            str(k): int(v) for k, v in day.dt.year.value_counts().sort_index().items()
        },
    ),
    terms=terms,
    seconds=round(time.time() - T0, 1),
)
(OUT / "counts.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
