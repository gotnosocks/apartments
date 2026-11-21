"""Reviewer's checks for PR #1495: exact copies in the own check, other-bedroom unit fills
against line fills on the same rows, and large sizes by decile of predicted rent."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
from stats import load, errors
from build import RUN

pd.set_option("display.width", 200)
d = load()
print("rows", len(d), "unique listing_id", d.listing_id.nunique())
o = d[d.stated.between(150, 8000) & (d.would != "none")].copy()
o["fill"], o["check"] = o.would_fill, o.stated
e = np.log(o.fill / o.check).abs()
print("own check exact-equal share (|log|<0.005) by class")
print(o.assign(eq=e < 0.005).groupby("would").eq.mean().round(3).to_string())


# own check limited to sources from another day group? count unit_n==1 share
# head-to-head: other-bed unit fill vs line fill, rows with both
def h2h(t, name):
    t = t[(t.line_n > 0)]
    rows = []
    for hf in "AB":
        g = t[t.half == hf]
        a = errors(
            g.assign(fill=g.unit_other_fill if "unit_other_fill" in g else g.unit_fill)
        )
        b = errors(g.assign(fill=g.line_fill))
        rows.append(
            (
                name,
                hf,
                int(a.n),
                a.off30,
                b.off30,
                a.big30,
                b.big30,
                a.rmse_fill,
                b.rmse_fill,
                a.rmse_med,
            )
        )
    g = t
    a = errors(g.assign(fill=g.unit_other_fill))
    b = errors(g.assign(fill=g.line_fill))
    rows.append(
        (
            name,
            "all",
            int(a.n),
            a.off30,
            b.off30,
            a.big30,
            b.big30,
            a.rmse_fill,
            b.rmse_fill,
            a.rmse_med,
        )
    )
    print(
        pd.DataFrame(
            rows,
            columns=[
                "check",
                "half",
                "n",
                "off30_unit",
                "off30_line",
                "big30_unit",
                "big30_line",
                "rmse_unit",
                "rmse_line",
                "rmse_med",
            ],
        )
        .round(3)
        .to_string()
    )


ob = o[o.would == "unit, other beds"].copy()
h2h(ob, "own")
f = d[d.source.isin(["unit", "line"]) & d.truth.notna()].copy()
f["check"] = f.truth
fb = f[f.klass == "unit, other beds"].copy()
h2h(fb, "later")
# later check restricted to truth ads not in the same bedroom? already same beds by construction.
# claim 5: matched predicted rent
s = np.load(RUN / "pred_scores.npz")
h = d[d.held].copy()
h["pred"] = pd.Series(s["pred"], index=h.index)
h = h[(h.year >= 2022)]
h["pq"] = pd.qcut(h.pred, 10, labels=False)
big = h[h.ratio > 1.4]
grp = big.klass.where(
    big.klass.isin(["stated", "line, other apartments", "unit, same beds"])
)
big = big.assign(g=grp).dropna(subset=["g"])
print("\nratio>1.4 held 2022+: pred decile mix by source")
print(pd.crosstab(big.g, big.pq).to_string())
big["low"] = big.cdf < 0.05
print(big.groupby(["g"]).low.agg(["mean", "size"]).round(3).to_string())
# reweight stated to filled pred-decile mix
for k in ["line, other apartments", "unit, same beds"]:
    w = big[big.g == k].pq.value_counts(normalize=True)
    st = big[big.g == "stated"].groupby("pq").low.mean()
    print(
        k,
        "stated low5 reweighted to its pred mix",
        round((st.reindex(w.index) * w).sum(), 3),
        "own",
        round(big[big.g == k].low.mean(), 3),
    )
# within top 3 deciles only
for lo_ in (0, 7):
    b2 = big[big.pq >= lo_]
    print(
        "pred decile >=",
        lo_,
        b2.groupby(["g", "half"]).low.agg(["mean", "size"]).round(3).to_string(),
    )
# also all-size low share by pred decile for stated vs filled
h["g"] = h.klass
print("\nlow5 by pred decile, all sizes")
print(
    h[h.g.isin(["stated", "line, other apartments", "unit, same beds"])]
    .groupby(["pq", "g"])
    .apply(lambda x: (x.cdf < 0.05).mean())
    .unstack()
    .round(3)
    .to_string()
)
