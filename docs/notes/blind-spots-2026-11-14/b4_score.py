"""S16, part 4: unblind the labels and score each cause by group.

I join `labels.parquet` (fixed in part 3) to `key.parquet` and `draw.parquet`, then for each
category and each group (overpriced, underpriced, control) I compute:

1. the count and share, with a 95% Wilson interval and an SE clustered by building;
2. for each miss group, the share less the controls' share, with a two-sample SE clustered by
   building (the delta method over the pooled ads of the miss group and the controls, as in
   `causal-screens-2026-11-13/common.py`);
3. the ratio of the miss group's share to the controls' share.

A category is flagged when, in either miss group, it has at least 5 reads and either appears
there at least twice as often as among the controls or never among the controls. I also count
the readers' directions within each category and group, the data-error subtypes, the confidence
mix, and the ads with a description over 80 characters. Everything goes to `scores.json` and
`table.csv`."""

import json

import numpy as np
import pandas as pd

OUT = "/data1/apartments/tmp/blind-spots-2026-11-14/"
GROUPS = ("overpriced", "underpriced", "control")
MISS = ("overpriced", "underpriced")

lab = pd.read_parquet(OUT + "labels.parquet")
key = pd.read_parquet(OUT + "key.parquet")
draw = pd.read_parquet(OUT + "draw.parquet")
d = lab.merge(key, on="read_id").merge(draw, on="listing_id")
assert len(d) == 400
text = pd.read_csv(OUT + "text_by_group.csv")


def wilson(k, n, z=1.96):
    p = k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return mid - half, mid + half


def share_se(x, b):
    """SE of the mean of `x`, clustered by `b`."""
    x = np.asarray(x, float)
    t = pd.Series(x - x.mean()).groupby(np.asarray(b)).sum()
    return float(np.sqrt(len(t) / (len(t) - 1) * (t**2).sum()) / len(x))


def diff_se(x, on, b):
    """Mean of `x` where `on` less the mean where not, with its building-clustered SE."""
    g = pd.DataFrame({"x": np.asarray(x, float), "on": np.asarray(on, bool), "b": b})
    m1, m0 = g.x[g.on].mean(), g.x[~g.on].mean()
    g["r"] = np.where(g.on, (g.x - m1) / g.on.sum(), -(g.x - m0) / (~g.on).sum())
    t = g.groupby("b").r.sum()
    return float(m1 - m0), float(np.sqrt(len(t) / (len(t) - 1) * (t**2).sum()))


def score(col):
    rows = []
    for cat in d[col].value_counts().index:
        x = d[col] == cat
        r = {"cause": cat}
        for g in GROUPS:
            m = d.group == g
            k, n = int(x[m].sum()), int(m.sum())
            lo, hi = wilson(k, n)
            r[g] = k
            r[g + "_share"] = k / n
            r[g + "_se"] = share_se(x[m], d.building[m])
            r[g + "_lo"], r[g + "_hi"] = lo, hi
        flagged = []
        for g in MISS:
            m = d.group.isin([g, "control"])
            diff, se = diff_se(x[m], d.group[m] == g, d.building[m].to_numpy())
            r[g + "_diff"], r[g + "_diff_se"] = diff, se
            ratio = r[g + "_share"] / r["control_share"] if r["control"] else np.inf
            r[g + "_ratio"] = ratio
            if r[g] >= 5 and ratio >= 2:
                flagged.append(g)
        r["flag"] = ",".join(flagged)
        rows.append(r)
    return pd.DataFrame(rows)


tab = score("category")
tab.to_csv(OUT + "table.csv", index=False)
d["catsub"] = np.where(d.subtype != "", d.category + "/" + d.subtype, d.category)
sub = score("catsub")
sub = sub[sub.cause.str.contains("/")]
sub.to_csv(OUT + "table_subtypes.csv", index=False)

direction = (
    d.groupby(["category", "group"]).direction.value_counts().unstack(fill_value=0)
)
conf = d.groupby("group").confidence.value_counts().unstack(fill_value=0)
named = d[d.category != "none_apparent"]
top3 = {}
for g, sign in (("overpriced", "raises"), ("underpriced", "lowers")):
    s = named[named.group == g]
    for cat in s.category.value_counts().index[:3]:
        c = s[s.category == cat]
        top3[f"{g}/{cat}"] = {
            "reads": len(c),
            "agree": int((c.direction == sign).sum()),
            "share_agree": float((c.direction == sign).mean()),
        }
misses = d.group.isin(MISS)
res = {
    "data_error_share": {
        g: float((d.category[d.group == g] == "data_error").mean()) for g in GROUPS
    }
    | {"all_misses": float((d.category[misses] == "data_error").mean())},
    "top3_direction": top3,
    "text_over_80": text.set_index("group").to_dict(orient="index"),
    "confidence": conf.to_dict(orient="index"),
    "flagged": tab.loc[tab.flag != "", "cause"].tolist(),
    "flagged_subtypes": sub.loc[sub.flag != "", "cause"].tolist(),
}
json.dump(res, open(OUT + "scores.json", "w"), indent=1)
pd.set_option("display.width", 250, "display.max_columns", 40, "display.max_rows", 80)
show = ["cause", *GROUPS, "flag"]
for g in GROUPS:
    show += [g + "_share", g + "_se"]
print(tab[show].round(3).to_string(index=False))
print()
for g in MISS:
    print(
        tab[["cause", g + "_diff", g + "_diff_se", g + "_ratio"]]
        .round(3)
        .to_string(index=False)
    )
print()
print(sub[["cause", *GROUPS, "flag"]].to_string(index=False))
print()
print(direction.to_string())
print(json.dumps(res, indent=1))
