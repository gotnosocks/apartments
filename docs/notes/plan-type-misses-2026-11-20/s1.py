"""How much of the held-out gap is shared within a building, a building and bedroom count,
and a line or floor plan image beyond that.

Usage: s1.py l2|bt

For pairs of held-out ads of two units of one building, the mean product of their gaps
(each less its stratum's mean, clipped at +-0.5) estimates the variance their units share.
Pair kinds: another bedroom count; the same count and another line; the same count and the
same line; the same count and the same or another first floor plan image. The standard
errors resample buildings (400 draws). In the latest-split run pairs are at most 365 days
apart; the backtest's ads are all priced on one day.
"""

import sys

import numpy as np
import pandas as pd

from b1 import OUT

NEW_YEARS = 3.0
CLIP = 0.5
KINDS = ["other_bed", "same_bed", "bed_other_line", "bed_same_line", "bed_other_plan"]
KINDS += ["bed_same_plan", "bed_same_baths", "bed_other_baths"]
rng = np.random.default_rng(20261120)


def strata(h: pd.DataFrame, which: str) -> pd.Series:
    age = np.where(h.bld_age <= NEW_YEARS, "new bld", "older bld")
    bed = np.where(h.bedrooms >= 2, "2+", h.bedrooms.clip(0, 1).astype(int).astype(str))
    if which == "bt":
        unit = np.where(h.n_unit == 0, "unit new", "unit seen")
    else:
        unit = np.where(h.n_unit == 1, "1 train ad", "2+ train ads")
    return pd.Series(age + " | " + bed + " bed | " + unit, index=h.index)


def pair_sums(g: pd.DataFrame, window: float | None) -> dict:
    """Per stratum and pair kind of one building: the sum of gap products and the pairs."""
    n = len(g)
    i, j = np.triu_indices(n, 1)
    x = g.x.to_numpy()
    st = g.stratum.to_numpy()
    bed = g.bedrooms.to_numpy()
    ok = np.ones(len(i), bool)
    if window is not None:
        d = g.day.to_numpy().astype("datetime64[D]").astype(int)
        ok = np.abs(d[i] - d[j]) <= window
    line = g.line.to_numpy()
    plan = g.plan.to_numpy()
    bath = g.full_baths.to_numpy()
    sb = bed[i] == bed[j]
    ln = pd.notna(line[i]) & pd.notna(line[j])
    pl = pd.notna(plan[i]) & pd.notna(plan[j])
    masks = {
        "other_bed": ~sb,
        "same_bed": sb & (st[i] == st[j]),
        "bed_other_line": sb & (st[i] == st[j]) & ln & (line[i] != line[j]),
        "bed_same_line": sb & (st[i] == st[j]) & ln & (line[i] == line[j]),
        "bed_other_plan": sb & (st[i] == st[j]) & pl & (plan[i] != plan[j]),
        "bed_same_plan": sb & (st[i] == st[j]) & pl & (plan[i] == plan[j]),
        "bed_same_baths": sb & (st[i] == st[j]) & (bath[i] == bath[j]),
        "bed_other_baths": sb & (st[i] == st[j]) & (bath[i] != bath[j]),
    }
    p = x[i] * x[j]
    out = {}
    for k, m in masks.items():
        m = m & ok
        if not m.any():
            continue
        if k == "other_bed":
            # a pair of two counts goes to the stratum of each of its ads, half weight
            for side in (i, j):
                s = pd.Series(p[m]).groupby(st[side][m]).agg(["sum", "size"])
                for name, r in s.iterrows():
                    a = out.setdefault((name, k), [0.0, 0.0])
                    a[0] += r["sum"] / 2
                    a[1] += r["size"] / 2
        else:
            s = pd.Series(p[m]).groupby(st[i][m]).agg(["sum", "size"])
            for name, r in s.iterrows():
                out[(name, k)] = [r["sum"], float(r["size"])]
    return out


def table(h: pd.DataFrame, window: float | None, label: str) -> pd.DataFrame:
    h = h.copy()
    h["x"] = (h.gap - h.groupby("stratum").gap.transform("mean")).clip(-CLIP, CLIP)
    rows = []
    for b, g in h.groupby("building", sort=False):
        if len(g) < 2:
            continue
        for (s, k), (sm, ct) in pair_sums(g, window).items():
            rows.append((b, s, k, sm, ct))
    p = pd.DataFrame(rows, columns=["building", "stratum", "kind", "sum", "pairs"])
    blds = p.building.unique()
    code = pd.Series(np.arange(len(blds)), index=blds)
    p["bc"] = code.reindex(p.building).to_numpy()
    out = []
    for s, ps in p.groupby("stratum"):
        hs = h[h.stratum == s]
        S = np.zeros((len(blds), len(KINDS)))
        N = np.zeros_like(S)
        for c, k in enumerate(KINDS):
            q = ps[ps.kind == k]
            np.add.at(S[:, c], q.bc.to_numpy(), q["sum"].to_numpy())
            np.add.at(N[:, c], q.bc.to_numpy(), q.pairs.to_numpy())
        w = rng.multinomial(len(blds), np.ones(len(blds)) / len(blds), size=400)
        with np.errstate(invalid="ignore", divide="ignore"):
            est = S.sum(0) / N.sum(0)
            boot = (w @ S) / (w @ N)
        se = np.nanstd(boot, 0)
        r = dict(stratum=s, ads=len(hs), bld=hs.building.nunique(), var=hs.x.var())
        for c, k in enumerate(KINDS):
            r[k] = est[c]
            r[k + "_se"] = se[c]
            r[k + "_pairs"] = N[:, c].sum()
            r[k + "_bld"] = (N[:, c] > 0).sum()
        for name, a, b in (
            ("line_excess", "bed_same_line", "bed_other_line"),
            ("plan_excess", "bed_same_plan", "bed_other_plan"),
            ("bed_excess", "same_bed", "other_bed"),
            ("bath_excess", "bed_same_baths", "bed_other_baths"),
        ):
            ca, cb = KINDS.index(a), KINDS.index(b)
            r[name] = est[ca] - est[cb]
            r[name + "_se"] = np.nanstd(boot[:, ca] - boot[:, cb])
        out.append(r)
    t = pd.DataFrame(out).set_index("stratum")
    print(f"\n===== {label}: ads {len(h)}, buildings {h.building.nunique()}")
    cols = ["ads", "bld", "var", "other_bed", "other_bed_se", "same_bed", "same_bed_se"]
    print(t[cols].round(4).to_string())
    cols = [
        "bed_other_line",
        "bed_other_line_se",
        "bed_other_line_bld",
        "bed_same_line",
    ]
    cols += ["bed_same_line_se", "bed_same_line_pairs", "bed_same_line_bld"]
    cols += ["line_excess", "line_excess_se"]
    print(t[cols].round(4).to_string())
    cols = ["bed_other_plan", "bed_other_plan_se", "bed_same_plan", "bed_same_plan_se"]
    cols += [
        "bed_same_plan_pairs",
        "bed_same_plan_bld",
        "plan_excess",
        "plan_excess_se",
    ]
    cols += ["bath_excess", "bath_excess_se", "bed_excess", "bed_excess_se"]
    print(t[cols].round(4).to_string())
    return t


if __name__ == "__main__":
    which = sys.argv[1]
    pd.set_option("display.width", 250)
    cols = ["building", "bedrooms", "full_baths", "gap", "n_unit", "half", "day"]
    cols += ["bld_age", "line", "plan"]
    h = pd.read_parquet(OUT / f"{which}_held.parquet", columns=cols)
    h = h[h.gap.notna() & h.bld_age.notna()].reset_index(drop=True)
    h["stratum"] = strata(h, which)
    window = 365 if which == "l2" else None
    table(h, window, "all buildings").to_csv(OUT / f"s1_{which}.csv")
    for hf in "AB":
        table(h[h.half == hf], window, "half " + hf)
