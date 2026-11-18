"""Free check: asks cut to a net-of-free-months fraction of the same ad's first ask."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from rentfrontier import drift_deals

ADS = Path("/data1/apartments/pipeline/datasets/ads-14f9e88d75290a0f.parquet")
R = Path("/data1/apartments/frontier/runs")
FRACTIONS = {
    f"{n - k}/{n}": (n - k) / n for n in (12, 13, 14, 15, 16, 18) for k in (1, 2, 3)
}
TOL = 0.0004


def nearest(ratio):
    names, vals = list(FRACTIONS), np.array(list(FRACTIONS.values()))
    d = np.abs(ratio[:, None] - vals[None, :])
    j = d.argmin(1)
    return np.where(d.min(1) < TOL, np.array(names)[j], "")


a = pq.read_table(
    ADS,
    columns=["listing_id", "page_price", "first_ask", "latest_ask", "months_free"],
).to_pandas()
a = a.drop_duplicates("listing_id").set_index("listing_id")
for run in sys.argv[1:]:
    t = drift_deals.deals(R / run, ADS)
    t = t.join(a, on="listing_id", rsuffix="_ad")
    ratio = (t.page_price_ad / t.first_ask).to_numpy()
    cut = ratio < 0.999
    t["net"] = np.where(cut, nearest(np.nan_to_num(ratio, nan=1.0)), "")
    free = t.months_free_ad.fillna(0) > 0
    clean = ~t.cautions.map(bool)
    print(run, "ads", len(t), "cut", cut.sum(), "at a fraction", (t.net != "").sum())
    # ratios of cut ads in bands of the same width beside 11/12, as the chance rate
    for name in ("11/12", "12/13", "13/14", "10/12", "14/15"):
        v = FRACTIONS[name]
        beside = [
            (np.abs(ratio - (v + s * 2 * TOL * j)) < TOL).sum()
            for s in (-1, 1)
            for j in (2, 3, 4)
        ]
        m = t.net == name
        print(
            f"  {name:6s} n {m.sum():4d} beside (mean of 6 bands) {np.mean(beside):5.1f}"
            f" free coded {(m & free).sum():3d} uncautioned {(m & clean).sum():3d}"
            f" median below_share {t.below_share[m].median():.3f}"
        )
    m = t.net.isin(["11/12", "12/13", "13/14", "10/12"])
    u = t[clean].reset_index(drop=True)
    mu = u.net.isin(["11/12", "12/13", "13/14", "10/12"])
    for n in (100, 200, 500):
        print(f"  first {n} uncautioned: {mu[:n].sum()}")
    print(
        "  share below 0.1:",
        round(100 * (t.below_share[m] < 0.1).mean(), 1),
        "all ads:",
        round(100 * (t.below_share < 0.1).mean(), 1),
        "other cut ads:",
        round(100 * (t.below_share[cut & ~m] < 0.1).mean(), 1),
    )
    t[m][
        [
            "listing_id",
            "below_share",
            "net",
            "months_free_ad",
            "first_ask",
            "page_price_ad",
        ]
    ].to_csv(
        f"/data1/apartments/tmp/rooms-up-read-2026-11-18/net-{run[-7:]}.csv",
        index=False,
    )
