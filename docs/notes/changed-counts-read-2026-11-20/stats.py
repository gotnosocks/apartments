"""Changed-count held-out ads of 2025 and 2026 by direction, by half of buildings.

The direction compares the held-out ad with the apartment's most recent training ad of other
counts: bedrooms up, bedrooms down, or baths only. `back` marks the ads whose previous
training ad already carries the held-out ad's counts (the other counts are older).
"""

import numpy as np
import pandas as pd

from build import OUT

LO, HI = 0.05, 0.95


def direction(c: pd.DataFrame) -> pd.Series:
    d = np.where(
        c.bedrooms > c.o_bedrooms,
        "beds up",
        np.where(c.bedrooms < c.o_bedrooms, "beds down", "baths only"),
    )
    return pd.Series(d, index=c.index)


def cell(g: pd.DataFrame) -> pd.Series:
    bm = g.groupby("building").gap.agg(["sum", "size"])
    se = np.sqrt(((bm["sum"] - bm["size"] * g.gap.mean()) ** 2).sum()) / len(g)
    return pd.Series(
        {
            "n": len(g),
            "gap": g.gap.mean(),
            "se": se,
            "sd": g.gap.std(),
            "low": (g.cdf < LO).mean(),
            "high": (g.cdf > HI).mean(),
        }
    )


def show(g: pd.DataFrame, by: list[str], title: str) -> None:
    print("\n" + title)
    t = g.groupby(by, observed=True).apply(cell, include_groups=False)
    print(t.round(4).to_string())


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    h = pd.read_parquet(OUT / "held.parquet")
    c = pd.read_parquet(OUT / "changed.parquet")
    c["dir"] = direction(c)
    c["back"] = c.p_listing != c.o_listing
    c["days_prev"] = (c.day - c.p_day).dt.days
    c["days_other"] = (c.day - c.o_day).dt.days
    c["dlog_prev"] = c.lask - c.p_lask
    c["dlog_other"] = c.lask - c.o_lask
    c["label_differs"] = (
        c.label.fillna("").str.lower() != c.o_label.fillna("").str.lower()
    )
    c["sqft_ratio"] = c.square_feet / c.o_square_feet
    c.to_parquet(OUT / "changed2.parquet")
    for name, g, gh in (
        ("2025 and 2026", c[c.year >= 2025], h[h.year >= 2025]),
        ("2022 on", c[c.year >= 2022], h[h.year >= 2022]),
    ):
        print("\n=====", name)
        show(gh, ["kind"], "all held-out ads by kind")
        show(gh, ["kind", "half"], "by kind and half")
        show(g, ["dir"], "changed counts by direction")
        show(g, ["dir", "half"], "by direction and half")
        show(g, ["back"], "previous training ad already has the held-out counts")
        show(g, ["dir", "back"], "by direction and back")
        show(g, ["back", "half"], "back by half")
        print("\ngaps to the earlier ads (median, quartiles)")
        q = g.groupby("dir")[["days_prev", "days_other", "dlog_prev", "dlog_other"]]
        print(q.quantile([0.25, 0.5, 0.75]).round(3).unstack().to_string())
        print("mean and sd of the log ask change")
        print(q.agg(["mean", "std"]).round(3).to_string())
        print("held-out ad earlier than the compared ad", (g.days_other < 0).mean())
        print("unit label differs", g.label_differs.mean().round(4))
        sq = g.sqft_ratio.dropna()
        print("both sizes stated", len(sq), "equal", (sq == 1).mean().round(3))
        print("size ratio quantiles", sq.quantile([0.05, 0.25, 0.75, 0.95]).to_dict())
        print("texts identical", (g.text == g.o_text).mean().round(4))
