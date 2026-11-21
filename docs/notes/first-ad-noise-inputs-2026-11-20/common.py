"""Shared pieces: the hash split of buildings, the bins of each input, clustered errors."""

import hashlib

import numpy as np
import pandas as pd

OUT = "/data1/apartments/tmp/po-firstad-noise"
SALT = "first-ad-noise-2026-11-20"


def half(buildings) -> np.ndarray:
    """0 or 1 per building name: the first byte of a salted sha1, modulo 2."""
    u = pd.unique(pd.Series(buildings))
    m = {b: hashlib.sha1((SALT + str(b)).encode()).digest()[0] % 2 for b in u}
    return pd.Series(buildings).map(m).to_numpy()


def bins(t: pd.DataFrame) -> pd.DataFrame:
    """The inputs as groups, at round cut points.

    The cut points were not fixed beforehand: every script prints both halves of the
    buildings together, so groups and cuts were chosen with both in view.
    """
    o = pd.DataFrame(index=t.index)
    o["label"] = t.label_st
    o["label seen before"] = np.where(t.lab_ads > 0, "yes", "no")
    o["lister closed same counts, 7 days"] = np.where(t.gap_same <= 7, "yes", "no")
    o["lister closed same counts, 30 days"] = np.where(t.gap_same <= 30, "yes", "no")
    o["lister ads here"] = pd.cut(
        t.lb_ads, [-1, 0, 4, 19, 1e9], labels=["0", "1-4", "5-19", "20+"]
    ).astype(str)
    o["building ads"] = pd.cut(
        t.b_ads, [-1, 0, 4, 19, 99, 1e9], labels=["0", "1-4", "5-19", "20-99", "100+"]
    ).astype(str)
    o["building years"] = pd.cut(
        t.b_years, [-1, 0, 1, 3, 1e9], labels=["0", "under 1", "1-3", "3+"]
    ).astype(str)
    o["lister ads"] = pd.cut(
        t.l_ads.where(t.lister.notna()),
        [-1, 9, 99, 999, 1e9],
        labels=["0-9", "10-99", "100-999", "1000+"],
    ).astype(str)
    share = (t.l_rel / t.l_ads.clip(lower=1)).where(t.lister.notna() & (t.l_ads >= 20))
    o["lister relabel share"] = pd.cut(
        share, [-1, 0, 0.02, 0.05, 1], labels=["0", "to 2%", "2-5%", "over 5%"]
    ).astype(str)
    return o.replace("nan", "unknown").fillna("unknown")


def ratio_se(num, den, cluster) -> float:
    """Clustered standard error of sum(num) / sum(den)."""
    g = pd.DataFrame({"a": num, "b": den, "c": np.asarray(cluster)}).groupby("c").sum()
    r = g.a.sum() / g.b.sum()
    e = g.a - r * g.b
    k = len(g)
    return float(np.sqrt(k / max(k - 1, 1) * (e**2).sum()) / g.b.sum())
