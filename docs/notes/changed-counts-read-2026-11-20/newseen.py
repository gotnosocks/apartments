"""Cross-tabs of the strictly-prior marks of `prior.py`, l2bt held-out ads from 2022 on.

The prior mark of a held-out ad uses only training ads of the apartment dated before it:
`same` (all have its counts, or none exists), `back` (some have other counts and the most
recent has its counts) and `fresh` (the most recent has other counts). Fresh ads are split
by whether any earlier training ad of the model unit has the held-out counts (`seen`), and
crossed with the building's same-bedroom training ads, the model unit's training rows and
three or more baths.

`m` is the scale factor needed. Each ad's place in the model's predictive distribution
(`cdf`) is turned into a Student t value with 4 degrees of freedom, u. m is the multiplier
that maximises the likelihood of u / m as t with 4 degrees of freedom, so 1 means the
model's width fits the group and 1.4 means the group needs a scale 1.4 times as wide.
`m_se` is its standard error over 200 resamples of buildings (groups under 20,000 ads).
"""

import numpy as np
import pandas as pd
from scipy import stats as st
from scipy.optimize import minimize_scalar

from build import OUT

DF = 4


def tvalue(cdf: pd.Series) -> np.ndarray:
    return st.t.ppf(cdf.clip(1e-6, 1 - 1e-6), DF)


def mfac(u: np.ndarray) -> float:
    def nll(lm: float) -> float:
        return -(st.t.logpdf(u / np.exp(lm), DF) - lm).sum()

    return float(np.exp(minimize_scalar(nll, bounds=(-2, 2), method="bounded").x))


def cell(g: pd.DataFrame) -> pd.Series:
    u = g.u.to_numpy()
    bs = []
    if len(g) < 20000:
        rng = np.random.default_rng(1)
        ub, inv = np.unique(g.building.to_numpy(), return_inverse=True)
        idx = [np.flatnonzero(inv == k) for k in range(len(ub))]
        for _ in range(200):
            pick = rng.integers(0, len(ub), len(ub))
            bs.append(mfac(np.concatenate([u[idx[k]] for k in pick])))
    return pd.Series(
        {
            "n": len(g),
            "sd": g.gap.std(),
            "low": (g.cdf < 0.05).mean(),
            "high": (g.cdf > 0.95).mean(),
            "tails": ((g.cdf < 0.05) | (g.cdf > 0.95)).mean(),
            "m": mfac(u),
            "m_se": np.std(bs) if bs else np.nan,
        }
    )


def show(g: pd.DataFrame, by: list[str], title: str) -> None:
    print("\n" + title)
    t = g.groupby(by, observed=True).apply(cell, include_groups=False)
    print(t.round(3).to_string())


def marks(h: pd.DataFrame) -> pd.DataFrame:
    a = h[h.year >= 2022].copy()
    a["u"] = tvalue(a.cdf)
    a["anymark"] = np.where(~a.anydiff, "same", np.where(a.lastdiff, "fresh", "back"))
    last = a.p_last.fillna(False).astype(bool)
    some = a.p_any.fillna(False).astype(bool)
    a["mark"] = np.where(last, "3 fresh", np.where(some, "2 back", "1 same"))
    a["noprior"] = a.p_n.isna()
    a["seenk"] = np.where(
        a.seen.isna(),
        "unit has no earlier ad",
        np.where(a.seen.fillna(False).astype(bool), "counts seen", "counts new"),
    )
    a["bbk"] = pd.cut(a.bb, [-1, 4, 19, 1e9], labels=["bb<5", "bb5-19", "bb20+"])
    a["b3"] = np.where(a.baths >= 3, "3+ baths", "under 3 baths")
    a["un"] = pd.cut(
        a.u_n.fillna(0), [-1, 0, 1, 2, 4, 1e9], labels=["0", "1", "2", "3-4", "5+"]
    )
    return a


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    a = marks(pd.read_parquet(OUT / "prior.parquet"))
    print("any-date marks", a.anymark.value_counts().to_dict())
    show(a, ["mark"], "strictly-prior mark, 2022 on")
    show(a, ["mark", "half"], "strictly-prior mark by half")
    show(
        a, ["mark", "noprior"], "strictly-prior mark by no earlier ad of the apartment"
    )
    show(
        a[a.year >= 2025],
        ["mark", "half"],
        "strictly-prior mark by half, 2025 and 2026",
    )
    show(a, ["anymark", "mark"], "any-date mark by strictly-prior mark")
    show(a, ["mark", "seenk"], "mark by counts seen in the model unit's earlier ads")
    f = a[a.mark == "3 fresh"]
    show(f, ["seenk", "half"], "fresh by counts seen and half")
    show(a, ["mark", "bbk"], "mark by the building's same-bedroom training ads")
    show(a, ["mark", "bbk", "half"], "mark by same-bedroom training ads and half")
    show(a, ["mark", "un"], "mark by the model unit's training rows")
    show(a, ["mark", "b3"], "mark by three or more baths")
    show(a, ["mark", "b3", "half"], "mark by three or more baths and half")
    show(a, ["anymark", "b3"], "any-date mark by three or more baths")
    show(a, ["anymark", "bbk"], "any-date mark by same-bedroom training ads")
