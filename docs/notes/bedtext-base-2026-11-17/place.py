"""Compare where two backtest runs place each open ad's first ask, by the bedroom-text flag.

    python docs/notes/bedtext-base-2026-11-17/place.py DATASET ADS BASE_RUN FLAG_RUN

DATASET is the backtest copy `rentfrontier.b0bedtext` wrote, and ADS the pipeline's ads
file. For each run I compute the place of every open ad's first ask in the run's predictive
distribution, as `drift_deals.validate` does (the first ask net of free months). An ad in
the lowest tenth of places is a candidate for the Deals list. I print, for all ads and for
the flagged ones: the mean place under each run, the ads each run puts in the lowest tenth,
and those ads' median days on market and share later raised.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from rentfrontier import drift_deals, drift_score


def places(run_dir: Path, ads: Path):
    _, h, _ = drift_deals._held_frame(run_dir)
    a = drift_deals._ads(ads, h.listing_id)
    final = h.latest_ask.to_numpy(float)
    free = np.nan_to_num(a.months_free.to_numpy(float)) > 0
    first = drift_deals.first_net(
        a.first_ask.to_numpy(float), final, a.page_price, free
    )
    ok = np.isfinite(first) & (first > 0)
    res = drift_score.score_run(run_dir, at=np.log(np.where(ok, first, final)))
    day = pd.to_datetime(h.final_day if "final_day" in h else h.latest_day)
    off = pd.to_datetime(a.off_day).to_numpy()
    end = np.where(np.isnat(off), day.to_numpy(), off)
    days = (end - pd.to_datetime(a.first_day).to_numpy()) / np.timedelta64(1, "D")
    ok &= np.isfinite(days) & (days >= 0)
    change = final / np.where(ok, first, 1.0) - 1
    return h.listing_id.astype(str).to_numpy(), res["cdf_at"], ok, days, change


def main(argv):
    dataset, ads, base, new = argv
    lid, pa, ok, days, change = places(Path(base), Path(ads))
    lid2, pb, ok2, _, _ = places(Path(new), Path(ads))
    assert np.array_equal(lid, lid2) and np.array_equal(ok, ok2)
    cols = ["listing_id", "bed_flex_at", "bed_text_fewer"]
    rows = pq.read_table(f"{dataset}/rows.parquet", columns=cols).to_pandas()
    rows = rows.assign(listing_id=rows.listing_id.astype(str)).drop_duplicates()
    f = rows.set_index("listing_id").reindex(lid)
    flag = (f.bed_flex_at.fillna(False) | f.bed_text_fewer.fillna(False)).to_numpy(bool)
    print(
        f"open ads {len(lid)}, with a first ask {ok.sum()}, flagged {(flag & ok).sum()}"
    )
    for name, m in (("all", ok), ("flagged", ok & flag), ("unflagged", ok & ~flag)):
        la, lb = m & (pa < 0.1), m & (pb < 0.1)
        print(
            f"{name:10s} ads {m.sum():5d}  mean place base {pa[m].mean():.3f}"
            f" flag {pb[m].mean():.3f}  lowest tenth base {la.sum():4d} flag {lb.sum():4d}"
            f" both {(la & lb).sum():4d}"
        )
        for run, low in (("base", la), ("flag", lb)):
            if low.any():
                print(
                    f"    {run} lowest tenth: median days {np.median(days[low]):.0f},"
                    f" share raised {100 * (change[low] > 0.001).mean():.1f}%,"
                    f" share cut {100 * (change[low] < -0.001).mean():.1f}%"
                )


if __name__ == "__main__":
    main(sys.argv[1:])
