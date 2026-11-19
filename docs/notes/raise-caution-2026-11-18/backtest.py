"""Free check: how many ads the `raised` caution marks on the Deals backtest and market tables.

A backtest dataset keeps each open ad's final ask, so `drift_deals` marks its buildings from
training ads only, and the table's asks are final asks. What marked ads did after the
backtest day is measured in `current.py` from price paths. This prints the count of marked
ads in the backtest run's table and in the market run's table, and where the marked ads
stand in the market table's order.

Run from the repo root with PYTHONPATH=frontier/src:
python docs/notes/raise-caution-2026-11-18/backtest.py BACKTEST_RUN MARKET_RUN
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from rentfrontier import drift_deals
from rentfrontier import run as run_module

ADS = Path("/data1/apartments/pipeline/datasets/ads-14f9e88d75290a0f.parquet")
pd.set_option("display.width", 200)


def table(run):
    t = drift_deals.deals(Path(run_module.RUNS) / run, ADS)
    t["raised"] = t.cautions.map(lambda v: "raised" in v)
    t["other"] = t.cautions.map(lambda v: any(c != "raised" for c in v))
    return t


t = table(sys.argv[1])
u = t[~t.other]
print(
    "backtest ads",
    len(t),
    "marked",
    t.raised.sum(),
    "buildings",
    t.building[t.raised].nunique(),
)
print("marked with another caution", (t.raised & t.other).sum())
low = u[u.below_share < 0.05]
print(
    "share of uncautioned ads below the 5% point that are marked",
    round(low.raised.mean(), 3),
)
print("share of all uncautioned ads marked", round(u.raised.mean(), 3))
m = table(sys.argv[2])
v = m[~m.other].reset_index(drop=True)
print(
    "\nmarket table",
    len(m),
    "marked",
    m.raised.sum(),
    "buildings",
    m.building[m.raised].nunique(),
    "| no other caution",
    v.raised.sum(),
    "| in the first 100 / 200 / 500 uncautioned",
    v.raised[:100].sum(),
    v.raised[:200].sum(),
    v.raised[:500].sum(),
)
print(
    v[v.raised]
    .head(15)[["building", "unit", "ask", "first_ask", "model_median", "below_share"]]
    .to_string(index=False)
)
