"""The field mark the read points to, on every changed-count held-out ad, by half.

`fresh`: the apartment's most recent training ad carries other counts than the held-out ad.
`back`: that ad already carries the held-out ad's counts and the other counts are older.
Both come from coded counts and dates alone. The mark is binary, so no threshold was chosen;
both halves are shown. Part 1 is the latest-split run (l2bt) from 2022 on. Part 2 is the
Deals backtest (range-j), whose model already holds mean terms for changed counts.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from build import OUT, half
from stats import cell, show

BT = "drift-building-bedtext-layout-range-b0-market-d9028c57-range-j"


def l2() -> None:
    h = pd.read_parquet(OUT / "held.parquet")
    c = pd.read_parquet(OUT / "changed2.parquet")
    c["mark"] = np.where(c.back, "changed, back", "changed, fresh")
    h = h.merge(
        c[["listing_id", "mark", "dir", "days_prev"]], on="listing_id", how="left"
    )
    h["mark"] = h.mark.fillna("counts as before")
    for name, g in (
        ("2022 on", h[h.year >= 2022]),
        ("2022 to 2024", h[h.year.between(2022, 2024)]),
        ("2025 and 2026", h[h.year >= 2025]),
    ):
        print("\n===== l2bt,", name)
        show(g, ["mark"], "by mark")
        show(g, ["mark", "half"], "by mark and half")
    g = h[(h.year >= 2022) & (h.mark != "counts as before")]
    show(g, ["mark", "dir", "half"], "2022 on: by mark, direction and half")
    f = g[g.mark == "changed, fresh"].copy()
    f["since"] = pd.cut(f.days_prev, [-1e5, 0, 365, 730, 1460, 1e5])
    show(f, ["since"], "fresh: by days since the previous training ad")
    show(f, ["since", "half"], "fresh: by days since the previous training ad and half")
    f["text"] = np.where(
        f.bed_flex_at | f.bed_text_fewer,
        "flex or fewer in text",
        np.where(f.bed_text_more, "more in text", "neither"),
    )
    show(f, ["text", "half"], "fresh: by the model's bedroom text marks")
    print("\nshare of the excess tails held by fresh, 2022 on")
    a = h[h.year >= 2022]
    base = a[a.mark == "counts as before"]
    for hf in "AB":
        for tail, m in (("low", a.cdf < 0.05), ("high", a.cdf > 0.95)):
            bm = (base.cdf < 0.05) if tail == "low" else (base.cdf > 0.95)
            rate = bm[base.half == hf].mean()
            out = []
            for k in ("changed, fresh", "changed, back"):
                s = (a.mark == k) & (a.half == hf)
                out.append(f"{k}: {m[s].sum() - rate * s.sum():.0f} over the base rate")
            print(hf, tail, f"base {rate:.3f}", "; ".join(out))


def backtest() -> None:
    from rentfrontier import drift_deals, drift_score

    run = Path("/data1/apartments/frontier/runs") / BT
    frame, h, held = drift_deals._held_frame(run)
    res = drift_score.score_run(run)
    h = h.copy()
    h["cdf"] = res["cdf"]
    h["gap"] = np.log(h.latest_ask.to_numpy(float)) - res["pred"]
    h["half"] = h.building.map(half)
    t = frame[~held].copy()
    for d in (t, h):
        d["baths"] = d.full_baths + 0.5 * d.half_baths.fillna(0)
        d["day"] = pd.to_datetime(d.price_at, utc=True).dt.tz_localize(None)
    u = t.groupby(["building", "unit_id"]).agg(
        un=("baths", "size"),
        bath_lo=("baths", "min"),
        bath_hi=("baths", "max"),
        bed_lo=("bedrooms", "min"),
        bed_hi=("bedrooms", "max"),
    )
    last = t.sort_values("day").groupby(["building", "unit_id"])[["bedrooms", "baths"]]
    last = last.last().rename(columns={"bedrooms": "p_bed", "baths": "p_bath"})
    h = h.merge(
        u.join(last), left_on=["building", "unit_id"], right_index=True, how="left"
    )
    same = (h.baths == h.bath_lo) & (h.baths == h.bath_hi)
    same &= (h.bedrooms == h.bed_lo) & (h.bedrooms == h.bed_hi)
    fresh = (h.bedrooms != h.p_bed) | (h.baths != h.p_bath)
    h["mark"] = np.where(
        h.un.isna(),
        "no unit history",
        np.where(
            same, "counts as before", np.where(fresh, "changed, fresh", "changed, back")
        ),
    )
    print("\n===== Deals backtest (range-j), held-out ads", len(h))
    show(h, ["mark"], "by mark")
    show(h, ["mark", "half"], "by mark and half")
    print(cell(h).round(4).to_string())


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    l2() if sys.argv[1] == "l2" else backtest()
