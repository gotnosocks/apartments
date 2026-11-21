"""The `new_counts` caution on the Deals backtest (range-j): marked ads against the rest.

The mark is `drift_deals._new_counts`, the publish code's own. For each group: the ads, the
shares of final asks below the model's 5% point and above its 95% point, and the scale
factor needed (m of `changed-counts-read-2026-11-20/newseen.py`, se over 200 resamples of
buildings), for all ads and by half of buildings. Then what happened to the ads whose first
ask was placed low (`drift_deals.validate`'s place): days on the market and the shares
cut and raised before closing, marked against the rest.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[1] / "changed-counts-read-2026-11-20"))

from build import half  # noqa: E402
from mark import BT  # noqa: E402
from newseen import cell, tvalue  # noqa: E402
from rentfrontier import drift_deals, drift_score  # noqa: E402

if __name__ == "__main__":
    pd.set_option("display.width", 250)
    run = Path("/data1/apartments/frontier/runs") / BT
    frame, h, held = drift_deals._held_frame(run)
    unit_key = frame.building.astype(str) + "|" + frame.unit_id.astype(str)
    mark = drift_deals._new_counts(frame, held, unit_key)
    res = drift_score.score_run(run)
    h = h.copy()
    h["cdf"] = res["cdf"]
    h["gap"] = np.log(h.latest_ask.to_numpy(float)) - res["pred"]
    h["half"] = h.building.map(half)
    h["u"] = tvalue(h.cdf)
    h["mark"] = np.where(mark, "new_counts", "the rest")
    known = frame.unit_id.notna().to_numpy()
    train = set(unit_key[~held & known])
    h["history"] = unit_key[held].isin(train).to_numpy() & known[held]
    print("held-out ads", len(h), "marked", int(mark.sum()))
    print("marked buildings", h.building[mark].nunique())
    print("marked ads with an unknown unit", int((mark & ~known[held]).sum()))
    for title, g, by in (
        ("all ads", h, ["mark"]),
        ("by half", h, ["mark", "half"]),
        ("ads with unit history", h[h.history], ["mark"]),
        ("ads with unit history, by half", h[h.history], ["mark", "half"]),
    ):
        print("\n" + title)
        print(g.groupby(by).apply(cell, include_groups=False).round(3).to_string())

    # The first ask's place and what followed, as `drift_deals.validate` computes them.
    market = drift_deals._manifest(run)
    ads = Path(market["ads"])
    a = drift_deals._ads(ads, h.listing_id)
    codes, _ = drift_deals._run_cautions(run, frame, h, held, a, ads, None)
    h["others"] = [bool(set(c) - {"new_counts"}) for c in codes]
    final = h.latest_ask.to_numpy(float)
    free = np.nan_to_num(a.months_free.to_numpy(float)) > 0
    first = drift_deals.first_net(
        a.first_ask.to_numpy(float), final, a.page_price, free
    )
    ok = np.isfinite(first) & (first > 0)
    at = drift_score.score_run(run, at=np.log(np.where(ok, first, final)))
    h["place"] = at["cdf_at"]
    day = pd.to_datetime(h.final_day if "final_day" in h else h.latest_day)
    off = pd.to_datetime(a.off_day).to_numpy()
    end = np.where(np.isnat(off), day.to_numpy(), off)
    h["days"] = (end - pd.to_datetime(a.first_day).to_numpy()) / np.timedelta64(1, "D")
    ok &= np.isfinite(h.days.to_numpy()) & (h.days.to_numpy() >= 0)
    h["change"] = final / np.where(ok, first, 1.0) - 1
    v = h[ok]
    print(
        "\nads with a first ask", len(v), "marked", int((v.mark == "new_counts").sum())
    )
    print(
        "marked with another caution", int((v.others & (v.mark == "new_counts")).sum())
    )

    def after(g: pd.DataFrame) -> pd.Series:
        return pd.Series(
            {
                "n": len(g),
                "median_days": g.days.median(),
                "within_14_days": (g.days <= 14).mean(),
                "cut": (g.change < -0.001).mean(),
                "raised": (g.change > 0.001).mean(),
                "median_change_pct": 100 * g.change.median(),
            }
        )

    for title, g in (
        ("first ask below the 5% point", v[v.place < 0.05]),
        ("first ask in the lowest tenth", v[v.place < 0.1]),
        (
            "first ask in the lowest tenth, no other caution",
            v[(v.place < 0.1) & ~v.others],
        ),
        ("first ask above the 95% point", v[v.place > 0.95]),
        ("all first asks", v),
    ):
        print("\n" + title)
        print(g.groupby("mark").apply(after, include_groups=False).round(3).to_string())
    print("\nfirst asks below the 5% point and above the 95% point, by mark")
    t = v.groupby("mark").place.agg(
        n="size", low=lambda p: (p < 0.05).mean(), high=lambda p: (p > 0.95).mean()
    )
    print(t.round(3).to_string())
