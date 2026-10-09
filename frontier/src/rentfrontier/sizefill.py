"""Each row's apartment size as of the day it was priced: the size it states,
else one filled from rows priced on earlier days only. Reads no rents.

Only 29% of the six neighbourhoods' rows state a size (150 to 8,000 sq ft).
`features.base_v1`'s `unit_size` fills from the median of all of the unit's
listings, later ones included. Here every fill reads earlier days only, in
this order (`SOURCES`):

- own: the row's stated size.
- unit: the mean log size of the unit's earlier rows that state one.
- line: other units of the same line (`data.unit_line_key`), bedrooms and full
  baths, each by the first size it stated, before the row's day.
- building: the same for other units of the building with the same bedrooms
  and full baths.
- none: no fill.

Accuracy, leave-one-unit-out on rows that state a size (NB6 frame,
2026-10-09): unit 0% median error, 93% within 10%; line 0.7%, 89%; building
5.5%, 70%. The cascade fills 49,753 of the 99,124 rows that state no size.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import data

MIN_SQFT, MAX_SQFT = 150, 8000
SOURCES = ("own", "unit", "line", "building", "none")


def earlier_sum(query_key, query_day, event_key, event_day, event_value):
    """Per query: the sum and count of events with its key on an earlier day.
    Queries with a missing key get 0 and 0."""
    q = pd.DataFrame(
        {"key": query_key, "day": query_day, "event": 0, "v": 0.0, "q": True}
    ).reset_index(drop=True)
    q["pos"] = np.arange(len(q))
    e = pd.DataFrame(
        {"key": event_key, "day": event_day, "event": 1, "v": event_value, "q": False}
    ).dropna(subset=["key", "v"])
    e["pos"] = -1
    d = pd.concat([q.dropna(subset=["key"]), e], ignore_index=True)
    # A query sorts before the events of its own day, so they do not count.
    d = d.sort_values(["key", "day", "event"], kind="stable")
    g = d.groupby("key", sort=False)
    d["s"], d["n"] = g.v.cumsum(), g.event.cumsum()
    hit = d[d.q]
    s, n = np.zeros(len(q)), np.zeros(len(q))
    s[hit.pos.to_numpy()] = hit.s.to_numpy()
    n[hit.pos.to_numpy()] = hit.n.to_numpy()
    return s, n


def _other_units(frame, key, day, lsq, known):
    """Mean log size of other units with `key`, each by its first stated size,
    over units that first stated it before the row's day."""
    rows = pd.DataFrame(
        {"unit": frame.unit_id.to_numpy(), "key": key, "day": day, "lsq": lsq}
    )[known.to_numpy() & key.notna().to_numpy()]
    first = rows.sort_values("day", kind="stable").groupby(["unit", "key"]).head(1)
    s, n = earlier_sum(key, day, first.key, first.day, first.lsq)
    own_key = key + "|" + frame.unit_id.astype(str)
    os_, on = earlier_sum(
        own_key, day, first.key + "|" + first.unit.astype(str), first.day, first.lsq
    )
    s, n = s - os_, n - on
    return np.where(n > 0, s / np.maximum(n, 1), np.nan)


def asof_size(frame: pd.DataFrame) -> pd.DataFrame:
    """Per row: `sqft` (NaN where no fill) and its `source` (`SOURCES`)."""
    sqft = frame.square_feet.astype(float)
    known = sqft.between(MIN_SQFT, MAX_SQFT)
    lsq = np.log(sqft.where(known))
    day = pd.to_datetime(frame.price_at, utc=True).dt.floor("D")
    unit_s, unit_n = earlier_sum(
        frame.unit_id.astype(str),
        day,
        frame.unit_id.astype(str)[known],
        day[known],
        lsq[known],
    )
    unit = np.where(unit_n > 0, unit_s / np.maximum(unit_n, 1), np.nan)
    beds = frame.bedrooms.round().clip(0, 5).astype(float)
    baths = frame.full_baths.astype(float)
    rooms = ("|" + beds.astype(str) + "|" + baths.astype(str)).where(
        beds.notna() & baths.notna()
    )
    line = data.unit_line_key(frame) + rooms
    building = frame.building + rooms
    fills = [
        ("own", lsq.to_numpy()),
        ("unit", unit),
        ("line", _other_units(frame, line, day, lsq, known)),
        ("building", _other_units(frame, building, day, lsq, known)),
    ]
    out = np.full(len(frame), np.nan)
    source = np.full(len(frame), "none", dtype=object)
    for name, value in fills:
        take = np.isnan(out) & ~np.isnan(value)
        out[take], source[take] = value[take], name
    return pd.DataFrame({"sqft": np.exp(out), "source": source}, index=frame.index)
