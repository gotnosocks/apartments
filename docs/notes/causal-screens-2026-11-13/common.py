"""Shared loaders for the causal screens of 2026-11-13: L1's held-out ads with their
predictive medians, intervals and draws, the dataset's rows and a few pipeline columns,
plus a rescoring of L1's exact predictive after a shift or a scale change."""

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/data1/apartments/serve/master/frontier/src")
from rentfrontier import drift_score as ds  # noqa: E402

RUN = "/data1/apartments/frontier/runs/drift-building-phase-b0-latest-9a7830fb-l1/"
DATA = (
    "/data1/apartments/frontier/datasets/"
    "b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise/rows.parquet"
)
PIPE = "/data1/apartments/pipeline/datasets/rows-b3ddebf19af1dc1e.parquet"
REG = "/data1/apartments/external/registry/20261019-bcfbb52-extend/registry.parquet"
PLUTO = "/data1/apartments/external/pluto/20261017-2c61ff1-all-lots4/pluto.parquet"
RECS = "/data1/apartments/tmp/outlier-sprint/s2/R/recs.parquet"
OUT = "/data1/apartments/tmp/sprint-20261113/"
os.makedirs(OUT, exist_ok=True)


def rows(extra=()):
    """Every row of L1's dataset, with a held-out mask, the unit key L1 uses and the
    pipeline's building attributes."""
    d = pd.read_parquet(
        DATA,
        columns=[
            "listing_id",
            "building",
            "unit_id",
            "neighbourhood",
            "price_at",
            "latest_ask",
            "latest_day",
            "bedrooms",
            "full_baths",
            "rent_stabilized",
            "description_known",
        ],
    )
    a = np.load(RUN + "pred_scores.npz", allow_pickle=True)
    d["held"] = a["heldout"]
    d["priced"] = d.price_at.dt.tz_convert(None)
    d["day"] = pd.to_datetime(d.latest_day)
    d["ukey"] = np.where(
        d.unit_id.isna(),
        "row:" + d.listing_id.astype(str),
        d.building.astype(str) + "|" + d.unit_id.astype(str),
    )
    p = pd.read_parquet(
        PIPE,
        columns=["listing_id", "elevator", "doorman_type", "square_feet", *extra],
    ).drop_duplicates("listing_id")
    d = d.merge(p, on="listing_id", how="left")
    reg = pd.read_parquet(REG, columns=["building", "bbl"]).drop_duplicates("building")
    d = d.merge(reg, on="building", how="left")
    d["boro"] = d.bbl.astype("string").str[0]
    d["manhattan"] = d.boro == "1"
    return d


def heldout(d=None):
    """L1's held-out ads in dataset order, with y, the median, the 80% interval and
    L1's own elpd, and a fold by a hash of the building."""
    a = np.load(RUN + "pred_scores.npz", allow_pickle=True)
    if d is None:
        d = rows()
    h = d[d.held.values].reset_index(drop=True)
    assert (h.listing_id.astype(str).values == a["listing"]).all()
    h["y"], h["pred"], h["elpd0"] = a["y"], a["pred"], a["elpd"]
    qs = list(a["quantiles"])
    h["lo"], h["hi"] = a["q"][:, qs.index(0.1)], a["q"][:, qs.index(0.9)]
    h["gap"] = h.y - h.pred
    h["in80"] = (h.y >= h.lo) & (h.y <= h.hi)
    h["fold"] = (pd.util.hash_array(h.building.astype(str).to_numpy()) % 2).astype(int)
    return h


class Draws:
    """L1's kept draws for the held-out ads, for rescoring its exact predictive."""

    def __init__(self, nodes=48):
        z = np.load(RUN + "posterior.npz")

        def flat(k):
            v = z["kept/" + k]
            return v.reshape(-1, *v.shape[2:])

        self.loc = flat("pred_loc").astype(np.float32)
        self.usd = flat("pred_unit_sd").astype(np.float32)
        self.sig = flat("sigma")
        self.fac = flat("phase_scale")
        self.nu = flat("nu")
        self.grp = z["kept/pred_group"]
        self.ph = z["kept/pred_phase"]
        self.y = z["kept/pred_y"]
        lam, logw = ds.mixture(self.nu, nodes)
        self.ilam = (1 / lam).astype(np.float32)[:, None, :]
        self.logw = logw.astype(np.float32)[:, None, :]
        self._base = {}

    def _lpd(self, sl, delta, scale):
        s = self.sig[:, self.grp[sl]] * self.fac[:, self.ph[sl]]
        loc = self.loc[:, sl]
        usd = self.usd[:, sl]
        if delta is not None:
            loc = loc + delta[sl][None, :].astype(np.float32)
        if scale is not None:
            s = s * scale[sl][None, :]
            usd = usd * scale[sl][None, :].astype(np.float32)
        var = usd[:, :, None] ** 2 + (s.astype(np.float32) ** 2)[:, :, None] * self.ilam
        dev = (self.y[sl][None, :] - loc)[:, :, None]
        lp = self.logw - 0.5 * (np.log(var) + dev * dev / var)
        m = lp.max(axis=2, keepdims=True)
        lp = (m[:, :, 0] + np.log(np.exp(lp - m).sum(axis=2))).astype(np.float64)
        n = lp.shape[0]
        return np.logaddexp.reduce(lp, axis=0) - np.log(n) - 0.5 * np.log(2 * np.pi)

    def elpd(self, idx, delta=None, scale=None, batch=400):
        """Log predictive density of the ads `idx` with their locations moved by
        `delta` and their noise and unit sd multiplied by `scale` (arrays over all
        held-out ads), on a 48-node grid for the Student-t's mixing scale."""
        out = np.empty(len(idx))
        for a0 in range(0, len(idx), batch):
            sl = idx[a0 : a0 + batch]
            out[a0 : a0 + batch] = self._lpd(sl, delta, scale)
        return out

    def gain(self, idx, delta=None, scale=None):
        """elpd of the ads `idx` after the change, less their elpd before it on the same
        grid."""
        key = (len(idx), int(idx[0]), int(idx[-1]), int(np.asarray(idx).sum()))
        if key not in self._base:
            self._base[key] = self.elpd(idx)
        return self.elpd(idx, delta, scale) - self._base[key]


def cluster_se(x, b):
    """SE of the sum of `x`, clustered by `b`."""
    t = pd.Series(np.asarray(x)).groupby(np.asarray(b)).sum()
    return float(np.sqrt(len(t) * t.var(ddof=1)))


def cluster_mean_diff(gap, on, b):
    """Mean of `gap` where `on` less the mean where not, with its building-clustered SE
    (delta method on the two cluster sums)."""
    g = pd.DataFrame({"g": gap, "on": on.astype(bool), "b": b})
    g = g[np.isfinite(g.g)]
    m1, m0 = g.g[g.on].mean(), g.g[~g.on].mean()
    g["r"] = np.where(g.on, (g.g - m1) / g.on.sum(), -(g.g - m0) / (~g.on).sum())
    t = g.groupby("b").r.sum()
    return float(m1 - m0), float(np.sqrt(len(t) / (len(t) - 1) * (t**2).sum()))


def within(gap, key):
    """`gap` less its mean within `key` (a building or building and segment)."""
    s = pd.Series(np.asarray(gap, float))
    return (s - s.groupby(np.asarray(key)).transform("mean")).to_numpy()


def wls_slope(y, x, b, w=None):
    """Least-squares slope of y on x (with intercept), SE clustered by b."""
    y, x = np.asarray(y, float), np.asarray(x, float)
    w = np.ones_like(y) if w is None else np.asarray(w, float)
    X = np.column_stack([np.ones_like(x), x])
    XtW = X.T * w
    A = np.linalg.inv(XtW @ X)
    beta = A @ (XtW @ y)
    e = y - X @ beta
    sc = pd.DataFrame(X * (w * e)[:, None]).groupby(np.asarray(b)).sum().to_numpy()
    V = A @ (sc.T @ sc) @ A
    g = len(sc)
    V *= g / (g - 1)
    return float(beta[1]), float(np.sqrt(V[1, 1])), float(beta[0])


def subfold(building):
    """A second building hash, for the inner split that picks the shrinkage."""
    return (pd.util.hash_array(np.asarray(building).astype(str) + "#") % 2).astype(int)


def crossfit_shift(gap, key, fold, sub, ks=(10, 30, 100, 300, 1000)):
    """Cross-fitted shrunk mean gap of each ad's cell: the mean over the other half of the
    buildings, shrunk to zero by n / (n + k), with k picked on an inner split of that half."""
    key = pd.Series(key).astype(str).to_numpy()

    def shrunk(est, tgt, k):
        g = pd.DataFrame({"k": key[est], "g": gap[est]}).groupby("k").g
        sm, n = g.sum(), g.size()
        kk = key[tgt]
        return (sm.reindex(kk).fillna(0) / (n.reindex(kk).fillna(0) + k)).to_numpy()

    out = np.zeros(len(gap))
    picked = {}
    for f in (0, 1):
        est = fold != f
        err = {}
        for k in ks:
            err[k] = 0.0
            for s in (0, 1):
                tgt = est & (sub == s)
                err[k] += float(
                    ((gap[tgt] - shrunk(est & (sub != s), tgt, k)) ** 2).sum()
                )
        picked[f] = min(err, key=err.get)
        out[fold == f] = shrunk(est, fold == f, picked[f])
    return out, picked
