"""Simulated rents with known effects, for checking that a building-zones fit recovers them.

I take a finished fit of `building-zones-floor` or `building-zones-location` and its exact design: the same rows, columns,
missing values, buildings, zones, map bases and weeks. I set every term to a known value, the
truth, and draw each row's log rent from the model:

    y = x beta + L(t) + F(site) + bld(site) + sigma_group * StudentT(nu)

Then I write a copy of the fit's dataset with `latest_ask` replaced by exp(y), so a fit of the
unchanged model on that copy reads simulated rents and nothing else changes. The design reads
no price column besides `latest_ask`, so the fit's rows differ from the original only in their
target. Other price columns of the copy keep their real values, so a feature set reading one of
them needs its own simulated copy.

The truth starts from the posterior medians of the fit's kept draws: the coefficients, the walk,
the map's wave coefficients, every building's residual level `bld`, nu and the four sigmas. The
scenario then changes some of it:

1. `realistic`: the walk-up floor curve rises WALKUP_SLOPE a flight (floor k gets
   WALKUP_SLOPE * (k - 1)), `unit:elev_top` is ELEV_TOP, `unit:lower` is 0, and the
   elevator curve keeps its fitted values.
2. `null`: both floor curves, every floor flag and every building feature (each `bld:`
   column, in-unit and in-building laundry, the dishwasher) are 0. The building levels keep
   the fit's residual effects, which already exclude the features.
3. `height`: both floor curves and every floor flag are 0, and each building's level gains
   HEIGHT_SLOPE per MapPLUTO floor, centred on the training rows' mean so the intercept keeps
   its value. A building with no MapPLUTO floor count gains nothing.
4. `fitted`: the medians as they are. On a `building-zones-location` fit this plants the
   transit, parks and noise terms at the fit's values, so a fit on the copy shows whether they
   come back without moving into the map.

    python -m rentfrontier.simulate make RUN SCENARIO DATASET_OUT [--seed N] [--root DIR]
    python -m rentfrontier.simulate score SIM_RUN TRUTH_DIR OUT_JSON [--root DIR]

`make` writes DATASET_OUT (rows.parquet, set_aside.parquet and manifest.json) and puts the
truth in ROOT/SCENARIO/truth.npz, with the scenario-free design facts in ROOT/design.npz.
ROOT is SIM_ROOT unless `--root` gives another folder, which a second source fit needs, since
each ROOT's design.npz belongs to one fit. `score` compares a fit on the simulated data with that truth and writes
a JSON of medians, 90% intervals and coverage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import (
    b0,
    building_attrs,
    building_zones_floor,
    building_zones_location,
    splits,
    whitened_zones,
)
from .run import RUNS

SIM_ROOT = Path("/data1/apartments/tmp/sim-recovery")
SCENARIOS = ("realistic", "null", "height", "fitted")
# The models a source fit may come from, by feature set.
SPECS = {
    building_zones_floor.NAME: building_zones_floor,
    building_zones_location.NAME: building_zones_location,
}
WALKUP_SLOPE = 0.004  # log points a flight above floor 1, in the realistic set
ELEV_TOP = math.log(1.04)  # a 4% top-floor bump in elevator buildings
HEIGHT_SLOPE = 0.002  # log points a MapPLUTO floor: 2% for every 10 floors
UNIT_FEATURES = ("unit:laundry_in_unit", "unit:laundry_in_building", "unit:dishwasher")
# The record keys whose snapshot paths the rebuilt design has to share with the fit.
SNAPSHOT_KEYS = (
    "registry",
    "nj_registry",
    "building_attrs",
    "footprints",
    "unit_features",
    "building_gym",
    "building_age",
    "unit_floor",
    "building_transit",
    "building_parks",
    "building_noise",
)
LEVEL = 0.90
# The prefix of the building-mean columns a fit may add to the truth's (building_zones_mundlak).
EXTRA_PREFIX = "bld:mean_"
DENSITY_BINS = ((0, 0, "0"), (1, 4, "1-4"), (5, 19, "5-19"), (20, 99, "20-99"))
DENSITY_BINS += ((100, 10**9, "100+"),)


def floor_terms(names) -> list[str]:
    """The floor curve columns and floor flags among `names`."""
    return [n for n in names if n in building_zones_floor.COLUMNS]


def feature_terms(names) -> list[str]:
    """The building feature columns among `names`: every `bld:` column and UNIT_FEATURES."""
    return [n for n in names if n.startswith("bld:") or n in UNIT_FEATURES]


def medians(kept: dict) -> dict:
    """Each kept quantity's posterior median over chains and draws."""
    out = {}
    for k in ("beta", "L", "gp_w", "bld", "nu", "sigma", "tau", "bld_sd", "amp"):
        v = np.asarray(kept[k], dtype=float)
        out[k] = np.median(v.reshape(-1, *v.shape[2:]), axis=0)
    return out


def surface(basis: list[np.ndarray], share: np.ndarray, w: np.ndarray) -> np.ndarray:
    """F at every building from wave coefficients `w` (..., waves), centred on the
    row shares as the model centres it."""
    parts, at = [], 0
    for B in basis:
        parts.append(w[..., at : at + B.shape[1]] @ B.T)
        at += B.shape[1]
    F = np.concatenate(parts, axis=-1)
    return F - (F @ share)[..., None]


def truth(names, med: dict, scenario: str, height: np.ndarray | None = None) -> dict:
    """The scenario's true beta and building levels, from the fit's medians `med`.
    `height` is each building's planted level for the height scenario."""
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario!r}")
    ix = {n: j for j, n in enumerate(names)}
    beta = med["beta"].copy()
    bld = med["bld"].copy()
    planted = np.zeros_like(bld)
    if scenario == "fitted":
        pass
    elif scenario == "realistic":
        for k in range(2, building_zones_floor.WALKUP_CAP + 1):
            beta[ix[f"unit:walkup_f{k}"]] = WALKUP_SLOPE * (k - 1)
        beta[ix["unit:elev_top"]] = ELEV_TOP
        beta[ix["unit:lower"]] = 0.0
    else:
        for n in floor_terms(names):
            beta[ix[n]] = 0.0
    if scenario == "null":
        for n in feature_terms(names):
            beta[ix[n]] = 0.0
    if scenario == "height":
        if height is None:
            raise ValueError("the height scenario needs each building's planted level")
        planted = np.asarray(height, dtype=float)
        bld = bld + planted
    return {"beta": beta, "bld": bld, "planted": planted}


def mean(d, beta, L, F, bld) -> np.ndarray:
    """Every row's log-rent location under the given terms."""
    return (
        d.x @ beta
        + (1 - d.frac) * L[d.week]
        + d.frac * L[d.week + 1]
        + F[d.site]
        + bld[d.site]
    )


def draw(d, mu, nu, sigma, seed) -> np.ndarray:
    """Log rents around `mu` with Student-t noise of each row's group scale."""
    rng = np.random.default_rng(seed)
    return mu + np.asarray(sigma)[d.group] * rng.standard_t(nu, len(mu))


def site_buildings(frame: pd.DataFrame, site: np.ndarray, n: int) -> np.ndarray:
    """The building id at each site, read off the rows."""
    s = pd.Series(frame.building.astype(str).to_numpy(), index=site)
    s = s[~s.index.duplicated()].reindex(range(n))
    if s.isna().any():
        raise ValueError(f"{int(s.isna().sum())} sites have no row")
    return s.to_numpy()


def pluto_floors(buildings: np.ndarray, registry: Path) -> np.ndarray:
    """Each building's MapPLUTO floor count (rounded down, NaN without one), joined
    through the registry's BBL as `unit_floor.top_floors` joins it."""
    reg = pd.read_parquet(registry, columns=["building", "bbl"]).dropna(subset=["bbl"])
    reg = reg.drop_duplicates("building")
    pluto = pd.read_parquet(building_attrs.PLUTO, columns=["bbl", "numfloors"])
    lots = pd.DataFrame(
        {
            "bbl": pluto.bbl.astype(str),
            "numfloors": np.floor(pd.to_numeric(pluto.numfloors, errors="coerce")),
        }
    ).drop_duplicates("bbl")
    fl = reg.assign(bbl=reg.bbl.astype(str), building=reg.building.astype(str))
    fl = fl.merge(lots, on="bbl").set_index("building").numfloors
    fl = fl[fl >= 1]
    return fl.reindex(buildings).to_numpy(float)


def planted_height(floors: np.ndarray, rows: np.ndarray) -> np.ndarray:
    """HEIGHT_SLOPE per floor, centred on the row-weighted mean floor count of buildings
    with one; 0 for a building without a count."""
    known = ~np.isnan(floors)
    centre = np.average(floors[known], weights=np.maximum(rows[known], 0) + 1e-12)
    return np.where(known, HEIGHT_SLOPE * (floors - centre), 0.0)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def make(run: str, scenario: str, out: Path, seed: int, root: Path = SIM_ROOT) -> None:
    """Write the simulated dataset `out` and the scenario's truth under `root`."""
    result = json.loads((RUNS / run / "result.json").read_text())
    spec = SPECS.get(result["feature_set"])
    if spec is None:
        raise SystemExit(
            f"{run} is a {result['feature_set']} fit, not one of {', '.join(SPECS)}"
        )
    if out.exists():
        raise SystemExit(f"{out} exists; choose a new dataset name")
    source = Path(result["dataset"])
    frame = b0.load_frame(source)
    if frame.attrs["source_sha256"] != result["dataset_observations_sha256"]:
        raise SystemExit(f"{source} holds other rows than the fit read")
    heldout = splits.SPLITS[result["split"]](frame)
    full = spec.design(frame)
    record = spec.run_record(full)
    for k in SNAPSHOT_KEYS:
        if str(record.get(k)) != str(result.get(k)):
            raise SystemExit(
                f"{k}: the design reads {record.get(k)}, the fit read {result.get(k)}"
            )
    with np.load(RUNS / run / "posterior.npz") as z:
        names = [str(n) for n in z["names"]]
        if names != list(full.names):
            raise SystemExit("the rebuilt design's columns differ from the fit's")
        if not np.array_equal(z["heldout"], heldout):
            raise SystemExit("the rebuilt split differs from the fit's")
        kept = {k[5:]: z[k] for k in z.files if k.startswith("kept/")}
    med = medians(kept)
    n_sites = sum(s["sites"] for s in full.surfaces)
    train = ~heldout
    rows = np.bincount(full.site[train], minlength=n_sites).astype(float)
    share = rows / rows.sum()
    basis = [s["basis"] for s in full.surfaces]
    F = surface(basis, share, med["gp_w"])
    buildings = site_buildings(frame, full.site, n_sites)
    floors = pluto_floors(buildings, Path(result["registry"]))
    t = truth(names, med, scenario, planted_height(floors, rows))
    mu = mean(full, t["beta"], med["L"], F, t["bld"])
    y = draw(full, mu, med["nu"], med["sigma"], seed)

    out.mkdir(parents=True)
    frame["latest_ask"] = np.exp(y)
    frame.attrs = {}
    frame.to_parquet(out / "rows.parquet")
    if (source / "set_aside.parquet").exists():
        shutil.copy2(source / "set_aside.parquet", out / "set_aside.parquet")

    tdir = root / scenario
    tdir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        tdir / "truth.npz",
        names=np.asarray(names),
        beta=t["beta"],
        L=med["L"],
        gp_w=med["gp_w"],
        F=F,
        bld=t["bld"],
        bld_resid=med["bld"],
        planted=t["planted"],
        nu=med["nu"],
        sigma=med["sigma"],
        fit_beta=med["beta"],
        fit_tau=med["tau"],
        fit_bld_sd=med["bld_sd"],
        fit_amp=med["amp"],
        mu_train=mu[train].astype(np.float32),
        y_train=y[train].astype(np.float32),
    )
    _write_design(full, frame, train, rows, share, buildings, floors, result, root)

    manifest = json.loads((source / "manifest.json").read_text())
    manifest["rows_sha256"] = sha256(out / "rows.parquet")
    manifest["simulated"] = {
        "source_dataset": str(source),
        "source_rows_sha256": result["dataset_observations_sha256"],
        "run": run,
        "scenario": scenario,
        "seed": seed,
        "truth": str(tdir / "truth.npz"),
        "truth_sha256": sha256(tdir / "truth.npz"),
        "walkup_slope": WALKUP_SLOPE if scenario == "realistic" else None,
        "elev_top": ELEV_TOP if scenario == "realistic" else None,
        "height_slope": HEIGHT_SLOPE if scenario == "height" else None,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    resid = y[train] - mu[train]
    print(
        f"{scenario}: {len(y)} rows ({int(train.sum())} training), log rent mean "
        f"{y[train].mean():.4f} (fit data {full.y[train].mean():.4f}), sd {y[train].std():.4f} "
        f"(fit data {full.y[train].std():.4f}), noise sd {resid.std():.4f}; wrote {out}"
    )


def _write_design(
    full, frame, train, rows, share, buildings, floors, result, root=SIM_ROOT
) -> None:
    """The scenario-free design facts the scoring reads, in `root`/design.npz."""
    path = root / "design.npz"
    if path.exists():
        with np.load(path) as z:
            if str(z["run"]) != result["name"]:
                raise SystemExit(f"{path} comes from {z['run']}, not {result['name']}")
        return
    n = len(rows)
    zone = np.concatenate([np.full(s["sites"], k) for k, s in enumerate(full.surfaces)])
    reg = pd.read_parquet(
        result["registry"], columns=["building", "bbl", "latitude", "longitude"]
    )
    nj = pd.read_parquet(
        result["nj_registry"], columns=["building", "latitude", "longitude"]
    )
    sites = whitened_zones.sites_of(frame, reg, nj).reindex(buildings)
    names = list(full.names)
    bcols = [j for j, c in enumerate(names) if c.startswith("bld:")]
    st = full.site[train]
    xb = (
        np.column_stack([np.bincount(st, full.x[train, j], minlength=n) for j in bcols])
        / np.maximum(rows, 1)[:, None]
    )
    col_rows = np.array([int((full.x[train, j] != 0).sum()) for j in range(len(names))])
    elev = full.x[:, names.index("bld:elevator")]
    site_elev = np.zeros(n)
    site_elev[full.site] = elev
    np.savez_compressed(
        path,
        run=np.asarray(result["name"]),
        zone_names=np.asarray([s["name"] for s in full.surfaces]),
        names=np.asarray(names),
        col_rows=col_rows,
        site_rows=rows,
        share=share,
        site_zone=zone,
        site_x=sites.x.to_numpy(float),
        site_y=sites.y.to_numpy(float),
        site_floors=floors,
        site_elevator=site_elev,
        bld_cols=np.asarray([names[j] for j in bcols]),
        site_bldx=xb,
        basis_sizes=np.asarray([s["basis"].shape[1] for s in full.surfaces]),
        **{
            f"basis_{k}": s["basis"].astype(np.float32)
            for k, s in enumerate(full.surfaces)
        },
    )


# ------------------------------------------------------------------ scoring


def _interval(draws: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    lo, hi = (1 - LEVEL) / 2, (1 + LEVEL) / 2
    q = np.quantile(draws, [lo, 0.5, hi], axis=0)
    return q[0], q[1], q[2]


def term_rows(draws: np.ndarray, truth_v: np.ndarray, names) -> list[dict]:
    """Per-term truth, median, 90% interval, coverage and chain medians. `draws` is
    (chains, draws, terms)."""
    flat = draws.reshape(-1, draws.shape[-1])
    q05, q50, q95 = _interval(flat)
    chain = np.median(draws, axis=1)
    out = []
    for j, n in enumerate(names):
        out.append(
            {
                "term": n,
                "truth": float(truth_v[j]),
                "median": float(q50[j]),
                "q05": float(q05[j]),
                "q95": float(q95[j]),
                "error": float(q50[j] - truth_v[j]),
                "width": float(q95[j] - q05[j]),
                "covered": bool(q05[j] <= truth_v[j] <= q95[j]),
                "chain_medians": [float(c) for c in chain[:, j]],
            }
        )
    return out


def site_coverage(draws: np.ndarray, truth_v: np.ndarray, rows: np.ndarray) -> dict:
    """Coverage, error and the shrinkage slope of a per-building quantity, overall and by
    the building's training rows. `draws` is (draws, sites)."""
    q05, q50, q95 = _interval(draws)
    cov = (q05 <= truth_v) & (truth_v <= q95)

    def part(m):
        if m.sum() < 2:
            return {"sites": int(m.sum())}
        t, e = truth_v[m], q50[m]
        tc = t - t.mean()
        slope = float((tc * (e - e.mean())).sum() / max((tc**2).sum(), 1e-300))
        return {
            "sites": int(m.sum()),
            "rows": int(rows[m].sum()),
            "coverage": float(cov[m].mean()),
            "rmse": float(np.sqrt(((e - t) ** 2).mean())),
            "mean_error": float((e - t).mean()),
            "mean_width": float((q95 - q05)[m].mean()),
            "truth_sd": float(t.std()),
            "slope": slope,
        }

    out = {"all": part(np.ones(len(rows), bool)), "with_rows": part(rows > 0)}
    out["by_rows"] = {
        lab: part((rows >= lo) & (rows <= hi)) for lo, hi, lab in DENSITY_BINS
    }
    return out


def score(sim_run: str, tdir: Path, out_json: Path, root: Path = SIM_ROOT) -> dict:
    """Compare the fit `sim_run` with the truth in `tdir` and write the scores."""
    t = dict(np.load(tdir / "truth.npz"))
    dz = dict(np.load(root / "design.npz"))
    names = [str(n) for n in t["names"]]
    with np.load(RUNS / sim_run / "posterior.npz") as z:
        kept = {k[5:]: z[k] for k in z.files if k.startswith("kept/")}
        fit_names = [str(n) for n in z["names"]]
    extra = fit_names[len(names) :]
    if fit_names[: len(names)] != names or not all(
        n.startswith(EXTRA_PREFIX) for n in extra
    ):
        raise SystemExit("the fit's columns differ from the truth's")
    # A fit with building means (rentfrontier.building_zones_mundlak) has columns the truth
    # lacks. Their true value is 0, since the truth's building levels have no such term, but
    # the means take up part of the residual levels, so I report them apart from the terms.
    extra_rows = term_rows(kept["beta"][..., len(names) :], np.zeros(len(extra)), extra)
    kept["beta"] = kept["beta"][..., : len(names)]
    result = json.loads((RUNS / sim_run / "result.json").read_text())
    sim = json.loads((Path(result["dataset"]) / "manifest.json").read_text()).get(
        "simulated"
    )
    if (
        not sim
        or sim["scenario"] != tdir.name
        or sim["truth_sha256"] != sha256(tdir / "truth.npz")
    ):
        raise SystemExit(
            f"{sim_run} was not fitted on the data drawn from {tdir}/truth.npz"
        )
    chains, draws = kept["beta"].shape[:2]
    terms = term_rows(kept["beta"], t["beta"], names)
    for r in terms:
        r["rows"] = int(dz["col_rows"][names.index(r["term"])])

    sigma_rows = term_rows(kept["sigma"], t["sigma"], [f"sigma[{g}]" for g in range(4)])
    nu_rows = term_rows(kept["nu"][..., None], np.atleast_1d(t["nu"]), ["nu"])
    L = np.asarray(kept["L"])
    weeks = list(range(0, L.shape[-1], 12)) + [L.shape[-1] - 1]
    walk = term_rows(L[..., weeks], t["L"][weeks], [f"L[{w}]" for w in weeks])
    walk_steps = np.diff(t["L"])
    hyper = {
        "tau": {
            "truth_realized_sd": float(walk_steps.std()),
            "fit_median": float(t["fit_tau"]),
            **_q(kept["tau"]),
        },
        "bld_sd": {
            "truth_realized_sd_with_rows": [
                float(t["bld"][(dz["site_zone"] == k) & (dz["site_rows"] > 0)].std())
                for k in range(len(dz["basis_sizes"]))
            ],
            "source_fit_median": [float(v) for v in t["fit_bld_sd"]],
            "recovered": [
                _q(kept["bld_sd"][..., k]) for k in range(len(dz["basis_sizes"]))
            ],
        },
        "amp": {
            "source_fit_median": [float(v) for v in t["fit_amp"]],
            "recovered": [
                _q(kept["amp"][..., k]) for k in range(len(dz["basis_sizes"]))
            ],
        },
        "gp_amp": [_q(kept["gp_amp"][..., k]) for k in range(kept["gp_amp"].shape[-1])],
        "gp_ls": [_q(kept["gp_ls"][..., k]) for k in range(kept["gp_ls"].shape[-1])],
    }

    basis = [dz[f"basis_{k}"].astype(float) for k in range(len(dz["basis_sizes"]))]
    w = np.asarray(kept["gp_w"]).reshape(chains * draws, -1)
    F = surface(basis, dz["share"], w)
    bld = np.asarray(kept["bld"], dtype=float).reshape(chains * draws, -1)
    rows = dz["site_rows"]
    zone = dz["site_zone"]
    maps = {}
    for k, zname in enumerate(str(z) for z in dz["zone_names"]):
        on = zone == k
        maps[zname] = {
            "F": site_coverage(F[:, on], t["F"][on], rows[on]),
            "bld": site_coverage(bld[:, on], t["bld"][on], rows[on]),
            "level": site_coverage(
                F[:, on] + bld[:, on], (t["F"] + t["bld"])[on], rows[on]
            ),
        }

    curves = {}
    for g, cap in building_zones_floor.GROUPS:
        cols = [f"unit:{g}_f{k}" for k in range(2, cap + 1)]
        curves[g] = [
            {"floor": k, **next(r for r in terms if r["term"] == c)}
            for k, c in zip(range(2, cap + 1), cols)
        ]
    elev = curves["elev"]
    high = [r for r in elev if r["floor"] >= 30]
    low = [r for r in elev if r["floor"] < 30]

    scalar = [r for r in terms] + sigma_rows + nu_rows
    covered = np.array([r["covered"] for r in scalar])
    groups = {
        "floor_curves": [r for r in terms if r["term"] in building_zones_floor.CURVE],
        "floor_flags": [r for r in terms if r["term"] in building_zones_floor.FLAGS],
        "building_features": [r for r in terms if r["term"] in feature_terms(names)],
        "other_terms": [
            r
            for r in terms
            if r["term"] not in building_zones_floor.COLUMNS
            and r["term"] not in feature_terms(names)
        ],
        "noise": sigma_rows + nu_rows,
    }
    summary = {
        "scalar_terms": int(len(covered)),
        "coverage_90": float(covered.mean()),
        "by_group": {
            k: {
                "terms": len(v),
                "coverage_90": float(np.mean([r["covered"] for r in v])) if v else None,
                "rms_error": float(np.sqrt(np.mean([r["error"] ** 2 for r in v])))
                if v
                else None,
            }
            for k, v in groups.items()
        },
        "elev_floor_coverage": {
            "below_30": float(np.mean([r["covered"] for r in low])),
            "30_up": float(np.mean([r["covered"] for r in high])),
        },
        "misses": [
            {k: r.get(k) for k in ("term", "truth", "median", "q05", "q95", "rows")}
            for r in terms + sigma_rows + nu_rows
            if not r["covered"]
        ],
        "walk_coverage_90": float(np.mean([r["covered"] for r in walk])),
    }
    out = {
        "run": sim_run,
        "scenario": tdir.name,
        "diagnostics": {
            k: result["diagnostics"].get(k)
            for k in ("max_rhat", "max_rhat_name", "min_ess", "min_ess_name", "passes")
        },
        "seconds": result.get("seconds"),
        "cost_usd": result.get("cost_usd"),
        "summary": summary,
        "terms": terms,
        "noise": sigma_rows + nu_rows,
        "walk": walk,
        "hyper": hyper,
        "curves": curves,
        "maps": maps,
    }
    if extra:
        out["extra_terms"] = extra_rows
    if np.any(t["planted"] != 0):
        out["height"] = height_leak(kept, t, dz, names, F, bld, curves)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(out, indent=1))
    print(
        f"{sim_run}: {summary['scalar_terms']} scalar terms, 90% coverage "
        f"{summary['coverage_90']:.3f}, {len(summary['misses'])} misses; wrote {out_json}"
    )
    return out


def _q(x) -> dict:
    x = np.asarray(x, dtype=float).reshape(-1)
    lo, mid, hi = np.quantile(x, [(1 - LEVEL) / 2, 0.5, (1 + LEVEL) / 2])
    return {"median": float(mid), "q05": float(lo), "q95": float(hi)}


def height_leak(kept, t, dz, names, F, bld, curves) -> dict:
    """Where the planted height term went: the recovered floor curve at a few floors, and
    the row-weighted regression on the planted term of each building's recovered level
    parts less their truth."""
    rows = dz["site_rows"]
    on = rows > 0
    cols = [str(c) for c in dz["bld_cols"]]
    ix = [names.index(c) for c in cols]
    beta = np.asarray(kept["beta"]).reshape(-1, len(names))
    xg = dz["site_bldx"] @ np.median(beta[:, ix], axis=0)
    xg_true = dz["site_bldx"] @ t["beta"][ix]
    p = t["planted"]
    parts = {
        "map": np.median(F, axis=0) - t["F"],
        "building_level": np.median(bld, axis=0) - t["bld_resid"],
        "building_columns": xg - xg_true,
    }
    parts["total"] = sum(parts.values())
    wgt = rows[on]
    pc = p[on] - np.average(p[on], weights=wgt)

    def slope(v):
        v = v[on] - np.average(v[on], weights=wgt)
        return float((wgt * pc * v).sum() / (wgt * pc * pc).sum())

    hgt = names.index("bld:log_height")
    floors = {
        str(k): next(r for r in curves["elev"] if r["floor"] == k)
        for k in (10, 20, 30, 40)
    }
    return {
        "slope_on_planted": {k: slope(v) for k, v in parts.items()},
        "log_height": _q(beta[:, hgt]) | {"truth": float(t["beta"][hgt])},
        "elev_curve": {
            k: {q: r[q] for q in ("median", "q05", "q95", "covered")}
            for k, r in floors.items()
        },
        "planted_sd_rows": float(np.sqrt(np.average(pc**2, weights=wgt))),
        "buildings_with_floors": int((~np.isnan(dz["site_floors"]))[on].sum()),
    }


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="rentfrontier.simulate")
    sub = p.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make")
    m.add_argument("run")
    m.add_argument("scenario", choices=SCENARIOS)
    m.add_argument("out", type=Path)
    m.add_argument("--seed", type=int, default=20261022)
    m.add_argument("--root", type=Path, default=SIM_ROOT)
    s = sub.add_parser("score")
    s.add_argument("sim_run")
    s.add_argument("truth_dir", type=Path)
    s.add_argument("out_json", type=Path)
    s.add_argument("--root", type=Path, default=SIM_ROOT)
    args = p.parse_args(argv)
    if args.cmd == "make":
        make(args.run, args.scenario, args.out, args.seed, args.root)
    else:
        score(args.sim_run, args.truth_dir, args.out_json, args.root)


if __name__ == "__main__":
    main(sys.argv[1:])
