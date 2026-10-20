"""Building attributes: the normal walk with a few measured qualities of each row's building.

I keep the normal walk (`rentfrontier.normal_walk`) as it is, with no location term, and add
twelve columns to its fixed design. Each column describes the row's building:

1. `bld:log_floors`, log(floors / 5), and `bld:floors_unknown`;
2. `bld:elevator` and `bld:elevator_unknown`, against a building without one;
3. `bld:doorman_full`, `bld:doorman_part` and `bld:doorman_virtual`, against ads that state
   no doorman;
4. `bld:condo` and `bld:coop`, against a rental building;
5. `bld:built_1980_2004`, `bld:built_2005_on` and `bld:built_unknown`, against a building
   built before 1980.

A building with no floor count, elevator record or year built takes that column's unknown
level. Tenure and doorman have no unknown level: a lot with no MapPLUTO match (about 3.7% of
rows) counts as rental, and a building whose ads state no doorman counts as none stated. Each coefficient gets the Normal(0, 0.5) prior that `b0.prior_arrays`
gives a column outside its named groups (the flag prior), so I reuse the normal walk's model,
starting values and sampler unchanged.

I chose these five from a screen of the converged all-data normal walk
(`normal-walk-b0-latest-ea4bcbd6-dense-w1500`): I averaged its training residuals in each
building and scored attribute groups by the share of between-building variance they explain
out of fold, with buildings held out in five folds and a permutation null. The five explain
23% of it, and 7.5% within a neighbourhood. I left out a landmark or historic-district flag
and the count of residential units: across neighbourhoods they explain 9% and 4%, but within
a neighbourhood 0.3% and 0.2%, so they mostly stand in for location.

The snapshot. `python -m rentfrontier.building_attrs snapshot ROWS` reads a pipeline build's
rows and writes one row per building to EXTERNAL_ROOT/building-attrs/<date>-<commit>/:

- floors: the median floor count the building's ads state, else MapPLUTO's `numfloors`.
  The ads come first because MapPLUTO counts the primary building of a lot, and on lots with
  a podium or several buildings it gives 8 floors for 8 Spruce (76 in the ads) and 14 for
  Gotham West (32).
- elevator: the majority of the ads that state yes or no (a tie counts as yes), else the MapPLUTO class (D, R4,
  R9 and RR have one; A, B, C, S, R2 and R3 do not), else unknown. NJ parcels carry no class
  that says, so NJ buildings read the ads alone.
- doorman: full when over a fifth of the ads say full time, part when over a fifth say part
  time or give no hours, virtual when over a fifth say virtual, and none stated otherwise.
  A missing amenity code does not say the building lacks one, so I take a share of the ads
  rather than any single ad.
- tenure: condo for a MapPLUTO class starting with R, co-op for C6, C8, D0 and D4, rental
  otherwise. An NJ lot is a condo when it holds parcels with a C qualifier.
- year built: MapPLUTO's `yearbuilt`, or the median `year_built` of the NJ lot's parcels;
  a year before 1800 counts as unknown.

The MapPLUTO release is the latest one (`PLUTO`). Floors, class and year built rarely change
for a standing building, and the ads' own floors win where both exist.

    python -m rentfrontier.building_attrs snapshot ROWS
    python -m rentfrontier.run --model building-attrs --split latest --name NAME [--chains 16 ...]
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import b0, b0_1, normal_walk
from .normal_walk import (  # noqa: F401  (the spec interface b0.main_run and b0.score read)
    KEPT,
    PROGRESS,
    TRACED,
    Priors,
    cell_log_premiums,
    diagnostics,
    initial_values,
    model,
    modal_contrasts,
    prior_arrays,
    split_index,
)
from .registry import EXTERNAL_ROOT

NAME = "building-attrs"
ATTRS = Path(
    os.environ.get(
        "FRONTIER_BUILDING_ATTRS",
        EXTERNAL_ROOT / "building-attrs" / "20261020-98ded48" / "attrs.parquet",
    )
)
REGISTRY = EXTERNAL_ROOT / "registry" / "20261019-bcfbb52-extend" / "registry.parquet"
REGISTRY_NJ = EXTERNAL_ROOT / "registry-nj" / "20261019-2d485c6" / "registry.parquet"
PLUTO = EXTERNAL_ROOT / "pluto" / "20261017-2c61ff1-all-lots4" / "pluto.parquet"
NJ_PARCELS = EXTERNAL_ROOT / "njparcels" / "20261019-27c8149" / "parcels.parquet"
FLOOR_REF = 5
SHARE = 0.2
COLUMNS = (
    "bld:log_floors",
    "bld:floors_unknown",
    "bld:elevator",
    "bld:elevator_unknown",
    "bld:doorman_full",
    "bld:doorman_part",
    "bld:doorman_virtual",
    "bld:condo",
    "bld:coop",
    "bld:built_1980_2004",
    "bld:built_2005_on",
    "bld:built_unknown",
)
ELEVATOR_CLASSES = ("R4", "R9", "RR")
WALKUP_CLASSES = ("R2", "R3")
COOP_CLASSES = ("C6", "C8", "D0", "D4")


# ------------------------------------------------------------------ the snapshot


def ad_attributes(rows: pd.DataFrame) -> pd.DataFrame:
    """Per building, from its ads: the median stated floor count, the shares of ads stating
    an elevator or none, and the shares stating each kind of doorman."""
    rows = rows.assign(
        elev_yes=rows.elevator.eq(True),
        elev_no=rows.elevator.eq(False),
        dm_full=rows.doorman_type.eq("full_time"),
        dm_part=rows.doorman_type.isin(["part_time", "unspecified"]),
        dm_virtual=rows.doorman_type.eq("virtual"),
        floors=rows.building_floor_count.where(rows.building_floor_count > 0),
    )
    g = rows.groupby("building")
    out = g[["elev_yes", "elev_no", "dm_full", "dm_part", "dm_virtual"]].mean()
    out["ad_floors"] = g.floors.median()
    out["ads"] = g.size()
    return out


def nyc_lots(registry: pd.DataFrame, pluto: pd.DataFrame) -> pd.DataFrame:
    """Per NYC building, its lot's MapPLUTO floors, class and year built."""
    pluto = pluto.assign(
        numfloors=pd.to_numeric(pluto.numfloors, errors="coerce"),
        yearbuilt=pd.to_numeric(pluto.yearbuilt, errors="coerce"),
    )
    out = registry.dropna(subset=["bbl"]).merge(
        pluto[["bbl", "numfloors", "bldgclass", "yearbuilt"]], on="bbl", how="left"
    )
    return out.drop_duplicates("building").set_index("building")[
        ["numfloors", "bldgclass", "yearbuilt"]
    ]


def nj_lots(registry: pd.DataFrame, parcels: pd.DataFrame) -> pd.DataFrame:
    """Per NJ building, its lot's median year built and whether the lot holds condo units
    (parcels with a C qualifier)."""
    parcels = parcels.assign(
        year_built=parcels.year_built.where(parcels.year_built >= 1800),
        condo=parcels.qualifier.fillna("").astype(str).str.upper().str.startswith("C"),
    )
    lots = parcels.groupby("lot").agg(
        yearbuilt=("year_built", "median"), condo=("condo", "any")
    )
    out = registry.dropna(subset=["lot"]).merge(
        lots, left_on="lot", right_index=True, how="left"
    )
    out = out.drop_duplicates("building").set_index("building")
    out["bldgclass"] = np.where(out.condo.fillna(False), "R", None)
    out["numfloors"] = np.nan
    return out[["numfloors", "bldgclass", "yearbuilt"]]


def attributes(ads: pd.DataFrame, lots: pd.DataFrame) -> pd.DataFrame:
    """One row per building in `ads` or `lots`: floors, elevator, doorman, tenure and year
    built, as the module docstring sets out."""
    t = ads.join(lots, how="outer")
    cls = t.bldgclass.fillna("").astype(str)
    floors = t.ad_floors.where(t.ad_floors > 0)
    floors = floors.fillna(t.numfloors.where(t.numfloors > 0))
    stated = t.elev_yes.fillna(0) + t.elev_no.fillna(0) > 0
    lot_yes = cls.str.startswith("D") | cls.isin(ELEVATOR_CLASSES)
    lot_no = cls.str[:1].isin(["A", "B", "C", "S"]) | cls.isin(WALKUP_CLASSES)
    elevator = np.select(
        [stated & (t.elev_yes >= t.elev_no), stated, lot_yes, lot_no],
        ["yes", "no", "yes", "no"],
        "unknown",
    )
    doorman = np.select(
        [t.dm_full > SHARE, t.dm_part > SHARE, t.dm_virtual > SHARE],
        ["full", "part", "virtual"],
        "none",
    )
    tenure = np.select(
        [cls.str.startswith("R"), cls.isin(COOP_CLASSES)], ["condo", "coop"], "rental"
    )
    year = t.yearbuilt.where(t.yearbuilt >= 1800)
    return pd.DataFrame(
        {
            "building": t.index.astype(str),
            "floors": floors.to_numpy(float),
            "elevator": elevator,
            "doorman": doorman,
            "tenure": tenure,
            "year_built": year.to_numpy(float),
            "ads": t.ads.fillna(0).astype(int).to_numpy(),
        }
    ).reset_index(drop=True)


def snapshot(rows_path: Path) -> Path:
    def git(*a):
        return subprocess.run(
            ["git", *a], capture_output=True, text=True, check=True
        ).stdout.strip()

    if git("status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("refusing a dirty tree")
    commit = git("rev-parse", "HEAD")
    started = dt.datetime.now(dt.UTC)
    rows = pd.read_parquet(
        rows_path,
        columns=["building", "elevator", "doorman_type", "building_floor_count"],
    )
    registry = pd.read_parquet(REGISTRY, columns=["building", "bbl"])
    registry_nj = pd.read_parquet(REGISTRY_NJ, columns=["building", "lot"])
    pluto = pd.read_parquet(PLUTO)
    parcels = pd.read_parquet(NJ_PARCELS, columns=["lot", "qualifier", "year_built"])
    lots = pd.concat([nyc_lots(registry, pluto), nj_lots(registry_nj, parcels)])
    lots = lots[~lots.index.duplicated()]
    table = attributes(ad_attributes(rows), lots)
    out_dir = EXTERNAL_ROOT / "building-attrs" / f"{started:%Y%m%d}-{commit[:7]}"
    out_dir.mkdir(parents=True, exist_ok=True)
    scratch = out_dir / "attrs.parquet.tmp"
    table.to_parquet(scratch, index=False)

    def sha(p):
        return hashlib.sha256(Path(p).read_bytes()).hexdigest()

    provenance = {
        "commit": commit,
        "built_at": started.isoformat(),
        "inputs": {
            str(p): sha(p)
            for p in (rows_path, REGISTRY, REGISTRY_NJ, PLUTO, NJ_PARCELS)
        },
        "buildings": len(table),
        "levels": {
            c: table[c].value_counts().to_dict()
            for c in ("elevator", "doorman", "tenure")
        },
        "floors_known": int(table.floors.notna().sum()),
        "year_built_known": int(table.year_built.notna().sum()),
        "sha256": sha(scratch),
    }
    (out_dir / "provenance.json").write_text(json.dumps(provenance, indent=2))
    path = out_dir / "attrs.parquet"
    os.replace(scratch, path)
    return path


# ------------------------------------------------------------------ the design


def columns(frame: pd.DataFrame, attrs: pd.DataFrame) -> np.ndarray:
    """The twelve building columns (COLUMNS) of `frame`'s rows."""
    a = attrs.set_index("building").reindex(frame.building.astype(str))
    floors = a.floors.to_numpy(float)
    known = np.isfinite(floors) & (floors > 0)
    log_floors = np.where(known, np.log(np.where(known, floors, 1.0) / FLOOR_REF), 0.0)
    elevator = a.elevator.fillna("unknown").to_numpy()
    doorman = a.doorman.fillna("none").to_numpy()
    tenure = a.tenure.fillna("rental").to_numpy()
    year = a.year_built.to_numpy(float)
    return np.column_stack(
        [
            log_floors,
            ~known,
            elevator == "yes",
            elevator == "unknown",
            doorman == "full",
            doorman == "part",
            doorman == "virtual",
            tenure == "condo",
            tenure == "coop",
            (year >= 1980) & (year < 2005),
            year >= 2005,
            ~np.isfinite(year),
        ]
    ).astype(float)


def design(
    frame: pd.DataFrame,
    start: pd.Timestamp | None = None,
    attrs: pd.DataFrame | None = None,
) -> b0.Design:
    """The normal walk's design of `frame`, with the building columns appended. I leave out
    a column no row sets, as B0 does for its indicators."""
    d = normal_walk.design(frame, start)
    if attrs is None:
        attrs = pd.read_parquet(ATTRS)
    new = columns(frame, attrs)
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


def run_record(d: b0.Design) -> dict:
    return {"building_attrs": str(ATTRS)}


# ------------------------------------------------------------------ the summary


def summarize(kept: dict, names) -> dict:
    """The normal walk's summary, with each building coefficient as a percent premium."""
    out = normal_walk.summarize(kept, names)
    beta = np.asarray(kept["beta"])
    out["building"] = {}
    for j, n in enumerate(names):
        if n.startswith("bld:"):
            v = 100 * np.expm1(beta[..., j]).ravel()
            out["building"][n] = {
                "median": float(np.median(v)),
                "lo": float(np.quantile(v, 0.025)),
                "hi": float(np.quantile(v, 0.975)),
            }
    return out


def scorecard(summary, season, trend) -> list:
    """The predictions written before the first building-attributes fit, each with the
    measured value and hit or miss, then the normal walk's own scorecard. Convergence, the
    noise scales and fit time are in the fit's notes."""
    rows = []
    b = summary["building"]

    def add(n, claim, name, lo, hi):
        if name not in b:
            return
        m = b[name]["median"]
        rows.append(
            {"n": n, "claim": claim, "value": f"{m:+.1f}%", "hit": bool(lo <= m <= hi)}
        )

    add("B1", "an elevator adds +6% to +22%", "bld:elevator", 6, 22)
    add("B2", "a condo building adds +6% to +22%", "bld:condo", 6, 22)
    add("B3", "a co-op building adds +3% to +16%", "bld:coop", 3, 16)
    add("B4", "a building e times as tall adds +6% to +16%", "bld:log_floors", 6, 16)
    add("B5", "a full-time doorman adds -2% to +12%", "bld:doorman_full", -2, 12)
    add("B6", "a virtual doorman is -9% to +1%", "bld:doorman_virtual", -9, 1)
    add(
        "B7",
        "built 2005 on is -18% to -3% against pre-1980",
        "bld:built_2005_on",
        -18,
        -3,
    )
    return rows + normal_walk.scorecard(summary, season, trend)


def log_density(d: b0.Design, priors: Priors):
    return normal_walk.log_density(d, priors)


def run(d, priors, settings, log=print, checkpoint=None):
    """B0.1's ChEES-HMC on the normal walk with the building columns."""
    return b0_1.run(d, priors, settings, log, checkpoint, spec=sys.modules[__name__])


def main_run(argv) -> None:
    """`rentfrontier.run --model building-attrs`: fit on the split's training rows and save."""
    parser = b0.run_parser()
    parser.prog = f"rentfrontier.run --model {NAME}"
    parser.set_defaults(model=NAME)
    parser.add_argument("--learning-rate", type=float)
    parser.add_argument("--max-leapfrog-steps", type=int)
    b0.main_run(
        argv,
        parser=parser,
        name=NAME,
        settings_cls=b0_1.Settings,
        sample=run,
        line="baseline-blackjax",
        spec=sys.modules[__name__],
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="step", required=True)
    sp = sub.add_parser("snapshot")
    sp.add_argument("rows", type=Path, help="a pipeline build's rows parquet")
    args = parser.parse_args(argv)
    if args.step == "snapshot":
        path = snapshot(args.rows)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
