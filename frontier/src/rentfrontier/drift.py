"""The drift model: the kitchen sink with a level for each unit that drifts over time.

The row model is the kitchen sink's (`rentfrontier.building_zones_kitchen_sink`) with one more
term in each row's mean:

    y_i ~ StudentT(nu, x_i beta + eta_site(i) + u_i + L(t_i), sigma_group(i))
    u_i = s_unit(i) + d_unit(i)(t_i)
    s_k ~ Normal(0, ss^2)                                  the unit's lasting level
    d_k ~ OU: Var d_k(t) = sd^2, Corr(d_k(t), d_k(t')) = exp(-|t - t'| / tau)   its drift

with t in years. A free check on fit 8's residuals (docs/notes/drift-2026-11-10.md) found that
two ads of one unit share 66% of their residual variance half a year apart and 21% eight years
apart. A constant unit effect, as in `building_zones_floor_asof2_unit`, averages a unit's ads
at any distance, so it leaves the recent ads' extra information unused. Here the lasting part
s and the drifting part d are separate, and a prediction for a unit weighs each of its
earlier ads by how long ago it ran.

A unit is a pair of the frame's building and `unit_id`. A row with no `unit_id` is a unit of
its own. Every unit sits inside one building.

Sampler. I write the Student-t as a scale mixture, y_i ~ Normal(mean_i, 1 / c_i) with
c_i = lam_i / sigma_g^2. Given the scales, a unit's rows are jointly Gaussian once u is
integrated out, with covariance D^-1 + K, where D = diag(c) and
K_ij = ss^2 + sd^2 exp(-|t_i - t_j| / tau). A unit has at most a few dozen ads, so its
precision W = (D^-1 + K)^-1 is a small dense matrix, and I build it for every unit in each
sweep (`unit_W`). The sweep is `building_zones_gibbs`'s, with u integrated out of every step
before its own draw:

1. The global block theta (coefficients, walk, g, waves) is drawn with the building levels
   and u integrated out. The rows' weights diag(c) of `building_zones_gibbs.global_system`
   become the block-diagonal W, and each building's sums use the row sums of W.
   `building_zones_floor_asof2_unit` drew theta with the unit effects held at their last draw,
   and the coefficients of columns that are constant within a unit mixed slowly against the
   935k effects (68 of 121 coefficients missed the gate in fit 4). With u integrated out the
   draw of theta is exact given the scales.
2. Each zone's building spread b_z, then every building's level eta, with u integrated out.
3. u given theta and eta, by Matheron's rule: a draw from the prior, corrected by
   K W (e - prior draw - noise draw), where e = y - mean without u.
4. nu, sigma and lam from the residuals e - u (`building_zones_gibbs`'s noise step).
5. (ss, sd, tau) given theta, eta and the new scales, with u integrated out. The marginal
   likelihood of each unit's e comes from a Kalman filter on the state (s, d), and I slice
   sample along three directions in (log ss, log sd, log tau). The directions start as the
   axes. After two thirds of the warmup the run sets them from the warmup draws' covariance,
   since the three trade off against each other.
6. tau of the walk, the zone amplitudes and waves, and the floor curves' Gaussian process
   scales, as in `building_zones_gibbs`.

Steps 1, 2 and 5 integrate u out, and no step reads u between step 5 and the next sweep's
step 3, which draws it again. So the sweep leaves the posterior unchanged.

Predictions. A unit's level at a new ad depends on its training ads, so the run predicts
every row outside the training rows (the held-out ads of a split, or the ads on the market
now) at each kept draw. Given theta, eta and the scales, u at the new ad's date is
Normal(k' W e, k0 - k' W k), with k the covariance between the new ad and the unit's training
ads and k0 = ss^2 + sd^2. A unit with no training ad gets mean 0 and sd sqrt(k0). The run
keeps, for every such row and kept draw, `pred_loc` = x beta + L(t) + eta + the mean of u, and
`pred_unit_sd`, the sd of u. `rentfrontier.drift_score` turns them into predictive densities,
quantiles and deal scores without rebuilding the design.

Local drift. With units accounted for, fit 4's residuals still move together inside a building
over a few months (two ads of different units of one building within three months correlate
at 0.26, and the correlation is gone a few years apart), and a little inside a neighbourhood
in its last two years (docs/notes/drift-2026-11-10.md). `make_sampler` and `run` take `groups`, a list of
local-drift terms from `groups_of`, each one more term in the row's mean:

    a_g(m) = rho a_g(m - 1) + Normal(0, s^2 (1 - rho^2)),   a_g(first) ~ Normal(0, s^2)

for group g (a building, or a neighbourhood) and step m (a month, or a quarter). `drift` itself
runs with none; `rentfrontier.drift_building` adds the buildings' and `rentfrontier.drift_local`
the buildings' and the neighbourhoods'. Steps 1 to 3 run on y less the terms' current paths.
After step 3 each term in turn is drawn given theta, eta, u and the other terms: (log s,
logit rho) by a slice update of each on the Kalman filter's marginal likelihood of every
group's cell sums, with the paths integrated out, then the paths by backward sampling. A
prediction adds each term's path at the row's group and step, which the filter carries past
the group's last ad by the same recursion.

    python -m rentfrontier.run --model drift --split latest --name NAME
"""

from __future__ import annotations

import dataclasses
import math
import sys
import time
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import (
    amp_joint,
    b0,
    building_zones_floor_asof,
    building_zones_kitchen_sink,
    market,
    two_zone,
)
from .building_zones_gibbs import _prior_vectors, gp_cov
from .building_zones_kitchen_sink import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    AD_FIELDS,
    BLD_SD_PRIOR,
    KEPT,
    PROGRESS,
    TRACED,
    ZONES,
    Priors,
    gp_spec,
    site_rows,
    site_zone,
    split_index,
    wave_matrix,
)
from .two_zone import site_share

NAME = "drift"
# The HalfNormal scales of the lasting level's sd ss and the drift's sd sd, on log rent. Units
# of one building with the same columns rarely differ by more than 10 to 20% in rent, so 0.1
# puts most of the prior mass below 0.2 and leaves 0 open.
UNIT_SD_PRIOR = 0.1
DRIFT_SD_PRIOR = 0.1
# The Normal prior on the log of the drift's correlation time tau in years: a median of 3 years,
# with 0.4 to 22 years inside two sds.
TAU_LOG_PRIOR = (math.log(3.0), 1.0)
# The HalfNormal scale of a local-drift process's sd, on log rent.
LOCAL_SD_PRIOR = 0.1
# Units are padded to these sizes, so that each size's units stack into one array.
PADS = (2, 3, 4, 5, 6, 8, 10, 14, 22)
YEAR_WEEKS = 365.25 / 7
# The traced unit scales, in the order of the state's `hyp`.
HYP = ("unit_sd", "drift_sd", "drift_tau")


@dataclass(frozen=True)
class Settings:
    chains: int = 4
    warmup: int = 300
    draws: int = 1000
    keep_every: int = 5
    seed: int = 20261110
    # Buildings per block of the Schur complement's dense products.
    site_block: int = 4096
    # Rounds of draws between progress lines and checkpoints. A checkpoint computes the
    # diagnostics of every traced scalar, which took about 100 s a time in the pilot fit, so
    # there are few.
    chunks: int = 4
    # Draw each zone's amplitude with the waves integrated out (`rentfrontier.amp_joint`).
    joint_amp: bool = True

    def to_dict(self):
        return dataclasses.asdict(self)


@dataclass
class Design(building_zones_kitchen_sink.Design):
    unit: np.ndarray = (
        None  # (rows,) the row's unit number, -1 for a unit with no training row
    )
    units: int = 0  # the number of units with a training row
    nbhd: np.ndarray = None  # (rows,) the row's neighbourhood number
    # The rows to predict, in the full design's order: a dict of their `unit`, `years`, `x`,
    # `site`, `week`, `frac`, `group` and `y`. `subset` fills it for the training rows.
    pred: dict = None


def unit_index(frame: pd.DataFrame, held) -> tuple[np.ndarray, int]:
    """Each row's unit number and the number of units. A unit is a (building, unit_id) pair,
    and a row with no `unit_id` is its own unit. The units with a training row are numbered
    in sorted order of their keys, and a row of any other unit carries -1."""
    building = frame.building.astype(str).to_numpy(object)
    none = frame.unit_id.isna().to_numpy()
    # A missing unit_id is NaN, and a str array sized from it would cut every key short, so
    # the keys are built as objects.
    unit_id = np.where(none, "", frame.unit_id.astype(object).to_numpy()).astype(str)
    key = np.array([f"{b}|{u}" for b, u in zip(building, unit_id)], dtype=object)
    key[none] = [f"{b}|#row{i}" for i, b in zip(np.flatnonzero(none), building[none])]
    key = key.astype(str)
    train = ~np.asarray(held, bool)
    keys = np.unique(key[train])
    return pd.Index(keys).get_indexer(key).astype(np.int64), len(keys)


def years(d) -> np.ndarray:
    """Each row's time in years from the grid's start."""
    return (d.week + d.frac) / YEAR_WEEKS


def design(
    frame: pd.DataFrame, start: pd.Timestamp | None = None, held=None, **kw
) -> Design:
    """The kitchen sink's design of `frame`, with each row's unit number. A dataset with an
    inputs.json (`rentfrontier.market`) names the snapshots the design reads."""
    market.apply_inputs(frame.attrs.get("dataset"))
    held = building_zones_floor_asof.held_out(frame, held)
    d = building_zones_kitchen_sink.design(frame, start, held=held, **kw)
    unit, units = unit_index(frame, held)
    nbhd, _ = pd.factorize(frame.neighbourhood.astype(str), sort=True)
    return Design(
        **{f.name: getattr(d, f.name) for f in dataclasses.fields(d)},
        unit=unit,
        units=units,
        nbhd=nbhd.astype(np.int64),
    )


def subset(d: Design, mask: np.ndarray) -> Design:
    """`d`'s rows under `mask`. When `mask` keeps most of the rows, they are the training
    rows, and the result carries the other rows as its rows to predict."""
    mask = np.asarray(mask, bool)
    other = ~mask
    pred = None
    if 0 < other.sum() < mask.sum():
        pred = dict(
            unit=d.unit[other],
            years=years(d)[other],
            x=d.x[other],
            site=d.site[other],
            week=d.week[other],
            frac=d.frac[other],
            group=d.group[other],
            y=d.y[other],
            nbhd=None if d.nbhd is None else d.nbhd[other],
        )
    return dataclasses.replace(
        building_zones_kitchen_sink.subset(d, mask),
        unit=d.unit[mask],
        nbhd=None if d.nbhd is None else d.nbhd[mask],
        pred=pred,
    )


def groups_of(d: Design, which) -> list[dict]:
    """The local-drift terms named in `which` for training design `d` (see the module
    docstring): `building`, one process per building in monthly steps, and `nbhd`, one per
    neighbourhood in quarterly steps. Each dict holds the term's `name`, each training row's
    group `row`, each predicted row's group `pred`, the number of groups `size`, the steps a
    year `per_year` and the HalfNormal scale `sd_prior` of the process's sd."""
    pred = d.pred or {}
    out = []
    for name in which:
        if name == "building":
            row, prd = d.site, pred.get("site")
            size, per_year = len(site_zone(d)), 12
        elif name == "nbhd":
            row, prd = d.nbhd, pred.get("nbhd")
            both = [row] + ([prd] if prd is not None and len(prd) else [])
            size, per_year = int(max(v.max() for v in both)) + 1, 4
        else:
            raise ValueError(f"unknown local-drift term {name!r}")
        out.append(
            dict(
                name=name,
                row=np.asarray(row, np.int64),
                pred=np.zeros(0, np.int64)
                if prd is None
                else np.asarray(prd, np.int64),
                size=size,
                per_year=per_year,
                sd_prior=LOCAL_SD_PRIOR,
            )
        )
    return out


# ------------------------------------------------------------------ the units' layout


def unit_layout(unit: np.ndarray, t: np.ndarray, pads=PADS) -> dict:
    """The static index arrays of the units' rows, for rows already sorted so that each
    unit's rows are contiguous and in time order.

    Returns
    - `single`: (rows,) whether the row's unit has one row;
    - `buckets`: one dict per padded size n with units of 2 or more rows, holding `idx`
      (units, n) row numbers, padded with the unit's last row, `mask` (units, n), and `t`
      (units, n) the rows' times, padded with the unit's last time;
    - `take_d`: (rows,) each row's place on the diagonal of its unit's matrix, in the
      buckets' matrices raveled and laid end to end (0 for a single row);
    - `pi`, `pj`, `take_off`: for every ordered pair of distinct rows of one unit, the two
      rows and the pair's place in the raveled matrices, sorted by `pi`;
    - `slot`: (units by number, 2) each unit's bucket (-1 for a single) and its place in it,
      or the row itself for a single."""
    n = len(unit)
    first = np.r_[0, np.flatnonzero(np.diff(unit)) + 1] if n else np.zeros(0, int)
    size = np.diff(np.r_[first, n])
    assert len(np.unique(unit)) == len(first), "each unit's rows must be contiguous"
    assert (np.diff(t)[np.diff(unit) == 0] >= 0).all(), (
        "a unit's rows must be in time order"
    )
    single = np.repeat(size == 1, size)
    pads = tuple(p for p in pads if p < size.max(initial=1)) + (
        int(size.max(initial=1)),
    )
    slot = np.full((int(unit.max(initial=-1)) + 1, 2), -1, np.int64)
    one = size == 1
    slot[unit[first[one]], 1] = first[one]
    buckets, take_d = [], np.zeros(n, np.int64)
    pi, pj, take_off = [], [], []
    offset, lo = 0, 1
    for b, pad in enumerate(p for p in pads if p >= 2):
        sel = np.flatnonzero((size > lo) & (size <= pad))
        lo = pad
        if not len(sel):
            continue
        pos = np.arange(pad)[None, :]
        mask = pos < size[sel, None]
        idx = first[sel, None] + np.minimum(pos, size[sel, None] - 1)
        k = len(buckets)
        slot[unit[first[sel]], 0] = k
        slot[unit[first[sel]], 1] = np.arange(len(sel))
        base = offset + np.arange(len(sel))[:, None] * pad * pad
        take_d[idx[mask]] = (base + pos * pad + pos)[mask]
        a, c = np.meshgrid(np.arange(pad), np.arange(pad), indexing="ij")
        a, c = a.ravel(), c.ravel()
        ok = (mask[:, a] & mask[:, c]) & (a != c)[None, :]
        pi.append(idx[:, a][ok])
        pj.append(idx[:, c][ok])
        take_off.append((base + (a * pad + c)[None, :])[ok])
        buckets.append(dict(idx=idx, mask=mask, t=t[idx]))
        offset += len(sel) * pad * pad
    cat = lambda v: np.concatenate(v) if v else np.zeros(0, np.int64)  # noqa: E731
    pi, pj, take_off = cat(pi), cat(pj), cat(take_off)
    o = np.argsort(pi, kind="stable")
    return dict(
        single=single,
        buckets=buckets,
        take_d=take_d,
        pi=pi[o],
        pj=pj[o],
        take_off=take_off[o],
        slot=slot,
    )


def pred_layout(lay: dict, pred_unit, pred_years) -> dict:
    """Where each row to predict finds its unit's training rows: `none` (rows) for a unit with
    no training row, `one` (rows, the training row) for a unit with a single training row,
    and per bucket the rows, their units' places and their times."""
    pred_unit = np.asarray(pred_unit, np.int64)
    pred_years = np.asarray(pred_years, float)
    seen = pred_unit >= 0
    slot = lay["slot"][np.maximum(pred_unit, 0)]
    one = seen & (slot[:, 0] < 0)
    out = dict(
        rows=len(pred_unit),
        years=pred_years,
        one=(np.flatnonzero(one), slot[one, 1]),
        buckets=[],
    )
    for k in range(len(lay["buckets"])):
        sel = np.flatnonzero(seen & (slot[:, 0] == k))
        out["buckets"].append((sel, slot[sel, 1]))
    return out


# ------------------------------------------------------------------ the sampler (JAX)


def make_sampler(d: Design, priors: Priors, settings: Settings, gp=None, groups=None):
    """The jitted sweep, the initial state, the jitted prediction step and the sampler's
    parts for design `d`. The sweep, the initial state and the prediction step are vmapped
    over chains. See `building_zones_gibbs.make_sampler` for `gp` and `groups_of` for
    `groups`, the local-drift terms."""
    jax, jnp = b0._jax()
    seg = jax.ops.segment_sum
    alpha = d.names.index("alpha")
    others = np.array([j for j in range(len(d.names)) if j != alpha])
    pb = len(others)
    W1 = d.weeks + 1
    Bc, sds = wave_matrix(d)
    K = len(sds)
    nz = len(d.surfaces)
    G = pb + W1 + 1 + K
    sl_b, sl_M, i_g, sl_w = (
        slice(0, pb),
        slice(pb, pb + W1),
        pb + W1,
        slice(pb + W1 + 1, G),
    )
    m_b, s_b, m_a, s_a = _prior_vectors(d, priors)
    prec_b, lin_b = 1 / s_b**2, m_b / s_b**2
    gps = []
    for spec in gp or ():
        pos = np.searchsorted(others, [d.names.index(c) for c in spec["cols"]])
        prec_b[pos], lin_b[pos] = 0.0, 0.0
        gps.append((pos, np.asarray(spec["x"], float), spec["amp"], spec["ls"]))
    m_g, s_g = priors.g
    tau_rate = -math.log(priors.tau_alpha) / priors.tau_u
    which = np.concatenate([np.full(len(s["sd"]), k) for k, s in enumerate(d.surfaces)])
    zone = site_zone(d)
    joint = (
        amp_joint.make_step(Bc, sds, which, zone, priors.amp)
        if settings.joint_amp
        else None
    )
    S = len(zone)
    rows_per_site = site_rows(d)
    n = len(d.y)
    assert (d.unit >= 0).all(), "every training row needs a unit"

    # Rows sorted by building, then unit, then time, and the buildings in blocks.
    t_all = years(d)
    order = np.lexsort((t_all, d.unit, d.site))
    active = np.flatnonzero(rows_per_site > 0)
    rank = np.full(S, -1)
    rank[active] = np.arange(len(active))
    site_sorted = d.site[order]
    arank = rank[site_sorted]
    Q = settings.site_block
    blocks = []
    for q0 in range(0, len(active), Q):
        q1 = min(q0 + Q, len(active))
        r0, r1 = np.searchsorted(arank, [q0, q1])
        blocks.append((q0, q1, int(r0), int(r1)))
    lay = unit_layout(d.unit[order], t_all[order])
    rows_to_predict = d.pred or dict(
        unit=np.zeros(0, np.int64),
        years=np.zeros(0),
        x=np.zeros((0, len(d.names))),
        site=np.zeros(0, np.int64),
        week=np.zeros(0, np.int64),
        frac=np.zeros(0),
    )
    pred = pred_layout(lay, rows_to_predict["unit"], rows_to_predict["years"])
    # Local-drift terms: each row's cell (group, step) in the term's raveled (groups, steps)
    # array.
    ars, ar_cell, ar_pcell = [], [], []
    for g in groups or ():
        step = np.floor(t_all[order] * g["per_year"]).astype(np.int64)
        pstep = np.floor(np.asarray(rows_to_predict["years"]) * g["per_year"]).astype(
            np.int64
        )
        T = int(max(step.max(initial=0), pstep.max(initial=0))) + 1
        ars.append(
            dict(name=g["name"], size=int(g["size"]), T=T, sd_prior=g["sd_prior"])
        )
        ar_cell.append(g["row"][order] * T + step)
        ar_pcell.append(g["pred"] * T + pstep)
    # Each block's part of every bucket. A unit's rows share a building, so a unit never
    # spans two blocks, and a bucket lists its units in row order, so a block's units are a
    # slice of it. `blk_part[j]` holds (bucket, first unit, last unit + 1) for block j,
    # `blk_idx[j]` those units' rows counted from the block's first row, and `blk_take[j]`
    # each row's place in the stack of the block's rows followed by its buckets' places.
    blk_part, blk_idx, blk_take = [], [], []
    for _, _, r0, r1 in blocks:
        take = np.arange(r1 - r0)
        offset = r1 - r0
        part, idxs = [], []
        for b, bucket in enumerate(lay["buckets"]):
            lo, hi = (int(v) for v in np.searchsorted(bucket["idx"][:, 0], [r0, r1]))
            if hi == lo:
                continue
            idx = bucket["idx"][lo:hi] - r0
            mask = bucket["mask"][lo:hi]
            place = offset + np.arange(idx.size).reshape(idx.shape)
            take[idx[mask]] = place[mask]
            offset += idx.size
            part.append((b, lo, hi))
            idxs.append(idx)
        blk_part.append(part)
        blk_idx.append(idxs)
        blk_take.append(take)
    x = d.x[order][:, others]
    wk_all, fr_all = d.week[order], d.frac[order]
    # The rows' data goes to the jitted sweep as an argument: closed over, it would be
    # compiled in as constants.
    data = dict(
        xs=[jnp.asarray(x[r0:r1]) for _, _, r0, r1 in blocks],
        wk=[jnp.asarray(wk_all[r0:r1]) for _, _, r0, r1 in blocks],
        fr=[jnp.asarray(fr_all[r0:r1]) for _, _, r0, r1 in blocks],
        loc=[jnp.asarray(arank[r0:r1] - q0) for q0, _, r0, r1 in blocks],
        Bact=[jnp.asarray(Bc[active[q0:q1]]) for q0, q1, _, _ in blocks],
        blk_idx=[[jnp.asarray(v) for v in idxs] for idxs in blk_idx],
        blk_take=[jnp.asarray(v) for v in blk_take],
        y=jnp.asarray(d.y[order]),
        group=jnp.asarray(d.group[order]),
        site=jnp.asarray(site_sorted),
        wk_all=jnp.asarray(wk_all),
        fr_all=jnp.asarray(fr_all),
        t=jnp.asarray(t_all[order]),
        single=jnp.asarray(lay["single"]),
        take_d=jnp.asarray(lay["take_d"]),
        take_off=jnp.asarray(lay["take_off"]),
        pi=jnp.asarray(lay["pi"]),
        pj=jnp.asarray(lay["pj"]),
        b_idx=[jnp.asarray(b["idx"]) for b in lay["buckets"]],
        b_mask=[jnp.asarray(b["mask"]) for b in lay["buckets"]],
        b_t=[jnp.asarray(b["t"]) for b in lay["buckets"]],
        Bc=jnp.asarray(Bc),
        p_years=jnp.asarray(pred["years"]),
        p_x=jnp.asarray(np.asarray(rows_to_predict["x"])[:, others]),
        p_site=jnp.asarray(rows_to_predict["site"]),
        p_wk=jnp.asarray(rows_to_predict["week"]),
        p_fr=jnp.asarray(rows_to_predict["frac"]),
        ar_cell=[jnp.asarray(v) for v in ar_cell],
        ar_pcell=[jnp.asarray(v) for v in ar_pcell],
        p_one=tuple(jnp.asarray(v) for v in pred["one"]),
        p_buckets=[tuple(jnp.asarray(v) for v in b) for b in pred["buckets"]],
    )
    del x
    n_pred = pred["rows"]
    active_j = jnp.asarray(active)
    zone_j = jnp.asarray(zone)
    which_j = jnp.asarray(which)
    sds_j = jnp.asarray(sds)
    prec_b, lin_b = jnp.asarray(prec_b), jnp.asarray(lin_b)
    # The walk's prior on (M, g): E (M, g) = diff(M) - g.
    E = np.zeros((W1 - 1, W1 + 1))
    E[np.arange(W1 - 1), np.arange(W1 - 1)] = -1
    E[np.arange(W1 - 1), np.arange(1, W1)] = 1
    E[:, W1] = -1
    EtE = jnp.asarray(E.T @ E)
    share = site_share(d)
    parts = [slice(s["first"], s["first"] + s["sites"]) for s in d.surfaces]
    zone_share = [jnp.asarray(share[p] / max(share[p].sum(), 1e-300)) for p in parts]
    row_wgt = [
        jnp.asarray(rows_per_site[p] / max(rows_per_site[p].sum(), 1.0)) for p in parts
    ]

    def row_mean(D, theta, j):
        """x beta + L(t) at block j's rows, with alpha folded into the levels M."""
        M = theta[sl_M]
        xs, fr, wk = D["xs"], D["fr"], D["wk"]
        return xs[j] @ theta[sl_b] + (1 - fr[j]) * M[wk[j]] + fr[j] * M[wk[j] + 1]

    def weights(D, st):
        """Each row's weight c_i = lam_i / sigma_g^2."""
        return st["lam"] / st["sigma"][D["group"]] ** 2

    def scales(hyp):
        ss, sd, tau = jnp.exp(hyp[0]), jnp.exp(hyp[1]), jnp.exp(hyp[2])
        return ss, sd, tau

    def kernel(hyp, ta, tb):
        """Cov(u(ta), u(tb)) for two ads of one unit."""
        ss, sd, tau = scales(hyp)
        return ss**2 + sd**2 * jnp.exp(-jnp.abs(ta - tb) / tau)

    def unit_W(D, hyp, c):
        """The units' precisions W = (D^-1 + K)^-1 at weights c: `w1`, the scalar of each
        row taken as a unit of one row (read only for single rows), and one (units, n, n)
        stack per bucket. A padded place has weight 0, so its row and column of W are 0."""
        ss, sd, _ = scales(hyp)
        w1 = c / (1 + c * (ss**2 + sd**2))
        Wb = []
        for idx, mask, tb in zip(D["b_idx"], D["b_mask"], D["b_t"]):
            sq = jnp.sqrt(jnp.where(mask, c[idx], 0.0))
            Kb = kernel(hyp, tb[:, :, None], tb[:, None, :])
            M = jnp.eye(idx.shape[1]) + sq[:, :, None] * Kb * sq[:, None, :]
            Mi = jnp.linalg.inv(M)
            Mi = 0.5 * (Mi + jnp.swapaxes(Mi, 1, 2))
            Wb.append(sq[:, :, None] * Mi * sq[:, None, :])
        return w1, Wb

    def pair_weights(D, w1, Wb):
        """W's diagonal for every row and its off-diagonal entries in the pairs' order."""
        flat = jnp.concatenate([w.ravel() for w in Wb]) if Wb else jnp.zeros(1)
        om_d = jnp.where(D["single"], w1, flat[D["take_d"]])
        return om_d, flat[D["take_off"]]

    def apply_W(D, om_d, om_off, v):
        """W v for a vector v over rows."""
        return om_d * v + seg(om_off * v[D["pj"]], D["pi"], num_segments=n)

    def offsets(D, st):
        """Each row's sum of its local-drift terms."""
        out = jnp.zeros(n)
        for k in range(len(ars)):
            out = out + st["ar"][k].ravel()[D["ar_cell"][k]]
        return out

    def global_system(D, st, c, w1, Wb, y_all=None):
        """The precision and linear term of theta given the scales, from responses `y_all`
        in the sorted row order (y less the local-drift terms by default), with every
        building's level and every unit's u integrated out."""
        xs, wk, fr, loc, Bact = (D[k] for k in ("xs", "wk", "fr", "loc", "Bact"))
        y_all = D["y"] - offsets(D, st) if y_all is None else y_all
        site_all = D["site"]
        bsd2 = st["bld_sd"][zone_j] ** 2
        om_d, om_off = pair_weights(D, w1, Wb)
        ctil = om_d + seg(om_off, D["pi"], num_segments=n)
        Wy = apply_W(D, om_d, om_off, y_all)
        C = seg(ctil, site_all, num_segments=S)
        h_eta = seg(Wy, site_all, num_segments=S)
        P = C + 1 / bsd2
        R = pb + W1
        XX = jnp.zeros((R, R))
        hR = jnp.zeros(R)
        Rw = jnp.zeros((R, K))
        ww = jnp.zeros((K, K))
        hw = jnp.zeros(K)
        for j, (q0, q1, r0, r1) in enumerate(blocks):
            od_j, ct, wy = om_d[r0:r1], ctil[r0:r1], Wy[r0:r1]
            a0, a1 = 1 - fr[j], fr[j]
            nq = q1 - q0
            # Z = W x over the block's rows: a single row's is w1 x, and a bucket's units
            # multiply their rows of x by their W. A padded place has W = 0 and is not taken.
            stack = [w1[r0:r1, None] * xs[j]]
            for (b, lo, hi), idx in zip(blk_part[j], D["blk_idx"][j]):
                stack.append((Wb[b][lo:hi] @ xs[j][idx]).reshape(-1, pb))
            Z = jnp.concatenate(stack)[D["blk_take"][j]]
            XX = XX.at[:pb, :pb].add(xs[j].T @ Z)
            XM = seg(a0[:, None] * Z, wk[j], num_segments=W1) + seg(
                a1[:, None] * Z, wk[j] + 1, num_segments=W1
            )
            XX = XX.at[pb:, :pb].add(XM)
            XX = XX.at[:pb, pb:].add(XM.T)
            # W's diagonal on (M, M); its off-diagonal pairs follow the loop.
            diag = seg(od_j * a0 * a0, wk[j], num_segments=W1) + seg(
                od_j * a1 * a1, wk[j] + 1, num_segments=W1
            )
            od = seg(od_j * a0 * a1, wk[j], num_segments=W1)[:-1]
            XX = XX.at[pb:, pb:].add(
                jnp.diag(diag) + jnp.diag(od, 1) + jnp.diag(od, -1)
            )
            hR = hR.at[:pb].add(xs[j].T @ wy)
            hR = hR.at[pb:].add(
                seg(a0 * wy, wk[j], num_segments=W1)
                + seg(a1 * wy, wk[j] + 1, num_segments=W1)
            )
            # Minus what the building levels take, from the row sums of W.
            CX = seg(ct[:, None] * xs[j], loc[j], num_segments=nq)
            flat = loc[j] * W1 + wk[j]
            CM = (
                seg(ct * a0, flat, num_segments=nq * W1)
                + seg(ct * a1, flat + 1, num_segments=nq * W1)
            ).reshape(nq, W1)
            CR = jnp.concatenate([CX, CM], axis=1)
            ids = active_j[q0:q1]
            Pq, Cq, bq = P[ids], C[ids], bsd2[ids]
            XX = XX - (CR / Pq[:, None]).T @ CR
            Rw = Rw + (CR / (bq * Pq)[:, None]).T @ Bact[j]
            hR = hR - CR.T @ (h_eta[ids] / Pq)
            ww = ww + (Bact[j] * (Cq / (bq * Pq))[:, None]).T @ Bact[j]
            hw = hw + Bact[j].T @ (h_eta[ids] / (bq * Pq))
        # The pairs' part of (M, M): each pair's two rows meet two walk levels each.
        wi, wj = D["wk_all"][D["pi"]], D["wk_all"][D["pj"]]
        fi, fj = D["fr_all"][D["pi"]], D["fr_all"][D["pj"]]
        MM = jnp.zeros(W1 * W1)
        for ai, oi in ((1 - fi, 0), (fi, 1)):
            for aj, oj in ((1 - fj, 0), (fj, 1)):
                MM = MM + seg(
                    om_off * ai * aj, (wi + oi) * W1 + wj + oj, num_segments=W1 * W1
                )
        XX = XX.at[pb:, pb:].add(MM.reshape(W1, W1))
        A = jnp.zeros((G, G))
        h = jnp.zeros(G)
        A = A.at[:R, :R].set(0.5 * (XX + XX.T))
        A = A.at[:R, sl_w].set(Rw)
        A = A.at[sl_w, :R].set(Rw.T)
        A = A.at[sl_w, sl_w].set(ww + jnp.diag(1 / (st["amp"][which_j] * sds_j) ** 2))
        h = h.at[:R].set(hR).at[sl_w].set(hw)
        A = A.at[sl_b, sl_b].add(jnp.diag(prec_b))
        h = h.at[sl_b].add(lin_b)
        for k, (pos, xk, _, _) in enumerate(gps):
            Lk = jnp.linalg.cholesky(gp_cov(jnp, xk, st["gp_ls"][k]))
            Ki = jax.scipy.linalg.cho_solve((Lk, True), jnp.eye(len(pos)))
            A = A.at[np.ix_(pos, pos)].add(Ki / st["gp_amp"][k] ** 2)
        A = A.at[pb, pb].add(1 / s_a**2)
        h = h.at[pb].add(m_a / s_a**2)
        A = A.at[pb : i_g + 1, pb : i_g + 1].add(EtE / st["tau"] ** 2)
        A = A.at[i_g, i_g].add(1 / s_g**2)
        h = h.at[i_g].add(m_g / s_g**2)
        return A, h, (om_d, om_off, ctil)

    def draw_theta(D, key, st, c, w1, Wb, y_all):
        A, h, om = global_system(D, st, c, w1, Wb, y_all)
        s = 1 / jnp.sqrt(jnp.diag(A))
        Cf = jnp.linalg.cholesky(A * s[:, None] * s[None, :])
        mean = jax.scipy.linalg.cho_solve((Cf, True), h * s)
        dev = jax.scipy.linalg.solve_triangular(
            Cf.T, jax.random.normal(key, (G,)), lower=False
        )
        return (mean + dev) * s, om

    def update_spread(key, st, C, Rs, F):
        """Each zone's spread b_z from the buildings' likelihood with their levels integrated
        out: per building, -log(1 + b^2 C_s) / 2 + (R_s - C_s F_s)^2 / (2 (C_s + 1 / b^2))."""
        Rp = Rs - C * F

        def logp(lb):
            b2 = jnp.exp(2 * lb)[zone_j]
            per = -0.5 * jnp.log1p(b2 * C) + 0.5 * Rp**2 / (C + 1 / b2)
            ll = seg(per, zone_j, num_segments=nz)
            return ll - jnp.exp(2 * lb) / (2 * BLD_SD_PRIOR**2) + lb

        return jnp.exp(b0.slice_vec(key, jnp.log(st["bld_sd"]), logp, 0.05))

    def draw_u(D, key, hyp, c, w1, Wb, e):
        """u at every row given the rows' remainders e = y - mean without u (Matheron's
        rule; a single row's u has a closed form)."""
        ss, sd, tau = scales(hyp)
        k0 = ss**2 + sd**2
        keys = jax.random.split(key, 1 + len(Wb))
        one = k0 * w1 * e + jnp.sqrt(k0 / (1 + c * k0)) * jax.random.normal(
            keys[0], (n,)
        )
        u = jnp.where(D["single"], one, 0.0)
        for kk, W, idx, mask, tb in zip(
            keys[1:], Wb, D["b_idx"], D["b_mask"], D["b_t"]
        ):
            B, m = idx.shape
            k1, k2, k3 = jax.random.split(kk, 3)
            # A draw of the drift from its prior: d = sd Lou z, with Lou the Cholesky factor
            # of the OU correlation, exp(-(t_a - t_b) / tau) sqrt(1 - phi_b^2) for a >= b.
            gap = jnp.concatenate([jnp.zeros((B, 1)), jnp.diff(tb, axis=1)], axis=1)
            s_b = jnp.sqrt(-jnp.expm1(-2 * gap / tau)).at[:, 0].set(1.0)
            Lou = jnp.tril(
                jnp.exp(-jnp.abs(tb[:, :, None] - tb[:, None, :]) / tau)
                * s_b[:, None, :]
            )
            z = jax.random.normal(k2, (B, m))
            u0 = ss * jax.random.normal(k1, (B, 1)) + sd * jnp.einsum(
                "bij,bj->bi", Lou, z
            )
            cb = jnp.where(mask, c[idx], 1.0)
            eps = jax.random.normal(k3, (B, m)) / jnp.sqrt(cb)
            res = jnp.where(mask, e[idx] - u0 - eps, 0.0)
            Kb = kernel(hyp, tb[:, :, None], tb[:, None, :])
            ub = u0 + jnp.einsum("bij,bj->bi", Kb, jnp.einsum("bij,bj->bi", W, res))
            u = (
                u
                + seg(
                    jnp.where(mask, ub, 0.0).ravel(),
                    jnp.where(mask, idx, n).ravel(),
                    num_segments=n + 1,
                )[:n]
            )
        return u

    def unit_loglik(D, hyp, c, e):
        """The log marginal likelihood of the rows' remainders e with u integrated out, up
        to a constant in (ss, sd, tau): a Kalman filter on each unit's state (s, d)."""
        ss, sd, tau = scales(hyp)
        k0 = ss**2 + sd**2
        f1 = 1 + c * k0
        ll = jnp.sum(jnp.where(D["single"], -0.5 * (jnp.log(f1) + c * e * e / f1), 0.0))
        for idx, mask, tb in zip(D["b_idx"], D["b_mask"], D["b_t"]):
            B, m = idx.shape
            cb = jnp.where(mask, c[idx], 1.0)
            eb = e[idx]
            m1 = jnp.zeros(B)
            m2 = jnp.zeros(B)
            p11 = jnp.full(B, ss**2)
            p12 = jnp.zeros(B)
            p22 = jnp.full(B, sd**2)
            for a in range(m):
                if a:
                    phi = jnp.exp(-(tb[:, a] - tb[:, a - 1]) / tau)
                    m2 = phi * m2
                    p12 = phi * p12
                    p22 = phi * phi * p22 + sd**2 * (1 - phi * phi)
                ok = mask[:, a]
                f = p11 + 2 * p12 + p22 + 1 / cb[:, a]
                v = eb[:, a] - m1 - m2
                ll = ll + jnp.sum(
                    jnp.where(ok, -0.5 * (jnp.log(cb[:, a] * f) + v * v / f), 0.0)
                )
                g1 = jnp.where(ok, (p11 + p12) / f, 0.0)
                g2 = jnp.where(ok, (p12 + p22) / f, 0.0)
                m1, m2 = m1 + g1 * v, m2 + g2 * v
                p11, p12, p22 = p11 - g1 * g1 * f, p12 - g1 * g2 * f, p22 - g2 * g2 * f
        return ll

    def hyp_logp(D, hyp, c, e):
        ss, sd, _ = scales(hyp)
        prior = (
            -(ss**2) / (2 * UNIT_SD_PRIOR**2)
            + hyp[0]
            - sd**2 / (2 * DRIFT_SD_PRIOR**2)
            + hyp[1]
            - (hyp[2] - TAU_LOG_PRIOR[0]) ** 2 / (2 * TAU_LOG_PRIOR[1] ** 2)
        )
        return unit_loglik(D, hyp, c, e) + prior

    def update_hyp(D, key, st, c, e):
        """(log ss, log sd, log tau) with u integrated out: a slice update along each
        column of the state's `hyp_dirs` in turn."""
        hyp = st["hyp"]
        for k, kk in enumerate(jax.random.split(key, 3)):
            v = st["hyp_dirs"][:, k]

            def logp(s, hyp=hyp, v=v):
                return hyp_logp(D, hyp + s[0] * v, c, e)[None]

            s = b0.slice_vec(kk, jnp.zeros(1), logp, 1.0, steps_out=4, shrink=32)
            hyp = hyp + s[0] * v
        return hyp

    def ar_filter(par, C, R):
        """The Kalman filter of one local-drift term's processes over its steps, from each
        cell's sum of row weights C and weighted remainders R, (groups, steps). Returns the
        log marginal likelihood up to a constant in (sd, rho), and the filtered means and
        variances, (steps, groups)."""
        s2 = jnp.exp(2 * par[0])
        rho = jax.nn.sigmoid(par[1])
        q = s2 * (1 - rho * rho)

        def step(carry, x):
            m, p, ll = carry
            Cc, Rr, t = x
            m = jnp.where(t > 0, rho * m, m)
            p = jnp.where(t > 0, rho * rho * p + q, p)
            P = Cc + 1 / p
            h = Rr + m / p
            ll = ll + jnp.sum(
                -0.5 * jnp.log1p(p * Cc) + 0.5 * h * h / P - 0.5 * m * m / p
            )
            m, p = h / P, 1 / P
            return (m, p, ll), (m, p)

        G_, T_ = C.shape
        init = (jnp.zeros(G_), jnp.full(G_, s2), jnp.zeros(()))
        (_, _, ll), (mf, pf) = jax.lax.scan(step, init, (C.T, R.T, jnp.arange(T_)))
        return ll, mf, pf

    def ar_draw(key, par, mf, pf):
        """A draw of every process's path given the filter's output (backward sampling),
        (groups, steps)."""
        s2 = jnp.exp(2 * par[0])
        rho = jax.nn.sigmoid(par[1])
        q = s2 * (1 - rho * rho)
        z = jax.random.normal(key, mf.shape)
        last = mf[-1] + jnp.sqrt(pf[-1]) * z[-1]

        def step(nxt, x):
            m, p, zz = x
            pp = rho * rho * p + q
            J = rho * p / pp
            mean = m + J * (nxt - rho * m)
            var = jnp.maximum(p - J * J * pp, 0.0)
            cur = mean + jnp.sqrt(var) * zz
            return cur, cur

        _, path = jax.lax.scan(step, last, (mf[:-1], pf[:-1], z[:-1]), reverse=True)
        return jnp.concatenate([path, last[None]], axis=0).T

    def update_ar(key, k, par, C, R):
        """One term's (log sd, logit rho) with its paths integrated out, by a slice update of
        each in turn, then the paths."""
        prior_sd = ars[k]["sd_prior"]

        def logp(x):
            ll, _, _ = ar_filter(x, C, R)
            rho = jax.nn.sigmoid(x[1])
            return (
                ll
                - jnp.exp(2 * x[0]) / (2 * prior_sd**2)
                + x[0]
                + jnp.log(rho)
                + jnp.log1p(-rho)
            )

        k1, k2, k3 = jax.random.split(key, 3)
        for j, (kk, width) in enumerate(((k1, 0.05), (k2, 0.2))):

            def along(v, par=par, j=j):
                return logp(par.at[j].set(v[0]))[None]

            par = par.at[j].set(
                b0.slice_vec(kk, par[j][None], along, width, steps_out=4, shrink=32)[0]
            )
        _, mf, pf = ar_filter(par, C, R)
        return par, ar_draw(k3, par, mf, pf)

    def update_noise(key, st, r, group_all):
        """nu, then sigma, with lam integrated out, then lam: b0's noise step."""
        k1, k2, k3 = jax.random.split(key, 3)
        a_nu, b_nu = priors.nu

        def logp_nu(lnu):
            nu = jnp.exp(lnu[0])
            ll = jnp.sum(b0.t_logpdf(r, nu, st["sigma"][group_all]))
            return (ll + a_nu * lnu[0] - b_nu * nu)[None]

        nu = jnp.exp(b0.slice_vec(k1, jnp.log(st["nu"])[None], logp_nu, 0.1)[0])

        def logp_sigma(ls):
            sig = jnp.exp(ls)
            ll = seg(b0.t_logpdf(r, nu, sig[group_all]), group_all, num_segments=4)
            return ll - sig**2 / (2 * priors.sigma**2) + ls

        sigma = jnp.exp(b0.slice_vec(k2, jnp.log(st["sigma"]), logp_sigma, 0.02))
        z2 = (r / sigma[group_all]) ** 2
        lam = jax.random.gamma(k3, (nu + 1) / 2, (n,)) / ((nu + z2) / 2)
        return nu, sigma, lam

    def update_tau(key, st, M, g):
        z = jnp.diff(M) - g
        ss, k = jnp.sum(z * z), z.shape[0]

        def logp(lt):
            t = jnp.exp(lt[0])
            return (-k * lt[0] - ss / (2 * t * t) - tau_rate * t + lt[0])[None]

        return jnp.exp(b0.slice_vec(key, jnp.log(st["tau"])[None], logp, 0.1)[0])

    def update_amp(key, st, w):
        q = seg((w / sds_j) ** 2, which_j, num_segments=nz)
        cnt = jnp.asarray(np.bincount(which, minlength=nz), dtype=w.dtype)

        def logp(la):
            a = jnp.exp(la)
            return -cnt * la - q / (2 * a * a) - a * a / (2 * priors.amp**2) + la

        return jnp.exp(b0.slice_vec(key, jnp.log(st["amp"]), logp, 0.1))

    def update_gp(key, st, theta):
        """Each process's lengthscale with its amplitude integrated out, then its amplitude:
        `building_zones_gibbs`'s step."""
        k1, k2 = jax.random.split(key)
        f = [theta[sl_b][pos] for pos, _, _, _ in gps]

        def quad(k, ls):
            Lk = jnp.linalg.cholesky(gp_cov(jnp, gps[k][1], ls))
            z = jax.scipy.linalg.solve_triangular(Lk, f[k], lower=True)
            return z @ z, 2 * jnp.sum(jnp.log(jnp.diag(Lk)))

        cnt = jnp.asarray([len(pos) for pos, _, _, _ in gps], dtype=theta.dtype)
        shape = jnp.asarray([a[0] for _, _, a, _ in gps]) + cnt / 2
        rate = jnp.asarray([a[1] for _, _, a, _ in gps])
        mu = jnp.asarray([m for _, _, _, (m, _) in gps])
        sd = jnp.asarray([s for _, _, _, (_, s) in gps])

        def parts_(ll):
            out = [quad(k, jnp.exp(ll[k])) for k in range(len(gps))]
            return jnp.stack([o[0] for o in out]), jnp.stack([o[1] for o in out])

        def logp_ls(ll):
            q, ld = parts_(ll)
            return (
                -ld / 2 - shape * jnp.log(rate + q / 2) - (ll - mu) ** 2 / (2 * sd**2)
            )

        ll = b0.slice_vec(k1, jnp.log(st["gp_ls"]), logp_ls, 0.3)
        q, _ = parts_(ll)
        amp2 = (rate + q / 2) / jax.random.gamma(k2, shape)
        return jnp.sqrt(amp2), jnp.exp(ll)

    def outputs(theta, lev, F):
        """The kept quantities building zones' NumPyro model reports, from one state."""
        M = theta[sl_M]
        g = theta[i_g]
        beta = (
            jnp.zeros(len(d.names), theta.dtype)
            .at[jnp.asarray(others)]
            .set(theta[sl_b])
            .at[alpha]
            .set(M[0])
        )
        pieces = [F[p] for p in parts]
        b = lev - F
        var_f, var_b = [], []
        for p, wgt in zip(parts, row_wgt):
            for v, out in ((F[p], var_f), (b[p], var_b)):
                mu = wgt @ v
                out.append(wgt @ (v - mu) ** 2)
        return dict(
            beta=beta,
            g=g,
            L=M - M[0],
            eta=jnp.diff(M) - g,
            gp_w=theta[sl_w],
            zone_level=jnp.stack([zs @ v for zs, v in zip(zone_share, pieces)]),
            zone_sd=jnp.stack([v.std() for v in pieces]),
            bld=b.astype(jnp.float32),
            zone_var_f=jnp.stack(var_f),
            zone_var_b=jnp.stack(var_b),
        )

    def all_means(D, theta):
        return jnp.concatenate([row_mean(D, theta, j) for j in range(len(blocks))])

    def sweep(D, key, st):
        # One key per step: `fold_in(key, i)` equals `split(key, n)[i]`, so every step takes
        # its key from this one split.
        ks = jax.random.split(key, 9 + len(ars))
        k1, k2, k3, k4, k5, k6, k7, k8, k_gp = ks[:9]
        c = weights(D, st)
        w1, Wb = unit_W(D, st["hyp"], c)
        y_eff = D["y"] - offsets(D, st)
        theta, (om_d, om_off, ctil) = draw_theta(D, k1, st, c, w1, Wb, y_eff)
        w = theta[sl_w]
        F = D["Bc"] @ w
        e0 = y_eff - all_means(D, theta)
        C = seg(ctil, D["site"], num_segments=S)
        Rs = seg(apply_W(D, om_d, om_off, e0), D["site"], num_segments=S)
        bsd = update_spread(k2, st, C, Rs, F)
        b2 = bsd[zone_j] ** 2
        P = C + 1 / b2
        lev = (Rs + F / b2) / P + jax.random.normal(k3, (S,)) / jnp.sqrt(P)
        e = e0 - lev[D["site"]]
        u = draw_u(D, k7, st["hyp"], c, w1, Wb, e)
        # Each local-drift term in turn, given u and the other terms.
        r = e - u
        ar, ar_par = [], []
        for k, a in enumerate(ars):
            cell = D["ar_cell"][k]
            cells = a["size"] * a["T"]
            tgt = r + st["ar"][k].ravel()[cell]
            Cc = seg(c, cell, num_segments=cells).reshape(a["size"], a["T"])
            Rc = seg(c * tgt, cell, num_segments=cells).reshape(a["size"], a["T"])
            par, path = update_ar(ks[9 + k], k, st["ar_par"][k], Cc, Rc)
            ar.append(path)
            ar_par.append(par)
            r = tgt - path.ravel()[cell]
        e = r + u
        nu, sigma, lam = update_noise(k4, st, r, D["group"])
        hyp = update_hyp(D, k8, st, lam / sigma[D["group"]] ** 2, e)
        tau = update_tau(k5, st, theta[sl_M], theta[i_g])
        if joint is None:
            amp = update_amp(k6, st, w)
        else:
            amp, w = joint(k6, lev, bsd, st["amp"])
            theta = theta.at[sl_w].set(w)
            F = D["Bc"] @ w
        new = dict(
            theta=theta,
            lev=lev,
            bld_sd=bsd,
            nu=nu,
            sigma=sigma,
            lam=lam,
            tau=tau,
            amp=amp,
            hyp=hyp,
            hyp_dirs=st["hyp_dirs"],
        )
        if gps:
            new["gp_amp"], new["gp_ls"] = update_gp(k_gp, st, theta)
        ss, sd, tu = scales(hyp)
        out = outputs(theta, lev, F) | dict(unit_sd=ss, drift_sd=sd, drift_tau=tu)
        if ars:
            new["ar"], new["ar_par"] = tuple(ar), jnp.stack(ar_par)
            for k, a in enumerate(ars):
                out[a["name"] + "_ar_sd"] = jnp.exp(ar_par[k][0])
                out[a["name"] + "_ar_rho"] = jax.nn.sigmoid(ar_par[k][1])
        return new, out

    def predict(D, st):
        """For each row to predict, the mean of its log rent given the state's theta, levels
        and scales (x beta + L(t) + eta + the mean of u), and the sd of u, with the training
        rows' u integrated out. A building with no training row has its level drawn from
        its prior in every sweep, so the mean carries that draw."""
        c = weights(D, st)
        hyp = st["hyp"]
        ss, sd, _ = scales(hyp)
        k0 = ss**2 + sd**2
        w1, Wb = unit_W(D, hyp, c)
        om_d, om_off = pair_weights(D, w1, Wb)
        e = D["y"] - offsets(D, st) - all_means(D, st["theta"]) - st["lev"][D["site"]]
        We = apply_W(D, om_d, om_off, e)
        tp = D["p_years"]
        mean = jnp.zeros(n_pred)
        var = jnp.full(n_pred, k0)
        rows, tr = D["p_one"]
        k = kernel(hyp, tp[rows], D["t"][tr])
        mean = mean.at[rows].set(k * w1[tr] * e[tr])
        var = var.at[rows].set(k0 - k * k * w1[tr])
        for (rows, slot), W, idx, mask, tb in zip(
            D["p_buckets"], Wb, D["b_idx"], D["b_mask"], D["b_t"]
        ):
            ks = jnp.where(mask[slot], kernel(hyp, tp[rows, None], tb[slot]), 0.0)
            mean = mean.at[rows].set(jnp.sum(ks * We[idx[slot]], axis=1))
            var = var.at[rows].set(k0 - jnp.einsum("pa,pab,pb->p", ks, W[slot], ks))
        M = st["theta"][sl_M]
        fixed = (
            D["p_x"] @ st["theta"][sl_b]
            + (1 - D["p_fr"]) * M[D["p_wk"]]
            + D["p_fr"] * M[D["p_wk"] + 1]
            + st["lev"][D["p_site"]]
        )
        for k in range(len(ars)):
            fixed = fixed + st["ar"][k].ravel()[D["ar_pcell"][k]]
        loc = (fixed + mean).astype(jnp.float32)
        return loc, jnp.sqrt(jnp.maximum(var, 0.0)).astype(jnp.float32), mean

    def init(key):
        k = jax.random.split(key, 6)
        jit = lambda kk, shape, sd: jnp.exp(sd * jax.random.normal(kk, shape))  # noqa: E731
        out = dict(
            theta=jnp.zeros(G),
            lev=jnp.zeros(S),
            bld_sd=0.2 * jit(k[0], (nz,), 0.1),
            nu=5.0 * jit(k[1], (), 0.2),
            sigma=0.15 * jit(k[2], (4,), 0.1),
            lam=jnp.ones(n),
            tau=0.005 * jit(k[3], (), 0.2),
            amp=0.5 * jit(k[4], (nz,), 0.2),
            hyp=jnp.log(jnp.asarray([0.05, 0.08, 3.0]))
            + 0.2 * jax.random.normal(k[5], (3,)),
            hyp_dirs=0.05 * jnp.eye(3),
        )
        if ars:
            out["ar"] = tuple(jnp.zeros((a["size"], a["T"])) for a in ars)
            out["ar_par"] = jnp.tile(
                jnp.asarray([math.log(0.03), 1.5]), (len(ars), 1)
            ) + (0.2 * jax.random.normal(jax.random.fold_in(key, 11), (len(ars), 2)))
        if gps:
            kg = jax.random.split(jax.random.fold_in(key, 7))
            out["gp_amp"] = jnp.asarray(
                [(a[1] / a[0]) ** 0.5 for _, _, a, _ in gps]
            ) * jit(kg[0], (len(gps),), 0.2)
            out["gp_ls"] = jnp.exp(jnp.asarray([m for _, _, _, (m, _) in gps])) * jit(
                kg[1], (len(gps),), 0.2
            )
        return out

    swept = jax.jit(jax.vmap(sweep, in_axes=(None, 0, 0)))
    predicted = jax.jit(jax.vmap(predict, in_axes=(None, 0)))
    return (
        lambda keys, st: swept(data, keys, st),
        jax.jit(jax.vmap(init)),
        lambda st: predicted(data, st),
        dict(
            data=data,
            order=order,
            G=G,
            layout=lay,
            weights=weights,
            unit_W=unit_W,
            pair_weights=pair_weights,
            apply_W=apply_W,
            global_system=global_system,
            unit_loglik=unit_loglik,
            update_hyp=update_hyp,
            draw_theta=draw_theta,
            update_noise=update_noise,
            ar_filter=ar_filter,
            ar_draw=ar_draw,
            offsets=offsets,
            ars=ars,
            draw_u=draw_u,
            predict=predict,
            all_means=all_means,
            kernel=kernel,
            slices=(sl_b, sl_M, i_g, sl_w),
        ),
    )


def adapted_dirs(hyp: np.ndarray) -> np.ndarray:
    """The slice directions for (log ss, log sd, log tau) from warmup draws `hyp`
    (chains, sweeps, 3): twice the Cholesky factor of the draws' covariance within chains."""
    dev = hyp - hyp.mean(axis=1, keepdims=True)
    cov = np.einsum("csi,csj->ij", dev, dev) / max(dev.shape[0] * (dev.shape[1] - 1), 1)
    cov = cov + 1e-10 * np.eye(3)
    return 2.0 * np.linalg.cholesky(cov)


def run(
    d: Design,
    priors: Priors,
    settings: Settings,
    log=print,
    checkpoint=None,
    gp="spec",
    groups=None,
):
    """Sample the posterior of design `d` with the sweep above and the floor curves' Gaussian
    process priors. The kept arrays hold `building_zones_gibbs`'s, the unit scales `unit_sd`
    (ss), `drift_sd` and `drift_tau`. For the design's rows to predict they also hold
    `pred_loc` and `pred_unit_sd`, (chains, kept draws, rows), and the rows' `pred_y` and
    `pred_group`."""
    jax, jnp = b0._jax()
    gp = gp_spec(d.names) if gp == "spec" else gp
    t0 = time.perf_counter()
    sweep, init, predict, _ = make_sampler(d, priors, settings, gp=gp, groups=groups)
    local = tuple(g["name"] + s for g in groups or () for s in ("_ar_sd", "_ar_rho"))
    scale_names = ("nu", "sigma", "tau", "amp", "bld_sd") + (
        ("gp_amp", "gp_ls") if gp else ()
    )
    traced = TRACED + HYP + local + (("gp_amp", "gp_ls") if gp else ())
    kept_names = KEPT + HYP + local + (("gp_amp", "gp_ls") if gp else ())
    key = jax.random.PRNGKey(settings.seed)
    key, sub = jax.random.split(key)
    st = init(jax.random.split(sub, settings.chains))
    jax.block_until_ready(st)
    setup_seconds = time.perf_counter() - t0

    trace = {k: [] for k in traced}
    kept = {k: [] for k in kept_names}
    preds = {"pred_loc": [], "pred_unit_sd": []}
    has_pred = d.pred is not None and len(d.pred["unit"]) > 0
    total = settings.warmup + settings.draws
    per = max(1, settings.draws // settings.chunks)
    marks = {"warmup": None}
    # The warmup sweeps whose unit scales set the slice directions, and the sweep that sets
    # them.
    adapt_from, adapt_at = settings.warmup // 3, (2 * settings.warmup) // 3
    warm_hyp = []

    def output(final=False):
        stack = lambda v: np.stack(v, axis=1)  # noqa: E731
        now = time.perf_counter()
        sampling = now - marks["warmup"] if marks["warmup"] else 0.0
        warm = (marks["warmup"] or now) - t_first
        done = len(trace[traced[0]])
        extra = {}
        if preds["pred_loc"]:
            extra = {k: stack(v) for k, v in preds.items()} | {
                "pred_y": np.asarray(d.pred["y"]),
                "pred_group": np.asarray(d.pred["group"]),
            }
        return {
            "trace": {k: stack(v) for k, v in trace.items()},
            "kept": {k: stack(v) for k, v in kept.items()} | extra,
            "seconds": {
                "setup": setup_seconds,
                "compile": compile_seconds,
                "warmup": warm,
                "sampling": sampling,
            },
            "result": {
                "gibbs": {
                    "sweeps": settings.warmup + done,
                    "seconds_per_sweep": (now - t_first)
                    / max(1, settings.warmup + done),
                    "hyp_dirs": np.asarray(st["hyp_dirs"][0]).tolist(),
                }
            },
        }

    def scalars(st):
        hyp = np.exp(np.asarray(st["hyp"]))
        return (
            f"nu {np.asarray(st['nu'])[:4].round(3)}, "
            f"amp {np.asarray(st['amp'])[:2].round(3).tolist()}, "
            f"bld_sd {np.asarray(st['bld_sd'])[:2].round(4).tolist()}, "
            f"unit_sd {hyp[:4, 0].round(4).tolist()}, "
            f"drift_sd {hyp[:4, 1].round(4).tolist()}, "
            f"drift_tau {hyp[:4, 2].round(3).tolist()}, "
        ) + "".join(
            f"{g['name']} sd {np.exp(np.asarray(st['ar_par'])[:4, k, 0]).round(4).tolist()} "
            f"rho {(1 / (1 + np.exp(-np.asarray(st['ar_par'])[:4, k, 1]))).round(3).tolist()}, "
            for k, g in enumerate(groups or ())
        )

    compile_seconds = 0.0
    t_first = time.perf_counter()
    for i in range(total):
        key, sub = jax.random.split(key)
        st, out = sweep(jax.random.split(sub, settings.chains), st)
        if i == 0:
            jax.block_until_ready(st)
            compile_seconds = time.perf_counter() - t_first
            t_first = time.perf_counter()
            log(f"first sweep (compile) {compile_seconds:.1f}s")
        if adapt_from <= i < adapt_at:
            warm_hyp.append(np.asarray(st["hyp"]))
        if i == adapt_at - 1 and len(warm_hyp) >= 8:
            dirs = adapted_dirs(np.stack(warm_hyp, axis=1))
            st = st | {
                "hyp_dirs": jnp.broadcast_to(jnp.asarray(dirs), st["hyp_dirs"].shape)
            }
            log(
                f"unit scales' slice directions set at sweep {i + 1}: {dirs.round(5).tolist()}"
            )
        if i == settings.warmup - 1 or (settings.warmup == 0 and i == 0):
            jax.block_until_ready(st)
            marks["warmup"] = time.perf_counter()
        if i >= settings.warmup:
            j = i - settings.warmup
            full = out | {k: st[k] for k in scale_names}
            for k in traced:
                trace[k].append(np.asarray(full[k]))
            if (j + 1) % settings.keep_every == 0:
                for k in kept_names:
                    kept[k].append(np.asarray(full[k]))
                if has_pred:
                    loc, s, _ = predict(st)
                    preds["pred_loc"].append(np.asarray(loc))
                    preds["pred_unit_sd"].append(np.asarray(s))
            if (j + 1) % per == 0:
                log(
                    f"draws {j + 1}/{settings.draws}: "
                    + scalars(st)
                    + f"tau {np.asarray(st['tau'])[:4].round(5)}, "
                    + (
                        f"gp_amp {np.asarray(st['gp_amp'])[:2].round(3).tolist()}, "
                        f"gp_ls {np.asarray(st['gp_ls'])[:2].round(3).tolist()}, "
                        if gp
                        else ""
                    )
                    + f"{time.perf_counter() - t0:.0f}s"
                )
                if j + 1 < settings.draws and checkpoint is not None and kept["beta"]:
                    checkpoint(output())
        elif (i + 1) % max(1, settings.warmup // 5) == 0:
            log(
                f"warmup {i + 1}/{settings.warmup}: "
                + scalars(st)
                + f"{time.perf_counter() - t0:.0f}s"
            )
    out = output(final=True)
    log(
        f"sampling {out['seconds']['sampling']:.0f}s, "
        f"{out['result']['gibbs']['seconds_per_sweep']:.3f}s a sweep of {settings.chains} chains"
    )
    return out


def diagnostics(trace: dict, names) -> dict:
    """The kitchen sink's convergence table, with the three unit scales."""
    from .run import ESS_GATE, RHAT_GATE, ess, split_rhat

    out = building_zones_kitchen_sink.diagnostics(trace, names)
    rows = out["per_quantity"]
    for k in [*HYP, *(k for k in trace if k.endswith(("_ar_sd", "_ar_rho")))]:
        x = np.asarray(trace[k])
        if np.ptp(x) > 0:
            rows[k] = {"rhat": split_rhat(x), "ess": ess(x)}
    worst = max(rows, key=lambda n: rows[n]["rhat"])
    least = min(rows, key=lambda n: rows[n]["ess"])
    return out | {
        "max_rhat": rows[worst]["rhat"],
        "max_rhat_name": worst,
        "min_ess": rows[least]["ess"],
        "min_ess_name": least,
        "passes": rows[worst]["rhat"] <= RHAT_GATE and rows[least]["ess"] > ESS_GATE,
    }


def summarize(kept: dict, names) -> dict:
    """The kitchen sink's summary, with the unit scales."""
    out = building_zones_kitchen_sink.summarize(kept, names)
    out["unit"] = {k: two_zone._q(np.asarray(kept[k])) for k in HYP}
    out["local"] = {
        k: two_zone._q(np.asarray(kept[k]))
        for k in kept
        if k.endswith(("_ar_sd", "_ar_rho"))
    }
    return out


def run_record(d: Design, groups=()) -> dict:
    """The kitchen sink's record, with the unit term's settings and those of the local-drift
    terms named in `groups`."""
    local = {
        g["name"]: {
            "groups": g["size"],
            "steps_per_year": g["per_year"],
            "sd_prior": f"HalfNormal({g['sd_prior']})",
            "rho_prior": "Uniform(0, 1)",
        }
        for g in groups_of(d, groups)
    }
    return (
        building_zones_kitchen_sink.run_record(d)
        | ({"local": local} if local else {})
        | {
            "unit": {
                "key": "building and unit_id; a row with no unit_id is its own unit",
                "units": int(d.units),
                "unit_sd_prior": f"HalfNormal({UNIT_SD_PRIOR})",
                "drift_sd_prior": f"HalfNormal({DRIFT_SD_PRIOR})",
                "drift_tau_log_prior": list(TAU_LOG_PRIOR),
                "kept": "pred_loc and pred_unit_sd for the rows outside the training rows",
            }
        }
    )


def main_run(argv, name=NAME, sample=None, spec=None) -> None:
    """`rentfrontier.run --model drift`: fit on the split's training rows and save the run.
    The modules that add local-drift terms pass their own `name`, `sample` and `spec`."""
    parser = b0.run_parser()
    parser.prog = f"rentfrontier.run --model {name}"
    parser.set_defaults(model=name)
    parser.add_argument("--site-block", type=int)
    building_zones_floor_asof.SPLIT = parser.parse_known_args(argv)[0].split
    b0.main_run(
        argv,
        parser=parser,
        name=name,
        settings_cls=Settings,
        sample=sample or run,
        line="baseline",
        spec=spec or sys.modules[__name__],
    )
