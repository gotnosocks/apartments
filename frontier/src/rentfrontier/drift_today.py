"""Today's asking rent for every apartment a drift fit knows, from the fit's saved draws.

    python -m rentfrontier.drift_today publish RUN --registry REGISTRY.parquet --out DIR \
        [--day YYYY-MM-DD] [--draws N] [--workers K]

A drift fit (`rentfrontier.drift`, `drift_building`) predicts only the rows its split holds
out, each on its own day. The site's Today page asks another question: what would this
apartment ask if it were listed today? This module answers it for every apartment of a fit
on the market split, which trained on every ad but the ones on the market on its scoring
day, so each apartment's whole history up to its newest ad is in the fit.

The apartment's row today. Each apartment (`drift.unit_index`'s unit) takes the columns of
its newest ad, with the season's columns set for `--day`: an ad on the market now keeps its
own columns, and any other apartment is priced as if its last ad ran again today. Columns the
design sets from a building's earlier ads keep the values of that last ad.

The prediction. Given a kept draw of the coefficients, the walk, the surface, every
building's level and the scales, the row's log rent is

    x beta + L(day) + level[building] + a_building(quarter of day) + u_apartment(day) + noise,

and the building's path a and the apartment's level u are Gaussian given the draw and the
Student-t noise's mixing scales lam of the building's training rows. With lam fixed, a
building's training residuals r = y - x beta - L(t) - level have covariance

    Sigma = B P B' + K + D^-1,

with P the path's stationary AR(1) covariance at the building's quarters with ads, B the map
from those quarters to the rows, K the apartments' kernel (`drift.make_sampler`'s `kernel`,
block diagonal over apartments) and D the rows' weights lam / sigma^2. With W = (K + D^-1)^-1
the apartments' precisions, Sigma^-1 = W - W B Q^-1 B' W, where Q = P^-1 + B' W B is the
fit's own building system (`cell_system`) with the level held at the draw. The apartment's
term today, f = a(q*) + u(t*), then has mean g' Sigma^-1 r and variance
Var f - g' Sigma^-1 g, g = Cov(r, f), which `targets` works out with no matrix larger than
a building's quarters.

The fit kept neither lam nor the paths nor u, so for each draw the module runs a short
Gibbs chain on lam alone: draw (a, u) given lam by Matheron's rule, as the fit draws u,
and lam given the noise they leave, from its Gamma. The draws of lam then follow their
conditional given the draw's other terms, which is the posterior's, and every kept sweep's
(mean, variance) is a component of the predictive mixture. `BURN` sweeps come before the
first kept one; the check below is how that count was chosen.

Time beyond the fit. The walk L ends with the fit's weekly grid (the week after the
dataset's last ad). A day past it carries the walk on as the fit models it, a random walk
with drift g and step sd tau a week, so its mean moves by g a week and its variance grows by
tau^2 a week. The building's path and the apartment's drift are carried by their own
processes in the formulas above. `meta.json` records how far the day lies past the grid.

The check. The same code predicts the rows the fit itself predicted, the ads on the market
on its scoring day, each on its own day, and compares them with `drift_score`'s scores of
the fit's own predictions: the elpd at the asks, the medians and the 80% widths. Both are
predictions from the same posterior, so they differ by Monte Carlo error and by nothing
else. `publish` writes the comparison into `meta.json`.

Lease phases. L1 (`drift_building_phase`) and the models built on it give each row a lease
phase from the months since its unit's previous ad. An apartment's phase today comes from
its last ad's price_at and `--day`, and an ad on the market keeps its own (`phase_today`).
L2 (`drift_building_phase_level`) adds a level in the mean for each phase, so its phase
columns follow the phase today. D1 (`drift_building_phase_duplex`) crosses the phase with
the row's duplex mark, and an apartment keeps its last ad's mark. The segment model
(`drift_building_phase_segment`) adds a path in time for each bedroom group and zone, and
its columns follow `--day` as the walk does; past the last quarter start a path holds its
value there.

Lines. LN1 (`drift_building_phase_line`) centers each apartment's lasting level on a level
for its line, the apartments of its building with its bedrooms and full baths, with
l_m ~ Normal(0, line_sd^2). The kept draws hold line_sd but no line levels, so for each draw
the module integrates the lines out with the path and u. Two training rows of one line
covary by line_sd^2 more, which adds l2 C C' to Sigma, with l2 = line_sd^2 and C the map
from the rows to their lines. Woodbury's identity turns W into

    W_L = W - W C G C' W,    G = diag(l2 / (1 + l2 c_m)),

with c_m the sum of W over line m's rows (`line_W`), and the building system's H into
B' W_L B (`building_system`). The apartment's term today then also holds its line's level. An apartment of a
line with training rows takes that level's conditional from them, with the path and u, as
`drift_line`'s prediction step adds the line's level to a held-out row of a known line. An
apartment of a new line takes no level from the rows, and l2 joins its variance. Each
apartment's line is the fit's own, `drift_line.line_index` as the design built it.

`publish` writes `today.parquet`, one row per apartment, and then `meta.json` (the model,
the run, its gate, the day, the grid's end, a segment model's last quarter start and
whether the day lies past it, the check and the table's sha256). Only a fit on
the market split that passed the convergence gate is accepted.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import multiprocessing
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from . import (
    b0,
    drift,
    drift_building,
    drift_building_phase,
    drift_building_phase_duplex,
    drift_building_phase_level,
    drift_building_phase_line,
    drift_building_phase_segment,
    drift_deals,
    drift_estimates,
    drift_line,
    drift_score,
    simulate,
    splits,
)
from . import run as run_module
from .b0data import sha256
from .total_walk import SEASON

# The models this module can predict, by the name a run records. Each is `drift`'s sweep
# with at most the buildings' collapsed path; the phase models add a noise factor per lease
# phase (or per cell of phase and duplex mark), L2 and the segment model add columns to
# the design, and LN1 adds a level for each line of a building, integrated out with the
# path. Models with Student-t unit levels or more local-drift terms are refused.
MODELS = {
    m.NAME: m
    for m in (
        drift,
        drift_building,
        drift_building_phase,
        drift_building_phase_level,
        drift_building_phase_segment,
        drift_building_phase_duplex,
        drift_building_phase_line,
    )
}
# The seed's second word for the stream the lines' prior draws come from, apart from the
# stream the lam step's other draws come from.
LINE_STREAM = 1
# Kept draws used, spread evenly over the run's chains and draws.
DRAWS = 96
# Sweeps of the lam step for each draw before its first kept sweep, and kept sweeps.
BURN = 4
KEEP = 2
# Replicates drawn from each component for the quantiles, as `drift_score` draws them.
SAMPLES = 4
# Rows per block when the quantiles are worked out.
CHUNK = 20_000
# The table's interval bounds, as places in `drift_score.Q`.
BOUNDS = {"lo95": 0, "lo80": 2, "lo50": 3, "hi50": 4, "hi80": 5, "hi95": 7}
NEW_YORK = ZoneInfo("America/New_York")
# The dataset's columns the table and the phases read.
FRAME = (
    "listing_id",
    "building",
    "unit_id",
    "neighbourhood",
    "bedrooms",
    "full_baths",
    "half_baths",
    "latest_day",
    "latest_ask",
    "price_at",
)
COLUMNS = (
    "apartment",
    "building",
    "address",
    "latitude",
    "longitude",
    "neighbourhood",
    "unit_id",
    "unit",
    "bedrooms",
    "full_baths",
    "half_baths",
    "listing_id",
    "last_day",
    "last_ask",
    "on_market",
    "unit_ads",
    "median",
    *BOUNDS,
    "unit_sd",
)


# ------------------------------------------------------------------ the layout


def layout(site, unit, t, per_year: int | None, sites: int) -> dict:
    """Index arrays for training rows sorted by building, apartment and time: each
    apartment's rows by its count of rows (`ub`), and with a path (`per_year` steps a year)
    each building's quarters with rows, its padded size in the building system and where
    its rows, quarters and pairs of rows sit in the flat arrays `H` (P x P a building) and
    `h` (P a building)."""
    site, unit, t = (np.asarray(v) for v in (site, unit, t))
    n = len(site)
    first = np.r_[0, np.flatnonzero(np.diff(unit) != 0) + 1] if n else np.zeros(0, int)
    size = np.diff(np.r_[first, n]).astype(np.int64)
    uid = unit[first]
    assert len(np.unique(uid)) == len(uid), "each apartment's rows must be contiguous"
    U = int(unit.max(initial=-1)) + 1
    where = np.full((U, 2), -1, np.int64)
    ub = {}
    for L in np.unique(size):
        sel = np.flatnonzero(size == L)
        idx = first[sel, None] + np.arange(L)[None, :]
        where[uid[sel], 0] = L
        where[uid[sel], 1] = np.arange(len(sel))
        ub[int(L)] = dict(idx=idx, t=t[idx])
    lay = dict(n=n, ub=ub, where=where, path=per_year is not None, sites=sites)
    if per_year is None:
        return lay
    q = np.floor(t * per_year).astype(np.int64)
    span = int(q.max(initial=0)) + 1
    keys, cell = np.unique(site * span + q, return_inverse=True)
    csite, cq = keys // span, keys % span
    cfirst = np.r_[0, np.flatnonzero(np.diff(csite)) + 1] if len(keys) else np.zeros(0)
    cfirst = cfirst.astype(np.int64)
    m = np.diff(np.r_[cfirst, len(keys)]).astype(np.int64)
    local = np.arange(len(keys)) - np.repeat(cfirst, m)
    bsite = csite[cfirst]
    pads, p = [], 1
    while p < m.max(initial=1):
        pads.append(p)
        p *= 2
    pads.append(p)
    pad_of = np.full(sites, 0, np.int64)
    H0 = np.full(sites, -1, np.int64)
    h0 = np.full(sites, -1, np.int64)
    buckets, offH, offh, lo = [], 0, 0, 0
    for P in pads:
        sel = np.flatnonzero((m > lo) & (m <= P))
        lo = P
        if not len(sel):
            continue
        nb = len(sel)
        pos = np.arange(P)[None, :]
        mask = pos < m[sel, None]
        cidx = cfirst[sel, None] + np.minimum(pos, m[sel, None] - 1)
        qs = np.where(mask, cq[cidx], cq[cidx[:, -1:]])
        gap = np.zeros((nb, P), np.int64)
        gap[:, 1:] = np.where(mask[:, 1:], np.diff(qs, axis=1), 0)
        b = bsite[sel]
        pad_of[b] = P
        H0[b] = offH + np.arange(nb) * P * P
        h0[b] = offh + np.arange(nb) * P
        buckets.append(
            dict(P=P, sites=b, mask=mask, q=qs, gap=gap, offH=offH, offh=offh)
        )
        offH += nb * P * P
        offh += nb * P
    row_local = local[cell]
    row_h = h0[site] + row_local
    for L, u in ub.items():
        idx = u["idx"]
        s0 = site[idx[:, 0]]
        lc = row_local[idx]
        u["lc"] = lc
        u["Hidx"] = (
            H0[s0][:, None, None]
            + lc[:, :, None] * pad_of[s0][:, None, None]
            + lc[:, None, :]
        )
    lay |= dict(
        per_year=per_year,
        buckets=buckets,
        sizeH=offH,
        sizeh=offh,
        row_h=row_h,
        row_local=row_local,
        pad_of=pad_of,
        H0=H0,
        h0=h0,
        Hidx=np.concatenate([u["Hidx"].ravel() for u in ub.values()])
        if ub
        else np.zeros(0, np.int64),
    )
    return lay


def with_lines(lay: dict, site, line, lines: int) -> dict:
    """`lay` with the sorted training rows' lines (`line`, of `lines`) and each line's
    building. With a path it also holds where the lines enter the building system, from
    `drift_line.line_layout`. A pair there is a line with one of its building's quarters;
    the pairs come grouped by line (`pair_start`, `pair_count`), each with its quarter's
    place in the flat `h` (`pair_h`) and among its building's quarters (`pair_local`), and
    `pp_a`, `pp_b` and `pp_H` hold every ordered pair of pairs of one line with their place
    in the flat `H`."""
    site = np.asarray(site, np.int64)
    line = np.asarray(line, np.int64)
    assert not (line < 0).any(), "every training row needs a line"
    for u in lay["ub"].values():
        assert (line[u["idx"]] == line[u["idx"][:, :1]]).all(), (
            "an apartment's rows must share a line"
        )
    line_site = np.full(lines, -1, np.int64)
    line_site[line] = site
    assert np.array_equal(line_site[line], site), "a line spans two buildings"
    out = dict(lay, line=line, lines=int(lines), line_site=line_site)
    if not lay["path"]:
        return out
    col = dict(
        size_h=lay["sizeh"],
        h=lay["row_h"],
        H_d=lay["H0"][site] + lay["row_local"] * (lay["pad_of"][site] + 1),
        buckets=[
            dict(off_h=b["offh"], off_H=b["offH"], gap=b["gap"]) for b in lay["buckets"]
        ],
    )
    ll = drift_line.line_layout(line, site, lay["row_h"], col, lines)
    pair_line = ll["pair_line"]
    count = np.bincount(pair_line, minlength=lines)
    out |= dict(
        pair_of_row=ll["pair_of_row"],
        pair_line=pair_line,
        pair_h=ll["pair_h"],
        pair_local=ll["pair_h"] - lay["h0"][line_site[pair_line]],
        pair_start=np.cumsum(count) - count,
        pair_count=count,
        pp_a=ll["pp_a"],
        pp_b=ll["pp_b"],
        pp_H=ll["pp_H"],
    )
    return out


def line_pairs(lay: dict, m: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Every pair of each line in `m` (`with_lines`), as each entry's place in `m` and the
    pair's place among all pairs."""
    count = lay["pair_count"][m]
    j = np.repeat(np.arange(len(m)), count)
    within = np.arange(len(j)) - np.repeat(np.cumsum(count) - count, count)
    return j, lay["pair_start"][m][j] + within


# ------------------------------------------------------------------ one building system


def unit_W(lay, c, ss, sd, tau) -> dict:
    """Each apartment's precision W = (K + D^-1)^-1 at row weights `c`, by its count of
    rows."""
    out = {}
    for L, u in lay["ub"].items():
        tt = u["t"]
        if L == 1:
            out[L] = (1.0 / (ss * ss + sd * sd + 1.0 / c[u["idx"]]))[:, :, None]
            continue
        K = ss * ss + sd * sd * np.exp(-np.abs(tt[:, :, None] - tt[:, None, :]) / tau)
        i = np.arange(L)
        K[:, i, i] += 1.0 / c[u["idx"]]
        W = np.linalg.inv(K)
        out[L] = 0.5 * (W + np.swapaxes(W, 1, 2))
    return out


def line_W(lay, Ws, l2) -> dict:
    """`unit_W`'s precisions with the lines' terms under "line", for a layout with lines
    (`with_lines`) at line variance `l2`: each row's w1, the sum of its row of W, each
    line's c, the sum of w1 over its rows, and G = l2 / (1 + l2 c), and with a path each
    pair's sum of w1. The rows' precision with the lines integrated out is then
    W_L = W - W C G C' W, since each apartment's rows share a line."""
    w1 = np.empty(lay["n"])
    for L, u in lay["ub"].items():
        w1[u["idx"]] = Ws[L].sum(axis=2)
    c = np.bincount(lay["line"], weights=w1, minlength=lay["lines"])
    terms = dict(w1=w1, c=c, G=l2 / (1 + l2 * c))
    if lay["path"]:
        terms["pv"] = np.bincount(
            lay["pair_of_row"], weights=w1, minlength=len(lay["pair_line"])
        )
    return Ws | {"line": terms}


def apply_W(lay, Ws, v) -> np.ndarray:
    """W v for a vector over the sorted training rows, or W_L v with the lines' terms
    (`line_W`)."""
    out = np.empty(lay["n"])
    for L, u in lay["ub"].items():
        idx = u["idx"]
        out[idx] = np.einsum("uab,ub->ua", Ws[L], v[idx])
    lw = Ws.get("line")
    if lw is not None:
        cw = np.bincount(lay["line"], weights=out, minlength=lay["lines"])
        out -= lw["w1"] * (lw["G"] * cw)[lay["line"]]
    return out


def ar_precision(bucket, s2, rho) -> np.ndarray:
    """The stationary AR(1) path's precision at a bucket's quarters (as `cell_system`)."""
    gap = bucket["gap"]
    nb, P = gap.shape
    phi = np.where(gap > 0, rho ** np.maximum(gap, 1), 0.0)
    v = 1 - phi * phi
    nxt = np.concatenate([(phi * phi / v)[:, 1:], np.zeros((nb, 1))], axis=1)
    A = np.zeros((nb, P, P))
    i = np.arange(P)
    A[:, i, i] = (1 / v + nxt) / s2
    off = -(phi / v)[:, 1:] / s2
    A[:, i[1:], i[:-1]] = off
    A[:, i[:-1], i[1:]] = off
    return A


def building_system(lay, Ws, s2, rho) -> tuple[np.ndarray, np.ndarray]:
    """The flat arrays of every building's H = B' W B and Q^-1 = (P^-1 + H)^-1, with W_L
    in place of W given the lines' terms (`line_W`)."""
    H = np.bincount(
        lay["Hidx"],
        weights=np.concatenate([Ws[L].ravel() for L in lay["ub"]]),
        minlength=lay["sizeH"],
    )
    lw = Ws.get("line")
    if lw is not None:
        # B' W C at a pair is the pair's sum of w1, so B' W C G C' W B adds G_m times the
        # product of the two pairs' sums for every ordered pair of pairs of line m.
        g = np.sqrt(lw["G"])[lay["pair_line"]] * lw["pv"]
        H -= np.bincount(
            lay["pp_H"],
            weights=g[lay["pp_a"]] * g[lay["pp_b"]],
            minlength=lay["sizeH"],
        )
    Qi = np.empty_like(H)
    for b in lay["buckets"]:
        nb, P = b["gap"].shape
        sl = slice(b["offH"], b["offH"] + nb * P * P)
        Q = H[sl].reshape(nb, P, P) + ar_precision(b, s2, rho)
        Qinv = np.linalg.inv(Q)
        Qi[sl] = (0.5 * (Qinv + np.swapaxes(Qinv, 1, 2))).ravel()
    return H, Qi


def apply_Qinv(lay, Qi, h) -> np.ndarray:
    """Q^-1 h for a flat vector `h` over every building's quarters."""
    out = np.empty_like(h)
    for b in lay["buckets"]:
        nb, P = b["gap"].shape
        Q = Qi[b["offH"] : b["offH"] + nb * P * P].reshape(nb, P, P)
        sl = slice(b["offh"], b["offh"] + nb * P)
        out[sl] = np.einsum("bij,bj->bi", Q, h[sl].reshape(nb, P)).ravel()
    return out


def sigma_inv(lay, Ws, Qi, v) -> np.ndarray:
    """Sigma^-1 v for a vector over the training rows."""
    w = apply_W(lay, Ws, v)
    if not lay["path"]:
        return w
    hb = np.bincount(lay["row_h"], weights=w, minlength=lay["sizeh"])
    y = apply_Qinv(lay, Qi, hb)
    return w - apply_W(lay, Ws, y[lay["row_h"]])


def prior_draw(rng, lay, sc, line_rng=None) -> np.ndarray:
    """A draw of the path at the rows' quarters plus each row's apartment level, and with
    lines each row's line level, from their priors. The line levels come from `line_rng`
    (`rng` when it is None)."""
    out = np.zeros(lay["n"])
    for L, u in lay["ub"].items():
        idx, tt = u["idx"], u["t"]
        z = rng.standard_normal((len(idx), L + 1))
        d = np.empty((len(idx), L))
        d[:, 0] = sc["sd"] * z[:, 1]
        for j in range(1, L):
            e = np.exp(-(tt[:, j] - tt[:, j - 1]) / sc["tau_u"])
            d[:, j] = e * d[:, j - 1] + sc["sd"] * np.sqrt(1 - e * e) * z[:, j + 1]
        out[idx] = sc["ss"] * z[:, :1] + d
    if lay["path"]:
        s, rho = math.sqrt(sc["s2"]), sc["rho"]
        a = np.zeros(lay["sizeh"])
        for b in lay["buckets"]:
            nb, P = b["gap"].shape
            z = rng.standard_normal((nb, P))
            phi = np.where(b["gap"] > 0, rho ** np.maximum(b["gap"], 1), 0.0)
            x = np.empty((nb, P))
            x[:, 0] = s * z[:, 0]
            for j in range(1, P):
                x[:, j] = (
                    phi[:, j] * x[:, j - 1] + s * np.sqrt(1 - phi[:, j] ** 2) * z[:, j]
                )
            a[b["offh"] : b["offh"] + nb * P] = x.ravel()
        out += a[lay["row_h"]]
    if "line" in lay:
        z = (rng if line_rng is None else line_rng).standard_normal(lay["lines"])
        out += math.sqrt(sc["l2"]) * z[lay["line"]]
    return out


def lam_step(rng, lay, Ws, Qi, r, c, row_sd, sc, line_rng=None) -> np.ndarray:
    """New mixing scales lam: the noise left by a draw of (path, u) given lam, by Matheron's
    rule, then lam from its Gamma given that noise. With lines the draw holds the line
    levels too, drawn from `line_rng`."""
    e0 = rng.standard_normal(lay["n"]) / np.sqrt(c)
    delta = r - prior_draw(rng, lay, sc, line_rng) - e0
    eps = e0 + sigma_inv(lay, Ws, Qi, delta) / c
    nu = sc["nu"]
    return rng.gamma((nu + 1) / 2, 2 / (nu + (eps / row_sd) ** 2))


# ------------------------------------------------------------------ the rows to predict


def pairs(site, q) -> tuple[np.ndarray, np.ndarray]:
    """The distinct (building, quarter) pairs of the rows to predict, and each row's pair."""
    keys, inv = np.unique(np.stack([site, q], axis=1), axis=0, return_inverse=True)
    return keys, inv.ravel()


def targets(lay, Ws, Qi, H, r, tg, sc) -> tuple[np.ndarray, np.ndarray]:
    """The mean and variance of each predicted row's path and apartment term, f = a(q*) +
    u(t*), given the training residuals `r` (see the module docstring). `tg` holds each
    row's training `unit` (-1 for none), `site`, `t` and `q`, and its `pair` and the
    distinct `pair_keys` from `pairs`.

    With the lines' terms (`line_W`), f also holds the row's line level, and `tg` holds each
    row's `line` (-1 for a new line). A row of a known line takes the level's conditional
    from the training rows: g gains l2 on every row of the line, and with
    kap the apartment's kernel on its own rows and s its sum of W kap,
    W_L g = W kap on the apartment's rows + beta w1 on the line's, beta = G (1 - s). A row
    of a new line adds l2 to its variance alone."""
    ss, sd, tau = sc["ss"], sc["sd"], sc["tau_u"]
    s2 = sc["s2"] if lay["path"] else 0.0
    k0 = ss * ss + sd * sd
    nT = len(tg["unit"])
    v = apply_W(lay, Ws, r)
    mean = np.zeros(nT)
    var = np.full(nT, s2 + k0)
    lw = Ws.get("line")
    if lw is not None:
        var += sc["l2"]
        # Each row's sum of W kap over its apartment's rows, and with a path
        # (W kap)' Q^-1 (B' W C) at its line; both are 0 for a new apartment.
        wsum = np.zeros(nT)
        cross = np.zeros(nT)
    Pmax = max([b["P"] for b in lay.get("buckets", ())] or [1])
    if lay["path"]:
        h = np.bincount(lay["row_h"], weights=v, minlength=lay["sizeh"])
        yh = apply_Qinv(lay, Qi, h)
        keys = tg["pair_keys"]
        npair = len(keys)
        pst = np.zeros((npair, Pmax))
        av = np.zeros((npair, Pmax))
        yv = np.zeros((npair, Pmax))
        pair_mean = np.zeros(npair)
        pair_quad = np.zeros(npair)
        psite, pq = keys[:, 0], keys[:, 1]
        P_of = lay["pad_of"][psite]
        for b in lay["buckets"]:
            P = b["P"]
            sel = np.flatnonzero(P_of == P)
            if not len(sel):
                continue
            slot = (lay["H0"][psite[sel]] - b["offH"]) // (P * P)
            qs, mask = b["q"][slot], b["mask"][slot]
            ps = np.where(mask, s2 * sc["rho"] ** np.abs(pq[sel, None] - qs), 0.0)
            nb = len(b["sites"])
            Hb = H[b["offH"] : b["offH"] + nb * P * P].reshape(nb, P, P)[slot]
            Qb = Qi[b["offH"] : b["offH"] + nb * P * P].reshape(nb, P, P)[slot]
            hb = h[b["offh"] : b["offh"] + nb * P].reshape(nb, P)[slot]
            yb = yh[b["offh"] : b["offh"] + nb * P].reshape(nb, P)[slot]
            Hp = np.einsum("pij,pj->pi", Hb, ps)
            a = np.einsum("pij,pj->pi", Qb, Hp)
            pair_mean[sel] = np.einsum("pi,pi->p", ps, hb) - np.einsum(
                "pi,pi->p", Hp, yb
            )
            pair_quad[sel] = np.einsum("pi,pi->p", ps, Hp) - np.einsum(
                "pi,pi->p", Hp, a
            )
            pst[sel, :P], av[sel, :P], yv[sel, :P] = ps, a, yb
        pr = tg["pair"]
        mean += pair_mean[pr]
        var -= pair_quad[pr]
    unit = tg["unit"]
    have = unit >= 0
    L_of = np.where(have, lay["where"][np.maximum(unit, 0), 0], 0)
    pos_of = lay["where"][np.maximum(unit, 0), 1]
    for L, u in lay["ub"].items():
        sel = np.flatnonzero(have & (L_of == L))
        if not len(sel):
            continue
        pos = pos_of[sel]
        idx, tt = u["idx"][pos], u["t"][pos]
        kap = ss * ss + sd * sd * np.exp(-np.abs(tg["t"][sel, None] - tt) / tau)
        Wk = Ws[L][pos]
        Wkap = np.einsum("uab,ub->ua", Wk, kap)
        mean[sel] += np.einsum("ua,ua->u", kap, v[idx])
        var[sel] -= np.einsum("ua,ua->u", kap, Wkap)
        if lay["path"]:
            lc = u["lc"][pos]
            pr = tg["pair"][sel]
            ps = np.take_along_axis(pst[pr], lc, axis=1)
            a = np.take_along_axis(av[pr], lc, axis=1)
            yb = np.take_along_axis(yv[pr], lc, axis=1)
            mean[sel] -= np.einsum("ua,ua->u", Wkap, yb)
            s0 = tg["site"][sel]
            Qg = Qi[
                lay["H0"][s0][:, None, None]
                + lc[:, :, None] * lay["pad_of"][s0][:, None, None]
                + lc[:, None, :]
            ]
            var[sel] -= 2 * np.einsum("ua,ua->u", Wkap, ps - a)
            var[sel] += np.einsum("ua,uab,ub->u", Wkap, Qg, Wkap)
        if lw is not None:
            assert np.array_equal(lay["line"][idx[:, 0]], tg["line"][sel]), (
                "a row's line must be its apartment's"
            )
            wsum[sel] = Wkap.sum(axis=1)
            if lay["path"]:
                j, p = line_pairs(lay, tg["line"][sel])
                at = (
                    lay["H0"][s0][j, None]
                    + lc[j] * lay["pad_of"][s0][j, None]
                    + lay["pair_local"][p][:, None]
                )
                cross[sel] = np.bincount(
                    j,
                    weights=lw["pv"][p] * np.einsum("ea,ea->e", Wkap[j], Qi[at]),
                    minlength=len(sel),
                )
    if lw is not None:
        known = np.flatnonzero(tg["line"] >= 0)
        m = tg["line"][known]
        assert np.array_equal(lay["line_site"][m], tg["site"][known]), (
            "a row's line must be of its building"
        )
        l2, G, s = sc["l2"], lw["G"][m], wsum[known]
        beta = G * (1 - s)
        Cv = np.bincount(lay["line"], weights=v, minlength=lay["lines"])
        mean[known] += l2 * Cv[m]
        var[known] -= l2 * s + beta * (s + l2 * lw["c"][m])
        if lay["path"]:
            # z = B' W_L g less the path's part is B' W kap + beta V, V the line's pairs'
            # sums of w1, so V's products with Q^-1 h, ps - a and Q^-1 V join the terms
            # the apartment's rows gave above.
            pv, pl = lw["pv"], lay["pair_line"]
            pa, pb = lay["pp_a"], lay["pp_b"]
            Vy = np.bincount(pl, weights=pv * yh[lay["pair_h"]], minlength=lay["lines"])
            VQV = np.bincount(
                pl[pa],
                weights=pv[pa] * pv[pb] * Qi[lay["pp_H"]],
                minlength=lay["lines"],
            )
            j, p = line_pairs(lay, m)
            pr, loc = tg["pair"][known][j], lay["pair_local"][p]
            Vpa = np.bincount(
                j, weights=pv[p] * (pst[pr, loc] - av[pr, loc]), minlength=len(known)
            )
            mean[known] -= beta * Vy[m]
            var[known] += beta * (2 * cross[known] - 2 * Vpa + beta * VQV[m])
    return mean, np.maximum(var, 0.0)


def components(lay, r, row_sd, tg, sc, seed, burn=None, keep=None):
    """For one kept draw, `keep` (mean, variance) pairs of each predicted row's path and
    apartment term, after `burn` sweeps of the lam step from lam = 1. With lines
    (`with_lines`) each sweep's precisions take the lines' terms at the draw's `l2`, and the
    lines' prior draws come from a stream of their own, so the lam step's other draws are
    the ones a layout with no lines would make."""
    burn = BURN if burn is None else burn
    keep = KEEP if keep is None else keep
    rng = np.random.default_rng(seed)
    lines = "line" in lay
    line_rng = np.random.default_rng([seed, LINE_STREAM]) if lines else None
    lam = np.ones(lay["n"])
    means, vars_ = [], []
    for sweep in range(burn + keep):
        c = lam / row_sd**2
        Ws = unit_W(lay, c, sc["ss"], sc["sd"], sc["tau_u"])
        if lines:
            Ws = line_W(lay, Ws, sc["l2"])
        H = Qi = None
        if lay["path"]:
            H, Qi = building_system(lay, Ws, sc["s2"], sc["rho"])
        if sweep >= burn:
            m, v = targets(lay, Ws, Qi, H, r, tg, sc)
            means.append(m)
            vars_.append(v)
        if sweep < burn + keep - 1:
            lam = lam_step(rng, lay, Ws, Qi, r, c, row_sd, sc, line_rng)
    return np.stack(means), np.stack(vars_)


def quantiles(loc, usd, sig, nu, seed=0, samples=SAMPLES) -> tuple:
    """The predictive quantiles at `drift_score.Q` and the median of rows whose components
    are (loc, usd, sig) (components, rows) with noise degrees of freedom `nu`
    (components,), from `samples` replicates of each component, as `drift_score` draws
    them."""
    rng = np.random.default_rng(seed)
    shape = (samples, *loc.shape)
    nu_ = np.broadcast_to(np.asarray(nu, float)[:, None], loc.shape)
    rep = (
        loc + usd * rng.standard_normal(shape) + sig * rng.standard_t(nu_, size=shape)
    ).reshape(-1, loc.shape[1])
    return np.quantile(rep, drift_score.Q, axis=0).T, np.median(rep, axis=0)


# ------------------------------------------------------------------ the run


@dataclasses.dataclass
class Fit:
    """What the predictions read from a run, the training rows in building, apartment and
    time order."""

    record: dict
    manifest: dict
    frame: pd.DataFrame
    names: list
    kept: dict
    pick: (
        np.ndarray
    )  # the kept draws used, as places in the chains' draws laid end to end
    rows: np.ndarray  # each sorted training row's place in the frame
    held: np.ndarray  # the frame's held-out rows
    y: np.ndarray
    t: np.ndarray
    week: np.ndarray
    frac: np.ndarray
    group: np.ndarray
    site: np.ndarray
    unit: np.ndarray
    phase: np.ndarray | None
    start: pd.Timestamp
    weeks: int
    Bc: np.ndarray
    lay: dict
    xb: np.ndarray  # (draws, training rows) x beta, alpha included
    # each frame row's unit, site, week, frac, t, group, phase, line (None with no lines), x
    full: SimpleNamespace
    season: np.ndarray  # (frame rows, len(SEASON)) the season columns
    season_cols: list
    seg: SimpleNamespace | None  # the segment paths' columns (`segment_terms`)


def set_split(split: str) -> None:
    """Point every loaded `rentfrontier` module with a SPLIT (the as-of designs) at the
    fit's split, as `simulate.set_split` does."""
    for m in list(sys.modules.values()):
        if getattr(m, "__name__", "").startswith("rentfrontier.") and hasattr(
            m, "SPLIT"
        ):
            m.SPLIT = split


def thin(chains: int, draws: int, n: int) -> np.ndarray:
    """`n` kept draws spread evenly over the chains' draws laid end to end."""
    total = chains * draws
    return np.unique(np.linspace(0, total - 1, min(n, total)).round().astype(int))


def level_columns(
    names: list[str], phases: tuple[str, ...] | None
) -> tuple[list[int], np.ndarray]:
    """L2's phase level columns among `names` (`phase:{phase}`), and each one's phase as its
    place in `phases`."""
    cols = [j for j, n in enumerate(names) if n.startswith("phase:")]
    if not cols:
        return [], np.zeros(0, np.int64)
    which = pd.Index(() if phases is None else phases).get_indexer(
        [names[j].split(":", 1)[1] for j in cols]
    )
    if (which < 0).any():
        raise SystemExit("a phase column's phase is not one of the design's phases")
    return cols, which


def segment_terms(d: b0.Design, names: list[str]) -> SimpleNamespace | None:
    """What `segment_shift` reads of a segment model's design, in the terms
    `drift_building_phase_segment.path_design` builds its columns from: the quarter starts
    in years from the grid start, each one's segment shares over the frame's rows, each
    frame row's segment, and each path column's segment and quarter start. None for a design
    with no path columns."""
    cols = [j for j, n in enumerate(names) if n.startswith("seg:")]
    if not cols:
        return None
    sp = drift_building_phase_segment
    q = sp.quarter_starts(d)
    knots = np.asarray((q - pd.Timestamp(d.start)).days, float) / sp.YEAR_DAYS
    segments = sp.segment_names(d)
    row = sp.segment_index(d)
    H = sp.hat_weights(drift.years(d), knots)
    weight = H.sum(axis=0)
    share = np.stack([H[row == k].sum(axis=0) for k in range(len(segments))], axis=1)
    share /= np.where(weight > 0, weight, 1.0)[:, None]
    at = {
        f"seg:{s}:{t.year}q{t.quarter}": (k, j)
        for k, s in enumerate(segments)
        for j, t in enumerate(q)
    }
    kj = np.asarray([at[names[c]] for c in cols])
    out = SimpleNamespace(
        knots=knots,
        share=share,
        row=row,
        cols=np.asarray(cols),
        k=kj[:, 0],
        j=kj[:, 1],
    )
    # The columns rebuilt from these terms on a spread of the frame's rows must be the
    # design's.
    some = np.unique(np.linspace(0, len(row) - 1, 2000).astype(np.int64))
    x = H[some][:, out.j] * (
        (row[some][:, None] == out.k[None, :]) - share[out.j, out.k][None, :]
    )
    if not np.allclose(x, d.x[some][:, cols], rtol=0, atol=1e-10):
        raise SystemExit("the segment columns rebuilt from their terms differ")
    return out


def load(run_dir: Path, draws: int = DRAWS, log=print) -> Fit:
    """Rebuild the run's design from its dataset and pick its kept draws."""
    record = json.loads((run_dir / "result.json").read_text())
    name = record.get("feature_set")
    spec = MODELS.get(name)
    if spec is None:
        raise SystemExit(
            f"{run_dir.name} is a {name} fit, not one of {', '.join(MODELS)}"
        )
    if record.get("split") != "market":
        raise SystemExit(f"{run_dir.name} is not a fit on the market split")
    if not drift_deals._gate(record)["passes"]:
        raise SystemExit(f"{run_dir.name} did not pass the convergence gate")
    # A fit on the market split of a market dataset (not a backtest) whose ads table is
    # unchanged since the dataset was built.
    _, manifest = drift_deals._checked(run_dir, backtest=False)
    dataset = drift_score.dataset_dir(run_dir)
    if dataset is None:
        raise SystemExit(f"the dataset {run_dir.name} read is not on this machine")
    t0 = time.perf_counter()
    frame = b0.load_frame(dataset)
    set_split(record["split"])
    held = splits.SPLITS[record["split"]](frame)
    d = spec.design(frame)
    # The snapshots the design read must be the fit's, as `simulate` checks them.
    now = spec.run_record(d)
    for k in simulate.SNAPSHOT_KEYS:
        if not simulate.same(now.get(k), record.get(k)):
            raise SystemExit(
                f"{k}: the design reads {now.get(k)}, the fit read {record.get(k)}"
            )
    with np.load(run_dir / "posterior.npz") as z:
        names = [str(v) for v in z["names"]]
        if names != list(d.names):
            raise SystemExit("the rebuilt design's columns differ from the fit's")
        if not np.array_equal(z["heldout"], held):
            raise SystemExit("the rebuilt split differs from the fit's")
        want = (
            "beta L g tau sigma nu bld gp_w unit_sd drift_sd drift_tau "
            "building_ar_sd building_ar_rho phase_scale line_sd"
        ).split()
        kept = {k: np.asarray(z[f"kept/{k}"]) for k in want if f"kept/{k}" in z}
    if "unit_dof" in kept:
        raise SystemExit(f"{name}'s Student-t unit levels are not supported here")
    lines = getattr(d, "line", None) is not None
    if lines != ("line_sd" in kept):
        raise SystemExit(f"{name}'s design and kept draws disagree on lines")
    if lines and record.get("line", {}).get("lines") != int(d.lines):
        raise SystemExit("the rebuilt design's lines differ from the fit's")
    if d.phase is not None and not {str(p).split("|", 1)[0] for p in d.phases} <= set(
        drift_building_phase.PHASES
    ):
        raise SystemExit(f"{name}'s noise phases are not L1's lease phases")
    log(f"design rebuilt: {d.x.shape} in {time.perf_counter() - t0:.0f}s")
    alpha = names.index("alpha")
    if not np.all(d.x[:, alpha] == 1):
        raise SystemExit("the design's alpha column is not all ones")
    cols, which = level_columns(names, d.phases)
    if cols and not np.array_equal(d.x[:, cols], d.phase[:, None] == which[None, :]):
        raise SystemExit("the design's phase columns are not its rows' phases")
    seg = segment_terms(d, names)
    C, K = kept["beta"].shape[:2]
    pick = thin(C, K, draws)
    kept = {k: v.reshape(C * K, *v.shape[2:])[pick] for k, v in kept.items()}
    train = np.flatnonzero(~held)
    t_all = drift.years(d)
    order = np.lexsort((t_all[train], d.unit[train], d.site[train]))
    rows = train[order]
    groups = getattr(spec, "GROUPS", ())
    if any(g != "building" for g in groups):
        raise SystemExit(f"{name}'s local-drift terms are not supported here")
    sites = len(drift.site_zone(d))
    lay = layout(d.site[rows], d.unit[rows], t_all[rows], 4 if groups else None, sites)
    if lines:
        lay = with_lines(lay, d.site[rows], d.line[rows], int(d.lines))
    Bc, _ = drift.wave_matrix(SimpleNamespace(site=d.site[train], surfaces=d.surfaces))
    xb = np.empty((len(pick), len(rows)), np.float32)
    beta = kept["beta"].T
    for a in range(0, len(rows), 200_000):
        xb[:, a : a + 200_000] = (d.x[rows[a : a + 200_000]] @ beta).T
    season_cols = [names.index(s) for s in SEASON if s in names]
    full = SimpleNamespace(
        unit=d.unit,
        site=d.site,
        week=d.week,
        frac=d.frac,
        t=t_all,
        group=d.group,
        phase=d.phase,
        phases=d.phases,
        line=d.line if lines else None,
        x_held=d.x[held],
    )
    fit = Fit(
        record=record,
        manifest=manifest,
        frame=frame[[c for c in FRAME if c in frame]].copy(),
        names=names,
        kept=kept,
        pick=pick,
        rows=rows,
        held=held,
        y=d.y[rows],
        t=t_all[rows],
        week=d.week[rows],
        frac=d.frac[rows],
        group=d.group[rows],
        site=d.site[rows],
        unit=d.unit[rows],
        phase=None if d.phase is None else d.phase[rows],
        start=d.start,
        weeks=int(d.weeks),
        Bc=Bc,
        lay=lay,
        xb=xb,
        full=full,
        season=d.x[:, season_cols].copy(),
        season_cols=season_cols,
        seg=seg,
    )
    del d, frame
    log(f"layout and x beta ready in {time.perf_counter() - t0:.0f}s")
    return fit


def scales(fit: Fit, i: int) -> dict:
    """Draw `i`'s scales."""
    k = fit.kept
    sc = dict(
        ss=float(k["unit_sd"][i]),
        sd=float(k["drift_sd"][i]),
        tau_u=float(k["drift_tau"][i]),
        nu=float(k["nu"][i]),
        sigma=np.asarray(k["sigma"][i], float),
        g=float(k["g"][i]),
        tau_w=float(k["tau"][i]),
    )
    if fit.lay["path"]:
        sc["s2"] = float(k["building_ar_sd"][i]) ** 2
        sc["rho"] = float(k["building_ar_rho"][i])
    if "phase_scale" in k:
        sc["phase"] = np.asarray(k["phase_scale"][i], float)
    if "line_sd" in k:
        sc["l2"] = float(k["line_sd"][i]) ** 2
    return sc


def walk(fit: Fit, i: int, week, frac) -> tuple[np.ndarray, np.ndarray]:
    """Draw `i`'s walk L at grid times (week, frac), with its mean carried on past the grid
    by the drift g and its variance by tau^2 a week."""
    L = np.asarray(fit.kept["L"][i], float)
    last = len(L) - 1
    u = np.asarray(week, float) + np.asarray(frac, float)
    past = np.maximum(u - last, 0.0)
    wk = np.minimum(np.asarray(week).astype(np.int64), last - 1)
    # The grid's last week itself is wk = last - 1 at fr = 1.
    fr = np.where(u >= last, 1.0, np.asarray(frac, float))
    inside = (1 - fr) * L[wk] + fr * L[np.minimum(wk + 1, last)]
    sc = scales(fit, i)
    return inside + past * sc["g"], past * sc["tau_w"] ** 2


def noise_sd(sc: dict, group, phase) -> np.ndarray:
    """Each row's noise scale: its bedroom group's sigma, times its phase's factor."""
    sd = sc["sigma"][np.asarray(group)]
    if phase is not None and "phase" in sc:
        sd = sd * sc["phase"][np.asarray(phase)]
    return sd


def level(fit: Fit, i: int) -> np.ndarray:
    """Draw `i`'s level of every building: its kept offset from the surface, plus the
    surface (`outputs` keeps `bld` = level - surface)."""
    return fit.kept["bld"][i].astype(float) + fit.Bc @ fit.kept["gp_w"][i]


def residuals(fit: Fit, i: int) -> np.ndarray:
    """Draw `i`'s training residuals y - x beta - L(t) - level."""
    L, _ = walk(fit, i, fit.week, fit.frac)
    return fit.y - fit.xb[i] - L - level(fit, i)[fit.site]


@dataclasses.dataclass
class Rows:
    """Rows to predict: each one's training unit (-1 for none), building, grid time, the
    x beta of its own columns at each kept draw, bedroom group, phase, and for a fit with
    lines its line (-1 for a line with no training row)."""

    unit: np.ndarray
    site: np.ndarray
    week: np.ndarray
    frac: np.ndarray
    xb: np.ndarray  # (draws, rows)
    group: np.ndarray
    phase: np.ndarray | None
    line: np.ndarray | None = None


def target_index(rows_list: list[Rows]) -> dict:
    """The rows of every set laid end to end, as `targets` reads them."""
    cat = lambda k: np.concatenate([getattr(rw, k) for rw in rows_list])  # noqa: E731
    unit, site = cat("unit").astype(np.int64), cat("site").astype(np.int64)
    t = (cat("week").astype(float) + cat("frac")) / drift.YEAR_WEEKS
    q = np.floor(t * 4).astype(np.int64)
    keys, pair = pairs(site, q)
    out = dict(unit=unit, site=site, t=t, q=q, pair_keys=keys, pair=pair)
    if rows_list and all(rw.line is not None for rw in rows_list):
        out["line"] = cat("line").astype(np.int64)
    return out


_STATE: dict = {}


def _worker(job):
    i, seed = job
    fit, tg = _STATE["fit"], _STATE["tg"]
    sc = scales(fit, i)
    r = residuals(fit, i)
    row_sd = noise_sd(sc, fit.group, fit.phase)
    m, v = components(fit.lay, r, row_sd, tg, sc, seed)
    return i, m.astype(np.float32), v.astype(np.float32)


def predict(
    fit: Fit, rows_list: list[Rows], workers: int = 1, seed: int = 0, log=print
):
    """The predictive mixture of each set of rows in `rows_list`: a dict of `loc` and
    `usd` (components, rows), and the components' `nu`, `sigma` (components, groups) and
    `phase` factors, from KEEP sweeps of each kept draw."""
    tg = target_index(rows_list)
    _STATE.update(fit=fit, tg=tg)
    jobs = [(i, seed * 100_003 + i) for i in range(len(fit.pick))]
    sizes = [len(rw.unit) for rw in rows_list]
    cuts = np.cumsum([0, *sizes])
    C = len(jobs) * KEEP
    out = [
        dict(
            loc=np.empty((C, n), np.float32),
            usd=np.empty((C, n), np.float32),
        )
        for n in sizes
    ]
    mix = dict(nu=np.empty(C), sigma=np.empty((C, 4)), phase=None)
    if "phase_scale" in fit.kept:
        mix["phase"] = np.empty((C, fit.kept["phase_scale"].shape[1]))
    t0 = time.perf_counter()
    pool = None
    if workers > 1:
        pool = multiprocessing.get_context("fork").Pool(workers)
        it = pool.imap_unordered(_worker, jobs)
    else:
        it = map(_worker, jobs)
    try:
        for done, (i, m, v) in enumerate(it, 1):
            sc = scales(fit, i)
            part = slice(i * KEEP, (i + 1) * KEEP)
            mix["nu"][part] = sc["nu"]
            mix["sigma"][part] = sc["sigma"]
            if mix["phase"] is not None:
                mix["phase"][part] = sc["phase"]
            lev = level(fit, i)
            for k, rw in enumerate(rows_list):
                sl = slice(cuts[k], cuts[k + 1])
                L, extra = walk(fit, i, rw.week, rw.frac)
                fixed = rw.xb[i] + L + lev[rw.site]
                out[k]["loc"][part] = fixed + m[:, sl]
                out[k]["usd"][part] = np.sqrt(v[:, sl] + extra)
            if done % 8 == 0 or done == len(jobs):
                log(f"draws {done}/{len(jobs)}: {time.perf_counter() - t0:.0f}s")
    finally:
        if pool is not None:
            pool.close()
            pool.join()
        _STATE.clear()
    return [o | mix for o in out]


def mixture_sd(comp: dict, rw: Rows, sl=slice(None)) -> np.ndarray:
    """The noise scale of each component at rows `sl` of `rw`: (components, rows)."""
    sd = comp["sigma"][:, rw.group[sl]]
    if rw.phase is not None and comp["phase"] is not None:
        sd = sd * comp["phase"][:, rw.phase[sl]]
    return sd


# ------------------------------------------------------------------ the apartments


def grid_time(fit: Fit, day: pd.Timestamp) -> tuple[float, float]:
    """`day`'s week and fraction on the fit's weekly grid."""
    u = (pd.Timestamp(day) - fit.start).days / 7.0
    return float(math.floor(u)), u - math.floor(u)


def season_at(day: pd.Timestamp) -> dict:
    """The season's columns for an ad on `day`, by name, as `b0.design` builds them."""
    doy = pd.Timestamp(day).dayofyear - 1 + 0.5
    out = {}
    for k in range(1, b0.HARMONICS + 1):
        angle = 2 * np.pi * k * doy / b0.YEAR_DAYS
        out[f"sin{k}"], out[f"cos{k}"] = math.sin(angle), math.cos(angle)
    return out


def apartments(fit: Fit) -> pd.DataFrame:
    """One row per apartment: its newest ad in the frame (training or held out), with the
    apartment's training unit number and count of training ads."""
    f = fit.frame
    unit = fit.full.unit
    none = f.unit_id.isna().to_numpy()
    key = (
        f.building.astype(str).to_numpy(object)
        + "|"
        + np.where(none, "", f.unit_id.astype(object).to_numpy()).astype(str)
    )
    key = np.where(none, key + "#" + np.arange(len(f)).astype(str), key)
    day = pd.to_datetime(f.latest_day).to_numpy()
    t = pd.DataFrame(
        {"key": key, "day": day, "row": np.arange(len(f)), "held": fit.held}
    ).sort_values(["key", "day", "held", "row"], kind="stable")
    newest = t.groupby("key", sort=False).tail(1)
    ads = np.bincount(unit[~fit.held & (unit >= 0)], minlength=int(unit.max()) + 1)
    rows = newest.row.to_numpy()
    out = pd.DataFrame(
        {
            "apartment": newest.key.str.replace(r"#\d+$", "", regex=True).to_numpy(),
            "row": rows,
            "unit": unit[rows],
            "held": fit.held[rows],
        }
    )
    out["unit_ads"] = np.where(out.unit >= 0, ads[np.maximum(out.unit, 0)], 0)
    return out


def phase_today(fit: Fit, rows: np.ndarray, day: pd.Timestamp) -> np.ndarray | None:
    """Each apartment's lease phase for an ad on `day` (phase models only): an ad on the
    market keeps its own phase, and any other is binned by the months from its last ad's
    price_at to `day`. Where the fit's phases are cells of phase and mark (D1's
    "phase|mark"), an apartment keeps its last ad's mark."""
    if fit.full.phase is None:
        return None
    f = fit.frame.iloc[rows]
    at = pd.to_datetime(f.price_at, utc=True).dt.tz_convert(None).to_numpy()
    months = (pd.Timestamp(day).to_datetime64() - at) / np.timedelta64(1, "D")
    months = months / drift_building_phase.MONTH_DAYS
    names = np.asarray(drift_building_phase.BINNED, dtype=object)[
        np.searchsorted(drift_building_phase.EDGES, months, side="right")
    ]
    names = np.where(f.unit_id.isna().to_numpy(), "none", names).astype(object)
    own = pd.Series(np.asarray(fit.full.phases, dtype=object)[fit.full.phase[rows]])
    parts = own.str.partition("|")
    names = names + parts[1].to_numpy(object) + parts[2].to_numpy(object)
    out = pd.Index(fit.full.phases).get_indexer(names).astype(np.int64)
    held = fit.held[rows]
    out[held] = fit.full.phase[rows][held]
    if (out < 0).any():
        raise SystemExit("an apartment's phase today is not one of the fit's phases")
    return out


def phase_level_shift(fit: Fit, rows: np.ndarray, phase: np.ndarray) -> np.ndarray:
    """The change in x beta of frame rows `rows` at each kept draw, (draws, rows), when L2's
    phase columns move from each row's own phase to `phase`."""
    cols, which = level_columns(fit.names, fit.full.phases)
    old = fit.full.phase[rows][:, None] == which[None, :]
    new = np.asarray(phase)[:, None] == which[None, :]
    return fit.kept["beta"][:, cols] @ (new.astype(float) - old).T


def segment_shift(fit: Fit, rows: np.ndarray, t_new: float) -> np.ndarray:
    """The change in x beta of frame rows `rows` at each kept draw, (draws, rows), when
    their segment path columns move from each row's own time to `t_new`, in years from the
    grid start. Past the last quarter start the paths hold their value there."""
    sg = fit.seg
    B = np.zeros((len(fit.pick), sg.share.shape[1], len(sg.knots)))
    B[:, sg.k, sg.j] = fit.kept["beta"][:, sg.cols]
    # A row of segment s with hat weights h gains sum_j h_j D[s, j] from the path columns:
    # its segment's coefficient at each quarter start less the share-weighted mean of all
    # segments' coefficients there. A column the design left out counts as 0.
    D = B - np.einsum("jk,dkj->dj", sg.share, B)[:, None, :]
    s = sg.row[rows]
    t_new = float(np.clip(t_new, sg.knots[0], sg.knots[-1]))
    hat = drift_building_phase_segment.hat_weights
    H_old = hat(fit.full.t[rows], sg.knots)
    H_new = hat(np.array([t_new]), sg.knots)[0]
    out = np.zeros((len(fit.pick), len(rows)))
    for j in range(len(sg.knots)):
        dh = H_new[j] - H_old[:, j]
        live = np.flatnonzero(dh)
        if len(live):
            out[:, live] += D[:, s[live], j] * dh[live]
    return out


def base_xb(fit: Fit, rows: np.ndarray) -> np.ndarray:
    """x beta of frame rows `rows` at each kept draw: a training row's from the fit's own
    product, a held-out row's from its columns."""
    out = np.empty((len(fit.pick), len(rows)))
    place = np.full(len(fit.frame), -1, np.int64)
    place[fit.rows] = np.arange(len(fit.rows))
    tr = place[rows] >= 0
    out[:, tr] = fit.xb[:, place[rows[tr]]]
    if (~tr).any():
        hp = np.full(len(fit.frame), -1, np.int64)
        hp[np.flatnonzero(fit.held)] = np.arange(int(fit.held.sum()))
        out[:, ~tr] = (fit.full.x_held[hp[rows[~tr]]] @ fit.kept["beta"].T).T
    return out


def today_rows(fit: Fit, apts: pd.DataFrame, day: pd.Timestamp) -> Rows:
    """The apartments' rows on `day`: each newest ad's columns with the season's set for
    `day`, at `day`'s grid time."""
    rows = apts.row.to_numpy()
    xb = base_xb(fit, rows)
    cols = fit.season_cols
    if cols:
        at = season_at(day)
        new = np.asarray([at[fit.names[j]] for j in cols])
        beta_s = fit.kept["beta"][:, cols]
        xb += beta_s @ (new[:, None] - fit.season[rows].T)
    week, frac = grid_time(fit, day)
    phase = phase_today(fit, rows, day)
    if level_columns(fit.names, fit.full.phases)[0]:
        xb += phase_level_shift(fit, rows, phase)
    if fit.seg is not None:
        xb += segment_shift(fit, rows, (week + frac) / drift.YEAR_WEEKS)
    n = len(rows)
    return Rows(
        unit=apts.unit.to_numpy(),
        site=fit.full.site[rows],
        week=np.full(n, week),
        frac=np.full(n, frac),
        xb=xb,
        group=fit.full.group[rows],
        phase=phase,
        line=line_of(fit, rows),
    )


def line_of(fit: Fit, rows: np.ndarray) -> np.ndarray | None:
    """The line of frame rows `rows` in a fit with lines, and None in any other fit."""
    line = getattr(fit.full, "line", None)
    return None if line is None else line[rows]


def check_rows(fit: Fit) -> Rows:
    """The rows the fit itself predicted, on their own days."""
    rows = np.flatnonzero(fit.held)
    return Rows(
        unit=fit.full.unit[rows],
        site=fit.full.site[rows],
        week=fit.full.week[rows].astype(float),
        frac=fit.full.frac[rows],
        xb=base_xb(fit, rows),
        group=fit.full.group[rows],
        phase=None if fit.full.phase is None else fit.full.phase[rows],
        line=line_of(fit, rows),
    )


def check(fit: Fit, comp: dict, rw: Rows, theirs: dict) -> dict:
    """These predictions of the fit's own predicted rows `rw` against the fit's, `theirs`
    (`drift_score.score_run`): elpd at the asks, the medians, the 80% widths and the
    coverage of both."""
    y = np.log(fit.frame.latest_ask.to_numpy(float)[fit.held])
    if not np.allclose(theirs["y"], y):
        raise SystemExit("the fit's predicted rows are not the rebuilt held-out rows")
    mine = {k: [] for k in ("elpd", "q", "pred")}
    for a in range(0, len(y), drift_score.CHUNK):
        sl = slice(a, a + drift_score.CHUNK)
        part = drift_score.score_rows(
            comp["loc"][:, sl].astype(float),
            comp["usd"][:, sl].astype(float),
            mixture_sd(comp, rw, sl),
            comp["nu"],
            y[sl],
            seed=a,
        )
        for k in mine:
            mine[k].append(part[k])
    mine = {k: np.concatenate(v) for k, v in mine.items()} | {"y": y}
    ours, fit_s = drift_score.summary(mine), drift_score.summary(theirs)
    gap = mine["pred"] - theirs["pred"]
    width = lambda q: q[:, 5] - q[:, 2]  # noqa: E731
    return {
        "rows": int(len(y)),
        "elpd": {"today": round(ours["elpd"], 1), "fit": round(fit_s["elpd"], 1)},
        "median_gap": {
            "median_abs": round(float(np.median(np.abs(gap))), 5),
            "p95_abs": round(float(np.quantile(np.abs(gap), 0.95)), 5),
            "mean": round(float(gap.mean()), 5),
        },
        "width80_ratio": round(
            float(np.median(width(mine["q"]) / width(theirs["q"]))), 4
        ),
        "coverage": {"today": ours["coverage"], "fit": fit_s["coverage"]},
    }


def unit_labels(ads: Path, listing_ids) -> np.ndarray:
    """Each listing's unit label ('6B') from its page URL in the ads table, as the Deals
    page shows it: the dataset's unit_id is an id, not a label. '' where there is none."""
    a = pd.read_parquet(ads, columns=["listing_id", "page"])
    page = a.assign(listing_id=a.listing_id.astype(str)).drop_duplicates("listing_id")
    page = page.set_index("listing_id").page.reindex(pd.Index(listing_ids).astype(str))
    return np.asarray([drift_deals.unit_label(v) for v in page], dtype=object)


def table(
    fit: Fit,
    apts: pd.DataFrame,
    comp: dict,
    rw: Rows,
    registry,
    ads: Path | None = None,
) -> pd.DataFrame:
    """The Today table from the apartments' predictive mixtures, with each listing's unit
    label from the ads table `ads` when given."""
    n = len(apts)
    q = np.empty((n, len(drift_score.Q)))
    med = np.empty(n)
    for a in range(0, n, CHUNK):
        sl = slice(a, a + CHUNK)
        q[sl], med[sl] = quantiles(
            comp["loc"][:, sl].astype(float),
            comp["usd"][:, sl].astype(float),
            mixture_sd(comp, rw, sl),
            comp["nu"],
            seed=a,
        )
    f = fit.frame.iloc[apts.row.to_numpy()]
    text = lambda c: f[c].where(f[c].notna(), "").astype(str).to_numpy()  # noqa: E731
    usd = comp["usd"].astype(float)
    out = pd.DataFrame(
        {
            "apartment": apts.apartment.to_numpy(),
            "building": f.building.astype(str).to_numpy(),
            "neighbourhood": text("neighbourhood"),
            "unit_id": text("unit_id"),
            "unit": unit_labels(ads, f.listing_id) if ads else "",
            "bedrooms": f.bedrooms.to_numpy(float),
            "full_baths": f.full_baths.to_numpy(float),
            "half_baths": f.half_baths.to_numpy(float),
            "listing_id": f.listing_id.astype(str).to_numpy(),
            "last_day": pd.to_datetime(f.latest_day).dt.strftime("%Y-%m-%d").to_numpy(),
            "last_ask": f.latest_ask.to_numpy(float),
            "on_market": apts.held.to_numpy(bool),
            "unit_ads": apts.unit_ads.to_numpy(int),
            "median": np.exp(med).round(0),
            **{b: np.exp(q[:, i]).round(0) for b, i in BOUNDS.items()},
            "unit_sd": np.sqrt(np.mean(usd * usd, axis=0)).round(4),
        }
    )
    if registry is None:
        out["address"], out["latitude"], out["longitude"] = "", np.nan, np.nan
    else:
        reg = registry.reindex(out.building)
        out["address"] = [drift_deals.title_address(v) for v in reg.label]
        out["latitude"] = reg.latitude.to_numpy(float).round(5)
        out["longitude"] = reg.longitude.to_numpy(float).round(5)
    return out[list(COLUMNS)].sort_values("apartment", kind="stable")


def segment_meta(fit: Fit, day: pd.Timestamp) -> dict:
    """A segment model's last quarter start, and whether `day` lies past it, where the
    paths hold their value."""
    if fit.seg is None:
        return {}
    days = float(fit.seg.knots[-1]) * drift_building_phase_segment.YEAR_DAYS
    last = fit.start + pd.Timedelta(days=round(days))
    return {
        "segment_paths": {
            "last_quarter_start": str(last.date()),
            "held_past_it": bool(day > last),
        }
    }


def today_ny() -> pd.Timestamp:
    """Today's date in New York."""
    return pd.Timestamp(datetime.now(NEW_YORK).date())


def publish(
    run_dir: Path,
    out: Path,
    day: pd.Timestamp | None = None,
    registry: Path | None = None,
    draws: int = DRAWS,
    workers: int = 1,
    log=print,
) -> dict:
    """Write `today.parquet` and then `meta.json` to the folder `out`. Everything is
    computed before anything is written."""
    day = pd.Timestamp(day) if day is not None else today_ny()
    fit = load(run_dir, draws, log)
    last_ad = pd.to_datetime(fit.frame.latest_day).max()
    if day < last_ad:
        raise SystemExit(f"{day.date()} is before the fit's last ad ({last_ad.date()})")
    grid_end = fit.start + pd.Timedelta(weeks=fit.weeks)
    apts = apartments(fit)
    log(
        f"{len(apts):,} apartments on {day.date()}; the walk's grid ends {grid_end.date()}"
    )
    today, own = today_rows(fit, apts, day), check_rows(fit)
    comp, comp_own = predict(fit, [today, own], workers, log=log)
    checked = check(fit, comp_own, own, drift_score.score_run(run_dir))
    log(f"against the fit's own predictions: {json.dumps(checked)}")
    frame = table(
        fit,
        apts,
        comp,
        today,
        drift_estimates._registry(registry),
        Path(fit.manifest["ads"]),
    )
    week, frac = grid_time(fit, day)
    past = max(0.0, week + frac - fit.weeks)
    tau_w = float(np.median(fit.kept["tau"]))
    meta = {
        "model": fit.record["model"]["name"],
        "run": run_dir.name,
        "dataset": Path(fit.record["dataset"]).name,
        "gate": drift_deals._gate(fit.record),
        "scoring_day": fit.manifest.get("scoring_day"),
        "day": str(day.date()),
        "last_ad_day": str(last_ad.date()),
        "grid_start": str(fit.start.date()),
        "grid_end": str(grid_end.date()),
        "weeks_past_grid": round(past, 2),
        "walk": {
            "drift_per_week": round(float(np.median(fit.kept["g"])), 6),
            "step_sd_per_week": round(tau_w, 6),
            "added_sd": round(math.sqrt(past) * tau_w, 5),
        },
        "draws": {"kept": int(len(fit.pick)), "burn": BURN, "keep": KEEP},
        **segment_meta(fit, day),
        "apartments": {
            "all": int(len(frame)),
            "on_market": int(frame.on_market.sum()),
            "unseen": int((frame.unit_ads == 0).sum()),
        },
        "check": checked,
    }
    out.mkdir(parents=True, exist_ok=True)
    # Both files are written under temporary names and renamed back to back, so the site's
    # reader meets a table and a meta that disagree only between the two renames.
    table_tmp = out / f"today.parquet.{os.getpid()}.tmp"
    meta_tmp = out / f"meta.json.{os.getpid()}.tmp"
    frame.to_parquet(table_tmp, index=False, compression="zstd")
    meta["today_sha256"] = sha256(table_tmp)
    meta["published"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta_tmp.write_text(json.dumps(meta, indent=2))
    os.replace(table_tmp, out / "today.parquet")
    os.replace(meta_tmp, out / "meta.json")
    return meta


def main(argv=None):
    global BURN
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("command", choices=("publish",))
    p.add_argument("run", help="a run on the market split")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument(
        "--day", help="the day to price, YYYY-MM-DD (default: today in New York)"
    )
    p.add_argument("--registry", type=Path)
    p.add_argument("--draws", type=int, default=DRAWS)
    p.add_argument("--workers", type=int, default=1)
    p.add_argument(
        "--burn", type=int, default=BURN, help="lam sweeps before the first kept one"
    )
    p.add_argument("--runs", default=str(run_module.RUNS))
    args = p.parse_args(argv)
    BURN = args.burn
    meta = publish(
        Path(args.runs) / args.run,
        args.out,
        pd.Timestamp(args.day) if args.day else None,
        args.registry,
        args.draws,
        args.workers,
    )
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
