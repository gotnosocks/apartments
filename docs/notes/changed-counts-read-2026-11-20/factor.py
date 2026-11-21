"""The scale factor needed (m of `newseen.py`) on the Deals backtest (range-j), by mark.

The marks use the model unit (the full unit id) and its training ads dated strictly before
the held-out ad: no unit history, counts as before (every earlier ad has the held-out
counts), back (the most recent has them and an older one differs), fresh (the most recent
differs). Fresh ads are split by whether any earlier ad of the unit has the held-out counts.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from build import half
from mark import BT
from newseen import show, tvalue
from rentfrontier import drift_deals, drift_score

if __name__ == "__main__":
    pd.set_option("display.width", 250)
    run = Path("/data1/apartments/frontier/runs") / BT
    frame, h, held = drift_deals._held_frame(run)
    res = drift_score.score_run(run)
    h = h.copy()
    h["cdf"] = res["cdf"]
    h["gap"] = np.log(h.latest_ask.to_numpy(float)) - res["pred"]
    h["half"] = h.building.map(half)
    h["u"] = tvalue(h.cdf)
    t = frame[~held].copy()
    for d in (t, h):
        d["baths"] = d.full_baths + 0.5 * d.half_baths.fillna(0)
        d["day"] = pd.to_datetime(d.price_at, utc=True).dt.tz_localize(None)
    print("training max day", t.day.max(), "held-out days", h.day.min(), h.day.max())
    h["lid"] = np.arange(len(h))
    keys = ["building", "unit_id", "bedrooms", "baths", "day"]
    m = h[["lid", *keys]].merge(
        t[keys], on=["building", "unit_id"], suffixes=("", "_t")
    )
    print(
        "unit training rows dated on or after the held-out ad",
        (m.day_t >= m.day).mean(),
    )
    m = m[m.day_t < m.day].sort_values("day_t")
    m["same"] = (m.bedrooms == m.bedrooms_t) & (m.baths == m.baths_t)
    g = m.groupby("lid").same
    f = pd.DataFrame({"seen": g.any(), "every": g.all(), "last": g.last()})
    h = h.merge(f, left_on="lid", right_index=True, how="left")
    seen = h.seen.fillna(False).astype(bool)
    h["mark"] = np.where(
        h.seen.isna(),
        "no unit history",
        np.where(
            h.every.fillna(False).astype(bool),
            "counts as before",
            np.where(
                h["last"].fillna(False).astype(bool),
                "back",
                np.where(seen, "fresh, counts seen", "fresh, counts new"),
            ),
        ),
    )
    h["mark2"] = h.mark.str.replace(", counts.*", "", regex=True)
    print("\n===== Deals backtest (range-j), held-out ads", len(h))
    show(h, ["mark2"], "by mark")
    show(h, ["mark2", "half"], "by mark and half")
    show(h, ["mark"], "fresh split by counts seen")
    show(h, ["mark", "half"], "fresh split by counts seen and half")
