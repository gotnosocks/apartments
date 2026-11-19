"""Free check: does the `raised` mark say an ad that is low on the backtest day is raised later?

A backtest dataset keeps each open ad's final ask, so this reads each open ad's ask on the
backtest day from its price path (`paths.py`). The mark uses what was knowable on the day:
training ads at their dataset ask and open ads at their ask on the day. For marked and
unmarked ads it prints the share whose ask rose afterwards, among all ads and among ads
whose ask on the day is below the 5% and 10% points of the run's prediction, split by
whether the ad still stood at or below its first ask.

Run from the repo root with PYTHONPATH=frontier/src:
python docs/notes/raise-caution-2026-11-18/current.py BACKTEST_RUN PATHS.parquet
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from rentfrontier import cautions, drift_deals, drift_score
from rentfrontier import run as run_module

ADS = Path("/data1/apartments/pipeline/datasets/ads-14f9e88d75290a0f.parquet")
pd.set_option("display.width", 200)
run_dir = Path(run_module.RUNS) / sys.argv[1]
frame, h, held = drift_deals._held_frame(run_dir)
day = pd.to_datetime(frame.price_at).max().tz_localize(None).normalize()
paths = (
    pd.read_parquet(sys.argv[2])
    .set_index("listing_id")
    .reindex(h.listing_id.astype(str))
)


def on_day(days, prices):
    """The last price dated on or before the day, and the path's last price."""
    if not isinstance(days, np.ndarray) or not len(days):
        return np.nan, np.nan
    before = [p for d, p in zip(days, prices) if pd.Timestamp(d) <= day]
    return (before[-1] if before else np.nan), prices[-1]


at = np.array([on_day(d, p) for d, p in zip(paths.days, paths.prices)])
a = drift_deals._ads(ADS, frame.listing_id)
first = a.first_ask.to_numpy(float)
ask = frame.latest_ask.to_numpy(float).copy()
ask[held] = at[:, 0]


def naive(days):
    return pd.DatetimeIndex(pd.to_datetime(np.asarray(days), utc=True)).tz_localize(
        None
    )


mark = cautions.raised(
    frame.building.to_numpy(),
    frame.unit_id.to_numpy(),
    naive(a.first_day),
    first,
    np.nan_to_num(ask),
    day,
)[held]
ah = a[held]
net = drift_deals.first_net(
    at[:, 0], h.latest_ask.to_numpy(float), ah.page_price, ah.months_free
)
ok = np.isfinite(net) & (net > 0)
res = drift_score.score_run(
    run_dir, at=np.log(np.where(ok, net, h.latest_ask.to_numpy(float)))
)
t = pd.DataFrame(
    dict(
        building=h.building.to_numpy(),
        mark=mark,
        place=res["cdf_at"],
        after=at[:, 1] / at[:, 0] - 1,
        own=at[:, 0] / first[held] - 1,
    )
)[ok]
print("backtest day", day.date(), "open ads", len(h), "with an ask on the day", len(t))
print("ask on the day differs from the final ask", (t.after.abs() > 0.001).sum())
print("marked", t.mark.sum(), "buildings", t.building[t.mark].nunique())
half = t.building.map(lambda b: hash(str(b)) % 2 == 0)
groups = {
    "all": t.place >= 0,
    "at or below the first ask": t.own <= 0.001,
    "below the 10% point": t.place < 0.10,
    "below the 5% point": t.place < 0.05,
    "below the 5% point, at or below the first ask": (t.place < 0.05)
    & (t.own <= 0.001),
    "below the 5% point, already raised": (t.place < 0.05) & (t.own > 0.001),
    "below the 15% point, at or below the first ask": (t.place < 0.15)
    & (t.own <= 0.001),
}
rows = []
for name, g in groups.items():
    for m in (True, False):
        s = t[g & (t.mark == m)]
        rows.append(
            dict(
                group=name,
                marked=m,
                ads=len(s),
                buildings=s.building.nunique(),
                up15=(s.after >= 0.15).mean(),
                up5=(s.after >= 0.05).mean(),
                cut5=(s.after <= -0.05).mean(),
            )
        )
print(pd.DataFrame(rows).round(3).to_string(index=False))
low = t[t.place < 0.05]
print("share of ads below the 5% point that are marked", round(low.mark.mean(), 3))
top = (
    low[low.mark]
    .groupby("building")
    .agg(ads=("after", "size"), up15=("after", lambda v: (v >= 0.15).sum()))
)
print(top.sort_values("ads", ascending=False).head(12).to_string())
