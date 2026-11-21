"""The readers' traits coded by pattern on every held-out ad, against the gap, by half.

Usage: t1.py l2|bt

Marks, each from the ad's own text or label and never from a rent:
- `outdoor_text`: the repo's private outdoor pattern (`features.REWRITTEN_FLAGS`);
- `penthouse_text`, `duplex_text`, `corner_text`, `office_text`: the words themselves;
- `plan_named`: a named residence, plan or line ("Residence 4", "the B line");
- `template`: the text, digits masked, is the same as another held-out ad's of the building.

For each mark: the ads and buildings holding it, the mean gap less the rest's (plain), and the
gap within building and bedroom count (the coefficient on the mark with a level for each
building and count), both with standard errors clustered by building. Then the shared
variance of pairs in one building and count whose texts are the same template, against pairs
with two texts.
"""

import re
import sys

import numpy as np
import pandas as pd

from b1 import OUT
from rentfrontier import features

MARKS = {
    "outdoor_text": features.REWRITTEN_FLAGS["private_outdoor"],
    "penthouse_text": r"\bpenthouse\b",
    "duplex_text": r"\b(?:duplex|triplex)\b",
    "corner_text": r"\bcorner (?:unit|apartment|residence|home|[0-9a-z]+[- ]bed|living)",
    "office_text": r"home office|\bden\b|bonus room",
    "plan_named": r"\bresidence (?:[a-z]\b|\d)|\b(?:the )?[a-z][- ]line\b|\bline [a-z]\b"
    r"|\b(?:floor ?plan|layout|plan) (?:type )?[a-z]?\d{1,2}[a-z]?\b",
}
rng = np.random.default_rng(20261120)


def clustered(x, y, b):
    """Mean of y where x less the mean where not x, se clustered by building b."""
    X = np.column_stack([np.ones(len(x)), x.astype(float)])
    XtXi = np.linalg.pinv(X.T @ X)
    beta = XtXi @ X.T @ y
    e = y - X @ beta
    g = pd.DataFrame(X * e[:, None]).groupby(b).sum().to_numpy()
    V = XtXi @ (g.T @ g) @ XtXi
    return beta[1], np.sqrt(V[1, 1])


def within(x, y, cell, b):
    """Coefficient of y on x with a level for each cell; se clustered by building."""
    d = pd.DataFrame({"x": x.astype(float), "y": y, "c": cell, "b": b})
    d["x"] -= d.groupby("c").x.transform("mean")
    d["y"] -= d.groupby("c").y.transform("mean")
    sxx = (d.x**2).sum()
    if sxx < 1e-9:
        return np.nan, np.nan, 0
    beta = (d.x * d.y).sum() / sxx
    g = (d.x * (d.y - beta * d.x)).groupby(d.b).sum()
    informative = int((d.x.abs() > 1e-9).sum())
    return beta, np.sqrt((g**2).sum()) / sxx, informative


def template_pairs(h: pd.DataFrame, window) -> pd.DataFrame:
    """Per building: sums of gap products over pairs of one bedroom count, by same text."""
    rows = []
    for b, g in h.groupby("building", sort=False):
        if len(g) < 2:
            continue
        i, j = np.triu_indices(len(g), 1)
        bed, x, t = g.bedrooms.to_numpy(), g.x.to_numpy(), g.norm.to_numpy()
        ok = (bed[i] == bed[j]) & (t[i] != "") & (t[j] != "")
        if window is not None:
            d = g.day.to_numpy().astype("datetime64[D]").astype(int)
            ok &= np.abs(d[i] - d[j]) <= window
        same = t[i] == t[j]
        p = x[i] * x[j]
        rows.append(
            (
                p[ok & same].sum(),
                (ok & same).sum(),
                p[ok & ~same].sum(),
                (ok & ~same).sum(),
            )
        )
    return pd.DataFrame(rows, columns=["s1", "n1", "s0", "n0"])


if __name__ == "__main__":
    which = sys.argv[1]
    pd.set_option("display.width", 220)
    h = pd.read_parquet(OUT / f"{which}_held.parquet")
    h = h[h.gap.notna()].reset_index(drop=True)
    # buildings read by the readers leave the half B checks (420 Carroll is in half B)
    read = set(pd.read_csv(OUT / "picked.csv").building)
    h = h[~((h.half == "B") & h.building.isin(read))].reset_index(drop=True)
    text = h.description.fillna("").str.lower()
    for k, pat in MARKS.items():
        h[k] = text.str.contains(pat, regex=True)
    h["penthouse_text"] |= h.label.fillna("").str.startswith("PH")
    h["norm"] = text.str.replace(r"\d", "#", regex=True).str.replace(
        r"\s+", " ", regex=True
    )
    h.loc[h.norm.str.len() < 40, "norm"] = ""
    h["template"] = h.duplicated(["building", "norm"], keep=False) & (h.norm != "")
    h["x"] = h.gap.clip(-0.5, 0.5)
    h["cell"] = h.building + "|" + h.bedrooms.astype(str)
    h["new_unit"] = h.n_unit == (0 if which == "bt" else 1)
    groups = {
        "all ads": h.index == h.index,
        "2+ bed": h.bedrooms >= 2,
        "2+ bed, new bld": (h.bedrooms >= 2) & (h.bld_age <= 3),
        "0-1 bed": h.bedrooms < 2,
    }
    out = []
    for gname, gm in groups.items():
        for hf in "AB":
            m = h[gm & (h.half == hf)]
            for k in [*MARKS, "template"]:
                x = m[k].to_numpy()
                if x.sum() < 10:
                    continue
                d, se = clustered(x, m.x.to_numpy(), m.building.to_numpy())
                w, wse, inf = within(
                    x, m.x.to_numpy(), m.cell.to_numpy(), m.building.to_numpy()
                )
                out.append(
                    dict(
                        group=gname,
                        half=hf,
                        mark=k,
                        ads=int(x.sum()),
                        share=x.mean(),
                        bld=m.building[x].nunique(),
                        plain=d,
                        plain_se=se,
                        within=w,
                        within_se=wse,
                        mad_with=m.x[x].abs().mean(),
                        mad_rest=m.x[~x].abs().mean(),
                    )
                )
    t = pd.DataFrame(out)
    t.to_csv(OUT / f"t1_{which}.csv", index=False)
    print(t.round(4).to_string())
    window = 365 if which == "l2" else None
    print(
        "\nshared variance in one building and bedroom count: same template, two texts"
    )
    for gname, gm in groups.items():
        for sel, sm in (("any unit", gm), ("fewest training ads", gm & h.new_unit)):
            p = template_pairs(h[sm], window)
            w = rng.multinomial(len(p), np.ones(len(p)) / len(p), size=400)
            a = p.to_numpy(float)
            est = a.sum(0)
            bs = w @ a
            c1, c0 = est[0] / est[1], est[2] / est[3]
            b1, b0 = bs[:, 0] / bs[:, 1], bs[:, 2] / bs[:, 3]
            print(
                f"{gname:16s} {sel:20s} same {c1:.4f} ({np.nanstd(b1):.4f}) pairs {int(est[1])}"
                f" bld {(p.n1 > 0).sum()}; two texts {c0:.4f} ({np.nanstd(b0):.4f}) pairs"
                f" {int(est[3])} bld {(p.n0 > 0).sum()}; diff {c1 - c0:.4f}"
                f" ({np.nanstd(b1 - b0):.4f})"
            )
