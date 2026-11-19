"""Free check: a predictive width by ad source on the base model's held-out ads.

The method is that of `docs/notes/duplex-scale-2026-11-18/calib.py`: each held-out ad of
`drift-building` (run b9) gets a Student-t approximation of its predictive distribution,
and the ads of one source have their distributions widened m times for m on a grid. m is
picked on one half of the buildings and scored on the other, both ways. Sources are FEED
(a landlord's feed), PARTNER (a brokerage) and OWNER, from each ad's latest stored record.
A random draw of 10,000 ads is the control. Income ads are left out.

Run from this folder: python calib_source.py
"""

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import t as student
from source import sources

ROWS = (
    "/data1/apartments/frontier/datasets/"
    "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-duplex-penthouse/rows.parquet"
)
RUN = "/data1/apartments/frontier/runs/drift-building-b0-latest-67d14e17-b9/pred_scores.npz"
HALVES = "/data1/apartments/tmp/low-outliers-2026-11-18/held_b9.parquet"
GRID = (0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5)
CACHE = Path("/data1/apartments/tmp/first-page-read-2026-11-18/source-b9.parquet")


def cluster_se(x, cluster):
    """The SE of the sum of `x` with ads of a building taken together."""
    s = pd.Series(x).groupby(np.asarray(cluster)).sum()
    return float(np.sqrt(len(s) / (len(s) - 1) * ((s - s.mean()) ** 2).sum()))


if __name__ == "__main__":
    fr = pd.read_parquet(ROWS, columns=["listing_id", "income_restricted"])
    p = np.load(RUN, allow_pickle=True)
    h = fr[p["heldout"]].reset_index(drop=True)
    assert (h.listing_id.to_numpy() == p["listing"]).all()
    qs = list(p["quantiles"])
    h["gap"] = p["y"] - p["pred"]
    h["cdf"], h["elpd"], h["building"] = p["cdf"], p["elpd"], p["building"]
    q = p["q"].astype(float)
    iqr = q[:, qs.index(0.75)] - q[:, qs.index(0.25)]
    wide = q[:, qs.index(0.975)] - q[:, qs.index(0.025)]
    half = pd.read_parquet(HALVES, columns=["listing_id", "half"])
    half["listing_id"] = half.listing_id.astype(h.listing_id.dtype)
    h = h.merge(half, on="listing_id", how="left", validate="1:1")
    keep = ~h.income_restricted.fillna(False).to_numpy(bool)
    h, iqr, wide = h[keep].reset_index(drop=True), iqr[keep], wide[keep]

    best = None
    for df in (2, 2.5, 3, 4, 5, 7, 10, 30):
        s = iqr / (2 * student.ppf(0.75, df))
        lp = student.logpdf(h.gap / s, df) - np.log(s)
        err = np.abs(lp - h.elpd)
        print(
            f"df {df:4}: mean log density {lp.mean():.4f} (stored {h.elpd.mean():.4f}), "
            f"median abs difference {err.median():.3f}, "
            f"95% width ratio {np.median(2 * s * student.ppf(0.975, df) / wide):.3f}"
        )
        if best is None or abs(lp.mean() - h.elpd.mean()) < best[0]:
            best = (abs(lp.mean() - h.elpd.mean()), df, s, lp)
    _, df, s, lp = best
    print("df used", df)
    z = (h.gap / s).to_numpy()
    cdf = h.cdf.to_numpy()

    if not CACHE.exists():
        sources(h.listing_id).to_parquet(CACHE)
    src = pd.read_parquet(CACHE).source.reindex(h.listing_id.astype(str)).fillna("none")
    src = src.to_numpy()
    print("held-out ads", len(h), pd.Series(src).value_counts().to_dict())
    rng = np.random.default_rng(20261119)
    groups = {v: np.flatnonzero(src == v) for v in ("FEED", "PARTNER", "OWNER")}
    groups["control"] = np.sort(rng.choice(len(h), 10_000, replace=False))
    for name, idx in groups.items():
        gains = {
            m: student.logpdf(z[idx] / m, df) - np.log(m) - student.logpdf(z[idx], df)
            for m in GRID
        }
        fold = (h.half.to_numpy()[idx] == "read").astype(int)
        picked, per_ad = {}, np.zeros(len(idx))
        for f in (0, 1):
            tot = {m: g[fold != f].sum() for m, g in gains.items()}
            picked[f] = max(tot, key=tot.get)
            per_ad[fold == f] = gains[picked[f]][fold == f]
        inside = (cdf[idx] > 0.1) & (cdf[idx] < 0.9)
        print(
            f"{name}: {len(idx)} ads, 80% interval covers {100 * inside.mean():.1f}%, "
            f"below 1% {100 * (cdf[idx] < 0.01).mean():.2f}%, above 99% {100 * (cdf[idx] > 0.99).mean():.2f}%"
        )
        print("  totals by m:", {m: round(float(g.sum()), 1) for m, g in gains.items()})
        print(
            f"  picked {picked}, cross-fit gain {per_ad.sum():.1f} "
            f"(SE {cluster_se(per_ad, h.building.to_numpy()[idx]):.1f})"
        )
        m = float(np.mean(list(picked.values())))
        new = student.cdf(student.ppf(np.clip(cdf[idx], 1e-9, 1 - 1e-9), df) / m, df)
        print(
            f"  at m {m:.2f}: 80% interval covers {100 * ((new > 0.1) & (new < 0.9)).mean():.1f}%, "
            f"below 1% {100 * (new < 0.01).mean():.2f}%, below 10% {100 * (new < 0.1).mean():.1f}% "
            f"(was {100 * (cdf[idx] < 0.1).mean():.1f}%)"
        )
