"""Building zones on Gibbs, with each building's level centred on its map value plus a few of
its measured qualities.

The model is building zones on Gibbs (`rentfrontier.building_zones_gibbs`) with the building
levels' mean moved:

    eta_s ~ Normal(F(s) + x_s' gamma, b_z)        gamma_j ~ Normal(0, 0.5)
    y ~ StudentT(nu, x beta + eta_site + L(t), sigma_group)

x_s holds eight columns, each constant within a building:

1. `bld:log_height`, the log of the building's roof height in the NYC building footprints
   (`height_roof`, joined on the registry's BIN), over HEIGHT_REF. HEIGHT_REF, 78 ft, rounds the
   geometric mean height of the NYC-only v36 dense rows with a height, 78.5 ft. I set
   `bld:height_unknown` where the BIN is a placeholder (N000000) or missing, or where no
   footprint gives it a positive height, and give those buildings no fallback to MapPLUTO's
   floor count.
2. `bld:elevator` and `bld:elevator_unknown`, against a building without one, as the
   building-attributes snapshot codes them (`building_attrs.ATTRS`: the ads first, then the
   MapPLUTO class).
3. `bld:condo`, a MapPLUTO class starting with R, against every other building.
4. `bld:doorman_full`, `bld:doorman_part` and `bld:doorman_virtual`, against a building
   whose ads state none, from the same snapshot.

Moving x_s' gamma from the level's mean into each row's mean leaves the model unchanged,
since every row of a building sees the same x_s. I append the eight columns to the rows'
fixed design, so gamma joins the global block the Gibbs sweep draws exactly, with the
levels integrated out, and its prior is the Normal(0, 0.5) that `b0.prior_arrays` gives a
column outside its named groups. The saved building effects `bld` are eta_s - F(s) -
x_s' gamma, each building's departure from the map net of its attributes.

The surfaces are whitened zones' at LENGTHSCALE, 1 km. `rentfrontier.building_zones_attrs_500m`
runs the same model with every zone's surface at 500 m.

    python -m rentfrontier.run --model building-zones-attrs --split latest --name NAME
"""

from __future__ import annotations

import dataclasses
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import (
    b0,
    building_attrs,
    building_zones,
    building_zones_gibbs,
    two_zone,
    whitened_zones,
)
from .building_zones_gibbs import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    BLD_SD_PRIOR,
    KEPT,
    PROGRESS,
    TRACED,
    ZONES,
    Design,
    Priors,
    Settings,
    diagnostics,
    site_rows,
    site_zone,
    split_index,
    subset,
    wave_matrix,
)
from .registry import EXTERNAL_ROOT

NAME = "building-zones-attrs"
FOOTPRINTS = Path(
    os.environ.get(
        "FRONTIER_FOOTPRINTS",
        EXTERNAL_ROOT / "footprints" / "20261016-5f07157-all" / "footprints.parquet",
    )
)
LENGTHSCALE = whitened_zones.LENGTHSCALE  # km
HEIGHT_REF = 78.0  # feet
COLUMNS = (
    "bld:log_height",
    "bld:height_unknown",
    "bld:elevator",
    "bld:elevator_unknown",
    "bld:condo",
    "bld:doorman_full",
    "bld:doorman_part",
    "bld:doorman_virtual",
)


def roof_heights(registry: pd.DataFrame, footprints: pd.DataFrame) -> pd.Series:
    """Each registry building's roof height in feet, NaN where its BIN is missing or a
    placeholder, or its footprint gives no positive height."""
    reg = registry.drop_duplicates("building").set_index("building")
    bins = reg.bin.astype("string")
    placeholder = bins.str.fullmatch(r"[1-5]000000").fillna(True).astype(bool)
    height = pd.to_numeric(footprints.height_roof, errors="coerce")
    by_bin = height.groupby(footprints.bin.astype(str)).max()
    out = bins.astype(str).map(by_bin).astype(float)
    out[placeholder.to_numpy()] = np.nan
    return out.where(out > 0)


def columns(frame: pd.DataFrame, heights: pd.Series, attrs: pd.DataFrame) -> np.ndarray:
    """The building columns (COLUMNS) of `frame`'s rows."""
    h = frame.building.astype(str).map(heights).to_numpy(float)
    known = np.isfinite(h)
    a = attrs.set_index("building").reindex(frame.building.astype(str))
    elevator = a.elevator.fillna("unknown").to_numpy()
    doorman = a.doorman.fillna("none").to_numpy()
    tenure = a.tenure.fillna("rental").to_numpy()
    x = np.column_stack(
        [
            np.where(known, np.log(np.where(known, h, HEIGHT_REF) / HEIGHT_REF), 0.0),
            ~known,
            elevator == "yes",
            elevator == "unknown",
            tenure == "condo",
            doorman == "full",
            doorman == "part",
            doorman == "virtual",
        ]
    ).astype(float)
    return x


def surfaces_at(
    d: Design,
    frame: pd.DataFrame,
    registry: pd.DataFrame,
    nj_registry: pd.DataFrame | None,
    lengthscale: float,
) -> list[dict]:
    """Whitened zones' surfaces of `d` rebuilt at `lengthscale` km, each zone's buildings in
    the order `whitened_zones.design` gives them."""
    if nj_registry is None:
        nj_registry = pd.read_parquet(
            whitened_zones.NJ_REGISTRY, columns=["building", "latitude", "longitude"]
        )
    sites = whitened_zones.sites_of(frame, registry, nj_registry)
    out = []
    for s in d.surfaces:
        on = sites[sites.zone == ZONES.index(s["name"])]
        assert len(on) == s["sites"], (s["name"], len(on), s["sites"])
        B, sd, shape = two_zone.zone_basis(
            on.x.to_numpy(), on.y.to_numpy(), lengthscale
        )
        out.append(
            {"name": s["name"], "basis": B, "sd": sd, "first": s["first"]}
            | {"sites": s["sites"], **shape}
        )
    return out


def design(
    frame: pd.DataFrame,
    start: pd.Timestamp | None = None,
    registry: pd.DataFrame | None = None,
    nj_registry: pd.DataFrame | None = None,
    attrs: pd.DataFrame | None = None,
    footprints: pd.DataFrame | None = None,
    lengthscale: float | None = None,
) -> Design:
    """Whitened zones' design of `frame` with the building columns appended. I leave out a
    column no row sets, as B0 does for its indicators. `lengthscale` (km) rebuilds the
    surfaces at another scale."""
    if registry is None:
        registry = pd.read_parquet(
            whitened_zones.REGISTRY,
            columns=["building", "bbl", "bin", "latitude", "longitude"],
        )
    if attrs is None:
        attrs = pd.read_parquet(building_attrs.ATTRS)
    if footprints is None:
        footprints = pd.read_parquet(FOOTPRINTS, columns=["bin", "height_roof"])
    d = whitened_zones.design(frame, start, registry=registry, nj_registry=nj_registry)
    lengthscale = LENGTHSCALE if lengthscale is None else lengthscale
    if lengthscale != whitened_zones.LENGTHSCALE:
        d = dataclasses.replace(
            d, surfaces=surfaces_at(d, frame, registry, nj_registry, lengthscale)
        )
    new = columns(frame, roof_heights(registry, footprints), attrs)
    count = dict(d.count)
    keep = []
    for j, n in enumerate(COLUMNS):
        count[n] = int(np.abs(new[:, j]).sum())
        if count[n] > 0:
            keep.append(j)
    return dataclasses.replace(
        d,
        x=np.hstack([d.x, new[:, keep]]),
        names=list(d.names) + [COLUMNS[j] for j in keep],
        count=count,
    )


def run_record(d: Design) -> dict:
    """Building zones on Gibbs' record, with the attribute sources and the height reference."""
    return building_zones_gibbs.run_record(d) | {
        "building_attrs": str(building_attrs.ATTRS),
        "footprints": str(FOOTPRINTS),
        "height_ref_ft": HEIGHT_REF,
    }


def summarize(kept: dict, names) -> dict:
    """Building zones' summary, with each building coefficient as a percent premium: for
    `bld:log_height`, a building e times as tall."""
    out = building_zones.summarize(kept, names)
    beta = np.asarray(kept["beta"])
    out["building"] = {}
    for j, n in enumerate(names):
        if n.startswith("bld:"):
            v = 100 * np.expm1(beta[..., j]).ravel()
            out["building"][n] = {
                "median": float(np.median(v)),
                "lo": float(np.quantile(v, 0.05)),
                "hi": float(np.quantile(v, 0.95)),
            }
    return out


def run(d: Design, priors: Priors, settings: Settings, log=print, checkpoint=None):
    """Building zones on Gibbs' sweep, on the design with the building columns."""
    return building_zones_gibbs.run(d, priors, settings, log, checkpoint)


def main_run(argv) -> None:
    """`rentfrontier.run --model building-zones-attrs`: fit on the split's training rows and
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
