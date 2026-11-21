"""The proposed rule's threshold: line fills by how far the fill is over the bedroom median.

For each band of fill / bedroom median, the field checks of `stats.py` and the held-out
tails, by half of buildings. Unit fills from the ad's bedroom count and stated sizes are
printed in the same bands for comparison. A blanked row is given the bedroom median, so a
band is worth blanking on the field evidence where `rmse_fill` is above `rmse_med`.
Then, for each threshold of 20% to 60%, the rows above it: counts, field errors, tails.
"""

import numpy as np
import pandas as pd

from stats import errors, load, show, tails

EDGES = [0, 0.8, 1.2, 1.3, 1.4, 1.5, 1.6, 2.0, np.inf]
CUTS = [1.2, 1.3, 1.4, 1.5, 1.6]

if __name__ == "__main__":
    pd.set_option("display.width", 200)
    d = load()
    d["band"] = pd.cut(d.ratio, EDGES).astype(str)
    d["wband"] = pd.cut(d.would_fill / d.bed_median, EDGES).astype(str)
    filled = d[d.source.isin(["unit", "line"]) & d.truth.notna()]
    filled = filled.assign(fill=filled.sqft, check=filled.truth)
    own = d[d.stated.between(150, 8000) & (d.would != "none")]
    own = own.assign(fill=own.would_fill, check=own.stated)
    held = d[d.held & (d.year >= 2022)]
    for k in ("line, other apartments", "unit, same beds"):
        show(
            f"later check by band, {k}",
            filled[filled.klass == k].groupby(["band", "half"]).apply(errors),
        )
        show(
            f"own check by band, {k}",
            own[own.would == k].groupby(["wband", "half"]).apply(errors),
        )
    for k in ("line, other apartments", "unit, same beds", "stated"):
        show(
            f"held-out 2022 on by band, {k}",
            held[held.klass == k].groupby(["band", "half"]).apply(tails),
        )
        h2 = held[(held.klass == k) & (held.year >= 2025)]
        show(f"held-out 2025-26 by band, {k}", h2.groupby("band").apply(tails))

    line = d[d.klass == "line, other apartments"]
    rows = []
    for cut in CUTS:
        for hf in ("A", "B"):
            a = line[(line.ratio > cut) & (line.half == hf)]
            f = filled[
                (filled.klass == "line, other apartments") & (filled.ratio > cut)
            ]
            f = f[f.half == hf]
            o = own[(own.would == "line, other apartments") & (own.half == hf)]
            o = o[o.would_fill / o.bed_median > cut]
            t = tails(a[a.held & (a.year >= 2022)])
            fe, oe = errors(f), errors(o)
            rows.append(
                {
                    "over": cut,
                    "half": hf,
                    "train": int((~a.held).sum()),
                    "held": int(a.held.sum()),
                    "later_n": fe.n,
                    "later_big30": fe.big30,
                    "later_rmse_fill": fe.rmse_fill,
                    "later_rmse_med": fe.rmse_med,
                    "own_n": oe.n,
                    "own_big30": oe.big30,
                    "own_rmse_fill": oe.rmse_fill,
                    "own_rmse_med": oe.rmse_med,
                    "held22": t.n,
                    "low5": t.low5,
                    "high95": t.high95,
                }
            )
    show(
        "line fills above each threshold",
        pd.DataFrame(rows).set_index(["over", "half"]),
    )
    print(
        "\nline fills from another piece of the ad's apartment:",
        (d.source.eq("line") & (d.line_piece_n > 0)).sum(),
    )
    u = d[d.klass.isin(["unit, other beds", "unit, mixed beds"])]
    print(
        "unit fills with another bedroom count:",
        pd.crosstab(u.klass, [u.held, u.year >= 2022]).to_string(),
    )
    low = held[held.cdf < 0.05]
    print("held-out 2022 on:", len(held), "below 5%:", len(low))
    for k in ("unit, other beds", "unit, mixed beds", "line, other apartments"):
        print(
            k,
            "share of low tail",
            round((low.klass == k).mean(), 4),
            "of ads",
            round((held.klass == k).mean(), 4),
        )

    # Where the other-bedroom unit fills go if the unit layer reads the ad's bedroom count
    # only: to the line layer where it has a size, else to no size.
    u = d[d.klass == "unit, other beds"]
    to_line = u.line_n > 0
    print("\nunit, other beds: to line", pd.crosstab(to_line, u.held).to_string())
    o2 = own[own.would == "unit, other beds"]
    has = o2.line_n > 0
    show(
        "own check, other beds, the unit fill, by line layer present",
        o2.groupby([has, "half"]).apply(errors),
    )
    show(
        "own check, other beds, the line fill instead",
        o2[has].assign(fill=o2.line_fill[has]).groupby("half").apply(errors),
    )
    for cut in (0, 1.2, 1.4):
        t = held[(held.klass == "unit, other beds") & (held.ratio > cut)]
        print(
            "held-out 2022 on, unit other beds, over", cut, tails(t).round(3).to_dict()
        )
    # The slope of the checked log relative size on the filled one: 1 for a fill as good as
    # a stated size, less where large fills overstate.
    for name, t, col in (("later", filled, "klass"), ("own", own, "would")):
        for k in ("line, other apartments", "unit, same beds", "unit, other beds"):
            for hf in ("A", "B"):
                g = t[(t[col] == k) & (t.half == hf)]
                x, y = np.log(g.fill / g.bed_median), np.log(g.check / g.bed_median)
                print(
                    name, k, hf, "n", len(g), "slope", round(np.polyfit(x, y, 1)[0], 3)
                )
    big = held[held.ratio > 1.4]
    show(
        "held-out 2022 on, size over 1.4 times the median",
        big.groupby(["klass", "half"]).apply(tails),
    )
