"""Building zones with building age and the unit's floor: a smooth floor curve for elevator
buildings and another for walk-ups, with flags for special floors on top.

The model is building zones with building age (`rentfrontier.building_zones_age`), with floor
columns appended. I read each listing's floor and flags from the unit floor snapshot
(`rentfrontier.unit_floor`) and put the listing's building in one of two groups:
- the elevator group, for a building coded with an elevator;
- the walk-up group, for every other building. This includes the 0.7% of training ads in
  buildings with an unknown elevator, since their floors look like walk-up floors (median 2,
  3% above floor 5). `bld:elevator_unknown` still moves their level.

Each group gets a curve over floors, measured from floor 1. I give a unit on floor k >= 2 a
1 in its group's column for that floor, `unit:elev_f{k}` or `unit:walkup_f{k}`, and a unit on
floor 1 none. I cap the floor at ELEV_CAP in elevator buildings and WALKUP_CAP in walk-ups,
about the 99th percentile of each group's training ads, so a unit above the cap gets the cap's
column. The curve's values at floors 2 to the cap are these columns' coefficients, and I give
them a Gaussian process prior in place of separate Normal priors
(`building_zones_gibbs.make_sampler`):

    f_group(log k) ~ GP(0, amp^2 SE(lengthscale)),  pinned to f(log 1) = 0

The input is the log of the floor. Going from floor 2 to 4 changes the light, the noise and
the stairs a lot more than going from 32 to 34, so I expect the curve to move fast near the
ground and slowly high up, and a single lengthscale fits that on the log scale. Each group's
amplitude has a HalfNormal(GP_AMP) prior and its lengthscale a LogNormal(GP_LS) prior, and the
sampler draws both every sweep. I keep every floor column even where no training row sets it,
so the process fills in those floors from their neighbours.

On top of the curve at the unit's floor I add these flags, against a unit without them:

    unit:elev_top                the building's top floor, in an elevator building
    unit:walkup_top              the building's top floor, in a walk-up
    unit:penthouse               a penthouse label
    unit:garden                  a garden or ground label, on floor 1
    unit:lower                   a basement, cellar or lower-level label, on floor 1
    unit:elev_floor_unknown      no floor, in an elevator building, against floor 1
    unit:walkup_floor_unknown    no floor, in a walk-up, against floor 1

A listing missing from the snapshot gets its group's unknown flag. The flags keep the
Normal(0, 0.5) prior and I leave out a flag no row sets. A 10th floor unit on its building's
top floor in an elevator building then gets f_elev(log 10) + `unit:elev_top`.

    python -m rentfrontier.run --model building-zones-floor --split latest --name NAME
"""

from __future__ import annotations

import dataclasses
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import (
    b0,
    building_zones_age,
    building_zones_gibbs,
    building_zones_unit,
    two_zone,
)
from .building_zones_unit import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    BLD_SD_PRIOR,
    KEPT,
    PROGRESS,
    TRACED,
    ZONES,
    Design,
    Priors,
    Settings,
    site_rows,
    site_zone,
    split_index,
    subset,
    wave_matrix,
)
from .registry import EXTERNAL_ROOT

NAME = "building-zones-floor"
FLOOR_SNAPSHOT = Path(
    os.environ.get(
        "FRONTIER_UNIT_FLOOR",
        EXTERNAL_ROOT / "unit-floor" / "20261021-d84914c0",
    )
)
# The highest floor each group's curve reaches: about the 99th percentile of the group's
# training ads with a known floor on the 2026-10-21 snapshot (elevator 47, walk-up 6).
ELEV_CAP = 47
WALKUP_CAP = 6
GROUPS = (("elev", ELEV_CAP), ("walkup", WALKUP_CAP))
# The amplitude's HalfNormal scale, and the mean and sd of the log lengthscale on log floor.
GP_AMP = 0.2
GP_LS = (math.log(0.7), 0.5)
FLAGS = (
    "unit:elev_top",
    "unit:walkup_top",
    "unit:penthouse",
    "unit:garden",
    "unit:lower",
    "unit:elev_floor_unknown",
    "unit:walkup_floor_unknown",
)
CURVE = tuple(f"unit:{g}_f{k}" for g, cap in GROUPS for k in range(2, cap + 1))
COLUMNS = CURVE + FLAGS


def columns(
    frame: pd.DataFrame, floors: pd.DataFrame, elevator: np.ndarray
) -> np.ndarray:
    """The new columns (COLUMNS) of `frame`'s rows. `elevator` is the rows' `bld:elevator`."""
    f = floors.drop_duplicates("listing_id").set_index("listing_id")
    f = f.reindex(frame.listing_id.astype(str))
    floor = f.floor.to_numpy(float)
    top = f.top.fillna(0.0).to_numpy(float) == 1
    flag = {
        k: f[k].fillna(0.0).to_numpy(float) == 1
        for k in ("penthouse", "garden", "lower")
    }
    group = {"elev": elevator == 1, "walkup": elevator != 1}
    curve = []
    for g, cap in GROUPS:
        k = np.minimum(floor, cap)
        curve += [group[g] & (k == j) for j in range(2, cap + 1)]
    return np.column_stack(
        [
            *curve,
            top & group["elev"],
            top & group["walkup"],
            flag["penthouse"],
            flag["garden"],
            flag["lower"],
            np.isnan(floor) & group["elev"],
            np.isnan(floor) & group["walkup"],
        ]
    ).astype(float)


def design(
    frame: pd.DataFrame,
    start: pd.Timestamp | None = None,
    registry: pd.DataFrame | None = None,
    nj_registry: pd.DataFrame | None = None,
    attrs: pd.DataFrame | None = None,
    footprints: pd.DataFrame | None = None,
    units: pd.DataFrame | None = None,
    trucks: pd.DataFrame | None = None,
    gyms: pd.DataFrame | None = None,
    ages: pd.DataFrame | None = None,
    floors: pd.DataFrame | None = None,
) -> Design:
    """Building zones with building age's design of `frame` with the floor columns appended.
    I keep every curve column and leave out a flag no row sets."""
    if floors is None:
        floors = pd.read_parquet(FLOOR_SNAPSHOT / "floor.parquet")
    d = building_zones_age.design(
        frame,
        start,
        registry=registry,
        nj_registry=nj_registry,
        attrs=attrs,
        footprints=footprints,
        units=units,
        trucks=trucks,
        gyms=gyms,
        ages=ages,
    )
    new = columns(frame, floors, d.x[:, d.names.index("bld:elevator")])
    count = dict(d.count)
    keep = []
    for j, n in enumerate(COLUMNS):
        count[n] = int((new[:, j] != 0).sum())
        if count[n] > 0 or n in CURVE:
            keep.append(j)
    return dataclasses.replace(
        d,
        x=np.hstack([d.x, new[:, keep]]),
        names=list(d.names) + [COLUMNS[j] for j in keep],
        count=count,
    )


def gp_spec(names) -> list[dict]:
    """The floor curves' Gaussian process priors for `building_zones_gibbs.make_sampler`, one
    per group with curve columns in `names`, each with its group's name."""
    out = []
    for g, cap in GROUPS:
        cols = [f"unit:{g}_f{k}" for k in range(2, cap + 1)]
        cols = [c for c in cols if c in names]
        if cols:
            k = [float(c.rsplit("_f", 1)[1]) for c in cols]
            out.append(dict(name=g, cols=cols, x=np.log(k), amp=GP_AMP, ls=GP_LS))
    return out


def run(d: Design, priors: Priors, settings: Settings, log=print, checkpoint=None):
    """The blocked Gibbs sweep with the floor curves' Gaussian process priors."""
    return building_zones_gibbs.run(
        d, priors, settings, log, checkpoint, gp=gp_spec(d.names)
    )


def _gp_extras(trace: dict, names) -> dict:
    """Each floor curve's amplitude and lengthscale draws, by name."""
    out = {}
    for k, spec in enumerate(gp_spec(names)):
        for q in ("gp_amp", "gp_ls"):
            out[f"{q}[{spec['name']}]"] = np.asarray(trace[q])[..., k]
    return out


def diagnostics(trace: dict, names) -> dict:
    """Building zones with unit features' convergence table, with each floor curve's
    amplitude and lengthscale."""
    from .run import ESS_GATE, RHAT_GATE, ess, split_rhat

    out = building_zones_unit.diagnostics(trace, names)
    rows = out["per_quantity"]
    for n, x in _gp_extras(trace, names).items():
        rows[n] = {"rhat": split_rhat(x), "ess": ess(x)}
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
    """Building zones with unit features' summary, with each floor curve's amplitude and
    lengthscale."""
    out = building_zones_unit.summarize(kept, names)
    out["floor_gp"] = {n: two_zone._q(x) for n, x in _gp_extras(kept, names).items()}
    return out


def run_record(d: Design) -> dict:
    """Building zones with building age's record, with the floor snapshot and the curves'
    settings."""
    return building_zones_age.run_record(d) | {
        "unit_floor": str(FLOOR_SNAPSHOT),
        "floor_gp": {
            "caps": dict(GROUPS),
            "input": "log floor",
            "amp_halfnormal": GP_AMP,
            "log_ls_normal": list(GP_LS),
            "nugget": building_zones_gibbs.GP_NUGGET,
        },
    }


def main_run(argv) -> None:
    """`rentfrontier.run --model building-zones-floor`: fit on the split's training rows and
    save the run."""
    parser = b0.run_parser()
    parser.prog = f"rentfrontier.run --model {NAME}"
    parser.set_defaults(model=NAME)
    parser.add_argument("--site-block", type=int)
    b0.main_run(
        argv,
        parser=parser,
        name=NAME,
        settings_cls=Settings,
        sample=run,
        line="baseline",
        spec=sys.modules[__name__],
    )
