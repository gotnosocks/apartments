"""Held-out screen for `bayesian_structure_graph` variants against the promoted model.

Same declared split as `bedroom_time_screen` (10% of rows from repeat-listed
units, split seed 20260922). `--method map` is conditional MAP: variance
components are fixed at a NUTS screen's posterior means (`--fix-scales-from`),
and any new drift scale is fixed by `--building-scale` (screen a grid of values;
free hierarchical scales degenerate at the joint mode).
"""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np
from scipy import special, stats
from threadpoolctl import threadpool_limits

from . import bayesian_feature_experiment_v3 as v3
from . import bayesian_floor_spline_design as floor
from . import bayesian_structure_graph_v5 as graph
from .bedroom_time_screen import split, map_posterior, summarize

UNSEEN_UNIT_DRAWS = 200


def split_units(data, fraction, seed):
    """Hold out every row of ~fraction of units whose building keeps other units."""
    units = data.groupby("unit_id").building.first()
    per_building = units.value_counts()
    eligible = units[units.map(per_building).ge(3)].index.to_numpy()
    chosen = set(
        np.random.default_rng(seed).choice(
            np.sort(eligible), size=int(round(fraction * len(units))), replace=False
        )
    )
    for _, members in units.reset_index().groupby("building").unit_id:
        members = sorted(members)
        if set(members) <= chosen:  # every building keeps at least one training unit
            chosen.discard(members[0])
    test = data.unit_id.isin(chosen).to_numpy()
    return data[~test].reset_index(drop=True), data[test].reset_index(drop=True)


FIXED = ("sigma", "sigma_unit", "sigma_building", "trend_scale", "bedroom_walk_scale")
DESCRIPTIONS = Path(
    "/home/ben/code/apartments/data/model/chelsea-refreshed-bayesian-descriptions-20260918/evidence.jsonl"
)
DUPLEX = r"\b(?:duplex|triplex)\b"
PRIVATE_OUTDOOR = (
    r"\b(?:private|your own|own private|exclusive)\s+(?:outdoor space|terrace|balcony|roof ?deck|rooftop|"
    r"garden|patio|backyard|yard)"
)
SHARED_BATH = r"\b(?:sro|single room occupancy|shared (?:bath|baths|bathroom|bathrooms|kitchen)|share ?bath)\b"
DATASET = None
EXTRA = {
    # Unit label (source identity), not description text: "penthouse" in text is
    # mostly building amenities ("penthouse lounge") and is not used.
    "penthouse_label": lambda f, d: (
        f.canonical_unit_url.str.rsplit("/", n=1)
        .str[-1]
        .str.lower()
        .str.match(r"^(ph|penthouse)")
        .to_numpy()
    ),
    "duplex_text": lambda f, d: d.str.contains(DUPLEX).to_numpy(),
    "private_outdoor_text": lambda f, d: d.str.contains(PRIVATE_OUTDOOR).to_numpy(),
    "shared_bath_text": lambda f, d: d.str.contains(SHARED_BATH).to_numpy(),
    # Unit-level versions: a unit is flagged when any of its own advertisements
    # matches. Ad text varies between relistings; the attribute should not.
    "duplex_unit": lambda f, d: unit_any(f, DUPLEX),
    "private_outdoor_unit": lambda f, d: unit_any(f, PRIVATE_OUTDOOR),
    "shared_bath_unit": lambda f, d: unit_any(f, SHARED_BATH),
    # As-of flags: only the unit's own ads at or before this listing count, so
    # later ad text is never carried back onto earlier listings.
    "duplex_asof": lambda f, d: unit_asof(f, DUPLEX),
    "private_outdoor_asof": lambda f, d: unit_asof(f, PRIVATE_OUTDOOR),
    "shared_bath_asof": lambda f, d: unit_asof(f, SHARED_BATH),
    # Convex size premium: log area above 20% over the bedroom-count median
    # (0 when area is unknown; the linear term and missing indicator stay).
    "large_area_hinge": lambda f, d: large_area(f),
    # Era interactions: premium change per decade, centered at 2018.
    "size_x_time": lambda f, d: relative_size(f) * decades(f),
    "laundry_in_unit_x_time": lambda f, d: (
        f.laundry_type.eq("in_unit").to_numpy(dtype=float) * decades(f)
    ),
    # Building covariates from archived building pages (year built is a
    # placeholder for most buildings and is not used).
    "log_stories": lambda f, d: building_covariate(f, "stories", log=True),
    "stories_unknown": lambda f, d: building_covariate(f, "stories", unknown=True),
    "log_units": lambda f, d: building_covariate(f, "residential_units", log=True),
    "units_unknown": lambda f, d: building_covariate(
        f, "residential_units", unknown=True
    ),
}
BUILDINGS = Path(
    "/home/ben/code/apartments/data/model/building-covariates-20260923/buildings.csv"
)


def building_covariate(frame, column, log=False, unknown=False):
    import pandas as pd

    if "buildings" not in UNIT_TEXT:
        UNIT_TEXT["buildings"] = pd.read_csv(BUILDINGS).set_index("building")
    values = frame.building.map(UNIT_TEXT["buildings"][column]).astype(float)
    values = values.where(values > 0)
    if unknown:
        return values.isna().to_numpy(dtype=float)
    return (
        np.log(values).fillna(0.0).to_numpy() if log else values.fillna(0.0).to_numpy()
    )


def decades(frame):
    import pandas as pd

    return (
        (
            pd.to_datetime(frame.period).dt.year
            + pd.to_datetime(frame.period).dt.month / 12.0
        )
        - 2018.0
    ).to_numpy() / 10.0


def relative_size(frame):
    import pandas as pd

    if "medians" not in UNIT_TEXT:
        rows = pd.read_json(DATASET / "observations.jsonl", lines=True)
        UNIT_TEXT["medians"] = (
            pd.to_numeric(rows.square_feet, errors="coerce")
            .groupby(rows.bedrooms)
            .median()
        )
    area = pd.to_numeric(frame.square_feet, errors="coerce")
    return (
        np.log(area / frame.bedrooms.map(UNIT_TEXT["medians"])).fillna(0.0).to_numpy()
    )


def large_area(frame):
    import pandas as pd

    if "medians" not in UNIT_TEXT:
        rows = pd.read_json(DATASET / "observations.jsonl", lines=True)
        UNIT_TEXT["medians"] = (
            pd.to_numeric(rows.square_feet, errors="coerce")
            .groupby(rows.bedrooms)
            .median()
        )
    area = pd.to_numeric(frame.square_feet, errors="coerce")
    relative = np.log(area / frame.bedrooms.map(UNIT_TEXT["medians"]))
    return np.maximum(relative.fillna(-np.inf).to_numpy() - 0.2, 0.0)


UNIT_TEXT = {}


def unit_asof(frame, pattern):
    key = ("asof", pattern)
    if key not in UNIT_TEXT:
        import pandas as pd

        rows = pd.read_json(DATASET / "observations.jsonl", lines=True)[
            ["audit_id", "unit_id", "period"]
        ]
        rows["hit"] = descriptions(rows).str.contains(pattern).to_numpy()
        rows = rows.sort_values(["unit_id", "period", "audit_id"])
        rows["asof"] = rows.groupby("unit_id")["hit"].cummax()
        UNIT_TEXT[key] = rows.set_index("audit_id")["asof"]
    return frame.audit_id.map(UNIT_TEXT[key]).fillna(False).to_numpy()


def unit_any(frame, pattern):
    if pattern not in UNIT_TEXT:
        import pandas as pd

        rows = pd.read_json(DATASET / "observations.jsonl", lines=True)[
            ["audit_id", "unit_id"]
        ]
        hit = descriptions(rows).str.contains(pattern).to_numpy()
        UNIT_TEXT[pattern] = rows.assign(hit=hit).groupby("unit_id").hit.any()
    return frame.unit_id.map(UNIT_TEXT[pattern]).fillna(False).to_numpy()


def descriptions(frame):
    import json as _json

    text = {}
    with DESCRIPTIONS.open() as stream:
        for line in stream:
            record = _json.loads(line)
            if record.get("description"):
                text[record["audit_id"]] = record["description"].lower()
    return frame.audit_id.map(text).fillna("")


class ExtendedDesign:
    """Screening-only design: the frozen feature design plus centered 0/1 flags."""

    def __init__(self, base, train, names, scale=0.2):
        self.base, self.names, self.time = base, list(names), base.time
        self.means = self.raw(train).mean(0)
        self.features = [*base.features, *self.names]
        self.prior_scales = np.r_[base.prior_scales, np.full(len(self.names), scale)]

    def raw(self, frame):
        text = (
            descriptions(frame)
            if any(n.endswith("_text") for n in self.names)
            else None
        )
        return (
            np.column_stack([EXTRA[n](frame, text).astype(float) for n in self.names])
            if self.names
            else np.zeros((len(frame), 0))
        )

    def matrix(self, frame):
        return np.column_stack([self.base.matrix(frame), self.raw(frame) - self.means])

    def __getattr__(self, name):
        return getattr(self.base, name)


def predictive(posterior, design, test, options, building_weights, thin, shock=None):
    d = design.time
    a = d.arrays(test)
    if (a["building"] < 0).any():
        raise ValueError("Held-out rows must have fitted buildings")
    unseen = a["unit"] < 0
    p = posterior.stack(sample=("chain", "draw")).isel(sample=slice(None, None, thin))
    x = design.matrix(test)
    monthly = (d.time_matrix - d.time_center) @ p.trend_coefficients.values + np.outer(
        d.linear_time - d.linear_center, p.annual_drift.values
    )
    seasonal = (
        d.season_matrix - d.season_weights @ d.season_matrix
    ) @ p.season_coefficients.values
    mu = (
        p.alpha.values[None]
        + x @ p.beta.values
        + monthly[a["period"]]
        + seasonal[a["season"]]
        + p.building_effect.values[a["building"]]
        + np.where(
            unseen[:, None],
            0.0,
            p.sigma_unit.values[None] * p.unit_z.values[np.maximum(a["unit"], 0)],
        )
    )
    g = graph.groups(test.bedrooms, options["bedroom_groups"])
    mu = mu + p.bedroom_time.values[g, a["period"]]
    mu = mu + graph.building_time_numpy(
        p,
        design,
        test,
        building_weights,
        building_time=options["building_time"],
        building_scale=options["building_scale"],
        building_knot_years=options["building_knot_years"],
        centering_rows=options.get("centering_rows"),
    )
    if "citywide_walk" in p:
        mu = mu + p["citywide_walk"].values[a["period"]]
    if shock and shock["months"]:
        mu = mu + graph.building_shock_numpy(
            p,
            design,
            test,
            shock["weights"],
            shock_months=shock["months"],
            shock_scale=shock["scale"],
        )
    if "building_bedroom_slope_z" in p:
        step = np.minimum(test.bedrooms.to_numpy(dtype=float), 4.0) - 1.0
        mu = mu + (
            p["building_bedroom_slope_scale"].values[None]
            * p["building_bedroom_slope_z"].values[a["building"]]
            * step[:, None]
        )
    if "building_feature_slope_z" in p:
        raw, raw_names, _ = design.raw_features(test)
        names = [str(n) for n in p["slope_feature"].values]
        columns = raw[:, [raw_names.index(n) for n in names]].astype(float)
        flat = p["building_feature_slope_z"].values  # (building*feature, sample)
        z = flat.reshape(len(d.buildings), len(names), flat.shape[-1])
        slopes = (
            p["building_feature_slope_scale"].values[None] * z[a["building"]]
        )  # rows x features x samples
        mu = mu + np.einsum("rf,rfs->rs", columns, slopes)
    if "unit_slope_z" in p:
        years = (np.arange(len(d.periods)) - d.anchor) / 12.0
        known = np.maximum(a["unit"], 0)
        scale = (
            p["unit_slope_scale"].values[None]
            if "unit_slope_scale" in p
            else options["unit_slope_scale"]
        )
        drift = (
            scale
            * p["unit_slope_z"].values[known]
            * (years[a["period"]] - options["unit_year_centers"][known])[:, None]
        )
        mu = mu + np.where(unseen[:, None], 0.0, drift)
    nu = p["nu"].values[None] if "nu" in p else 5.0
    sigma = p.sigma.values[None] * np.ones((len(test), 1))
    if "noise_level_slope" in p:
        center = float(np.mean(np.log(options["train_rent"])))
        sigma = p.sigma.values[None] * np.exp(
            p["noise_level_slope"].values[None] * (mu - center)
        )
    if "noise_building_z" in p:
        tau = (
            p["noise_building_scale"].values
            if "noise_building_scale" in p
            else np.full(p.sigma.shape, options["noise_scale"])
        )
        sigma = p.sigma.values[None] * np.exp(
            tau[None] * p["noise_building_z"].values[a["building"]]
        )
    y = np.log(test.asking_rent.to_numpy())[:, None]
    if unseen.any():
        # A new unit's effect is unknown: integrate sigma_unit * z, z ~ N(0, 1),
        # with fixed-seed draws (repeated per posterior draw when there are few).
        k = max(1, UNSEEN_UNIT_DRAWS // mu.shape[1])
        z = np.random.default_rng(0).standard_normal((mu.shape[0], mu.shape[1] * k))
        mu_k = np.repeat(mu, k, axis=1) + np.where(
            unseen[:, None], np.repeat(p.sigma_unit.values, k)[None] * z, 0.0
        )
        nu_k = np.repeat(nu, k, axis=1) if np.ndim(nu) else nu
        logpdf = stats.t.logpdf(y, nu_k, loc=mu_k, scale=np.repeat(sigma, k, axis=1))
    else:
        logpdf = stats.t.logpdf(y, nu, loc=mu, scale=sigma)
    lpd = special.logsumexp(logpdf, axis=1) - math.log(logpdf.shape[1])
    return lpd, y[:, 0] - np.median(mu, axis=1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--method", choices=("nuts", "map"), default="map")
    parser.add_argument("--fix-scales-from", type=Path)
    parser.add_argument(
        "--free-scales",
        default="",
        help="Comma-separated FIXED names to leave free (global scalars only)",
    )
    parser.add_argument("--bedroom-groups", type=int, choices=(4, 5), default=4)
    parser.add_argument("--building-time", choices=graph.BUILDING_TIME, default="none")
    parser.add_argument("--building-scale", type=float, default=None)
    parser.add_argument("--building-knot-years", type=float, default=4)
    parser.add_argument(
        "--building-scale-prior",
        type=float,
        default=0.02,
        help="HalfNormal prior scale for the drift scale when --building-scale is omitted",
    )
    parser.add_argument("--estimate-nu", action="store_true")
    parser.add_argument(
        "--noise", choices=("shared", "building", "level"), default="shared"
    )
    parser.add_argument("--noise-scale", type=float, default=None)
    parser.add_argument("--building-bedroom-slope", action="store_true")
    parser.add_argument("--citywide-walk-months", type=int, default=None)
    parser.add_argument(
        "--walk-centering", choices=("none", "across_buildings"), default="none"
    )
    parser.add_argument(
        "--building-feature-slopes",
        default="",
        help="Comma-separated raw design columns with per-building slopes",
    )
    parser.add_argument(
        "--unit-slope-scale",
        type=lambda v: v if v == "free" else float(v),
        default=None,
        help="Fixed per-unit drift scale, or free (NUTS only)",
    )
    parser.add_argument(
        "--extra-features",
        default="",
        help="Comma-separated screening flags: " + ", ".join(EXTRA),
    )
    parser.add_argument("--shock-months", type=int, default=None)
    parser.add_argument("--shock-scale", type=float, default=None)
    parser.add_argument("--shock-scale-prior", type=float, default=0.05)
    parser.add_argument("--fraction", type=float, default=0.10)
    parser.add_argument(
        "--split",
        choices=("rows", "units"),
        default="rows",
        help="rows: 10%% of rows from repeat units; units: every row of 10%% of units",
    )
    parser.add_argument("--split-seed", type=int, default=20260922)
    parser.add_argument("--seed", type=int, default=20260918)
    parser.add_argument("--tune", type=int, default=1000)
    parser.add_argument("--draws", type=int, default=1000)
    parser.add_argument("--chains", type=int, default=4)
    parser.add_argument("--thin", type=int, default=2)
    parser.add_argument("--maxeval", type=int, default=50000)
    args = parser.parse_args()
    global DATASET
    DATASET = args.dataset
    args.output.mkdir(parents=True, exist_ok=True)
    data, _ = v3.load_data(args.dataset)
    train, test = (split if args.split == "rows" else split_units)(
        data, args.fraction, args.split_seed
    )
    design = floor.FeatureDesign(train, "full_half_balance", floor_prior_scale=0.10)
    values = floor.listed_floor_values(test)
    supported = ~np.isfinite(values) | (
        (values >= min(design.floor_levels)) & (values <= max(design.floor_levels))
    )
    test = test[
        supported
        & test.period.between(
            design.time.periods[0], design.time.periods[-1]
        ).to_numpy()
    ]
    test = test.reset_index(drop=True)
    extra = [n for n in args.extra_features.split(",") if n]
    if extra:
        design = ExtendedDesign(design, train, extra)
    options = {
        "bedroom_groups": args.bedroom_groups,
        "building_time": args.building_time,
        "building_scale": args.building_scale,
        "building_knot_years": args.building_knot_years,
    }
    model = graph.build_model(
        train,
        design,
        nu=None if args.estimate_nu else 5.0,
        building_scale_prior=args.building_scale_prior,
        shock_months=args.shock_months,
        shock_scale=args.shock_scale,
        shock_scale_prior=args.shock_scale_prior,
        noise=args.noise,
        noise_scale=args.noise_scale,
        unit_slope_scale=args.unit_slope_scale,
        building_bedroom_slope=args.building_bedroom_slope,
        citywide_walk_months=args.citywide_walk_months,
        walk_centering=args.walk_centering,
        building_feature_slopes=tuple(
            n for n in args.building_feature_slopes.split(",") if n
        ),
        **options,
    )
    started = time.monotonic()
    diagnostic = None
    if args.method == "map":
        fixed = None
        if args.fix_scales_from:
            saved = json.loads(args.fix_scales_from.read_text())["scalars"]
            free = set(filter(None, args.free_scales.split(",")))
            fixed = {n: saved[n]["mean"] for n in FIXED if n in saved and n not in free}
        posterior = map_posterior(model, args.seed, args.maxeval, fixed)
    else:
        import nutpie

        compiled = nutpie.compile_pymc_model(model, backend="numba")
        inference = nutpie.sample(
            compiled,
            draws=args.draws,
            tune=args.tune,
            chains=args.chains,
            cores=args.chains,
            seed=args.seed,
            target_accept=0.93,
            progress_bar=False,
        )
        diagnostic, _ = v3.v2.base.diagnostics(inference)
        posterior = inference["posterior"].to_dataset()
    elapsed = time.monotonic() - started
    shock = {
        "months": args.shock_months,
        "scale": args.shock_scale,
        "weights": getattr(model, "shock_weights", None),
    }
    lpd, error = predictive(
        posterior,
        design,
        test,
        {
            **options,
            "noise_scale": args.noise_scale,
            "train_rent": train.asking_rent.to_numpy(),
            "unit_slope_scale": args.unit_slope_scale,
            "unit_year_centers": getattr(model, "unit_year_centers", None),
            "centering_rows": np.bincount(
                design.time.arrays(train)["building"],
                minlength=len(design.time.buildings),
            )
            if args.walk_centering == "across_buildings"
            else None,
        },
        model.building_weights,
        args.thin if args.method == "nuts" else 1,
        shock,
    )
    scalars = {
        n: {"mean": float(posterior[n].mean()), "sd": float(posterior[n].std())}
        for n in (
            "alpha",
            "sigma",
            "sigma_unit",
            "sigma_building",
            "annual_drift",
            "trend_scale",
            "season_scale",
            "bedroom_walk_scale",
            "building_time_scale",
            "building_shock_scale",
            "nu",
            "noise_level_slope",
            "unit_slope_scale",
            "building_bedroom_slope_scale",
            "citywide_walk_scale",
        )
        if n in posterior
    }
    if "building_feature_slope_scale" in posterior:
        for name in posterior["slope_feature"].values:
            draws = posterior["building_feature_slope_scale"].sel(slope_feature=name)
            scalars[f"building_feature_slope_scale[{name}]"] = {
                "mean": float(draws.mean()),
                "sd": float(draws.std()),
            }
    coefficients = {}
    if extra:
        beta = posterior["beta"].stack(sample=("chain", "draw")).values
        for name in extra:
            i = design.features.index(name)
            coefficients[name] = {
                "mean": float(beta[i].mean()),
                "sd": float(beta[i].std()),
                "rows": int(design.raw(train)[:, extra.index(name)].sum()),
            }
    result = {
        "method": args.method,
        "split": args.split,
        **options,
        "extra_features": coefficients,
        "estimate_nu": args.estimate_nu,
        "seconds": elapsed,
        "shock_months": args.shock_months,
        "shock_scale": args.shock_scale,
        "train_rows": len(train),
        "scalars": scalars,
        "heldout": summarize(test, lpd, error),
        "diagnostics": diagnostic,
        "configuration": model.graph_configuration,
    }
    np.savez_compressed(
        args.output / "heldout.npz",
        lpd=lpd,
        error=error,
        audit_id=test.audit_id.to_numpy(),
    )
    (args.output / "result.json").write_text(
        json.dumps(result, indent=1, default=float) + "\n"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "seconds": round(elapsed),
                "elpd": result["heldout"]["elpd"],
                **{
                    k: v["mean"]
                    for k, v in scalars.items()
                    if k in ("nu", "building_time_scale")
                },
            }
        )
    )


if __name__ == "__main__":
    with threadpool_limits(limits=1, user_api="blas"):
        main()
