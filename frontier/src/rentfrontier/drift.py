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
2. The scales (ss, sd, tau), each group's sigma and nu together, with u and the buildings'
   levels integrated out (`update_scales`). The marginal likelihood of each unit's rows comes
   from a Kalman filter on the state (s, d), and each building's level adds a term from the
   row sums of W. nu moves with the mixing scales lam carried along: each row keeps its
   standardized log lam, so nu is not pinned by the lam drawn at its old value. I slice
   sample along eight directions, which start as the axes. The run sets them twice in the
   warmup: first from the draws' covariance, then from the curvature of this step's own
   density at the chains' states (`scales_curvature`, `conditional_dirs`), which is
   narrower than the posterior and tilted against it.
3. Each zone's building spread b_z, then every building's level eta, with u integrated out,
   at the new scales.
4. u given theta and eta, by Matheron's rule: a draw from the prior, corrected by
   K W (e - prior draw - noise draw), where e = y - mean without u.
5. nu, sigma and lam from the residuals e - u (`building_zones_gibbs`'s noise step). With
   step 2 this draws nu and sigma twice a sweep, once free of u and the levels and once
   free of lam.
6. tau of the walk, the zone amplitudes and waves, and the floor curves' Gaussian process
   scales, as in `building_zones_gibbs`.

Step 2 integrates out u and the levels, and steps 3 and 4 draw both again before any step
reads them. So the sweep leaves the posterior unchanged. The first fits of 2026-11-10 drew
sigma given u, the unit scales given the levels and nu given u only, and missed the gate
on those scales: the chains agreed and crept.

Predictions. A unit's level at a new ad depends on its training ads, so the run predicts
every row outside the training rows (the held-out ads of a split, or the ads on the market
now) at each kept draw. Given theta, eta and the scales, u at the new ad's date is
Normal(k' W e, k0 - k' W k), with k the covariance between the new ad and the unit's training
ads and k0 = ss^2 + sd^2. A unit with no training ad gets mean 0 and sd sqrt(k0). The run
keeps, for every such row and kept draw, `pred_loc` = x beta + L(t) + eta + the mean of u, and
`pred_unit_sd`, the sd of u. `rentfrontier.drift_score` turns them into predictive densities,
quantiles and deal scores without rebuilding the design.

Student-t unit levels. `make_sampler`'s `unit_t` gives each unit a mixing scale kap_k, so
that s_k ~ Normal(0, ss^2 / kap_k), and samples the units' degrees of freedom
(`rentfrontier.drift_building_unitt` explains the scheme). Steps 1 to 3 hold the kap as
they are, step 4 draws each unit's lasting level s_k jointly with u (`draw_us`), and a
step after it draws the degrees of freedom, the kap and a common rescaling of ss and the
kap given those levels (`update_unit_t`). With `unit_dof_fixed` the degrees of freedom stay
at a set value, and that step draws only the kap and the rescaling.

Local drift. With units accounted for, fit 4's residuals still move together inside a building
over a few months (two ads of different units of one building within three months correlate
at 0.26, and the correlation is gone a few years apart), and a little inside a neighbourhood
in its last two years (docs/notes/drift-2026-11-10.md). `make_sampler` and `run` take `groups`, a list of
local-drift terms from `groups_of`, each one more term in the row's mean:

    a_g(m) = rho a_g(m - 1) + Normal(0, s^2 (1 - rho^2)),   a_g(first) ~ Normal(0, s^2)

for group g (a building, or a neighbourhood) and step m (a quarter). `drift` itself runs with
none; `rentfrontier.drift_building` adds the buildings' and `rentfrontier.drift_local` the
buildings' and the neighbourhoods'. Steps 1 and 2 run on y less the terms' current paths
(step 2 with the collapsed term's paths integrated out as well, through `level_loglik`).

The buildings' term is collapsed (`update_cells`). A building's state is its level eta and
its path at its cells, the steps in which it has a row. With u integrated out the rows of a
building are jointly Gaussian in that state, with precision B' W B for the units' precisions
W, so step 3 becomes: the zones' spreads b and the path's (log s, logit rho) by slice
updates on the buildings' marginal likelihood with the levels, the paths and u all
integrated out (one dense Cholesky factor of at most 1 + cells a building), then every
building's level and path in one draw with u integrated out, then the path's steps between
the cells. Drawing the paths given u instead, as the first fits of 2026-11-10 did, left
every chain creeping (R-hat 1.6): the rows pin a path far more tightly given u than they do
once u is free to follow.

Before the paths are drawn, the coefficients of the columns named by `Settings.slow_columns`
(the `bld:` columns) are drawn once more with the paths integrated out as well
(`update_slow`). Step 1 draws theta given the paths, and a building amenity code changes
within a building over time, so given the paths its coefficient is pinned.

A term that is not collapsed (the neighbourhoods') is drawn after step 4 given theta, eta, u
and the other terms: (log s, logit rho) by a slice update of each on the Kalman filter's
marginal likelihood of every group's cell sums, with the paths integrated out, then the
paths by backward sampling. A prediction adds each term's path at the row's group and step,
which the filter carries past the group's last ad by the same recursion.

    python -m rentfrontier.run --model drift --split latest --name NAME
"""

from __future__ import annotations

import argparse
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
    drift_scales,
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
# Bath steps this design leaves out, as `building_zones_attrs.DROPPED_STEPS` leaves out
# `bed=2:full>=4`. The steps are cumulative, so a studio with three full baths then takes the
# premium of one with two, and a 1 bedroom with four that of one with three. On the latest
# split's training rows the two steps are set by 37 ads of 34 units and by 26 ads of 26
# units. The first drew a premium of 52% from ads that read like larger apartments entered
# with no bedrooms (median rent $6,095 against a studio's $2,500), and it missed the gate in
# every fit of 2026-11-10: with so few units behind it, the coefficient and whether its rows
# count as outliers trade places slowly.
DROPPED_STEPS = ("bed=0:full>=3", "bed=1:full>=4")
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
# The slice intervals' lengths: along each of (log ss, log sd, log tau) and each group's
# log sigma until the warmup sets the directions, and for a local-drift term's (log sd,
# logit rho).
HYP_WIDTH = 0.3
SIGMA_WIDTH = 0.1
PHASE_WIDTH = 0.1
NU_WIDTH = 0.02
AR_WIDTHS = (0.5, 1.0)
# The collapsed building term (`cell_layout`): a building's cells are padded to these sizes,
# the slice interval's length for each zone's log spread, the lengths along (log sd, logit
# rho) until the warmup sets the directions, and the weight that pins a path at its drawn
# cells while the steps between them are filled in.
CELL_PADS = (1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 44, 60, 80, 108, 144)
SPREAD_WIDTH = 0.05
# The step of `scales_curvature`'s finite differences, in columns of the slice directions.
CURV_STEP = 0.05
CELL_WIDTHS = (0.1, 0.3)
PIN = 1e14
# What the sweep's key is folded with for the buildings' mixing scales (`Settings.level_dof`).
KAP_KEY = 97
# Units are padded to these sizes, so that each size's units stack into one array.
PADS = (2, 3, 4, 5, 6, 8, 10, 14, 22)
YEAR_WEEKS = 365.25 / 7
# The Normal prior's sd on the log of each noise phase's factor (`Design.phase`): two sds
# span factors from 0.55 to 1.8.
PHASE_PRIOR = 0.3
# The traced unit scales, in the order of the state's `hyp`.
HYP = ("unit_sd", "drift_sd", "drift_tau")
# The units' Student-t lasting levels (`make_sampler`'s `unit_t`): the Gamma(shape, rate)
# prior on their degrees of freedom, the slice interval's length along its log, and what
# the sweep's key is folded with for the step that draws them.
UNIT_DOF_PRIOR = (2.0, 0.1)
UNIT_DOF_WIDTH = 0.1
UNIT_T_KEY = 89
# The step that draws the units' mixing scales with u and the lasting levels integrated out
# (`make_sampler`'s `unit_kap_collapsed`): the slice interval's length along each log kap,
# and what the sweep's key is folded with for it.
UNIT_KAP_WIDTH = 2.0
UNIT_KAP_KEY = 83
# The noise step's update of the phases' factors with lam integrated out (`make_sampler`'s
# `phase_collapsed`): the slice interval's length along each log factor, and what the noise
# step's key is folded with for it.
PHASE_NOISE_WIDTH = 0.02
PHASE_KEY = 79
# The lasting level's slow reversion (`make_sampler`'s `unit_slow`): the Normal prior on
# the log of its time constant in years, the slice interval's starting length along that
# log, and the time constant the chains start near.
UNIT_TAU_LOG_PRIOR = (math.log(40.0), 1.0)
UNIT_TAU_WIDTH = 0.5
UNIT_TAU_START = 40.0


@dataclass(frozen=True)
class Settings:
    chains: int = 4
    warmup: int = 300
    draws: int = 1000
    keep_every: int = 5
    seed: int = 20261110
    # Buildings per block of the Schur complement's dense products.
    site_block: int = 4096
    # Rounds of draws between progress lines.
    chunks: int = 4
    # Write a checkpoint at each progress line but the last. A checkpoint computes the
    # diagnostics of every traced scalar and stacks the kept predictions: 110 to 230 s a
    # time on the full data, which a fit capped at an hour cannot spare three times.
    checkpoints: bool = False
    # Stop drawing once the sweeps after the first have taken this long, at the next kept
    # draw, and report the draws there are. Modal stops a fit's container at 75 minutes and
    # the project's rule is an hour a fit; outside the sweeps the pilots took 13 to 15
    # minutes (image, design, compile, output). None runs every draw asked for.
    budget_seconds: float | None = 2520.0
    # With a collapsed building term, the columns whose names start with one of these are
    # drawn a second time with the buildings' paths integrated out (`update_slow`).
    # `slow_within` above zero keeps only the columns with at least that share of their
    # variance within buildings: a path can only stand in for a column that moves inside a
    # building. The pilot that measured the step (p6b) redrew every named column, and
    # before the step `bld:elevator` and `bld:gym` took 6 to 8 sweeps a draw against 2 for
    # a lot's size, so the default keeps them all; the run logs each column's share.
    slow_columns: tuple[str, ...] = ("bld:",)
    slow_within: float = 0.0
    # Draw each zone's amplitude with the waves integrated out (`rentfrontier.amp_joint`).
    joint_amp: bool = True
    # The degrees of freedom of a Student-t prior on each building's level about its
    # neighbourhood's, in place of the normal one: level_s ~ Normal(F_s, b_z^2 / kap_s) with
    # kap_s ~ Gamma(dof / 2, rate dof / 2). None keeps the normal prior and the sweep as it
    # was. Under the normal prior a building 5 to 6 spreads from its neighbourhood moves its
    # zone's spread by its square over 2 b N, and the fits of 2026-11-10 missed the gate on
    # bld_sd[outer] through ten such buildings (docs/notes/drift-2026-11-10.md).
    level_dof: float | None = None
    # The name of a set of scales in `rentfrontier.drift_scales`. The sweep holds each scale
    # of the set at the set's value and draws everything else given them
    # (`make_sampler`'s `scales_fixed`). None has the sweep draw every scale.
    scales_fixed: str | None = None

    def to_dict(self):
        return dataclasses.asdict(self)


@dataclass
class Design(building_zones_kitchen_sink.Design):
    unit: np.ndarray = (
        None  # (rows,) the row's unit number, -1 for a unit with no training row
    )
    units: int = 0  # the number of units with a training row
    nbhd: np.ndarray = None  # (rows,) the row's neighbourhood number
    # (rows,) the row's noise phase, a place in `phases`, whose first phase is the
    # reference. With phases each row's noise scale is its group's sigma times its phase's
    # factor, and the reference phase's factor is 1. A design with no phases leaves both
    # empty, and its rows take their group's sigma alone.
    phase: np.ndarray = None
    phases: tuple = ()
    # With no map every phase but the reference has a free factor of its own. A map, a
    # (len(phases), free) array of 0s and 1s, makes a phase's factor the product of the
    # free factors its row marks, so that the phases can be the cells of two crossed
    # factor sets (`rentfrontier.drift_building_phase_year`). The reference's row is 0.
    phase_map: np.ndarray = None
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
    d = drop_columns(
        building_zones_kitchen_sink.design(frame, start, held=held, **kw), DROPPED_STEPS
    )
    unit, units = unit_index(frame, held)
    nbhd = nbhd_index(frame)
    return Design(
        **{f.name: getattr(d, f.name) for f in dataclasses.fields(d)},
        unit=unit,
        units=units,
        nbhd=nbhd.astype(np.int64),
    )


def drop_columns(d, names):
    """Design `d` without the columns in `names`."""
    on = [j for j, n in enumerate(d.names) if n not in names]
    return dataclasses.replace(
        d,
        x=d.x[:, on],
        names=[d.names[j] for j in on],
        count={n: c for n, c in d.count.items() if n not in names},
    )


def nbhd_index(frame: pd.DataFrame) -> np.ndarray:
    """Each row's neighbourhood number. Rows with no neighbourhood share one of their own:
    `factorize` would number them -1, and they would read the last neighbourhood's path."""
    hood = frame.neighbourhood.astype(object)
    return pd.factorize(hood.where(hood.notna(), "").astype(str), sort=True)[0]


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
            phase=None if d.phase is None else d.phase[other],
        )
    return dataclasses.replace(
        building_zones_kitchen_sink.subset(d, mask),
        unit=d.unit[mask],
        nbhd=None if d.nbhd is None else d.nbhd[mask],
        phase=None if d.phase is None else d.phase[mask],
        pred=pred,
    )


def groups_of(d: Design, which) -> list[dict]:
    """The local-drift terms named in `which` for training design `d` (see the module
    docstring): `building`, one process per building, and `nbhd`, one per neighbourhood, both
    in quarterly steps. Each dict holds the term's `name`, each training row's group `row`,
    each predicted row's group `pred`, the number of groups `size`, the steps a year
    `per_year`, the HalfNormal scale `sd_prior` of the process's sd and whether the sweep
    draws the term `collapsed` (the buildings' is).

    The buildings' steps were months in the first fits of 2026-11-10. Their rho came out at
    0.94 a month, a half-life near a year, so quarters lose little, and a building then has
    at most 52 cells in place of 155, which keeps the collapsed step's dense factors small."""
    pred = d.pred or {}
    out = []
    for name in which:
        if name == "building":
            row, prd = d.site, pred.get("site")
            size, per_year = len(site_zone(d)), 4
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
                collapsed=name == "building",
            )
        )
    return out


def slice_along(key, x, lp, logp, dirs, shrink=32):
    """A slice update of vector `x` along each column of `dirs` in turn, for a scalar log
    density `logp` with `lp` = logp(x). Returns the new x and its log density.

    Along a column the interval is one column long, placed at random around the current
    point, and it only shrinks. `b0.slice_vec` steps the interval out a fixed number of
    times on each side first, which narrows the draws when the slice is longer than the
    stepped-out interval. Placing a wide interval at random needs no stepping out and is
    exact at any width. The log density at each accepted point is carried to the next
    column, so a column costs one evaluation for each point it tries.

    The columns run in a `jax.lax.scan`, so the compiled sweep holds one copy of `logp`
    however many columns there are."""
    jax, jnp = b0._jax()

    def column(carry, kv):
        x, lp = carry
        kk, v = kv
        k1, k2, k3 = jax.random.split(kk, 3)
        level = lp - jax.random.exponential(k1)
        lo = -jax.random.uniform(k2)

        def cond(s):
            return (s[0] < shrink) & ~s[5]

        def body(s):
            i, lo, hi, t, lpt, _, key = s
            key, sub = jax.random.split(key)
            prop = lo + (hi - lo) * jax.random.uniform(sub)
            lpp = logp(x + prop * v)
            ok = lpp > level
            lo = jnp.where(~ok & (prop < 0), prop, lo)
            hi = jnp.where(~ok & (prop >= 0), prop, hi)
            return (
                i + 1,
                lo,
                hi,
                jnp.where(ok, prop, t),
                jnp.where(ok, lpp, lpt),
                ok,
                key,
            )

        start = (0, lo, lo + 1.0, jnp.zeros(()), lp, jnp.zeros((), bool), k3)
        _, _, _, t, lp, _, _ = jax.lax.while_loop(cond, body, start)
        return (x + t * v, lp), None

    keys = jax.random.split(key, dirs.shape[1])
    (x, lp), _ = jax.lax.scan(column, (x, jnp.asarray(lp)), (keys, jnp.asarray(dirs).T))
    return x, lp


def within_share(x: np.ndarray, site: np.ndarray) -> float:
    """The share of a column's variance that is within buildings (0 for a constant one)."""
    total = float(np.var(x))
    if total == 0:
        return 0.0
    count = np.bincount(site)
    mean = np.bincount(site, weights=x) / np.maximum(count, 1)
    return float(np.mean((x - mean[site]) ** 2)) / total


def cell_layout(site, step, pi, pj, size: int, steps: int, pads=CELL_PADS) -> dict:
    """The static index arrays of the collapsed building term, for rows sorted by building.

    A cell is a building in a step with at least one row. A building's state is its level
    followed by its path at its cells, in step order, and the buildings are stacked by their
    padded number of cells. `site` and `step` are the rows' building and step, `pi` and `pj`
    the units' pairs of rows (`unit_layout`), `size` the number of buildings with and
    without rows, and `steps` the number of steps of a path.

    Returns
    - `buckets`: one dict per padded size m, holding `sites` (buildings,), `gap` (buildings,
      m) the steps from the cell before (0 for a building's first cell and for a padded
      place), `cells` (buildings, m) each cell's place in the paths raveled as (buildings,
      steps), padded with one past the end, and `off_H`, `off_h` the bucket's first place in
      the two flat arrays below;
    - `H_d`, `H_o`: each row's and each pair's place in the buckets' (buildings, m, m) arrays
      raveled and laid end to end, of `size_H` entries;
    - `h`: each row's place in the buckets' (buildings, m) arrays laid end to end, of
      `size_h` entries;
    - `active`: (size * steps,) whether the building has a row in the step."""
    assert (np.diff(site) >= 0).all(), "the rows must be sorted by building"
    cells, cell_of_row = np.unique(site * steps + step, return_inverse=True)
    c_site, c_step = cells // steps, cells % steps
    sites, first, count = np.unique(c_site, return_index=True, return_counts=True)
    bld_of_cell = np.repeat(np.arange(len(sites)), count)
    pos_of_cell = np.arange(len(cells)) - first[bld_of_cell]
    pads = np.array(
        sorted(
            {p for p in pads if p < count.max(initial=1)} | {int(count.max(initial=1))}
        )
    )
    pad_of = pads[np.searchsorted(pads, count)]
    slot = np.zeros(len(sites), np.int64)
    off_H = np.zeros(len(sites), np.int64)
    off_h = np.zeros(len(sites), np.int64)
    buckets, size_H, size_h = [], 0, 0
    for m in pads:
        which = np.flatnonzero(pad_of == m)
        if not len(which):
            continue
        m = int(m)
        slot[which] = np.arange(len(which))
        off_H[which], off_h[which] = size_H, size_h
        sel = pad_of[bld_of_cell] == m
        at = (slot[bld_of_cell[sel]], pos_of_cell[sel])
        stp = np.zeros((len(which), m), np.int64)
        stp[at] = c_step[sel]
        real = np.zeros((len(which), m), bool)
        real[at] = True
        gap = np.zeros((len(which), m), np.int64)
        gap[:, 1:] = np.where(real[:, 1:], np.diff(stp, axis=1), 0)
        place = np.full((len(which), m), size * steps)
        place[at] = cells[sel]
        buckets.append(
            dict(sites=sites[which], gap=gap, cells=place, off_H=size_H, off_h=size_h)
        )
        size_H += len(which) * m * m
        size_h += len(which) * m
    b = bld_of_cell[cell_of_row]
    pos = pos_of_cell[cell_of_row]
    m = pad_of[b]
    base = off_H[b] + slot[b] * m * m
    active = np.zeros(size * steps, bool)
    active[cells] = True
    return dict(
        buckets=buckets,
        H_d=base + pos * m + pos,
        H_o=base[pi] + pos[pi] * m[pi] + pos[pj],
        h=off_h[b] + slot[b] * m + pos,
        size_H=size_H,
        size_h=size_h,
        active=active,
    )


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


# The scales a set of `rentfrontier.drift_scales` may hold, by the step of the sweep that
# draws them. A set holds all of a step's scales or none of them, since a step draws its
# scales together. `{term}` is the collapsed term's name.
HELD_STEPS = {
    "noise": ("nu", "sigma", *HYP),
    "cells": ("bld_sd", "{term}_ar_sd", "{term}_ar_rho"),
    "tau": ("tau",),
    "amp": ("amp",),
    "gp": ("gp_amp", "gp_ls"),
}


def held_steps(scales: dict | None, groups) -> frozenset:
    """The steps of `HELD_STEPS` whose scales `scales` holds. `groups` are the sampler's
    local-drift terms, and the first of them is the collapsed term when it is drawn
    collapsed."""
    if not scales:
        return frozenset()
    first = (groups or [{}])[0]
    term = first.get("name") if first.get("collapsed") else None
    steps, known = set(), set()
    for step, names in HELD_STEPS.items():
        names = [k.format(term=term) for k in names]
        known |= set(names)
        given = [k for k in names if k in scales]
        if given:
            assert len(given) == len(names), (
                f"the sweep draws {names} in one step, and the set holds only {given}"
            )
            assert step != "cells" or term, (
                "bld_sd is held with a collapsed term's scales"
            )
            steps.add(step)
    assert set(scales) <= (known | {"phase_scale"}), (
        f"not scales to hold: {sorted(set(scales) - (known | {'phase_scale'}))}"
    )
    return frozenset(steps)


def held_state(scales: dict | None, held: frozenset) -> dict:
    """The entries of the sampler's state at the held scales of `scales`: the unit scales
    as `hyp`, their logs, and the collapsed term's as the first row of `ar_par`, its log sd
    and logit rho."""
    out = {}
    if "noise" in held:
        out |= {
            "nu": scales["nu"],
            "sigma": scales["sigma"],
            "hyp": np.log([scales[k] for k in HYP]),
        }
        if "phase_scale" in scales:
            out["phase_scale"] = scales["phase_scale"]
    if "cells" in held:
        sd = next(v for k, v in scales.items() if k.endswith("_ar_sd"))
        rho = next(v for k, v in scales.items() if k.endswith("_ar_rho"))
        out |= {
            "bld_sd": scales["bld_sd"],
            "ar_par": np.array([math.log(sd), math.log(rho / (1 - rho))]),
        }
    for step in ("tau", "amp"):
        if step in held:
            out[step] = scales[step]
    if "gp" in held:
        out |= {"gp_amp": scales["gp_amp"], "gp_ls": scales["gp_ls"]}
    return out


def make_sampler(
    d: Design,
    priors: Priors,
    settings: Settings,
    gp=None,
    groups=None,
    unit_t: bool = False,
    unit_dof_fixed: float | None = None,
    unit_kap_collapsed: bool = False,
    row_dof_fixed: float | None = None,
    unit_slow: bool = False,
    phase_collapsed: bool = False,
    scales_fixed: dict | None = None,
    scalar_sigma: bool = False,
    walk_stride: int = 1,
    scale_passes: int = 1,
    scales_no_phase: bool = False,
    scales_phase_k: int | None = None,
    scales_phase_idx: tuple[int, ...] | None = None,
    slow_gps: bool = False,
    em_laplace: bool = False,
    em_warm: int = 0,
):
    """The jitted sweep, the initial state, the jitted prediction step and the sampler's
    parts for design `d`. The sweep, the initial state and the prediction step are vmapped
    over chains. See `building_zones_gibbs.make_sampler` for `gp` and `groups_of` for
    `groups`, the local-drift terms.

    `unit_t` gives each unit's lasting level a Student-t prior through a mixing scale of its
    own, s_k ~ Normal(0, ss^2 / kap_k) with kap_k ~ Gamma(nu_u / 2, rate nu_u / 2), and
    samples nu_u (`rentfrontier.drift_building_unitt`). Without it the sweep is unchanged.
    `unit_dof_fixed` holds nu_u at that value under `unit_t`: the sweep draws the kap and
    the orbit as before, skips nu_u's slice update and leaves log nu_u out of the scale
    step's coordinates (`rentfrontier.drift_building_phase_unitt`).
    `unit_kap_collapsed` draws the kap from their conditional with u and the lasting levels
    integrated out (`collapsed_kap`), in place of their Gamma conditional given the levels
    (`rentfrontier.drift_building_phase_unitk`).
    `row_dof_fixed` holds the rows' degrees of freedom nu at that value: the noise step
    skips nu's slice update, and the scale step leaves log nu out of its coordinates and
    holds lam's standardized logs at the fixed nu.
    `unit_slow` lets each unit's lasting level revert to 0 with a time constant `unit_tau`
    of years, so that its covariance between two ads is v_k exp(-|t_a - t_b| / unit_tau)
    with v_k = ss^2 / kap_k (`rentfrontier.drift_building_phase_unitkn_level_slow`). The
    scale step samples log unit_tau as its last coordinate, and the collapsed kap step
    reads each unit's density from the eigenvalues of its lasting correlation against the
    rest of its covariance (`kap_logp`). It needs `unit_kap_collapsed`.
    `phase_collapsed` has the noise step draw each free phase factor after sigma, given the
    rows' remainders and with lam integrated out, as it draws sigma
    (`rentfrontier.drift_building_phase_unitkn_level_phase`). Without it the scale step
    alone moves the factors, at the lam the state holds. It needs a design with phases and
    no phase map, so that each factor scales rows of its own.

    `scales_fixed` is a set of `rentfrontier.drift_scales`: a value for each scale of some
    of the sweep's scale steps (`HELD_STEPS`). The initial state takes those values in every
    chain, and the sweep skips the steps and draws the rest of the state given them. The
    lam, the buildings' mixing scales, the levels, the paths and u are still drawn. It
    needs normal unit levels (no `unit_t`) and a design with no lease phases.
    """
    assert unit_dof_fixed is None or unit_t, "unit_dof_fixed needs unit_t"
    assert unit_kap_collapsed or not unit_slow, "unit_slow needs unit_kap_collapsed"
    fixed_steps = held_steps(scales_fixed, groups)
    # Whether the sweep moves nu_u.
    dof_free = unit_t and unit_dof_fixed is None
    assert not (fixed_steps and (dof_free or unit_slow)), (
        "scales_fixed needs fixed or normal unit dof (not free unit_dof or unit_slow)"
    )
    assert unit_t or not unit_kap_collapsed, "unit_kap_collapsed needs unit_t"
    # Whether the sweep moves the rows' nu, and where the phases' factors start in the
    # scale step's coordinates.
    assert walk_stride >= 1, "walk_stride must be at least 1"
    assert scale_passes >= 1, "scale_passes must be at least 1"
    assert not scales_no_phase or phase_collapsed, (
        "scales_no_phase needs phase_collapsed so phase_scale is still sampled"
    )
    assert scales_phase_k is None or scales_phase_k >= 0, "scales_phase_k must be >= 0"
    assert scales_phase_k is None or phase_collapsed, (
        "scales_phase_k needs phase_collapsed so omitted phase_scale factors are still sampled"
    )
    assert scales_phase_idx is None or phase_collapsed, (
        "scales_phase_idx needs phase_collapsed so omitted phase_scale factors are still sampled"
    )
    nu_free = row_dof_fixed is None
    n_sigma = 1 if scalar_sigma else 4
    pf = 3 + n_sigma + nu_free
    # The kap drawn with u integrated out must come after every move of nu_u, which a free
    # nu_u's slice update in `update_unit_t` does not.
    assert not (dof_free and unit_kap_collapsed), (
        "unit_kap_collapsed needs unit_dof_fixed"
    )
    jax, jnp = b0._jax()
    seg = jax.ops.segment_sum
    alpha = d.names.index("alpha")
    others = np.array([j for j in range(len(d.names)) if j != alpha])
    pb = len(others)
    W1_full = d.weeks + 1
    W1 = W1_full if walk_stride == 1 else (d.weeks + walk_stride - 1) // walk_stride + 1
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
    gp_kernels = []
    for spec in gp or ():
        pos = np.searchsorted(others, [d.names.index(c) for c in spec["cols"]])
        prec_b[pos], lin_b[pos] = 0.0, 0.0
        gps.append((pos, np.asarray(spec["x"], float), spec["amp"], spec["ls"]))
        gp_kernels.append((spec.get("kernel", "rbf"), spec.get("nugget")))

    def _gp_cov(xk, ls, kernel, nugget):
        if kernel == "rbf":
            if nugget is None:
                return gp_cov(jnp, xk, ls)
            K = jnp.exp(-0.5 * (xk[:, None] - xk[None, :]) ** 2 / ls**2)
            k0 = jnp.exp(-0.5 * xk**2 / ls**2)
            return K - jnp.outer(k0, k0) + nugget * jnp.eye(xk.shape[0])
        if kernel == "matern32":
            r = jnp.sqrt(3.0) * jnp.abs(xk[:, None] - xk[None, :]) / ls
            K = (1.0 + r) * jnp.exp(-r)
            r0 = jnp.sqrt(3.0) * jnp.abs(xk) / ls
            k0 = (1.0 + r0) * jnp.exp(-r0)
            nug = 1e-4 if nugget is None else nugget
            return K - jnp.outer(k0, k0) + nug * jnp.eye(xk.shape[0])
        raise ValueError(f"unknown gp kernel: {kernel!r}")

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
    dof = settings.level_dof
    assert dof is None or dof > 0, "level_dof is a number of degrees of freedom"
    rows_per_site = site_rows(d)
    n = len(d.y)
    assert (d.unit >= 0).all(), "every training row needs a unit"
    # The noise phases (`Design.phase`). Every phase but the reference has a free factor,
    # or the columns of `Design.phase_map` are the free factors, and the scale step's x
    # ends with the factors' logs.
    pmap = None if d.phase is None else d.phase_map
    if pmap is not None:
        pmap = np.asarray(pmap, float)
        assert pmap.shape[0] == len(d.phases) and not pmap[0].any(), "phase_map rows"
    if d.phase is None:
        free = 0
    elif pmap is not None:
        free = pmap.shape[1]
    else:
        free = len(d.phases) - 1
    phased = free > 0
    if not phased:
        ph_idx_np = np.zeros(0, dtype=int)
    elif scales_phase_idx is not None:
        ph_idx_np = np.array(
            [int(j) for j in scales_phase_idx if 0 <= int(j) < free], dtype=int
        )
    elif scales_phase_k is not None:
        ph_idx_np = np.arange(min(free, int(scales_phase_k)), dtype=int)
    elif scales_no_phase:
        ph_idx_np = np.zeros(0, dtype=int)
    else:
        ph_idx_np = np.arange(free, dtype=int)
    k_ph = len(ph_idx_np)
    ph_idx_j = jnp.asarray(ph_idx_np)
    use_fisher_hmc = phased and (k_ph < free) and phase_collapsed and pmap is not None
    assert not phase_collapsed or phased, "phase_collapsed needs phases"
    if "noise" in fixed_steps and phased:
        assert scales_fixed is not None and "phase_scale" in scales_fixed, (
            "a held noise step leaves the lease phases' factors undrawn"
        )
        assert len(scales_fixed["phase_scale"]) == free, (
            f"scales_fixed phase_scale has {len(scales_fixed['phase_scale'])} "
            f"values, expected {free}"
        )
    pmap_j = None if pmap is None else jnp.asarray(pmap)
    pmap_binary = pmap is not None and bool(np.all((pmap == 0.0) | (pmap == 1.0)))
    # Precompute cell-level Gram matrix of [group_indicators, phase_map] for Fisher-preconditioned
    # joint HMC over (log_sigma, log_phase_factors) when `k_ph < free` (`scales_no_phase` / `scales_phase_k`).
    noise_gram_j = None
    if use_fisher_hmc:
        n_cells = len(d.phases)
        M_pm = np.asarray(pmap, float)
        g_idx = np.asarray(d.group, int)
        p_idx = np.asarray(d.phase, int)
        if scalar_sigma:
            c_cnt = np.bincount(p_idx, minlength=n_cells).astype(float)
            M_aug = np.column_stack([np.ones(n_cells), M_pm])
            gram = (M_aug.T * c_cnt) @ M_aug
        else:
            G_sig = np.zeros((4, 4), float)
            G_cross = np.zeros((4, free), float)
            for gk in range(4):
                c_gk = np.bincount(p_idx[g_idx == gk], minlength=n_cells).astype(float)
                G_sig[gk, gk] = c_gk.sum()
                G_cross[gk] = c_gk @ M_pm
            c_cnt = np.bincount(p_idx, minlength=n_cells).astype(float)
            G_pm = (M_pm.T * c_cnt) @ M_pm
            gram = np.block([[G_sig, G_cross], [G_cross.T, G_pm]])
        noise_gram_j = jnp.asarray(gram)

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
    ars, ar_cell, ar_pcell, col = [], [], [], None
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
        if g.get("collapsed"):
            # The collapsed step draws the buildings' levels with the paths, so its term is
            # the buildings' and comes first.
            assert not ars[:-1] and np.array_equal(g["row"], d.site), (
                "only the first term, grouped by building, can be collapsed"
            )
            col = cell_layout(site_sorted, step, lay["pi"], lay["pj"], S, T)
    # The collapsed term's slow columns, as places among theta's coefficients.
    held = set() if slow_gps else {int(k) for pos, *_ in gps for k in pos}
    named = {
        k: within_share(d.x[:, j], d.site)
        for k, j in enumerate(others)
        if col is not None
        and settings.slow_columns
        and d.names[j].startswith(settings.slow_columns)
        and k not in held
    }
    slow = np.array(
        [k for k, share in named.items() if share >= settings.slow_within], dtype=int
    )
    slow_shares = {d.names[others[k]]: share for k, share in named.items()}
    # Map any GP blocks wholly contained inside `slow` so `update_slow` includes their exact GP prior.
    slow_pos = {int(k): idx for idx, k in enumerate(slow)}
    slow_gp_blocks = []
    if slow_gps and len(slow):
        for gk, (pos, xk, _, _) in enumerate(gps):
            inside = [int(p) in slow_pos for p in pos]
            # A block only partly in `slow` would lose its GP prior in both steps.
            assert all(inside) or not any(inside), (
                f"GP block {gk} is only partly among the slow columns"
            )
            if all(inside):
                sub = np.array([slow_pos[int(p)] for p in pos], dtype=int)
                slow_gp_blocks.append((gk, sub, xk))
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
    if walk_stride == 1:
        wk_all, fr_all = d.week[order], d.frac[order]
        p_wk_arr = np.asarray(rows_to_predict["week"])
        p_fr_arr = np.asarray(rows_to_predict["frac"])
    else:
        pos_tr = (d.week[order] + d.frac[order]) / float(walk_stride)
        wk_all = np.minimum(np.floor(pos_tr).astype(np.int64), W1 - 2)
        fr_all = pos_tr - wk_all
        pos_pr = (
            np.asarray(rows_to_predict["week"], float)
            + np.asarray(rows_to_predict["frac"], float)
        ) / float(walk_stride)
        p_wk_arr = np.minimum(np.floor(pos_pr).astype(np.int64), W1 - 2)
        p_fr_arr = pos_pr - p_wk_arr
    # The rows' data goes to the jitted sweep as an argument: closed over, it would be
    # compiled in as constants. Each block's rows and columns of the design are gathered on
    # their own, so the host holds no sorted copy of the whole design.
    data = dict(
        xs=[jnp.asarray(d.x[np.ix_(order[r0:r1], others)]) for _, _, r0, r1 in blocks],
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
        p_wk=jnp.asarray(p_wk_arr),
        p_fr=jnp.asarray(p_fr_arr),
        ar_cell=[jnp.asarray(v) for v in ar_cell],
        ar_pcell=[jnp.asarray(v) for v in ar_pcell],
        cells={k: jnp.asarray(v) for k, v in (col or {}).items() if k != "buckets"}
        | {
            k: [jnp.asarray(b[k]) for b in (col or {}).get("buckets", ())]
            for k in ("sites", "gap", "cells")
        },
        p_one=tuple(jnp.asarray(v) for v in pred["one"]),
        p_buckets=[tuple(jnp.asarray(v) for v in b) for b in pred["buckets"]],
    )
    if phased:
        data["phase"] = jnp.asarray(d.phase[order])
    U = int(d.units)
    if unit_t:
        # Each training row's unit, each bucket's units and each row to predict's unit
        # (-1 for a unit with no training row).
        unit_sorted = d.unit[order]
        data["unit"] = jnp.asarray(unit_sorted)
        data["b_unit"] = [
            jnp.asarray(unit_sorted[b["idx"][:, 0]]) for b in lay["buckets"]
        ]
        data["p_unit"] = jnp.asarray(np.asarray(rows_to_predict["unit"], np.int64))
    n_pred = pred["rows"]
    active_j = jnp.asarray(active)
    zone_j = jnp.asarray(zone)
    which_j = jnp.asarray(which)
    sds_j = jnp.asarray(sds)
    prec_b, lin_b = jnp.asarray(prec_b), jnp.asarray(lin_b)
    # The walk's prior on (M, g): E (M, g) = diff(M) - walk_stride * g.
    E = np.zeros((W1 - 1, W1 + 1))
    E[np.arange(W1 - 1), np.arange(W1 - 1)] = -1
    E[np.arange(W1 - 1), np.arange(1, W1)] = 1
    E[:, W1] = -float(walk_stride)
    EtE = jnp.asarray(E.T @ E)
    if walk_stride > 1:
        g_pos = np.arange(W1_full, dtype=float) / float(walk_stride)
        g_wk = np.minimum(np.floor(g_pos).astype(np.int64), W1 - 2)
        g_fr = g_pos - g_wk
        full_wk_j = jnp.asarray(g_wk)
        full_fr_j = jnp.asarray(g_fr)
    else:
        full_wk_j = full_fr_j = None
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

    def row_sd(D, sigma, factor=None):
        """Each row's noise scale: its group's sigma, times its phase's factor in a design
        with phases. `factor` holds the factors of every phase but the reference."""
        sd = sigma[D["group"]]
        if not phased:
            return sd
        return sd * phase_factors(factor)[D["phase"]]

    def phase_factors(factor):
        """Every phase's factor, the reference's 1 first, from the free factors."""
        if pmap_j is None:
            return jnp.concatenate([jnp.ones(1), factor])
        return jnp.exp(pmap_j @ jnp.log(factor))

    def weights(D, st):
        """Each row's weight c_i = lam_i / s_i^2, with s_i the row's noise scale."""
        return st["lam"] / row_sd(D, st["sigma"], st.get("phase_scale")) ** 2

    def site_var(bsd, kap=None):
        """Each building's prior variance of its level: its zone's spread squared, over the
        building's mixing scale `kap` under the Student-t prior (`Settings.level_dof`)."""
        b2 = bsd[zone_j] ** 2
        return b2 if kap is None else b2 / kap

    def scales(hyp):
        ss, sd, tau = jnp.exp(hyp[0]), jnp.exp(hyp[1]), jnp.exp(hyp[2])
        return ss, sd, tau

    def kernel(hyp, ta, tb, vs=None):
        """Cov(u(ta), u(tb)) for two ads of one unit. `vs` is the unit's variance of its
        lasting level under `unit_t`, ss^2 without it. Under `unit_slow` hyp carries log
        unit_tau fourth (`unit_hyp`), and the lasting part reverts with it."""
        ss, sd, tau = scales(hyp)
        lasting = ss**2 if vs is None else vs
        if unit_slow:
            lasting = lasting * jnp.exp(-jnp.abs(ta - tb) / jnp.exp(hyp[3]))
        return lasting + sd**2 * jnp.exp(-jnp.abs(ta - tb) / tau)

    def unit_hyp(st):
        """The state's unit scales as the unit functions read them: `hyp`, and under
        `unit_slow` log unit_tau after it."""
        if not unit_slow:
            return st["hyp"]
        return jnp.concatenate([st["hyp"], jnp.log(st["unit_tau"])[None]])

    def ou_factor(tb, tau):
        """The lower Cholesky factor of the OU correlation exp(-|t_a - t_b| / tau) at each
        bucket's dates tb, exp(-(t_a - t_b) / tau) sqrt(1 - phi_b^2) for a >= b."""
        gap = jnp.concatenate(
            [jnp.zeros((tb.shape[0], 1)), jnp.diff(tb, axis=1)], axis=1
        )
        s_b = jnp.sqrt(-jnp.expm1(-2 * gap / tau)).at[:, 0].set(1.0)
        return jnp.tril(
            jnp.exp(-jnp.abs(tb[:, :, None] - tb[:, None, :]) / tau) * s_b[:, None, :]
        )

    def lasting(D, hyp, ukap):
        """Under `unit_t`, the variance ss^2 / kap_k of the lasting level of each training
        row's unit, and of each bucket's units."""
        v = scales(hyp)[0] ** 2 / ukap
        return v[D["unit"]], [v[b] for b in D["b_unit"]]

    def unit_W(D, hyp, c, ukap=None):
        """The units' precisions W = (D^-1 + K)^-1 at weights c: `w1`, the scalar of each
        row taken as a unit of one row (read only for single rows), and one (units, n, n)
        stack per bucket. A padded place has weight 0, so its row and column of W are 0.
        `ukap` holds the units' mixing scales under `unit_t`."""
        ss, sd, _ = scales(hyp)
        if ukap is None:
            w1 = c / (1 + c * (ss**2 + sd**2))
            vb = [None] * len(D["b_idx"])
        else:
            vr, vb = lasting(D, hyp, ukap)
            w1 = c / (1 + c * (vr + sd**2))
        Wb = []
        for idx, mask, tb, v in zip(D["b_idx"], D["b_mask"], D["b_t"], vb):
            sq = jnp.sqrt(jnp.where(mask, c[idx], 0.0))
            Kb = kernel(
                hyp,
                tb[:, :, None],
                tb[:, None, :],
                None if v is None else v[:, None, None],
            )
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
        bsd2 = site_var(st["bld_sd"], st.get("kap"))
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
            Lk = jnp.linalg.cholesky(_gp_cov(xk, st["gp_ls"][k], *gp_kernels[k]))
            Ki = jax.scipy.linalg.cho_solve((Lk, True), jnp.eye(len(pos)))
            A = A.at[np.ix_(pos, pos)].add(Ki / st["gp_amp"][k] ** 2)
        A = A.at[pb, pb].add(1 / s_a**2)
        h = h.at[pb].add(m_a / s_a**2)
        A = A.at[pb : i_g + 1, pb : i_g + 1].add(
            EtE / (float(walk_stride) * st["tau"] ** 2)
        )
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
            b2 = site_var(jnp.exp(lb), st.get("kap"))
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

    def draw_us(D, key, hyp, c, w1, Wb, e, ukap):
        """Under `unit_t`: u at every row and each unit's lasting level s_k, jointly given
        the rows' remainders e, by Matheron's rule. The step draws the lasting level, the
        drift and the noise from their prior, then corrects u by K W r and s_k by v_k 1' W r
        over the unit's rows, with r = e - (the prior draws), since Cov(s_k, u(t)) = v_k = ss^2 /
        kap_k at every ad. A single row takes the same rule with W = w1."""
        _, sd, tau = scales(hyp)
        vr, vb = lasting(D, hyp, ukap)
        keys = jax.random.split(key, 1 + len(Wb))
        k1, k2, k3 = jax.random.split(keys[0], 3)
        s0 = jnp.sqrt(vr) * jax.random.normal(k1, (n,))
        d0 = sd * jax.random.normal(k2, (n,))
        res = e - s0 - d0 - jax.random.normal(k3, (n,)) / jnp.sqrt(c)
        one = D["single"]
        u = jnp.where(one, s0 + d0 + (vr + sd**2) * w1 * res, 0.0)
        # A single row's unit is the row's alone, so the segment sum places its s.
        s_unit = seg(jnp.where(one, s0 + vr * w1 * res, 0.0), D["unit"], num_segments=U)
        for kk, W, idx, mask, tb, v, bu in zip(
            keys[1:], Wb, D["b_idx"], D["b_mask"], D["b_t"], vb, D["b_unit"]
        ):
            B, m = idx.shape
            k1, k2, k3 = jax.random.split(kk, 3)
            gap = jnp.concatenate([jnp.zeros((B, 1)), jnp.diff(tb, axis=1)], axis=1)
            s_b = jnp.sqrt(-jnp.expm1(-2 * gap / tau)).at[:, 0].set(1.0)
            Lou = jnp.tril(
                jnp.exp(-jnp.abs(tb[:, :, None] - tb[:, None, :]) / tau)
                * s_b[:, None, :]
            )
            if unit_slow:
                # The lasting level's prior draw follows its own OU path.
                a0 = jnp.sqrt(v)[:, None] * jnp.einsum(
                    "bij,bj->bi",
                    ou_factor(tb, jnp.exp(hyp[3])),
                    jax.random.normal(k1, (B, m)),
                )
            else:
                a0 = jnp.sqrt(v) * jax.random.normal(k1, (B,))
            u0 = (a0 if unit_slow else a0[:, None]) + sd * jnp.einsum(
                "bij,bj->bi", Lou, jax.random.normal(k2, (B, m))
            )
            cb = jnp.where(mask, c[idx], 1.0)
            eps = jax.random.normal(k3, (B, m)) / jnp.sqrt(cb)
            res = jnp.where(mask, e[idx] - u0 - eps, 0.0)
            Wr = jnp.einsum("bij,bj->bi", W, res)
            Kb = kernel(hyp, tb[:, :, None], tb[:, None, :], v[:, None, None])
            ub = u0 + jnp.einsum("bij,bj->bi", Kb, Wr)
            if not unit_slow:
                # Under `unit_slow` the lasting level moves, and the step that would read
                # s_k (`update_unit_t` with nu_u free or the kap given s) is not taken.
                s_unit = s_unit.at[bu].add(a0 + v * jnp.sum(Wr, axis=1))
            u = (
                u
                + seg(
                    jnp.where(mask, ub, 0.0).ravel(),
                    jnp.where(mask, idx, n).ravel(),
                    num_segments=n + 1,
                )[:n]
            )
        return u, s_unit

    def update_unit_t(key, st, s, hyp, kap=None):
        """Under `unit_t`, given the units' lasting levels s from `draw_us`:

        1. nu_u by a slice update on the Student-t density of s with scale ss, the mixing
           scales integrated out, or the state's nu_u under `unit_dof_fixed`;
        2. every unit's kap_k from its Gamma conditional, ((nu_u + 1) / 2, rate
           (nu_u + s_k^2 / ss^2) / 2);
        3. ss and every kap_k together along the orbit ss -> g ss, kap_k -> g^2 kap_k,
           which leaves each v_k = ss^2 / kap_k and so the rows' density as they are. On
           the orbit g^2 is Gamma((1 + nu_u U) / 2, rate ss^2 / (2 UNIT_SD_PRIOR^2) +
           nu_u sum(kap) / 2), from ss's HalfNormal prior and the kap's Gamma priors in log
           coordinates, where the orbit is a translation. Without this step ss and the
           mixing scales trade their common factor only through the scale step's single
           draw of ss a sweep;
        4. a mixing scale from the prior for each row to predict, which a row of a unit with
           no training row reads (`predict`).

        Each draw is from a conditional of the posterior, so each leaves it unchanged.
        Given `kap`, already drawn by `collapsed_kap`, the step skips 2 and takes the orbit
        from them. Returns nu_u, the units' kap, hyp with its new log ss, and the rows'
        prior kap."""
        k1, k2, k3, k4 = jax.random.split(key, 4)
        ss = scales(hyp)[0]
        a, b = UNIT_DOF_PRIOR

        def logp(lnu):
            nu = jnp.exp(lnu[0])
            return (jnp.sum(b0.t_logpdf(s, nu, ss)) + a * lnu[0] - b * nu)[None]

        if dof_free:
            lnu = b0.slice_vec(k1, jnp.log(st["unit_dof"])[None], logp, UNIT_DOF_WIDTH)
            nu = jnp.exp(lnu[0])
        else:
            nu = st["unit_dof"]
        if kap is None:
            kap = jax.random.gamma(k2, (nu + 1) / 2, (U,)) / ((nu + (s / ss) ** 2) / 2)
        pred_kap = jax.random.gamma(k4, nu / 2, (n_pred,)) / (nu / 2)
        if "noise" in fixed_steps:
            return nu, kap, hyp, pred_kap
        g2 = jax.random.gamma(k3, (1 + nu * U) / 2) / (
            ss**2 / (2 * UNIT_SD_PRIOR**2) + nu * jnp.sum(kap) / 2
        )
        return nu, kap * g2, hyp.at[0].add(0.5 * jnp.log(g2)), pred_kap

    def collapsed_kap(D, key, hyp, nu, ukap, w1, Wb, e, c=None):
        """Under `unit_t`, every unit's mixing scale kap_k from its conditional given the
        rows' remainders e, with u and the lasting level s_k integrated out: a slice update
        of each log kap_k on `kap_logp`, the units being independent given e. `unit_slow`
        needs the rows' weights c."""
        logp = kap_logp(D, hyp, nu, ukap, w1, Wb, e, c)
        return jnp.exp(b0.slice_vec(key, jnp.log(ukap), logp, UNIT_KAP_WIDTH))

    def kap_logp(D, hyp, nu, ukap, w1, Wb, e, c=None):
        """The log density of every unit's log kap_k given e, with u and s_k integrated out,
        as a function of the vector of log kap, up to a constant for each unit. `w1` and
        `Wb` are `unit_W`'s at the state's `ukap`.

        With v = ss^2 / kap_k and A the unit's precision W at v = 0, the unit's rows have
        log density -log(1 + v a) / 2 + v b^2 / (2 (1 + v a)) in v, up to a constant, with
        a = 1' A 1 and b = 1' A e (Sherman-Morrison). W at the state's kap (`unit_W`) gives
        a0 = 1' W 1 = a / (1 + v0 a) and b0 = 1' W e = b / (1 + v0 a), so a and b follow
        from it with no new inverse. The Gamma(nu / 2, rate nu / 2) prior and the Jacobian
        of log kap add nu l / 2 - nu e^l / 2 at l = log kap.

        Under `unit_slow` the lasting part of the unit's covariance is v R, with R the OU
        correlation at unit_tau, and the rest is M, the drift's covariance plus the rows'
        noise 1 / c. With M = L L' and L^-1 R L^-T = Q diag(g) Q', the rows have log
        density -sum_i log(1 + v g_i) / 2 - sum_i z_i^2 / (2 (1 + v g_i)) in v, up to a
        constant, with z = Q' L^-1 e. The step factors each unit once a sweep, and every
        slice evaluation is then a sum over the unit's rows."""
        if unit_slow:
            return kap_logp_slow(D, hyp, nu, c, e)
        ss2 = scales(hyp)[0] ** 2
        one = D["single"]
        a0 = seg(jnp.where(one, w1, 0.0), D["unit"], num_segments=U)
        b0_ = seg(jnp.where(one, w1 * e, 0.0), D["unit"], num_segments=U)
        for W, idx, mask, bu in zip(Wb, D["b_idx"], D["b_mask"], D["b_unit"]):
            eb = jnp.where(mask, e[idx], 0.0)
            a0 = a0.at[bu].add(jnp.sum(W, axis=(1, 2)))
            b0_ = b0_.at[bu].add(jnp.einsum("bij,bj->b", W, eb))
        v0 = ss2 / ukap
        a = a0 / (1 - v0 * a0)
        b = b0_ * (1 + v0 * a)

        def logp(lk):
            v = ss2 * jnp.exp(-lk)
            return (
                nu * lk / 2
                - nu * jnp.exp(lk) / 2
                - 0.5 * jnp.log1p(v * a)
                + 0.5 * v * b * b / (1 + v * a)
            )

        return logp

    def kap_logp_slow(D, hyp, nu, c, e):
        """`kap_logp` under `unit_slow`."""
        ss, sd, tau = scales(hyp)
        ss2, ts = ss**2, jnp.exp(hyp[3])
        one = D["single"]
        # A single row: M = sd^2 + 1 / c and R = 1.
        m1 = sd**2 + 1 / c
        g = [seg(jnp.where(one, 1 / m1, 0.0), D["unit"], num_segments=U)[:, None]]
        z2 = [seg(jnp.where(one, e * e / m1, 0.0), D["unit"], num_segments=U)[:, None]]
        at = [None]
        for idx, mask, tb, bu in zip(D["b_idx"], D["b_mask"], D["b_t"], D["b_unit"]):
            m = idx.shape[1]
            both = mask[:, :, None] & mask[:, None, :]
            dt = jnp.abs(tb[:, :, None] - tb[:, None, :])
            cb = jnp.where(mask, c[idx], 1.0)
            # Padded places take M's identity row and R's zero row, so they add nothing.
            M = (
                jnp.where(both, sd**2 * jnp.exp(-dt / tau), 0.0)
                + jnp.eye(m) / cb[:, None, :]
            )
            R = jnp.where(both, jnp.exp(-dt / ts), 0.0)
            L = jnp.linalg.cholesky(M)
            tri = jax.lax.linalg.triangular_solve
            X = tri(L, R, left_side=True, lower=True)
            A = tri(L, jnp.swapaxes(X, 1, 2), left_side=True, lower=True)
            gb, Q = jnp.linalg.eigh(0.5 * (A + jnp.swapaxes(A, 1, 2)))
            y = tri(
                L, jnp.where(mask, e[idx], 0.0)[:, :, None], left_side=True, lower=True
            )
            zb = jnp.einsum("bij,bi->bj", Q, y[:, :, 0])
            g.append(jnp.maximum(gb, 0.0))
            z2.append(zb * zb)
            at.append(bu)

        def logp(lk):
            v = ss2 * jnp.exp(-lk)
            out = nu * lk / 2 - nu * jnp.exp(lk) / 2
            for gg, zz, bu in zip(g, z2, at):
                vb = v[:, None] if bu is None else v[bu][:, None]
                f = 1 + vb * gg
                term = -0.5 * jnp.sum(jnp.log(f) + zz / f, axis=1)
                out = out + term if bu is None else out.at[bu].add(term)
            return out

        return logp

    def unit_loglik(D, hyp, c, e, ukap=None):
        """The log marginal likelihood of the rows' remainders e with u integrated out, up
        to a constant in (ss, sd, tau): a Kalman filter on each unit's state (s, d).
        `ukap` holds the units' mixing scales under `unit_t`."""
        ss, sd, tau = scales(hyp)
        if ukap is None:
            k0 = ss**2 + sd**2
            vb = [None] * len(D["b_idx"])
        else:
            vr, vb = lasting(D, hyp, ukap)
            k0 = vr + sd**2
        f1 = 1 + c * k0
        ll = jnp.sum(jnp.where(D["single"], -0.5 * (jnp.log(f1) + c * e * e / f1), 0.0))
        for idx, mask, tb, v in zip(D["b_idx"], D["b_mask"], D["b_t"], vb):
            B, m = idx.shape
            cb = jnp.where(mask, c[idx], 1.0)
            eb = e[idx]
            m1 = jnp.zeros(B)
            m2 = jnp.zeros(B)
            p11 = jnp.full(B, ss**2) if v is None else v
            p12 = jnp.zeros(B)
            p22 = jnp.full(B, sd**2)
            vl = p11
            for a in range(m):
                if a:
                    phi = jnp.exp(-(tb[:, a] - tb[:, a - 1]) / tau)
                    m2 = phi * m2
                    p12 = phi * p12
                    p22 = phi * phi * p22 + sd**2 * (1 - phi * phi)
                    if unit_slow:
                        # The lasting level's own OU step.
                        ps = jnp.exp(-(tb[:, a] - tb[:, a - 1]) / jnp.exp(hyp[3]))
                        m1 = ps * m1
                        p12 = ps * p12
                        p11 = ps * ps * p11 + vl * (1 - ps * ps)
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

    def hyp_logp(D, hyp, c, e, ukap=None):
        ss, sd, _ = scales(hyp)
        prior = (
            -(ss**2) / (2 * UNIT_SD_PRIOR**2)
            + hyp[0]
            - sd**2 / (2 * DRIFT_SD_PRIOR**2)
            + hyp[1]
            - (hyp[2] - TAU_LOG_PRIOR[0]) ** 2 / (2 * TAU_LOG_PRIOR[1] ** 2)
        )
        if unit_slow:
            prior = prior - (hyp[3] - UNIT_TAU_LOG_PRIOR[0]) ** 2 / (
                2 * UNIT_TAU_LOG_PRIOR[1] ** 2
            )
        return unit_loglik(D, hyp, c, e, ukap) + prior

    group_rows = jnp.asarray(np.bincount(d.group, minlength=4), dtype=float)
    # Each free factor's rows: under a map, the rows of every phase it enters.
    phase_rows = None
    if phased and pmap is None:
        phase_rows = jnp.asarray(
            np.bincount(d.phase, minlength=free + 1)[1:], dtype=float
        )
    elif phased:
        phase_rows = jnp.asarray(np.bincount(d.phase, minlength=len(d.phases)) @ pmap)

    def level_loglik(D, bsd, par, F, om_d, om_off, tgt, kap=None):
        """What integrating the buildings' levels (and the collapsed term's paths) out adds
        to the log density of `tgt` = y less every other term, on top of the units' own
        marginal density of tgt: the sum over buildings of
        log |P|^(1/2) |Q|^(-1/2) exp(lin' Q^-1 lin / 2 - mu' P mu / 2), for the building
        state's prior precision P and mean mu and its posterior precision Q and linear term
        lin at the units' precisions (om_d, om_off)."""
        if col is not None:
            sums = cell_sums(D, om_d, om_off, tgt)
            return jnp.sum(cell_loglik(D, jnp.log(bsd), par, sums, F, kap))
        ctil = om_d + seg(om_off, D["pi"], num_segments=n)
        C = seg(ctil, D["site"], num_segments=S)
        Rs = seg(apply_W(D, om_d, om_off, tgt), D["site"], num_segments=S)
        b2 = site_var(bsd, kap)
        return jnp.sum(
            -0.5 * jnp.log1p(b2 * C)
            + 0.5 * (Rs + F / b2) ** 2 / (C + 1 / b2)
            - 0.5 * F * F / b2
        )

    def lam_moments(lnu):
        """The mean and sd of log lam for lam ~ Gamma(nu / 2, rate nu / 2)."""
        a = jnp.exp(lnu) / 2
        return (
            jax.scipy.special.digamma(a) - jnp.log(a),
            jnp.sqrt(jax.scipy.special.polygamma(1, a)),
        )

    def scales_logp(D, x, eta, tgt, bsd, par, F, kap=None, keta=None, phase_scale=None):
        """The log density of x = (log ss, log sd, log tau, log sigma of each group, log nu
        unless `row_dof_fixed` holds it), in a design with noise phases (unless `scales_no_phase`)
        the log factor of each phase but the reference, and
        under `unit_t` the log of the units' degrees of freedom nu_u, given theta, the
        buildings' spreads, the collapsed path's scales and the rows' standardized log
        mixing scales eta, with u, the buildings' levels and the collapsed
        paths integrated out.

        nu moves with the mixing scales in tow: log lam = m(nu) + s(nu) eta, where m and s
        are the mean and sd of log lam under Gamma(nu / 2, nu / 2). Holding eta fixed keeps
        each row's place in the distribution of lam roughly where it was, so nu is not
        pinned by 1.7 million lam drawn at its old value. The map is a bijection of lam for
        each nu, and its Jacobian (lam s for each row) is in the density.

        Under `unit_t` nu_u moves the same way with the units' mixing scales in tow, and
        `keta` holds their standardized logs.

        `unit_loglik` leaves out the rows' log c / 2."""
        ls = x[3 : 3 + n_sigma]
        lnu = x[3 + n_sigma] if nu_free else jnp.log(jnp.asarray(row_dof_fixed))
        sig_free = jnp.exp(ls)
        sig = jnp.broadcast_to(sig_free, (4,)) if scalar_sigma else sig_free
        a = jnp.exp(lnu) / 2
        m, sd = lam_moments(lnu)
        loglam = m + sd * eta
        lam = jnp.exp(loglam)
        if k_ph == free and phased:
            p_scale = jnp.exp(x[pf : pf + free])
        elif k_ph > 0:
            p_scale = phase_scale.at[ph_idx_j].set(jnp.exp(x[pf : pf + k_ph]))
        else:
            p_scale = phase_scale
        c = lam / row_sd(D, sig, p_scale) ** 2
        ukap = None
        if unit_t:
            m_u, sd_u = lam_moments(
                x[-1] if dof_free else jnp.log(jnp.asarray(unit_dof_fixed))
            )
            logk = m_u + sd_u * keta
            ukap = jnp.exp(logk)
        hu = jnp.concatenate([x[:3], x[-1:]]) if unit_slow else x[:3]
        w1, Wb = unit_W(D, hu, c, ukap)
        om_d, om_off = pair_weights(D, w1, Wb)
        a_nu, b_nu = priors.nu
        sig_term = n * ls[0] if scalar_sigma else jnp.sum(group_rows * ls)
        out = (
            hyp_logp(D, hu, c, tgt, ukap)
            + 0.5 * jnp.sum(loglam)
            - sig_term
            + level_loglik(D, bsd, par, F, om_d, om_off, tgt, kap)
            # lam's Gamma(a, rate a) density, with the map's Jacobian.
            + n * (a * jnp.log(a) - jax.scipy.special.gammaln(a) + jnp.log(sd))
            + a * jnp.sum(loglam)
            - a * jnp.sum(lam)
            - jnp.sum(sig_free**2) / (2 * priors.sigma**2)
            + jnp.sum(ls)
            + a_nu * lnu
            - b_nu * 2 * a
        )
        if dof_free:
            # The kap's Gamma(a_u, rate a_u) density with the map's Jacobian, and nu_u's
            # Gamma prior in its log. With nu_u fixed the kap stay put, and these terms
            # are a constant.
            a_u = jnp.exp(x[-1]) / 2
            ua, ub = UNIT_DOF_PRIOR
            out = (
                out
                + U * (a_u * jnp.log(a_u) - jax.scipy.special.gammaln(a_u))
                + U * jnp.log(sd_u)
                + a_u * jnp.sum(logk)
                - a_u * jnp.sum(ukap)
                + ua * x[-1]
                - ub * 2 * a_u
            )
        if k_ph == 0:
            return out
        # Each phase's factor enters c as sigma does, and its log takes a Normal prior.
        lf = x[pf : pf + k_ph]
        return (
            out
            - jnp.sum(phase_rows[ph_idx_j] * lf)
            - jnp.sum(lf**2) / (2 * PHASE_PRIOR**2)
        )

    def unit_eta(st):
        """Under `unit_t`, the units' standardized log mixing scales at the state's nu_u."""
        m_u, sd_u = lam_moments(jnp.log(st["unit_dof"]))
        return (jnp.log(st["ukap"]) - m_u) / sd_u

    def scales_x(st):
        """The state's point in the coordinates of `scales_logp`."""
        lnu = jnp.log(st["nu"])[None] if nu_free else jnp.zeros(0)
        ls_vec = jnp.log(st["sigma"][:1]) if scalar_sigma else jnp.log(st["sigma"])
        x = jnp.concatenate([st["hyp"], ls_vec, lnu])
        x = (
            jnp.concatenate([x, jnp.log(st["phase_scale"][ph_idx_j])])
            if k_ph > 0
            else x
        )
        x = jnp.concatenate([x, jnp.log(st["unit_dof"])[None]]) if dof_free else x
        return jnp.concatenate([x, jnp.log(st["unit_tau"])[None]]) if unit_slow else x

    def update_scales(D, key, st, tgt, F):
        """The unit scales, the groups' sigma, nu and any noise phases' factors together,
        with u, the buildings' levels and the collapsed paths integrated out
        (`scales_logp`): a slice update along each column of the state's `hyp_dirs` in
        turn. Returns the new hyp, sigma, nu, lam and phase_scale as a dict.

        Each of these scales was at first drawn given a latent that pins it: sigma given u,
        the unit scales given the buildings' levels and paths, nu given u. The chains then
        agreed with each other and crept, and the fits of 2026-11-10 missed the gate on
        exactly these. Here every one of those latents is out of the way.

        The slices are `slice_along`'s."""
        lnu = jnp.log(st["nu"])
        m, sd = lam_moments(lnu)
        eta = (jnp.log(st["lam"]) - m) / sd
        bsd, par = st["bld_sd"], st["ar_par"][0] if col is not None else None

        keta = unit_eta(st) if unit_t else None
        p_fixed = st.get("phase_scale") if (phased and k_ph < free) else None

        def logp(x):
            return scales_logp(
                D, x, eta, tgt, bsd, par, F, st.get("kap"), keta, p_fixed
            )

        x = scales_x(st)
        x, _ = slice_along(key, x, logp(x), logp, st["hyp_dirs"])
        lnu = x[3 + n_sigma] if nu_free else lnu
        m, sd = lam_moments(lnu)
        sig_new = (
            jnp.broadcast_to(jnp.exp(x[3:4]), (4,)) if scalar_sigma else jnp.exp(x[3:7])
        )
        new = dict(
            hyp=x[:3],
            sigma=sig_new,
            nu=jnp.exp(lnu),
            lam=jnp.exp(m + sd * eta),
        )
        if k_ph == free and phased:
            new["phase_scale"] = jnp.exp(x[pf : pf + free])
        elif k_ph > 0:
            new["phase_scale"] = (
                st["phase_scale"].at[ph_idx_j].set(jnp.exp(x[pf : pf + k_ph]))
            )
        if dof_free:
            m_u, sd_u = lam_moments(x[-1])
            new["unit_dof"] = jnp.exp(x[-1])
            new["ukap"] = jnp.exp(m_u + sd_u * keta)
        if unit_slow:
            new["unit_tau"] = jnp.exp(x[-1])
        return new

    def scales_curvature(D, st, h=CURV_STEP):
        """The Hessian of `scales_logp` at the state's scales, in the coordinates of the
        state's `hyp_dirs` (x = x0 + dirs a), by finite differences of step h. Every other
        input is the state's own: theta, the buildings' spreads and the rows' standardized
        mixing scales. `conditional_dirs` turns it into slice directions."""
        lnu = jnp.log(st["nu"])
        m, sd = lam_moments(lnu)
        eta = (jnp.log(st["lam"]) - m) / sd
        F = D["Bc"] @ st["theta"][sl_w]
        tgt = D["y"] - offsets(D, st) - all_means(D, st["theta"])
        bsd, par = st["bld_sd"], None
        if col is not None:
            tgt = tgt + st["ar"][0].ravel()[D["ar_cell"][0]]
            par = st["ar_par"][0]
        p_fixed = st.get("phase_scale") if (phased and k_ph < free) else None
        x0 = scales_x(st)
        K = x0.shape[0]
        eye = jnp.eye(K)
        i, j = np.triu_indices(K, 1)
        corner = eye[i] + eye[j]
        pts = h * jnp.concatenate([jnp.zeros((1, K)), eye, -eye, corner, -corner])
        f = jax.lax.map(
            lambda a: scales_logp(
                D,
                x0 + st["hyp_dirs"] @ a,
                eta,
                tgt,
                bsd,
                par,
                F,
                st.get("kap"),
                unit_eta(st) if unit_t else None,
                p_fixed,
            ),
            pts,
        )
        f0, up, down = f[0], f[1 : K + 1], f[K + 1 : 2 * K + 1]
        both = f[2 * K + 1 :].reshape(2, -1).sum(axis=0)
        ends = up + down
        H = (
            jnp.zeros((K, K))
            .at[i, j]
            .set((both - ends[i] - ends[j] + 2 * f0) / (2 * h**2))
        )
        return H + H.T + jnp.diag((up + down - 2 * f0) / h**2)

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

    def ar_mean(par, mf, pf):
        """Rauch-Tung-Striebel smoother mean of every process's path given the filter's
        output (ar_draw with zero noise), (groups, steps)."""
        s2 = jnp.exp(2 * par[0])
        rho = jax.nn.sigmoid(par[1])
        q = s2 * (1 - rho * rho)
        last = mf[-1]

        def step(nxt, x):
            m, p = x
            pp = rho * rho * p + q
            J = rho * p / pp
            cur = m + J * (nxt - rho * m)
            return cur, cur

        _, path = jax.lax.scan(step, last, (mf[:-1], pf[:-1]), reverse=True)
        return jnp.concatenate([path, last[None]], axis=0).T

    def fill_path_mean(par, at, active):
        C = jnp.where(active, PIN, 0.0)
        _, mf, pf = ar_filter(par, C, C * at)
        return jnp.where(active, at, ar_mean(par, mf, pf))

    def unit_moments(D, hyp, c, w1, Wb, e, ukap):
        """Deterministic posterior mean and marginal variance of (u, s_unit) given e
        for exact variational-EM E-steps of Student-t mixing weights."""
        ss, sd, _ = scales(hyp)
        one = D["single"]
        if ukap is None:
            k0 = ss**2 + sd**2
            u = jnp.where(one, k0 * w1 * e, 0.0)
            var_u = jnp.where(one, k0 / (1 + c * k0), 0.0)
            s_unit = jnp.zeros(U)
            var_s = jnp.zeros(U)
            for W, idx, mask, tb in zip(Wb, D["b_idx"], D["b_mask"], D["b_t"]):
                eb = jnp.where(mask, e[idx], 0.0)
                We = jnp.einsum("bij,bj->bi", W, eb)
                Kb = kernel(hyp, tb[:, :, None], tb[:, None, :])
                ub = jnp.einsum("bij,bj->bi", Kb, We)
                vub = jnp.maximum(k0 - jnp.einsum("bij,bjk,bik->bi", Kb, W, Kb), 0.0)
                u = (
                    u
                    + seg(
                        jnp.where(mask, ub, 0.0).ravel(),
                        jnp.where(mask, idx, n).ravel(),
                        num_segments=n + 1,
                    )[:n]
                )
                var_u = (
                    var_u
                    + seg(
                        jnp.where(mask, vub, 0.0).ravel(),
                        jnp.where(mask, idx, n).ravel(),
                        num_segments=n + 1,
                    )[:n]
                )
            return u, var_u, s_unit, var_s
        vr, vb = lasting(D, hyp, ukap)
        k0r = vr + sd**2
        u = jnp.where(one, k0r * w1 * e, 0.0)
        var_u = jnp.where(one, k0r / (1 + c * k0r), 0.0)
        s_unit = seg(jnp.where(one, vr * w1 * e, 0.0), D["unit"], num_segments=U)
        var_s = seg(
            jnp.where(one, jnp.maximum(vr - vr * vr * w1, 0.0), 0.0),
            D["unit"],
            num_segments=U,
        )
        for W, idx, mask, tb, v, bu in zip(
            Wb, D["b_idx"], D["b_mask"], D["b_t"], vb, D["b_unit"]
        ):
            eb = jnp.where(mask, e[idx], 0.0)
            We = jnp.einsum("bij,bj->bi", W, eb)
            Kb = kernel(hyp, tb[:, :, None], tb[:, None, :], v[:, None, None])
            ub = jnp.einsum("bij,bj->bi", Kb, We)
            vub = jnp.maximum(
                (v[:, None] + sd**2) - jnp.einsum("bij,bjk,bik->bi", Kb, W, Kb), 0.0
            )
            u = (
                u
                + seg(
                    jnp.where(mask, ub, 0.0).ravel(),
                    jnp.where(mask, idx, n).ravel(),
                    num_segments=n + 1,
                )[:n]
            )
            var_u = (
                var_u
                + seg(
                    jnp.where(mask, vub, 0.0).ravel(),
                    jnp.where(mask, idx, n).ravel(),
                    num_segments=n + 1,
                )[:n]
            )
            s_unit = s_unit.at[bu].add(v * jnp.sum(We, axis=1))
            var_s = var_s.at[bu].add(
                jnp.maximum(v - (v * v) * jnp.sum(W, axis=(1, 2)), 0.0)
            )
        return u, var_u, s_unit, var_s

    def em_step(D, st):
        """One deterministic variational-EM fixed-point iteration with scales held."""
        hyp = unit_hyp(st)
        c = weights(D, st)
        w1, Wb = unit_W(D, hyp, c, st.get("ukap"))
        y_eff = D["y"] - offsets(D, st)
        A, h, _ = global_system(D, st, c, w1, Wb, y_eff)
        s = 1 / jnp.sqrt(jnp.diag(A))
        Cf = jnp.linalg.cholesky(A * s[:, None] * s[None, :])
        theta = jax.scipy.linalg.cho_solve((Cf, True), h * s) * s
        F = D["Bc"] @ theta[sl_w]
        e0 = y_eff - all_means(D, theta)
        om_d, om_off = pair_weights(D, w1, Wb)
        if col is None:
            ctil = om_d + seg(om_off, D["pi"], num_segments=n)
            C = seg(ctil, D["site"], num_segments=S)
            Rs = seg(apply_W(D, om_d, om_off, e0), D["site"], num_segments=S)
            b2 = site_var(st["bld_sd"], st.get("kap"))
            P = C + 1 / b2
            lev = (Rs + F / b2) / P
            var_lev = 1 / P
            e = e0 - lev[D["site"]]
            ar_new = st.get("ar", ())
        else:
            cell = D["ar_cell"][0]
            tgt = e0 + st["ar"][0].ravel()[cell]
            sums = cell_sums(D, om_d, om_off, tgt)
            if len(slow):
                As, lins, Gs = slow_system(D, st, om_d, om_off, sums, tgt, F)
                cur = theta[sl_b][slow]
                Qs = As + jnp.diag(prec_b[slow])
                for gk, sub, xk in slow_gp_blocks:
                    Lk = jnp.linalg.cholesky(
                        _gp_cov(xk, st["gp_ls"][gk], *gp_kernels[gk])
                    )
                    Ki = jax.scipy.linalg.cho_solve((Lk, True), jnp.eye(len(sub)))
                    Qs = Qs.at[np.ix_(sub, sub)].add(Ki / st["gp_amp"][gk] ** 2)
                rhs = lins + As @ cur + lin_b[slow]
                ss_q = 1 / jnp.sqrt(jnp.diag(Qs))
                Cfs = jnp.linalg.cholesky(Qs * ss_q[:, None] * ss_q[None, :])
                step = jax.scipy.linalg.cho_solve((Cfs, True), rhs * ss_q) * ss_q - cur
                theta = theta.at[sl_b].set(theta[sl_b].at[slow].add(step))
                tgt = tgt - jnp.concatenate([x[:, slow] @ step for x in D["xs"]])
                sums = [(H, hv - Gb @ step) for (H, hv), Gb in zip(sums, Gs)]
            par = st["ar_par"][0]
            b2 = site_var(st["bld_sd"], st.get("kap"))
            lev = F
            var_lev = b2
            a0 = ars[0]
            cells = a0["size"] * a0["T"]
            at = jnp.zeros(cells + 1)
            for (H, hv), ids, gap, place in zip(
                sums,
                D["cells"]["sites"],
                D["cells"]["gap"],
                D["cells"]["cells"],
            ):
                L, x, _ = cell_system(par, b2[ids], F[ids], H, hv, gap)
                z = jax.vmap(
                    lambda Lk, bk: jax.scipy.linalg.solve_triangular(
                        Lk.T, bk, lower=False
                    )
                )(L, x)
                # Diagonal variance of building level (row 0 of L^{-1})
                e0_vec = jnp.zeros_like(x).at[:, 0].set(1.0)
                v0 = jax.vmap(
                    lambda Lk, bk: jax.scipy.linalg.solve_triangular(Lk, bk, lower=True)
                )(L, e0_vec)
                lev = lev.at[ids].set(z[:, 0])
                var_lev = var_lev.at[ids].set(jnp.sum(v0 * v0, axis=1))
                at = at.at[place.ravel()].set(z[:, 1:].ravel())
            active = D["cells"]["active"].reshape(a0["size"], a0["T"])
            path = fill_path_mean(par, at[:cells].reshape(a0["size"], a0["T"]), active)
            e = tgt - lev[D["site"]] - path.ravel()[cell]
            ar_new = (path, *st["ar"][1:])
        u, var_u, s_unit, var_s = unit_moments(
            D, hyp, c, w1, Wb, e, st.get("ukap") if unit_t else None
        )
        r = e - u
        rsd = row_sd(D, st["sigma"], st.get("phase_scale"))
        lam = (st["nu"] + 1.0) / (st["nu"] + (r * r + var_u) / (rsd * rsd))
        new = st | dict(theta=theta, lev=lev, lam=lam)
        if ars:
            new["ar"] = ar_new
        if dof is not None:
            z2 = ((lev - F) ** 2 + var_lev) / st["bld_sd"][zone_j] ** 2
            new["kap"] = (dof + 1.0) / (dof + z2)
        if unit_t:
            ss_u = scales(hyp)[0]
            new["ukap"] = (st["unit_dof"] + 1.0) / (
                st["unit_dof"] + (s_unit * s_unit + var_s) / (ss_u * ss_u)
            )
        return new

    def laplace_draw(D, key, st_map):
        """One independent analytical Laplace draw around the converged EM state `st_map`:
        re-draws Student-t mixing scales (lam, kap, ukap) from their conditional Gamma
        around the EM residuals so tail uncertainty propagates cleanly, then draws
        theta ~ N(theta*, A*^-1), slow_columns with (lev, path) integrated out,
        (lev, path) ~ p(lev, path | theta, lam, kap, ukap), and fresh new-unit ukap."""
        k1, k2, k3, k4, k5, k6, k7 = jax.random.split(key, 7)
        hyp = unit_hyp(st_map)
        # Re-draw Student-t mixing scales from their conditional Gamma given EM mean rate
        # (since lam_map = (nu+1)/(nu + r2/sig2), Gamma((nu+1)/2, rate=(nu+1)/(2*lam_map)) has mean lam_map).
        a_lam = (st_map["nu"] + 1.0) / 2.0
        lam_d = jax.random.gamma(k6, a_lam, (n,)) * (st_map["lam"] / a_lam)
        st_use = st_map | {"lam": lam_d}
        if unit_t:
            a_u_tr = (st_map["unit_dof"] + 1.0) / 2.0
            st_use = st_use | {
                "ukap": jax.random.gamma(k7, a_u_tr, (U,)) * (st_map["ukap"] / a_u_tr)
            }
        if dof is not None:
            has_row = jnp.asarray(rows_per_site > 0)
            a_k = (dof + 1.0) / 2.0
            k4a, k4b = jax.random.split(k4)
            kap_tr = jax.random.gamma(k4a, a_k, (S,)) * (st_map["kap"] / a_k)
            kap_prior = jax.random.gamma(k4b, dof / 2.0, (S,)) / (dof / 2.0)
            st_use = st_use | {"kap": jnp.where(has_row, kap_tr, kap_prior)}
        c = weights(D, st_use)
        w1, Wb = unit_W(D, hyp, c, st_use.get("ukap"))
        y_eff = D["y"] - offsets(D, st_use)
        theta, _ = draw_theta(D, k1, st_use, c, w1, Wb, y_eff)
        w = theta[sl_w]
        F = D["Bc"] @ w
        e0 = y_eff - all_means(D, theta)
        om_d, om_off = pair_weights(D, w1, Wb)
        if col is None:
            ctil = om_d + seg(om_off, D["pi"], num_segments=n)
            C = seg(ctil, D["site"], num_segments=S)
            Rs = seg(apply_W(D, om_d, om_off, e0), D["site"], num_segments=S)
            bsd = st_use["bld_sd"]
            b2 = site_var(bsd, st_use.get("kap"))
            P = C + 1 / b2
            lev = (Rs + F / b2) / P + jax.random.normal(k2, (S,)) / jnp.sqrt(P)
            ar_out = st_use.get("ar", ())
            par_out = st_use.get("ar_par")
        else:
            cell = D["ar_cell"][0]
            tgt = e0 + st_map["ar"][0].ravel()[cell]
            sums = cell_sums(D, om_d, om_off, tgt)
            if len(slow):
                theta, tgt, sums = update_slow(
                    D, k3, st_use, theta, om_d, om_off, sums, tgt, F
                )
            bsd, lev, par, path = update_cells(D, k2, st_use, sums, F)
            ar_out = (path, *st_map["ar"][1:])
            par_out = st_map["ar_par"].at[0].set(par)
        new = st_use | dict(theta=theta, lev=lev, bld_sd=bsd)
        if ars:
            new["ar"] = ar_out
            new["ar_par"] = par_out
        if unit_t:
            a_u = st_map["unit_dof"] / 2.0
            new["pred_ukap"] = jax.random.gamma(k5, a_u, (n_pred,)) / a_u
        ss, sd, tu = scales(hyp)
        out = outputs(theta, lev, F) | dict(unit_sd=ss, drift_sd=sd, drift_tau=tu)
        if phased:
            factor = st_map["phase_scale"]
            if pmap_j is None:
                out["phase_scale"] = phase_factors(factor)
            else:
                out["phase_factor"] = factor
        if dof_free:
            out["unit_dof"] = st_map["unit_dof"]
        if unit_slow:
            out["unit_tau"] = st_map["unit_tau"]
        if ars:
            for k, a in enumerate(ars):
                out[a["name"] + "_ar_sd"] = jnp.exp(par_out[k][0])
                out[a["name"] + "_ar_rho"] = jax.nn.sigmoid(par_out[k][1])
        return new, out

    def update_ar(key, k, par, C, R):
        """One term's (log sd, logit rho) with its paths integrated out, by a slice update of
        each in turn, then the paths. As in `update_scales` the interval only shrinks, from
        AR_WIDTHS, which are several times the scales' posterior spread on any dataset."""
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
        for j, (kk, width) in enumerate(zip((k1, k2), AR_WIDTHS)):

            def along(v, par=par, j=j):
                return logp(par.at[j].set(v[0]))[None]

            par = par.at[j].set(
                b0.slice_vec(kk, par[j][None], along, width, steps_out=0, shrink=32)[0]
            )
        _, mf, pf = ar_filter(par, C, R)
        return par, ar_draw(k3, par, mf, pf)

    def ar_sums(D, k, c, tgt):
        """Term k's cell sums of the row weights c and of c times the rows' `tgt`, each
        (groups, steps)."""
        a, cell = ars[k], D["ar_cell"][k]
        cells = a["size"] * a["T"]
        C = jax.ops.segment_sum(c, cell, num_segments=cells)
        R = jax.ops.segment_sum(c * tgt, cell, num_segments=cells)
        return C.reshape(a["size"], a["T"]), R.reshape(a["size"], a["T"])

    def update_local(D, keys, st, c, r, first=0):
        """Each local-drift term from `first` on in turn, given the other terms: its scales,
        then its paths. `r` is y less every other term of the mean and less all the current
        paths. Returns r with the new paths in place of the old, the paths and the scales."""
        ar = list(st["ar"][:first]) if first else []
        ar_par = list(st["ar_par"][:first]) if first else []
        for k in range(first, len(ars)):
            cell = D["ar_cell"][k]
            tgt = r + st["ar"][k].ravel()[cell]
            par, path = update_ar(keys[k], k, st["ar_par"][k], *ar_sums(D, k, c, tgt))
            ar.append(path)
            ar_par.append(par)
            r = tgt - path.ravel()[cell]
        return r, tuple(ar), tuple(ar_par)

    def cell_sums(D, om_d, om_off, tgt):
        """For each bucket of the collapsed term, the buildings' H = B' W B, (buildings, m,
        m), and h = B' W tgt, (buildings, m): W is the units' precision and B maps a
        building's cells to its rows. A padded place holds 0."""
        cl = D["cells"]
        H = seg(om_d, cl["H_d"], num_segments=col["size_H"]) + seg(
            om_off, cl["H_o"], num_segments=col["size_H"]
        )
        h = seg(apply_W(D, om_d, om_off, tgt), cl["h"], num_segments=col["size_h"])
        out = []
        for b in col["buckets"]:
            nb, m = b["gap"].shape
            out.append(
                (
                    H[b["off_H"] : b["off_H"] + nb * m * m].reshape(nb, m, m),
                    h[b["off_h"] : b["off_h"] + nb * m].reshape(nb, m),
                )
            )
        return out

    def cell_system(par, b2, F, H, h, gap):
        """One bucket's buildings given `tgt` = y less every other term, with u integrated
        out. A building's state is z = (level, path at its cells). Its prior is level ~
        Normal(F, b2) and a stationary AR(1) path with (log sd, logit rho) = `par`, whose
        precision at the cells is tridiagonal: consecutive cells `gap` steps apart correlate
        at rho^gap. Returns the Cholesky factor L of z's posterior precision Q, L^-1 times
        its linear term, and each building's log marginal likelihood up to a constant in
        (b2, par). A padded place is an independent Normal(0, sd^2) with no rows."""
        s2 = jnp.exp(2 * par[0])
        rho = jax.nn.sigmoid(par[1])
        nb, m = gap.shape
        phi = jnp.where(gap > 0, rho ** jnp.maximum(gap, 1), 0.0)
        v = 1 - phi * phi
        nxt = jnp.concatenate([(phi * phi / v)[:, 1:], jnp.zeros((nb, 1))], axis=1)
        off = -(phi / v)[:, 1:] / s2
        i = jnp.arange(m)
        A = (
            H.at[:, i, i]
            .add((1 / v + nxt) / s2)
            .at[:, i[1:], i[:-1]]
            .add(off)
            .at[:, i[:-1], i[1:]]
            .add(off)
        )
        r = H.sum(axis=2)
        top = jnp.concatenate(
            [(1 / b2 + r.sum(axis=1))[:, None, None], r[:, None, :]], axis=2
        )
        Q = jnp.concatenate([top, jnp.concatenate([r[:, :, None], A], axis=2)], axis=1)
        lin = jnp.concatenate([(h.sum(axis=1) + F / b2)[:, None], h], axis=1)
        L = jnp.linalg.cholesky(Q)
        x = jax.vmap(
            lambda Lk, bk: jax.scipy.linalg.solve_triangular(Lk, bk, lower=True)
        )(L, lin)
        ll = (
            -jnp.sum(jnp.log(jnp.diagonal(L, axis1=1, axis2=2)), axis=1)
            + 0.5 * jnp.sum(x * x, axis=1)
            - 0.5 * jnp.log(b2)
            - 0.5 * F * F / b2
            - 0.5 * m * jnp.log(s2)
            - 0.5 * jnp.sum(jnp.log(v), axis=1)
        )
        return L, x, ll

    def apply_W_mat(D, om_d, om_off, X):
        """W X for a (n, m) matrix X over rows."""
        return om_d[:, None] * X + seg(
            om_off[:, None] * X[D["pj"]], D["pi"], num_segments=n
        )

    def slow_system(D, st, om_d, om_off, sums, tgt, F):
        """The likelihood's precision and linear term for a shift of the slow columns'
        coefficients from where `tgt` has them, with u, the buildings' levels and the
        collapsed paths integrated out: X' V X and X' V (tgt - F), for the columns X and
        the rows' marginal precision V = W - W Z Q^-1 Z' W, where Z maps a building's state
        to its rows and Q is the state's posterior precision (`cell_system`). Also returns
        each bucket's G = B' W X, (buildings, cells, columns)."""
        cl, xs = D["cells"], D["xs"]
        Wt = apply_W(D, om_d, om_off, tgt)
        n_s = len(slow)
        chunk_sz = 16
        # Chunked batched W @ X_slow: avoids 1-column-at-a-time lax.map while capping peak VRAM.
        G_parts = []
        A_parts = []
        for c0 in range(0, n_s, chunk_sz):
            sl_c = slow[c0 : c0 + chunk_sz]
            Xc = jnp.concatenate([x[:, sl_c] for x in xs], axis=0)
            WXc = apply_W_mat(D, om_d, om_off, Xc)
            G_parts.append(seg(WXc, cl["h"], num_segments=col["size_h"]).T)
            A_parts.append(
                sum(
                    x[:, slow].T @ WXc[r0:r1] for x, (_, _, r0, r1) in zip(xs, blocks)
                ).T
            )
        G = jnp.concatenate(G_parts, axis=0)
        A = jnp.concatenate(A_parts, axis=0)
        lin = sum(x[:, slow].T @ Wt[r0:r1] for x, (_, _, r0, r1) in zip(xs, blocks))
        par = st["ar_par"][0]
        b2 = site_var(st["bld_sd"], st.get("kap"))
        Gs = []
        for (H, h), b, ids, gap in zip(sums, col["buckets"], cl["sites"], cl["gap"]):
            nb, m = gap.shape
            Gb = G[:, b["off_h"] : b["off_h"] + nb * m].reshape(-1, nb, m)
            Gb = Gb.transpose(1, 2, 0)
            Gz = jnp.concatenate([Gb.sum(axis=1, keepdims=True), Gb], axis=1)
            L, x, _ = cell_system(par, b2[ids], F[ids], H, h, gap)
            Y = jax.vmap(
                lambda Lk, Gk: jax.scipy.linalg.solve_triangular(Lk, Gk, lower=True)
            )(L, Gz)
            A = A - jnp.einsum("bms,bmt->st", Y, Y)
            lin = lin - jnp.einsum("bms,bm->s", Y, x)
            Gs.append(Gb)
        return 0.5 * (A + A.T), lin, Gs

    def update_slow(D, key, st, theta, om_d, om_off, sums, tgt, F):
        """The slow columns' coefficients given the rest of theta and the scales, with u,
        the buildings' levels and the collapsed paths integrated out. Returns theta, and
        `tgt` and `sums` at the new coefficients.

        theta is drawn given the buildings' paths. A building amenity code is set from the
        building's ads up to each row's day, so it changes within a building over time, and
        a path can stand in for it: given the paths these coefficients are pinned, and the
        pilots of the collapsed term had them at autocorrelation times of 9 to 24 sweeps
        against 2 without the paths. This draw has the paths out of the way. The paths are
        drawn next (`update_cells`), at the new coefficients."""
        A, lin, Gs = slow_system(D, st, om_d, om_off, sums, tgt, F)
        cur = theta[sl_b][slow]
        Q = A + jnp.diag(prec_b[slow])
        for gk, sub, xk in slow_gp_blocks:
            Lk = jnp.linalg.cholesky(_gp_cov(xk, st["gp_ls"][gk], *gp_kernels[gk]))
            Ki = jax.scipy.linalg.cho_solve((Lk, True), jnp.eye(len(sub)))
            Q = Q.at[np.ix_(sub, sub)].add(Ki / st["gp_amp"][gk] ** 2)
        rhs = lin + A @ cur + lin_b[slow]
        s = 1 / jnp.sqrt(jnp.diag(Q))
        Cf = jnp.linalg.cholesky(Q * s[:, None] * s[None, :])
        mean = jax.scipy.linalg.cho_solve((Cf, True), rhs * s)
        dev = jax.scipy.linalg.solve_triangular(
            Cf.T, jax.random.normal(key, (len(slow),)), lower=False
        )
        step = (mean + dev) * s - cur
        theta = theta.at[sl_b].set(theta[sl_b].at[slow].add(step))
        tgt = tgt - jnp.concatenate([x[:, slow] @ step for x in D["xs"]])
        sums = [(H, h - Gb @ step) for (H, h), Gb in zip(sums, Gs)]
        return theta, tgt, sums

    def fill_path(key, par, at, active):
        """Paths (groups, steps) that hold `at` where `active` and, at every other step, a
        draw given those: the filter with each active step pinned at its value, backward
        sampling, then the pinned values themselves put back."""
        C = jnp.where(active, PIN, 0.0)
        _, mf, pf = ar_filter(par, C, C * at)
        return jnp.where(active, at, ar_draw(key, par, mf, pf))

    def cell_loglik(D, lb, par, sums, F, kap=None):
        """Each zone's sum of its buildings' log marginal likelihoods at log spreads `lb`
        and the path's `par`, with the levels, the paths and u integrated out. `kap` is
        the buildings' mixing scales under the Student-t prior on the levels."""
        out = jnp.zeros(nz)
        b2 = site_var(jnp.exp(lb), kap)
        for (H, h), ids, gap in zip(sums, D["cells"]["sites"], D["cells"]["gap"]):
            _, _, ll = cell_system(par, b2[ids], F[ids], H, h, gap)
            out = out + seg(ll, zone_j[ids], num_segments=nz)
        return out

    def update_cells(D, key, st, sums, F):
        """The collapsed building step. Each zone's spread b, then the path's (log sd, logit
        rho) along each column of the state's `cell_dirs`, all with the buildings' levels,
        their paths and u integrated out. Then every building's level and path at its cells
        in one draw with u integrated out, and the path's other steps given those.

        The uncollapsed step (`update_local`) draws a path given u, where the rows pin it
        far more tightly than they do once u is free to follow, and the sweep then creeps:
        the fits of 2026-11-10 with that step missed the gate at R-hat 1.6."""
        k1, k2, k3, k4 = jax.random.split(key, 4)
        par = st["ar_par"][0]
        prior_sd = ars[0]["sd_prior"]
        kap = st.get("kap")

        def logp_b(lb):
            ll = cell_loglik(D, lb, par, sums, F, kap)
            return ll - jnp.exp(2 * lb) / (2 * BLD_SD_PRIOR**2) + lb

        lb = jnp.log(st["bld_sd"])
        if "cells" not in fixed_steps:
            lb = b0.slice_vec(k1, lb, logp_b, SPREAD_WIDTH, steps_out=0, shrink=32)

        def logp(x):
            rho = jax.nn.sigmoid(x[1])
            return (
                jnp.sum(cell_loglik(D, lb, x, sums, F, kap))
                - jnp.exp(2 * x[0]) / (2 * prior_sd**2)
                + x[0]
                + jnp.log(rho)
                + jnp.log1p(-rho)
            )

        if "cells" not in fixed_steps:
            par, _ = slice_along(k2, par, logp(par), logp, st["cell_dirs"])
        bsd = jnp.exp(lb)
        b2 = site_var(bsd, kap)
        # A building with no row keeps its prior.
        lev = F + jnp.sqrt(b2) * jax.random.normal(k3, (S,))
        a = ars[0]
        cells = a["size"] * a["T"]
        at = jnp.zeros(cells + 1)
        keys = jax.random.split(k4, len(sums) + 1)
        for kk, (H, h), ids, gap, place in zip(
            keys[1:],
            sums,
            D["cells"]["sites"],
            D["cells"]["gap"],
            D["cells"]["cells"],
        ):
            L, x, _ = cell_system(par, b2[ids], F[ids], H, h, gap)
            z = jax.vmap(
                lambda Lk, bk: jax.scipy.linalg.solve_triangular(Lk.T, bk, lower=False)
            )(L, x + jax.random.normal(kk, x.shape))
            lev = lev.at[ids].set(z[:, 0])
            at = at.at[place.ravel()].set(z[:, 1:].ravel())
        active = D["cells"]["active"].reshape(a["size"], a["T"])
        path = fill_path(keys[0], par, at[:cells].reshape(a["size"], a["T"]), active)
        return bsd, lev, par, path

    def update_noise(key, st, r, D):
        """b0's noise step: nu, then sigma with lam integrated out, then lam. Under
        `phase_collapsed` the step also draws each free phase factor after sigma, from its
        own rows' Student-t density at the new sigma, before it draws lam. Returns nu,
        sigma, lam and the free factors, None in a design without phases."""
        k1, k2, k3 = jax.random.split(key, 3)
        a_nu, b_nu = priors.nu
        group_all = D["group"]

        def scale(sig):
            return row_sd(D, sig, st.get("phase_scale"))

        def logp_nu(lnu):
            nu = jnp.exp(lnu[0])
            ll = jnp.sum(b0.t_logpdf(r, nu, scale(st["sigma"])))
            return (ll + a_nu * lnu[0] - b_nu * nu)[None]

        nu = (
            jnp.exp(b0.slice_vec(k1, jnp.log(st["nu"])[None], logp_nu, 0.1)[0])
            if nu_free and "noise" not in fixed_steps
            else st["nu"]
        )

        if "noise" in fixed_steps or use_fisher_hmc:
            sigma = st["sigma"]
        elif scalar_sigma:

            def logp_sigma_scalar(ls):
                sig = jnp.exp(ls[0])
                ll = jnp.sum(b0.t_logpdf(r, nu, scale(jnp.broadcast_to(sig, (4,)))))
                return (ll - sig**2 / (2 * priors.sigma**2) + ls[0])[None]

            sig_s = jnp.exp(
                b0.slice_vec(k2, jnp.log(st["sigma"][:1]), logp_sigma_scalar, 0.02)[0]
            )
            sigma = jnp.broadcast_to(sig_s, (4,))
        else:

            def logp_sigma(ls):
                sig = jnp.exp(ls)
                ll = seg(b0.t_logpdf(r, nu, scale(sig)), group_all, num_segments=4)
                return ll - sig**2 / (2 * priors.sigma**2) + ls

            sigma = jnp.exp(b0.slice_vec(k2, jnp.log(st["sigma"]), logp_sigma, 0.02))
        factor = st.get("phase_scale")
        if use_fisher_hmc and "noise" not in fixed_steps:
            # Exact Fisher-preconditioned HMC over (log_sigma, log_phase_factors) jointly with
            # `lam` integrated out. Eliminates the (sigma, phase:*, sv:m00) collinear ridge in
            # 5 row passes instead of ~290 coordinate-slice passes while preserving exact balance.
            k_hmc = jax.random.fold_in(key, PHASE_KEY)
            ls0 = jnp.log(st["sigma"][:1]) if scalar_sigma else jnp.log(st["sigma"])
            lf0 = jnp.log(factor)
            th0 = jnp.concatenate([ls0, lf0])
            d_th = th0.shape[0]
            ph_idx = D["phase"]
            n_cells = pmap_j.shape[0]
            r2_nu = (r * r) / nu
            half_nu1 = 0.5 * (nu + 1.0)
            fish_c = (2.0 * nu) / (nu + 3.0)
            prior_diag = jnp.concatenate(
                [
                    jnp.full((n_sigma,), 1.0 / priors.sigma**2),
                    jnp.full((free,), 1.0 / PHASE_PRIOR**2),
                ]
            )
            I_mat = fish_c * noise_gram_j + jnp.diag(prior_diag)
            L_fish = jnp.linalg.cholesky(I_mat)
            L_inv = jax.scipy.linalg.solve_triangular(
                L_fish.T, jnp.eye(d_th), lower=False
            )

            def logp_and_grad(th):
                ls_v = th[:n_sigma]
                lf_v = th[n_sigma:]
                sig_v = jnp.exp(ls_v)
                cell_ls = pmap_j @ lf_v
                s_row = (
                    ls_v[0] + cell_ls[ph_idx]
                    if scalar_sigma
                    else ls_v[group_all] + cell_ls[ph_idx]
                )
                u = r2_nu * jnp.exp(-2.0 * s_row)
                ll = -jnp.sum(s_row) - half_nu1 * jnp.sum(jnp.log1p(u))
                lp = (
                    ll
                    - jnp.sum(sig_v**2) / (2.0 * priors.sigma**2)
                    + jnp.sum(ls_v)
                    - jnp.sum(lf_v**2) / (2.0 * PHASE_PRIOR**2)
                )
                g_row = -1.0 + (nu + 1.0) * (u / (1.0 + u))
                g_ls = (
                    jnp.sum(g_row)[None]
                    if scalar_sigma
                    else seg(g_row, group_all, num_segments=4)
                )
                g_ls = g_ls - (sig_v**2) / (priors.sigma**2) + 1.0
                g_cell = seg(g_row, ph_idx, num_segments=n_cells)
                g_lf = pmap_j.T @ g_cell - lf_v / (PHASE_PRIOR**2)
                return lp, jnp.concatenate([g_ls, g_lf])

            eps = 0.31

            def hmc_proposal(th_in, k_step):
                km, ka = jax.random.split(k_step)
                p0 = jax.random.normal(km, (d_th,))
                lp0, g0 = logp_and_grad(th_in)
                p_cur = p0 + 0.5 * eps * (L_inv.T @ g0)
                th_cur = th_in

                def leap(carry, _):
                    th_c, p_c = carry
                    th_n = th_c + eps * (L_inv @ p_c)
                    _, g_n = logp_and_grad(th_n)
                    p_n = p_c + eps * (L_inv.T @ g_n)
                    return (th_n, p_n), None

                (th_cur, p_cur), _ = jax.lax.scan(leap, (th_cur, p_cur), None, length=4)
                th_prop = th_cur + eps * (L_inv @ p_cur)
                lp_prop, g_prop = logp_and_grad(th_prop)
                p_prop = p_cur + 0.5 * eps * (L_inv.T @ g_prop)
                log_alpha = (lp_prop - 0.5 * jnp.sum(p_prop**2)) - (
                    lp0 - 0.5 * jnp.sum(p0**2)
                )
                accept = jnp.log(jax.random.uniform(ka)) < log_alpha
                return jnp.where(accept, th_prop, th_in), None

            th_new, _ = jax.lax.scan(hmc_proposal, th0, jax.random.split(k_hmc, 2))
            sig_new = jnp.exp(th_new[:n_sigma])
            sigma = jnp.broadcast_to(sig_new, (4,)) if scalar_sigma else sig_new
            factor = jnp.exp(th_new[n_sigma:])
        elif phase_collapsed and "noise" not in fixed_steps:
            # Its key is folded in, so nu, sigma and lam take the keys they had without
            # this step.
            k_ph = jax.random.fold_in(key, PHASE_KEY)
            if pmap_j is None:

                def logp_phase(lf):
                    ll = b0.t_logpdf(r, nu, row_sd(D, sigma, jnp.exp(lf)))
                    by_phase = seg(ll, D["phase"], num_segments=free + 1)[1:]
                    return by_phase - lf**2 / (2 * PHASE_PRIOR**2)

                factor = jnp.exp(
                    b0.slice_vec(k_ph, jnp.log(factor), logp_phase, PHASE_NOISE_WIDTH)
                )
            elif pmap_binary:
                # Exact systematic-scan coordinate slice update over each binary log-factor
                # in `phase_map` with `lam` integrated out, holding `r`, `nu`, `sigma` fixed.
                # Carrying u2 = (r / sd)^2 / nu avoids array exp() inside every slice step.
                lf0 = jnp.log(factor)
                ph_idx = D["phase"]
                sd0 = row_sd(D, sigma, factor)
                u2_0 = (r / sd0) ** 2 / nu
                half_nu1 = 0.5 * (nu + 1.0)

                def step_factor_bin(carry, j):
                    lf_cur, u2_cur = carry
                    active = pmap_j[ph_idx, j] > 0.5
                    old_v = lf_cur[j]
                    n_act = jnp.sum(active)
                    u2_act = jnp.where(active, u2_cur * jnp.exp(2.0 * old_v), 0.0)

                    def logp_j(val):
                        v = val[0]
                        ll = -v * n_act - half_nu1 * jnp.sum(
                            jnp.log1p(u2_act * jnp.exp(-2.0 * v))
                        )
                        return (ll - v * v / (2 * PHASE_PRIOR**2))[None]

                    new_v = b0.slice_vec(
                        jax.random.fold_in(k_ph, j),
                        old_v[None],
                        logp_j,
                        PHASE_NOISE_WIDTH,
                    )[0]
                    lf_next = lf_cur.at[j].set(new_v)
                    u2_next = jnp.where(
                        active, u2_cur * jnp.exp(2.0 * (old_v - new_v)), u2_cur
                    )
                    return (lf_next, u2_next), None

                (lf_new, _), _ = jax.lax.scan(
                    step_factor_bin, (lf0, u2_0), jnp.arange(free)
                )
                factor = jnp.exp(lf_new)
            else:
                # General systematic-scan coordinate slice update for non-binary `phase_map`.
                # Carries u2 = (r / sd)^2 / nu and drops constants in `v` (exact match to t_logpdf).
                lf0 = jnp.log(factor)
                ph_idx = D["phase"]
                sd0 = row_sd(D, sigma, factor)
                u2_0 = (r / sd0) ** 2 / nu
                half_nu1 = 0.5 * (nu + 1.0)

                def step_factor(carry, j):
                    lf_cur, u2_cur = carry
                    m_j = pmap_j[ph_idx, j]
                    active = m_j != 0.0
                    old_v = lf_cur[j]
                    sum_m = jnp.sum(m_j)
                    u2_act = jnp.where(active, u2_cur, 0.0)

                    def logp_j(val):
                        dv = val[0] - old_v
                        ll = -dv * sum_m - half_nu1 * jnp.sum(
                            jnp.log1p(u2_act * jnp.exp(-2.0 * dv * m_j))
                        )
                        return (ll - val[0] * val[0] / (2 * PHASE_PRIOR**2))[None]

                    new_v = b0.slice_vec(
                        jax.random.fold_in(k_ph, j),
                        old_v[None],
                        logp_j,
                        PHASE_NOISE_WIDTH,
                    )[0]
                    lf_next = lf_cur.at[j].set(new_v)
                    u2_next = jnp.where(
                        active, u2_cur * jnp.exp(-2.0 * (new_v - old_v) * m_j), u2_cur
                    )
                    return (lf_next, u2_next), None

                (lf_new, _), _ = jax.lax.scan(
                    step_factor, (lf0, u2_0), jnp.arange(free)
                )
                factor = jnp.exp(lf_new)
        z2 = (r / row_sd(D, sigma, factor)) ** 2
        lam = jax.random.gamma(k3, (nu + 1) / 2, (n,)) / ((nu + z2) / 2)
        return nu, sigma, lam, factor

    def update_tau(key, st, M, g):
        z = jnp.diff(M) - float(walk_stride) * g
        ss, k = jnp.sum(z * z) / float(walk_stride), z.shape[0]

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
            Lk = jnp.linalg.cholesky(_gp_cov(gps[k][1], ls, *gp_kernels[k]))
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
        M_out = (
            M
            if full_wk_j is None
            else (1 - full_fr_j) * M[full_wk_j] + full_fr_j * M[full_wk_j + 1]
        )
        g = theta[i_g]
        beta = (
            jnp.zeros(len(d.names), theta.dtype)
            .at[jnp.asarray(others)]
            .set(theta[sl_b])
            .at[alpha]
            .set(M_out[0])
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
            L=M_out - M_out[0],
            eta=jnp.diff(M_out) - g,
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
        w1, Wb = unit_W(D, unit_hyp(st), c, st.get("ukap"))
        y_eff = D["y"] - offsets(D, st)
        theta, _ = draw_theta(D, k1, st, c, w1, Wb, y_eff)
        w = theta[sl_w]
        F = D["Bc"] @ w
        e0 = y_eff - all_means(D, theta)
        # y less every term but the buildings' levels, the collapsed paths and u.
        tgt = e0 if col is None else e0 + st["ar"][0].ravel()[D["ar_cell"][0]]
        # The scales move with all three integrated out, so the three are drawn afresh
        # below, at the new scales, before anything reads them.
        if "noise" not in fixed_steps:
            st = st | update_scales(D, k8, st, tgt, F)
        hyp = unit_hyp(st)
        c = weights(D, st)
        w1, Wb = unit_W(D, hyp, c, st.get("ukap"))
        om_d, om_off = pair_weights(D, w1, Wb)
        if col is None:
            ctil = om_d + seg(om_off, D["pi"], num_segments=n)
            C = seg(ctil, D["site"], num_segments=S)
            Rs = seg(apply_W(D, om_d, om_off, e0), D["site"], num_segments=S)
            bsd = update_spread(k2, st, C, Rs, F)
            b2 = site_var(bsd, st.get("kap"))
            P = C + 1 / b2
            lev = (Rs + F / b2) / P + jax.random.normal(k3, (S,)) / jnp.sqrt(P)
            e = e0 - lev[D["site"]]
            first = 0
        else:
            cell = D["ar_cell"][0]
            sums = cell_sums(D, om_d, om_off, tgt)
            if len(slow):
                theta, tgt, sums = update_slow(
                    D, k3, st, theta, om_d, om_off, sums, tgt, F
                )
            bsd, lev, par, path = update_cells(D, k2, st, sums, F)
            e = tgt - lev[D["site"]] - path.ravel()[cell]
            st = st | {
                "ar": (path, *st["ar"][1:]),
                "ar_par": st["ar_par"].at[0].set(par),
            }
            first = 1
        if unit_t:
            # The units' lasting levels are drawn with u, then nu_u and the mixing scales
            # given them, or under `unit_kap_collapsed` the mixing scales first, with u
            # integrated out. Their keys are folded in, as the buildings' mixing scales' is.
            ukap = st["ukap"]
            if unit_kap_collapsed:
                # The kap given e with u and s integrated out, then u and s given them.
                ukap = collapsed_kap(
                    D,
                    jax.random.fold_in(key, UNIT_KAP_KEY),
                    hyp,
                    st["unit_dof"],
                    ukap,
                    w1,
                    Wb,
                    e,
                    c,
                )
                w1, Wb = unit_W(D, hyp, c, ukap)
            u, s_unit = draw_us(D, k7, hyp, c, w1, Wb, e, ukap)
            unit_dof, ukap, hyp, pred_ukap = update_unit_t(
                jax.random.fold_in(key, UNIT_T_KEY),
                st,
                s_unit,
                hyp,
                ukap if unit_kap_collapsed else None,
            )
        else:
            u = draw_u(D, k7, hyp, c, w1, Wb, e)
        r, ar, ar_par = update_local(D, ks[9:], st, c, e - u, first)
        nu, sigma, lam, factor = update_noise(k4, st, r, D)
        for p_idx in range(1, scale_passes):
            kp = jax.random.fold_in(key, 500 + p_idx)
            kp_s, kp_b, kp_l, kp_u, kp_n, kp_k, kp_ut = jax.random.split(kp, 7)
            st_p = st | dict(
                bld_sd=bsd,
                nu=nu,
                sigma=sigma,
                lam=lam,
                hyp=hyp[:3] if unit_slow else hyp,
            )
            if phased:
                st_p["phase_scale"] = factor
            if unit_t:
                st_p |= dict(unit_dof=unit_dof, ukap=ukap, pred_ukap=pred_ukap)
            if ars:
                st_p["ar"], st_p["ar_par"] = tuple(ar), jnp.stack(ar_par)
            y_eff_p = D["y"] - offsets(D, st_p)
            e0_p = y_eff_p - all_means(D, theta)
            tgt_p = (
                e0_p if col is None else e0_p + st_p["ar"][0].ravel()[D["ar_cell"][0]]
            )
            if "noise" not in fixed_steps:
                st_p = st_p | update_scales(D, kp_s, st_p, tgt_p, F)
            hyp = unit_hyp(st_p)
            c = weights(D, st_p)
            w1, Wb = unit_W(D, hyp, c, st_p.get("ukap"))
            om_d, om_off = pair_weights(D, w1, Wb)
            if col is None:
                ctil = om_d + seg(om_off, D["pi"], num_segments=n)
                C = seg(ctil, D["site"], num_segments=S)
                Rs = seg(apply_W(D, om_d, om_off, e0_p), D["site"], num_segments=S)
                bsd = update_spread(kp_b, st_p, C, Rs, F)
                b2 = site_var(bsd, st_p.get("kap"))
                P = C + 1 / b2
                lev = (Rs + F / b2) / P + jax.random.normal(kp_l, (S,)) / jnp.sqrt(P)
                e = e0_p - lev[D["site"]]
            else:
                cell = D["ar_cell"][0]
                sums = cell_sums(D, om_d, om_off, tgt_p)
                bsd, lev, par, path = update_cells(D, kp_b, st_p, sums, F)
                e = tgt_p - lev[D["site"]] - path.ravel()[cell]
                ar = [path, *ar[1:]]
                ar_par = [par, *ar_par[1:]]
            if unit_t:
                ukap = st_p["ukap"]
                if unit_kap_collapsed:
                    ukap = collapsed_kap(
                        D, kp_k, hyp, st_p["unit_dof"], ukap, w1, Wb, e, c
                    )
                    w1, Wb = unit_W(D, hyp, c, ukap)
                u, s_unit = draw_us(D, kp_u, hyp, c, w1, Wb, e, ukap)
                unit_dof, ukap, hyp, pred_ukap = update_unit_t(
                    kp_ut, st_p, s_unit, hyp, ukap if unit_kap_collapsed else None
                )
            else:
                u = draw_u(D, kp_u, hyp, c, w1, Wb, e)
            nu, sigma, lam, factor = update_noise(kp_n, st_p, e - u, D)
            st = st_p
        tau = (
            st["tau"]
            if "tau" in fixed_steps
            else update_tau(k5, st, theta[sl_M], theta[i_g])
        )
        if "amp" in fixed_steps:
            amp = st["amp"]
        elif joint is None:
            amp = update_amp(k6, st, w)
        else:
            amp, w = joint(k6, lev, bsd, st["amp"], st.get("kap"))
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
            hyp=hyp[:3] if unit_slow else hyp,
            hyp_dirs=st["hyp_dirs"],
        )
        if unit_slow:
            new["unit_tau"] = st["unit_tau"]
        if phased:
            new["phase_scale"] = factor
        if unit_t:
            new |= dict(unit_dof=unit_dof, ukap=ukap, pred_ukap=pred_ukap)
        if dof is not None:
            # Each building's mixing scale given its level, its neighbourhood's and the
            # spread: the scale mixture's Gamma. Its key is folded in, so the other steps'
            # keys are the ones they had without this step.
            z2 = (lev - F) ** 2 / bsd[zone_j] ** 2
            new["kap"] = jax.random.gamma(
                jax.random.fold_in(key, KAP_KEY), (dof + 1) / 2, (S,)
            ) / ((dof + z2) / 2)
        if gps and "gp" in fixed_steps:
            new["gp_amp"], new["gp_ls"] = st["gp_amp"], st["gp_ls"]
        elif gps:
            new["gp_amp"], new["gp_ls"] = update_gp(k_gp, st, theta)
        ss, sd, tu = scales(hyp)
        out = outputs(theta, lev, F) | dict(unit_sd=ss, drift_sd=sd, drift_tau=tu)
        if phased:
            if pmap_j is None:
                out["phase_scale"] = phase_factors(factor)
            else:
                out["phase_factor"] = factor
        if dof_free:
            out["unit_dof"] = unit_dof
        if unit_slow:
            out["unit_tau"] = st["unit_tau"]
        if col is not None:
            new["cell_dirs"] = st["cell_dirs"]
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
        its prior in every sweep, so the mean carries that draw. Under `unit_t` a row of a
        unit with training rows takes its unit's mixing scale, and a row of a unit with
        none takes the state's draw from the prior (`update_unit_t`)."""
        c = weights(D, st)
        hyp = unit_hyp(st)
        ss, sd, _ = scales(hyp)
        k0 = ss**2 + sd**2
        vp = k0p = None
        if unit_t:
            pu = D["p_unit"]
            kp = jnp.where(pu >= 0, st["ukap"][jnp.maximum(pu, 0)], st["pred_ukap"])
            vp = ss**2 / kp
            k0p = vp + sd**2
        w1, Wb = unit_W(D, hyp, c, st.get("ukap"))
        om_d, om_off = pair_weights(D, w1, Wb)
        e = D["y"] - offsets(D, st) - all_means(D, st["theta"]) - st["lev"][D["site"]]
        We = apply_W(D, om_d, om_off, e)
        tp = D["p_years"]
        mean = jnp.zeros(n_pred)
        var = jnp.full(n_pred, k0) if k0p is None else k0p
        rows, tr = D["p_one"]
        if vp is None:
            k = kernel(hyp, tp[rows], D["t"][tr])
            var = var.at[rows].set(k0 - k * k * w1[tr])
        else:
            k = kernel(hyp, tp[rows], D["t"][tr], vp[rows])
            var = var.at[rows].set(k0p[rows] - k * k * w1[tr])
        mean = mean.at[rows].set(k * w1[tr] * e[tr])
        for (rows, slot), W, idx, mask, tb in zip(
            D["p_buckets"], Wb, D["b_idx"], D["b_mask"], D["b_t"]
        ):
            v = None if vp is None else vp[rows][:, None]
            ks = jnp.where(mask[slot], kernel(hyp, tp[rows, None], tb[slot], v), 0.0)
            mean = mean.at[rows].set(jnp.sum(ks * We[idx[slot]], axis=1))
            prior = k0 if k0p is None else k0p[rows]
            var = var.at[rows].set(prior - jnp.einsum("pa,pab,pb->p", ks, W[slot], ks))
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
            nu=5.0 * jit(k[1], (), 0.2) if nu_free else jnp.full((), row_dof_fixed),
            sigma=(
                jnp.broadcast_to(0.15 * jit(k[2], (1,), 0.1), (4,))
                if scalar_sigma
                else 0.15 * jit(k[2], (4,), 0.1)
            ),
            lam=jnp.ones(n),
            tau=0.005 * jit(k[3], (), 0.2),
            amp=0.5 * jit(k[4], (nz,), 0.2),
            hyp=jnp.log(jnp.asarray([0.05, 0.08, 3.0]))
            + 0.2 * jax.random.normal(k[5], (3,)),
            hyp_dirs=jnp.diag(
                jnp.asarray(
                    [HYP_WIDTH] * 3
                    + [SIGMA_WIDTH] * n_sigma
                    + [NU_WIDTH] * nu_free
                    + [PHASE_WIDTH] * k_ph
                    + [UNIT_DOF_WIDTH] * dof_free
                    + [UNIT_TAU_WIDTH] * unit_slow
                )
            ),
        )
        if unit_slow:
            out["unit_tau"] = UNIT_TAU_START * jit(jax.random.fold_in(key, 17), (), 0.2)
        if phased:
            out["phase_scale"] = jit(jax.random.fold_in(key, 13), (free,), 0.1)
        if dof is not None:
            out["kap"] = jnp.ones(S)
        if unit_t:
            out |= dict(
                unit_dof=(
                    10.0 * jit(jax.random.fold_in(key, UNIT_T_KEY), (), 0.2)
                    if dof_free
                    else jnp.full((), unit_dof_fixed)
                ),
                ukap=jnp.ones(U),
                pred_ukap=jnp.ones(n_pred),
            )
        if ars:
            out["ar"] = tuple(jnp.zeros((a["size"], a["T"])) for a in ars)
            out["ar_par"] = jnp.tile(
                jnp.asarray([math.log(0.03), 1.5]), (len(ars), 1)
            ) + (0.2 * jax.random.normal(jax.random.fold_in(key, 11), (len(ars), 2)))
        if col is not None:
            out["cell_dirs"] = jnp.diag(jnp.asarray(CELL_WIDTHS))
        if gps:
            kg = jax.random.split(jax.random.fold_in(key, 7))
            out["gp_amp"] = jnp.asarray(
                [(a[1] / a[0]) ** 0.5 for _, _, a, _ in gps]
            ) * jit(kg[0], (len(gps),), 0.2)
            out["gp_ls"] = jnp.exp(jnp.asarray([m for _, _, _, (m, _) in gps])) * jit(
                kg[1], (len(gps),), 0.2
            )
        # Every chain starts at the held values, and the sweep leaves them there.
        for k, v in held_state(scales_fixed, fixed_steps).items():
            if k == "ar_par":
                out[k] = out[k].at[0].set(jnp.asarray(v, dtype=out[k].dtype))
            else:
                out[k] = jnp.broadcast_to(
                    jnp.asarray(v, dtype=out[k].dtype), out[k].shape
                )
        return out

    swept = jax.jit(jax.vmap(sweep, in_axes=(None, 0, 0)))
    predicted = jax.jit(jax.vmap(predict, in_axes=(None, 0)))
    curved = jax.jit(jax.vmap(scales_curvature, in_axes=(None, 0)))
    em_stepped = jax.jit(em_step) if (em_laplace or em_warm > 0) else None
    laplaced = (
        jax.jit(jax.vmap(laplace_draw, in_axes=(None, 0, None))) if em_laplace else None
    )
    return (
        lambda keys, st: swept(data, keys, st),
        jax.jit(jax.vmap(init)),
        lambda st: predicted(data, st),
        dict(
            data=data,
            em_step=(
                (lambda st: em_stepped(data, st))
                if (em_laplace or em_warm > 0)
                else None
            ),
            laplace_draw=(
                (lambda keys, st_map: laplaced(data, keys, st_map))
                if em_laplace
                else None
            ),
            order=order,
            G=G,
            layout=lay,
            weights=weights,
            unit_W=unit_W,
            pair_weights=pair_weights,
            apply_W=apply_W,
            global_system=global_system,
            unit_loglik=unit_loglik,
            update_scales=update_scales,
            scales_x=scales_x,
            row_sd=row_sd,
            phased=phased,
            scales_k_ph=k_ph,
            scales_ph_idx=ph_idx_np,
            phase_factors=phase_factors,
            scales_logp=scales_logp,
            scales_curvature=scales_curvature,
            curvature=lambda st: curved(data, st),
            lam_moments=lam_moments,
            level_loglik=level_loglik,
            draw_theta=draw_theta,
            update_noise=update_noise,
            ar_filter=ar_filter,
            ar_draw=ar_draw,
            ar_sums=ar_sums,
            update_local=update_local,
            cell_sums=cell_sums,
            cell_system=cell_system,
            cell_loglik=cell_loglik,
            slow_system=slow_system,
            update_slow=update_slow,
            slow=slow,
            slow_shares=slow_shares,
            fill_path=fill_path,
            zone=zone,
            update_cells=update_cells,
            cell_layout=col,
            offsets=offsets,
            ars=ars,
            draw_u=draw_u,
            draw_us=draw_us,
            update_unit_t=update_unit_t,
            collapsed_kap=collapsed_kap,
            kap_logp=kap_logp,
            unit_t=unit_t,
            dof_free=dof_free,
            nu_free=nu_free,
            held=fixed_steps,
            unit_slow=unit_slow,
            unit_hyp=unit_hyp,
            predict=predict,
            all_means=all_means,
            kernel=kernel,
            slices=(sl_b, sl_M, i_g, sl_w),
        ),
    )


def adapted_dirs(hyp: np.ndarray) -> np.ndarray:
    """The slice directions for (log ss, log sd, log tau, log sigma of each group, log nu,
    then any noise phases' log factors) from warmup draws `hyp` (chains, sweeps, 8 or more):
    four times the Cholesky factor of the draws'
    covariance within chains, so that the interval of `update_scales` covers the slice. The
    same for the collapsed building path's (log sd, logit rho)."""
    dev = hyp - hyp.mean(axis=1, keepdims=True)
    cov = np.einsum("csi,csj->ij", dev, dev) / max(dev.shape[0] * (dev.shape[1] - 1), 1)
    cov = cov + 1e-10 * np.eye(cov.shape[0])
    return 4.0 * np.linalg.cholesky(cov)


def conditional_dirs(dirs: np.ndarray, H: np.ndarray):
    """Slice directions for the density `update_scales` samples, from its Hessian `H` in the
    coordinates of `dirs` (`scales_curvature`): four times a square root of the covariance
    -H^-1, mapped back through `dirs`. Also returns that covariance's eigenvalues in units
    of `dirs` / 4, which is the share of the posterior's variance one scale update can
    renew along each axis when `dirs` came from the posterior's covariance.

    `update_scales` draws the scales given theta and the rows' standardized mixing scales,
    and that density is narrower than the posterior and tilted against it. Directions cut
    from the posterior's covariance cross its ridge at an angle, each slice is then short,
    and one round of them moves the scales a small part of what the density allows. The
    pilots of 2026-11-10 showed it: the unit scales' autocorrelation time went from 8 to 28
    sweeps when the scale step took more parameters with directions from the posterior.

    Returns (`dirs`, None) when H is not finite or -H is not positive definite, which a
    state far from the mode of a skewed density can give."""
    if not np.isfinite(H).all():
        return dirs, None
    w, V = np.linalg.eigh(-(H + H.T) / 2)
    if w.min() <= 0:
        return dirs, None
    root = V / np.sqrt(w)
    return 4.0 * dirs @ root, np.sort(16.0 / w)


def run(
    d: Design,
    priors: Priors,
    settings: Settings,
    log=print,
    checkpoint=None,
    gp="spec",
    groups=None,
    unit_t: bool = False,
    unit_dof_fixed: float | None = None,
    unit_kap_collapsed: bool = False,
    row_dof_fixed: float | None = None,
    unit_slow: bool = False,
    phase_collapsed: bool = False,
    scalar_sigma: bool = False,
    walk_stride: int = 1,
    scale_passes: int = 1,
    scales_no_phase: bool = False,
    scales_phase_k: int | None = None,
    scales_phase_idx: tuple[int, ...] | None = None,
    slow_gps: bool = False,
    em_laplace: bool = False,
    em_warm: int = 0,
):
    """Sample the posterior of design `d` with the sweep above and the floor curves' Gaussian
    process priors. The kept arrays hold `building_zones_gibbs`'s, the unit scales `unit_sd`
    (ss), `drift_sd` and `drift_tau`. For the design's rows to predict they also hold
    `pred_loc` and `pred_unit_sd`, (chains, kept draws, rows), and the rows' `pred_y` and
    `pred_group`. A design with noise phases keeps `phase_scale`, every phase's factor,
    and each predicted row's `pred_phase`. With a phase map, only the free `phase_factor`
    values are traced and the cells are expanded on kept draws. Otherwise `phase_scale`
    is also traced. `unit_t`
    (`make_sampler`) adds the units' degrees of freedom `unit_dof` to both, unless
    `unit_dof_fixed` holds them at a value. `unit_kap_collapsed` is `make_sampler`'s. With `row_dof_fixed`
    (`make_sampler`) nu is traced and kept at its value, and the gate's diagnostics skip it
    as a constant. `unit_slow` (`make_sampler`) adds the lasting level's time constant
    `unit_tau` to both. `phase_collapsed` is `make_sampler`'s.

    With `settings.scales_fixed` the sweep holds that set's scales
    (`rentfrontier.drift_scales`). They are traced and kept at their values, the gate's
    diagnostics skip them as constants, and the result's `gibbs` entry records the set, its
    source and its values. The warmup sets no slice directions for a skipped step."""
    jax, jnp = b0._jax()
    gp = gp_spec(d.names) if gp == "spec" else gp
    fixed, fixed_source = (
        drift_scales.resolve(settings.scales_fixed)
        if settings.scales_fixed
        else (None, None)
    )
    t0 = time.perf_counter()
    sweep, init, predict, parts = make_sampler(
        d,
        priors,
        settings,
        gp=gp,
        groups=groups,
        unit_t=unit_t,
        unit_dof_fixed=unit_dof_fixed,
        unit_kap_collapsed=unit_kap_collapsed,
        row_dof_fixed=row_dof_fixed,
        unit_slow=unit_slow,
        phase_collapsed=phase_collapsed,
        scales_fixed=fixed,
        scalar_sigma=scalar_sigma,
        walk_stride=walk_stride,
        scale_passes=scale_passes,
        scales_no_phase=scales_no_phase,
        scales_phase_k=scales_phase_k,
        scales_phase_idx=scales_phase_idx,
        slow_gps=slow_gps,
        em_laplace=em_laplace,
        em_warm=em_warm,
    )
    held = parts["held"]
    if held:
        log(
            f"scales held at the set {settings.scales_fixed!r} "
            f"(from {fixed_source}): {fixed}"
        )
    local = tuple(g["name"] + s for g in groups or () for s in ("_ar_sd", "_ar_rho"))
    scale_names = ("nu", "sigma", "tau", "amp", "bld_sd") + (
        ("gp_amp", "gp_ls") if gp else ()
    )
    mapped = parts["phased"] and d.phase_map is not None
    phase = ("phase_factor" if mapped else "phase_scale",) if parts["phased"] else ()
    expand_phase = jax.jit(jax.vmap(parts["phase_factors"])) if mapped else None
    more = (
        phase
        + (("unit_dof",) if parts["dof_free"] else ())
        + (("unit_tau",) if unit_slow else ())
    )
    traced = TRACED + HYP + local + (("gp_amp", "gp_ls") if gp else ()) + more
    kept_names = KEPT + HYP + local + (("gp_amp", "gp_ls") if gp else ()) + more
    key = jax.random.PRNGKey(settings.seed)
    key, sub = jax.random.split(key)
    st = init(jax.random.split(sub, settings.chains))
    jax.block_until_ready(st)
    setup_seconds = time.perf_counter() - t0

    trace = {k: [] for k in traced}
    kept = {k: [] for k in kept_names}
    if expand_phase is not None:
        kept["phase_scale"] = []
    preds = {"pred_loc": [], "pred_unit_sd": []}
    has_pred = d.pred is not None and len(d.pred["unit"]) > 0
    if not has_pred:
        log("the split leaves no row to predict: this fit will have no pred_loc")
    total = settings.warmup + settings.draws
    per = max(1, settings.draws // settings.chunks)
    marks = {"warmup": None}
    # The slice directions of `update_scales` are set twice in the warmup, at a third and at two
    # thirds of it, each time from the sweeps of the sixth of the warmup before: the first
    # setting lets the scales move along their trade-offs, and the second measures them.
    adapt_at = {
        (k * settings.warmup) // 3: (k * settings.warmup) // 3 - settings.warmup // 6
        for k in (1, 2)
    }
    warm_hyp, warm_cell = {}, {}

    def output(final=False):
        stack = lambda v: np.stack(v, axis=1)  # noqa: E731
        now = time.perf_counter()
        sampling = now - marks["warmup"] if marks["warmup"] else 0.0
        warm = (marks["warmup"] or now) - t_first
        done = len(trace[traced[0]])
        extra = {}
        if preds["pred_loc"]:
            extra = (
                {k: stack(v) for k, v in preds.items()}
                | {
                    "pred_y": np.asarray(d.pred["y"]),
                    "pred_group": np.asarray(d.pred["group"]),
                }
                | ({"pred_phase": np.asarray(d.pred["phase"])} if phase else {})
            )
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
                    "G_dim": int(parts["G"]),
                    "n_sigma": 1 if scalar_sigma else 4,
                    "walk_stride": int(walk_stride),
                    "scale_passes": int(scale_passes),
                    "n_gp": len(gp or ()),
                    "has_bld_ar": bool(groups),
                    "hyp_dirs": np.asarray(st["hyp_dirs"][0]).tolist(),
                }
                | (
                    {"cell_dirs": np.asarray(st["cell_dirs"][0]).tolist()}
                    if "cell_dirs" in st
                    else {}
                )
                | (
                    {
                        "scales_fixed": {
                            "set": settings.scales_fixed,
                            "source": fixed_source,
                            "values": fixed,
                        }
                    }
                    if held
                    else {}
                )
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
            + (
                f"phase_scale {np.asarray(st['phase_scale'])[:2].round(4).tolist()}, "
                if phase
                else ""
            )
            + (
                f"unit_dof {np.asarray(st['unit_dof'])[:4].round(2).tolist()}, "
                if unit_t
                else ""
            )
            + (
                f"unit_tau {np.asarray(st['unit_tau'])[:4].round(2).tolist()}, "
                if unit_slow
                else ""
            )
        ) + "".join(
            f"{g['name']} sd {np.exp(np.asarray(st['ar_par'])[:4, k, 0]).round(4).tolist()} "
            f"rho {(1 / (1 + np.exp(-np.asarray(st['ar_par'])[:4, k, 1]))).round(3).tolist()}, "
            for k, g in enumerate(groups or ())
        )

    if parts["slow_shares"]:
        log(
            f"{len(parts['slow'])} of {len(parts['slow_shares'])} named columns are redrawn "
            "with the building paths integrated out; each one's share of variance within "
            f"buildings: { {k: round(v, 4) for k, v in parts['slow_shares'].items()} }"
        )
    compile_seconds = 0.0
    t_first = time.perf_counter()
    if em_laplace:
        assert held, "em_laplace requires --scales-fixed"
        st_map = jax.tree_util.tree_map(lambda a: a[0], st)
        em_fn = parts["em_step"]
        lap_fn = parts["laplace_draw"]
        for i in range(settings.warmup):
            st_prev_th = st_map["theta"]
            st_map = em_fn(st_map)
            if i == 0:
                jax.block_until_ready(st_map)
                compile_seconds = time.perf_counter() - t_first
                t_first = time.perf_counter()
                log(f"em_laplace first EM step (compile) {compile_seconds:.1f}s")
            if (i + 1) % max(1, settings.warmup // 5) == 0 or i == settings.warmup - 1:
                d_th = float(jnp.max(jnp.abs(st_map["theta"] - st_prev_th)))
                log(
                    f"em_laplace iter {i + 1}/{settings.warmup}: max|dtheta|={d_th:.2e}, "
                    f"{time.perf_counter() - t_first:.1f}s"
                )
        jax.block_until_ready(st_map)
        marks["warmup"] = time.perf_counter()
        t_lap_comp = time.perf_counter()
        for j in range(settings.draws):
            key, sub = jax.random.split(key)
            st_draw, out = lap_fn(jax.random.split(sub, settings.chains), st_map)
            if j == 0:
                jax.block_until_ready(st_draw)
                log(
                    f"em_laplace first Laplace draw (compile) "
                    f"{time.perf_counter() - t_lap_comp:.1f}s"
                )
            full = out | {k: st_draw[k] for k in scale_names}
            for k in traced:
                trace[k].append(np.asarray(full[k]))
            if (j + 1) % settings.keep_every == 0:
                for k in kept_names:
                    kept[k].append(np.asarray(full[k]))
                if expand_phase is not None:
                    kept["phase_scale"].append(
                        np.asarray(expand_phase(full["phase_factor"]))
                    )
                if has_pred:
                    loc, s, _ = predict(st_draw)
                    preds["pred_loc"].append(np.asarray(loc))
                    preds["pred_unit_sd"].append(np.asarray(s))
            if (j + 1) % per == 0:
                log(
                    f"em_laplace draws {j + 1}/{settings.draws}: "
                    f"{time.perf_counter() - marks['warmup']:.1f}s"
                )
        st = st_draw
        return output(final=True)
    if em_warm > 0:
        t_em = time.perf_counter()
        st_map = jax.tree_util.tree_map(lambda a: a[0], st)
        em_fn = parts["em_step"]
        for _ in range(em_warm):
            st_map = em_fn(st_map)
        jax.block_until_ready(st_map)
        log(
            f"em_warm: {em_warm} deterministic EM steps in {time.perf_counter() - t_em:.1f}s"
        )
        # Warm-start every chain's latent state at the EM mode while preserving scale inits.
        for k_em in ("theta", "lev", "lam", "kap", "ukap"):
            if k_em in st and k_em in st_map:
                st = st | {k_em: jnp.broadcast_to(st_map[k_em][None], st[k_em].shape)}
        if "ar" in st and "ar" in st_map:
            st = st | {
                "ar": tuple(
                    jnp.broadcast_to(a[None], b.shape)
                    for a, b in zip(st_map["ar"], st["ar"])
                )
            }
        t_first = time.perf_counter()
    for i in range(total):
        key, sub = jax.random.split(key)
        st, out = sweep(jax.random.split(sub, settings.chains), st)
        if i == 0:
            jax.block_until_ready(st)
            compile_seconds = time.perf_counter() - t_first
            t_first = time.perf_counter()
            log(f"first sweep (compile) {compile_seconds:.1f}s")
        if i < settings.warmup:
            sig_warm = (
                np.log(np.asarray(st["sigma"])[:, :1])
                if scalar_sigma
                else np.log(np.asarray(st["sigma"]))
            )
            warm_hyp[i] = np.concatenate(
                [
                    np.asarray(st["hyp"]),
                    sig_warm,
                ]
                + ([np.log(np.asarray(st["nu"]))[:, None]] if parts["nu_free"] else [])
                + (
                    [np.log(np.asarray(st["phase_scale"])[:, parts["scales_ph_idx"]])]
                    if parts["scales_k_ph"] > 0
                    else []
                )
                + (
                    [np.log(np.asarray(st["unit_dof"]))[:, None]]
                    if parts["dof_free"]
                    else []
                )
                + ([np.log(np.asarray(st["unit_tau"]))[:, None]] if unit_slow else []),
                axis=1,
            )
            if "cell_dirs" in st and "cells" not in held:
                warm_cell[i] = np.asarray(st["ar_par"])[:, 0]
        adapting = i + 1 in adapt_at and i + 1 - adapt_at[i + 1] >= 10
        # With the scale step's scales held, its directions have nothing to follow.
        if adapting and "noise" not in held:
            window = [warm_hyp[j] for j in range(adapt_at[i + 1], i + 1)]
            dirs = adapted_dirs(np.stack(window, axis=1))
            st = st | {
                "hyp_dirs": jnp.broadcast_to(jnp.asarray(dirs), st["hyp_dirs"].shape)
            }
            log(
                f"scales' slice directions set at sweep {i + 1}: {dirs.round(5).tolist()}"
            )
            H = np.asarray(parts["curvature"](st)).mean(axis=0)
            dirs, share = conditional_dirs(dirs, H)
            if share is None:
                log(
                    "the scale step's curvature is not negative definite: directions kept"
                )
            else:
                st = st | {
                    "hyp_dirs": jnp.broadcast_to(
                        jnp.asarray(dirs), st["hyp_dirs"].shape
                    )
                }
                log(
                    "reset along the scale step's own curvature; its variance over the "
                    f"window's, by axis: {share.round(3).tolist()}"
                )
        if adapting and warm_cell:
            window = [warm_cell[j] for j in range(adapt_at[i + 1], i + 1)]
            dirs = adapted_dirs(np.stack(window, axis=1))
            st = st | {
                "cell_dirs": jnp.broadcast_to(jnp.asarray(dirs), st["cell_dirs"].shape)
            }
            log(f"the building path's slice directions: {dirs.round(5).tolist()}")
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
                if expand_phase is not None:
                    kept["phase_scale"].append(
                        np.asarray(expand_phase(full["phase_factor"]))
                    )
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
                mid = settings.checkpoints and j + 1 < settings.draws
                if mid and checkpoint is not None and kept["beta"]:
                    checkpoint(output())
            spent = time.perf_counter() - t_first
            if (
                settings.budget_seconds is not None
                and spent > settings.budget_seconds
                and (j + 1) % settings.keep_every == 0
                and j + 1 < settings.draws
            ):
                log(
                    f"stopping at draw {j + 1} of {settings.draws}: the sweeps have taken "
                    f"{spent:.0f}s of a budget of {settings.budget_seconds:.0f}s"
                )
                break
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
    """The kitchen sink's convergence table, with the three unit scales, the local-drift
    terms' scales, any noise phases' factors and the units' degrees of freedom under
    `unit_t`."""
    from .run import ESS_GATE, RHAT_GATE, ess, split_rhat

    out = building_zones_kitchen_sink.diagnostics(trace, names)
    rows = out["per_quantity"]
    quantities = {
        k: trace[k]
        for k in [*HYP, *(k for k in trace if k.endswith(("_ar_sd", "_ar_rho")))]
    }
    for k in ("unit_dof", "unit_tau"):
        if k in trace:
            quantities[k] = trace[k]
    # The constant reference in an unmapped phase_scale is skipped below.
    phase_key = "phase_factor" if "phase_factor" in trace else "phase_scale"
    if phase_key in trace:
        f = np.asarray(trace[phase_key])
        quantities |= {f"{phase_key}[{j}]": f[..., j] for j in range(f.shape[-1])}
    for k, x in quantities.items():
        x = np.asarray(x)
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
    phase_key = "phase_factor" if "phase_factor" in kept else "phase_scale"
    if phase_key in kept:
        f = np.asarray(kept[phase_key])
        out[phase_key] = [two_zone._q(f[..., j]) for j in range(f.shape[-1])]
    for k in ("unit_dof", "unit_tau"):
        if k in kept:
            out["unit"][k] = two_zone._q(np.asarray(kept[k]))
    return out


def run_record(d: Design, groups=()) -> dict:
    """The kitchen sink's record, with the unit term's settings and those of the local-drift
    terms named in `groups`."""
    local = {
        g["name"]: {
            "groups": g["size"],
            "steps_per_year": g["per_year"],
            "collapsed": bool(g.get("collapsed")),
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


def _level_dof(text: str) -> float | None:
    """`--level-dof`'s value. 0 asks for the normal prior, which a model whose default is
    a Student-t has no other way to name."""
    value = float(text)
    if not (0 <= value < float("inf")):
        raise argparse.ArgumentTypeError(
            f"{text!r} is not a number of degrees of freedom (0 for the normal prior)"
        )
    return value or None


def run_parser(name=NAME, level_dof=None):
    """The command line of `rentfrontier.run --model NAME`. `level_dof` is the model's own
    default for `Settings.level_dof`."""
    parser = b0.run_parser()
    parser.prog = f"rentfrontier.run --model {name}"
    parser.set_defaults(model=name)
    parser.add_argument("--site-block", type=int)
    parser.add_argument(
        "--budget-seconds",
        type=float,
        help="stop drawing once sweeps exceed this many seconds "
        "(default: Settings.budget_seconds)",
    )
    parser.add_argument(
        "--level-dof",
        type=_level_dof,
        default=level_dof,
        help="degrees of freedom of a Student-t prior on the buildings' levels; 0 for a "
        f"normal prior (default: {level_dof or 'a normal prior'})",
    )
    parser.add_argument(
        "--scales-fixed",
        help="hold the scales of this set in rentfrontier.drift_scales or a converged run "
        "directory at their posterior means (default: the sweep draws every scale)",
    )
    return parser


def main_run(argv, name=NAME, sample=None, spec=None, level_dof=None) -> None:
    """`rentfrontier.run --model drift`: fit on the split's training rows and save the run.
    The modules that add local-drift terms pass their own `name`, `sample` and `spec`, and
    may pass their own default for `--level-dof`."""
    parser = run_parser(name, level_dof)
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
