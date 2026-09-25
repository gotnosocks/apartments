"""Combined candidate v2: the LAST code-hash protocol version (Ben, September 24).

After this fit, new work follows the self-contained experiment-script
convention and the shared summary-output reader; do not add protocol versions.

v2 adds graph v5's accepted terms (screen log, September 23-24): a
per-building bedroom slope, per-building slopes on log size within bedrooms
and 2+/3+ full baths, an estimated Student-t nu, and a quarterly citywide
random walk with the building walks centered across buildings (neutral on
accuracy, faster sampling). Residual reports add a leave-own-row-out fitted
rent (Pareto-smoothed importance sampling), so a listing can be compared with
an estimate that is not pulled toward its own ask.

v1 description follows.

Combined candidate: efficient parameterization, as-of attributes, per-unit drift.

Same stages and reports as `bayesian_drift_experiment` (bedroom-group time
curve, per-building half-year random walk, per-unit linear drift, bounded
building/unit caches). Differences:

* feature design `bayesian_attribute_design_v2`: attribute flags as of each
  listing (the unit's own ads at or before it; never carried backward);
* graph `bayesian_structure_graph_v3` with the iteration-speed
  reparameterizations that leave the model unchanged: intercept as the
  building-level mean, within-building feature centering, QR feature basis.
  Removing the building walks' common drift is NOT used: it is a model change
  (the citywide trend basis cannot absorb the sharp 2021 rebound; the E3 fit
  over-predicted 2021-22 by about 1.7%);
* right-sized defaults of 1,000 warmup + 3,000 draws per chain (1,500 left 13
  of 65k parameters at R-hat 1.010-1.016 in E3), with unchanged gates.

Research fit: publishing it never changes the main selection.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
from pathlib import Path

import numpy as np
import xarray as xr
from threadpoolctl import threadpool_limits

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from . import bayesian_attribute_experiment as previous
from . import bayesian_structure_graph_v5 as graph
from . import bayesian_attribute_design_v2 as asof
from . import bayesian_location_terms_v2 as location_terms

structure = previous.previous
VERSION = "observable-bayesian-combined-experiment-v2"
UNIT_DRIFT_VERSION = "unit-drift-summary-v1"
EXTENSIONS_VERSION = "structure-extensions-summary-v1"
FEATURE_SLOPES = (
    "log_size_within_bedrooms",
    # Per-building offset for unsized listings: removes the size-slope
    # bimodality at buildings mixing sized lofts with unsized small units
    # (110 W 26th; screen +41.1 +/- 9.6 on units, neutral on rows).
    "size_missing",
    "full_bathrooms_gt_1",
    "full_bathrooms_gt_2",
)
CITYWIDE_WALK_MONTHS = 3
if location_terms.COMBINED_V2_EXPERIMENT != VERSION:
    raise ImportError("Reader and runner disagree on the combined version")
attribute = previous.attribute
floor, storage, disk_protocol, execution, report_cache = (
    previous.floor,
    previous.storage,
    previous.disk_protocol,
    previous.execution,
    previous.report_cache,
)
v2 = previous.v2
load_data = previous.load_data
floor_contrasts = previous.floor_contrasts
building_cache = structure.building_cache
REQUIRED_FIT = previous.REQUIRED_FIT | {"unit-drift.json", "structure-extensions.json"}
CACHE_BLOCK_BYTES = 64 * 1024 * 1024


def validate_args(args):
    previous.validate_args(args)


def graph_kwargs(args):
    return {
        "building_time": "walk",
        "building_knot_years": args.building_knot_years,
        "building_scale": None,
        "building_scale_prior": args.building_scale_prior,
        "walk_prior_scale": args.bedroom_walk_prior_scale,
        "building_prior_scale": args.building_prior_scale,
        "unit_prior_scale": args.unit_prior_scale,
        "prior_multiplier": args.prior_multiplier,
        "unit_slope_scale": "free",
        "intercept": "building_mean",
        "walk_centering": "across_buildings",
        "feature_basis": args.feature_basis,
        "feature_centering": "building",
        "nu": None,
        "building_bedroom_slope": True,
        "bedroom_slope_prior": 0.1,
        "building_feature_slopes": FEATURE_SLOPES,
        "feature_slope_prior": 0.1,
        "citywide_walk_months": CITYWIDE_WALK_MONTHS,
        "citywide_walk_prior": 0.05,
    }


def attributes(args, data):
    """As-of attribute flags from the verified description archive bound to the dataset."""
    from apartments.bayesian_evidence import load_evidence

    captures = load_evidence(args.dataset, args.evidence)
    return asof.attribute_audits(data, captures), digest(
        Path(args.evidence) / "complete.json"
    )


def implementation_paths(base=None):
    return [
        *previous.implementation_paths(),
        Path(asof.__file__),
        Path(graph.__file__),
        Path(location_terms.__file__),
        Path(__file__),
    ]


def make_protocol(args, data, source, code, configuration, units, evidence_sha):
    result = previous.make_protocol(
        args, data, source, code, configuration, units, evidence_sha
    )
    result.pop("attribute_units_sha256", None)
    result.update(
        feature_design_version=asof.VERSION,
        attribute_policy=asof.policy(),
        attribute_audits_sha256=hashlib.sha256(canonical(units).encode()).hexdigest(),
        attribute_counts={k: len(v) for k, v in units.items()},
        reparameterization="intercept as building-level mean; within-building feature centering; "
        "QR feature basis; building walks centered across buildings (with a citywide walk)",
        last_code_hash_protocol=True,
        building_feature_slopes=list(FEATURE_SLOPES),
        citywide_walk_months=CITYWIDE_WALK_MONTHS,
        likelihood="Student-t(log gross asking rent) with estimated nu ~ Gamma(2, 0.1)",
        structure_extensions="per-building bedroom slope tau*z_b*(min(beds,4)-1), tau~HalfNormal(0.1); "
        "per-building slopes on raw log_size_within_bedrooms, size_missing, full_bathrooms_gt_1, "
        "full_bathrooms_gt_2 (tau_j~HalfNormal(0.1)); quarterly citywide random walk "
        "(scale~HalfNormal(0.05)), centered on training rows",
        version=VERSION,
        unit_drift="linear per unit, centered on its training years; scale ~ HalfNormal(0.01)",
        graph="Attribute spline design, bedroom-group time deviations, per-building half-year random "
        "walk and per-unit linear drift; unique feature rows compressed losslessly.",
    )
    return result


def validate_posterior(inference, args, design, configuration):
    structure.validate_posterior(inference, args, design, configuration)
    posterior = v2.base.posterior_dataset(inference)
    if (
        "unit_slope_z" not in posterior
        or "unit_slope_scale" not in posterior
        or posterior["unit_slope_z"].dims != ("chain", "draw", "unit")
        or posterior["unit_slope_z"].unit.values.tolist() != list(design.time.unit_ids)
    ):
        raise ValueError("Unit-drift draws differ from the unit design")
    buildings = list(design.time.buildings)
    expected = {
        "nu": (),
        "building_bedroom_slope_scale": (),
        "building_bedroom_slope_z": ("building",),
        "building_feature_slope_scale": ("slope_feature",),
        "building_feature_slope_z": ("building_slope",),
        "citywide_walk_scale": (),
        "citywide_walk": ("period",),
        "building_walk_common": ("building_walk_knot",),
    }
    for name, dims in expected.items():
        if name not in posterior or posterior[name].dims != ("chain", "draw", *dims):
            raise ValueError(f"Combined v2 draws missing or misshaped: {name}")
    if (
        posterior["building_bedroom_slope_z"].building.values.tolist() != buildings
        or posterior["slope_feature"].values.tolist() != list(FEATURE_SLOPES)
        or posterior.sizes["building_slope"] != len(buildings) * len(FEATURE_SLOPES)
    ):
        raise ValueError("Per-building slope draws differ from the design")


def unit_cache(posterior, directory, posterior_sha256):
    """Unit-major, sample-contiguous copy of unit_slope_z (bounded reads)."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path, marker = directory / "unit-slope-samples.npy", directory / "complete.json"
    variable = posterior["unit_slope_z"].transpose("chain", "draw", "unit")
    chains, draws, width = variable.shape
    identity = {
        "version": UNIT_DRIFT_VERSION,
        "posterior_sha256": posterior_sha256,
        "chains": chains,
        "draws": draws,
        "units": width,
        "dtype": str(variable.dtype),
        "sample_order": "chain_major_then_draw",
    }
    if marker.exists():
        saved = json.loads(marker.read_text())
        if saved["identity"] != identity or digest(path) != saved["cache_sha256"]:
            raise ValueError("Unit-slope cache identity or contents changed")
        return np.load(path, mmap_mode="r", allow_pickle=False)
    if path.exists():
        raise ValueError("Incomplete unit-slope cache; use a new cache directory")
    mapped = np.lib.format.open_memmap(
        path,
        mode="w+",
        dtype=variable.dtype,
        shape=(chains * draws, width),
        fortran_order=True,
    )
    step = max(1, CACHE_BLOCK_BYTES // (width * variable.dtype.itemsize))
    for chain in range(chains):
        for start in range(0, draws, step):
            stop = min(draws, start + step)
            block = variable.isel(chain=chain, draw=slice(start, stop)).values
            if not np.isfinite(block).all():
                raise ValueError("Nonfinite unit-drift draws")
            mapped[chain * draws + start : chain * draws + stop] = block
    mapped.flush()
    del mapped
    marker.write_text(
        canonical({"identity": identity, "cache_sha256": digest(path)}) + "\n"
    )
    return np.load(path, mmap_mode="r", allow_pickle=False)


def loo_quantiles(mu, loglik, probabilities=(0.025, 0.5, 0.975)):
    """Leave-own-row-out quantiles of mu per row by Pareto-smoothed importance
    sampling: weights proportional to 1 / p(y_i | theta_s).

    mu, loglik: samples x rows. Returns (quantiles x rows, pareto_k per row)."""
    from arviz_stats.base import array_stats

    # arviz_stats' psislw takes the log-likelihood and negates it internally.
    log_weights, pareto_k = array_stats.psislw(loglik.T, axis=-1)
    weights = np.exp(log_weights - log_weights.max(1, keepdims=True))
    order = np.argsort(mu.T, axis=1)
    sorted_mu = np.take_along_axis(mu.T, order, axis=1)
    cumulative = np.cumsum(np.take_along_axis(weights, order, axis=1), axis=1)
    cumulative /= cumulative[:, -1:]
    result = np.empty((len(probabilities), mu.shape[1]))
    for q, probability in enumerate(probabilities):
        index = (cumulative < probability).sum(1)
        result[q] = sorted_mu[
            np.arange(mu.shape[1]), np.minimum(index, mu.shape[0] - 1)
        ]
    return result, np.array(pareto_k, dtype=float)


def fitted_summary(inference, design, data, protocol, building_samples, unit_slopes):
    """Residual rows in source order.

    mu adds the bedroom curve, the centered building walk, per-unit drift, the
    per-building bedroom and feature slopes and the citywide walk. Each row also
    carries a leave-own-row-out (PSIS) fitted rent and its Pareto k."""
    from scipy import stats

    base = v2.base
    p = base.posterior_dataset(inference)
    samples = {
        name: base.sample_values(p, name)
        for name in (
            "alpha",
            "beta",
            "trend_coefficients",
            "annual_drift",
            "season_coefficients",
            "building_effect",
            "sigma_unit",
            "unit_z",
            "building_time_scale",
            "unit_slope_scale",
            "sigma",
            "nu",
            "building_bedroom_slope_scale",
            "building_bedroom_slope_z",
            "building_feature_slope_scale",
            "building_feature_slope_z",
            "citywide_walk",
            "building_walk_common",
        )
    }
    curve = (
        p["bedroom_time"]
        .stack(sample=("chain", "draw"))
        .transpose("sample", "bedroom_group", "period")
        .values
    )
    d = design.time
    a = d.arrays(data)
    x = design.matrix(data)
    group = graph.groups(data.bedrooms, 4)
    step = location_terms.bedroom_step(data.bedrooms)
    slope_columns = location_terms.feature_columns(design, data, FEATURE_SLOPES)
    feature_z = samples["building_feature_slope_z"].reshape(
        len(samples["alpha"]), len(d.buildings), len(FEATURE_SLOPES)
    )
    knot_years = protocol["building_knot_years"]
    basis, _ = location_terms.v1.building_knots(d.periods, knot_years)
    centers = location_terms.v1.building_centers(
        a["building"], a["period"], len(d.buildings), basis
    )
    unit_years = location_terms.unit_year_centers(design, data)
    years = (np.arange(len(d.periods)) - d.anchor) / 12.0
    width = basis.shape[1]
    log_rent = np.log(data.asking_rent.to_numpy(dtype=float))
    # A unit listed once is informed about its own effect only by this row, so
    # importance sampling cannot remove it (Pareto k explodes). Leaving the row
    # out returns that unit effect to its prior, which is drawn exactly here
    # (other parameters are shared by ~52k rows and barely move). Its drift term
    # is zero by construction (centered on its only year).
    single = np.bincount(a["unit"], minlength=len(d.unit_ids)) == 1
    rng = np.random.default_rng(20260924)
    prior_unit = rng.standard_normal((len(samples["alpha"]), int(single.sum())))
    prior_column = np.full(len(d.unit_ids), -1)
    prior_column[single] = np.arange(int(single.sum()))
    rows = [None] * len(data)
    order = np.argsort(a["building"], kind="stable")
    for building in np.unique(a["building"]):
        members = order[a["building"][order] == building]
        z = np.asarray(building_samples[:, building * width : (building + 1) * width])
        for start in range(0, len(members), 128):
            sl = members[start : start + 128]
            periods = a["period"][sl]
            walk = location_terms.centered_building_walk(
                z,
                samples["building_time_scale"],
                knot_years,
                basis[periods],
                centers[building],
                samples["building_walk_common"],
            )
            units = a["unit"][sl]
            drift = (
                samples["unit_slope_scale"][:, None]
                * np.asarray(unit_slopes[:, units])
                * (years[periods] - unit_years[units])[None]
            )
            slopes = (
                samples["building_bedroom_slope_scale"][:, None]
                * samples["building_bedroom_slope_z"][:, [building]]
                * step[sl][None]
                + (samples["building_feature_slope_scale"] * feature_z[:, building])
                @ slope_columns[sl].T
            )
            mu = (
                samples["alpha"][:, None]
                + samples["beta"] @ x[sl].T
                + samples["trend_coefficients"]
                @ (d.time_matrix - d.time_center)[periods].T
                + samples["annual_drift"][:, None]
                * (d.linear_time - d.linear_center)[periods]
                + samples["season_coefficients"]
                @ (d.season_matrix - d.season_weights @ d.season_matrix)[
                    a["season"][sl]
                ].T
                + samples["building_effect"][:, a["building"][sl]]
                + samples["sigma_unit"][:, None] * samples["unit_z"][:, units]
                + curve[:, group[sl], periods]
                + walk
                + drift
                + slopes
                + samples["citywide_walk"][:, periods]
            )
            quantiles = np.exp(np.quantile(mu, [0.025, 0.5, 0.975], axis=0))
            loglik = stats.t.logpdf(
                log_rent[sl][None],
                df=samples["nu"][:, None],
                loc=mu,
                scale=samples["sigma"][:, None],
            )
            loo, pareto_k = loo_quantiles(mu, loglik)
            once = single[units]
            if once.any():
                replaced = mu[:, once] + samples["sigma_unit"][:, None] * (
                    prior_unit[:, prior_column[units[once]]]
                    - samples["unit_z"][:, units[once]]
                )
                loo[:, once] = np.quantile(replaced, [0.025, 0.5, 0.975], axis=0)
                pareto_k[once] = np.nan
            loo = np.exp(loo)
            for j, i in enumerate(sl):
                row = data.iloc[i]
                estimate = float(quantiles[1, j])
                held_out = float(loo[1, j])
                rows[i] = {
                    "audit_id": row.audit_id,
                    "source_listing_id": str(row.source_listing_id),
                    "unit_id": row.unit_id,
                    "building": row.building,
                    "period": row.period.strftime("%Y-%m-%d"),
                    "asking_rent": float(row.asking_rent),
                    "fitted_rent": estimate,
                    "latent_rent_lower_95": float(quantiles[0, j]),
                    "latent_rent_upper_95": float(quantiles[2, j]),
                    "residual_dollars": float(row.asking_rent - estimate),
                    "residual_log": float(np.log(row.asking_rent / estimate)),
                    "loo_fitted_rent": held_out,
                    "loo_latent_rent_lower_95": float(loo[0, j]),
                    "loo_latent_rent_upper_95": float(loo[2, j]),
                    "loo_residual_log": float(np.log(row.asking_rent / held_out)),
                    "loo_method": "unit_prior" if once[j] else "psis",
                    "loo_pareto_k": None if once[j] else float(pareto_k[j]),
                }
    if any(r is None for r in rows):
        raise ValueError("Every source row needs a fitted residual")
    return rows, samples


def building_time_summary(inference, design, data, protocol, building_samples):
    """Latest building offsets from the centered walks (structure's summary otherwise)."""
    posterior = v2.base.posterior_dataset(inference)
    summary = structure.building_time_summary(
        inference, design, data, protocol, building_samples
    )
    years = protocol["building_knot_years"]
    basis, _ = location_terms.v1.building_knots(design.time.periods, years)
    a = design.time.arrays(data)
    centers = location_terms.v1.building_centers(
        a["building"], a["period"], len(design.time.buildings), basis
    )
    scale = v2.base.sample_values(posterior, "building_time_scale")
    common = v2.base.sample_values(posterior, "building_walk_common")
    width = basis.shape[1]
    shifts = []
    for building, name in enumerate(design.time.buildings):
        z = np.asarray(building_samples[:, building * width : (building + 1) * width])
        value = location_terms.centered_building_walk(
            z, scale, years, basis[[-1]], centers[building], common
        )[:, 0]
        shifts.append(
            {"building": name, "latest_log_offset": v2.reports.interval(value)}
        )
    summary["latest_building_offsets"] = shifts
    summary["centering"] = (
        "Building walks centered across buildings (row-weighted) at every knot; "
        "the citywide walk carries shared movement."
    )
    return summary


def residual_scale_summary(inference, data, configuration):
    summary = previous.residual_scale_summary(inference, data, configuration)
    nu = v2.base.sample_values(v2.base.posterior_dataset(inference), "nu")
    summary["student_t_nu"] = v2.reports.interval(nu)
    summary["interpretation"] = (
        "Separate conditional 95% posterior intervals. Residual variation is not "
        "latent conditional-median uncertainty. nu is estimated; with nu <= 2 the "
        "Student-t has no finite variance, so compare scales, not standard deviations."
    )
    return summary


def extensions_summary(inference, design):
    posterior = v2.base.posterior_dataset(inference)
    names = (
        "nu",
        "building_bedroom_slope_scale",
        "building_feature_slope_scale",
        "citywide_walk_scale",
    )
    diagnostic, _ = v2.base.diagnostics(
        {
            "posterior": xr.Dataset({n: posterior[n] for n in names}),
            "sample_stats": inference["sample_stats"],
        }
    )
    feature_scales = v2.base.sample_values(posterior, "building_feature_slope_scale")
    walk = v2.base.sample_values(posterior, "citywide_walk")
    return {
        "version": EXTENSIONS_VERSION,
        "nu": v2.reports.interval(v2.base.sample_values(posterior, "nu")),
        "building_bedroom_slope_scale": v2.reports.interval(
            v2.base.sample_values(posterior, "building_bedroom_slope_scale")
        ),
        "building_feature_slope_scales": {
            name: v2.reports.interval(feature_scales[:, j])
            for j, name in enumerate(FEATURE_SLOPES)
        },
        "citywide_walk_scale": v2.reports.interval(
            v2.base.sample_values(posterior, "citywide_walk_scale")
        ),
        "citywide_walk": {
            period.strftime("%Y-%m"): v2.reports.interval(walk[:, t])
            for t, period in enumerate(design.time.periods)
        },
        "diagnostics": diagnostic,
        "interpretation": "Scales of per-building bedroom-step and feature-premium "
        "deviations from the Chelsea-wide premiums (log rent), the Student-t degrees of "
        "freedom, and the citywide random walk relative to the training-row mean. "
        "Conditional associations.",
    }


def unit_drift_summary(inference):
    posterior = v2.base.posterior_dataset(inference)
    diagnostic, _ = v2.base.diagnostics(
        {
            "posterior": xr.Dataset(
                {"unit_slope_scale": posterior["unit_slope_scale"]}
            ),
            "sample_stats": inference["sample_stats"],
        }
    )
    return {
        "version": UNIT_DRIFT_VERSION,
        "scale": v2.reports.interval(
            v2.base.sample_values(posterior, "unit_slope_scale")
        ),
        "diagnostics": diagnostic,
        "interpretation": "Scale of per-unit linear log-rent drift per year around each unit's own "
        "training-year mean; single-listing units contribute nothing. Conditional associations.",
    }


def write_reports(
    target,
    inference,
    design,
    data,
    protocol_hash,
    protocol,
    building_samples,
    unit_slopes,
):
    """`bayesian_structure_experiment.write_reports` with unit drift in every location."""
    reports, base = v2.reports, v2.base
    diag, table = base.diagnostics(inference)
    diag["acceptable"] = bool(diag["acceptable"] and diag["maxdepth_reached"] == 0)
    table.to_csv(target / "parameter-diagnostics.csv", index_label="parameter")
    (target / "diagnostics.json").write_text(canonical(diag) + "\n")
    derived, derived_table = v2.derived_diagnostics(inference, design, data)
    derived_table.to_csv(target / "derived-diagnostics.csv", index_label="parameter")
    (target / "derived-diagnostics.json").write_text(canonical(derived) + "\n")
    acceptable = diag["acceptable"] and derived["acceptable"]
    residuals, samples = fitted_summary(
        inference, design, data, protocol, building_samples, unit_slopes
    )
    contrasts = reports.bathroom_contrasts(design, data, samples["beta"])
    contrasts["half_bath_increments"] = v2.half_bath_contrasts(
        design, data, samples["beta"]
    )
    (target / "bathroom-contrasts.json").write_text(canonical(contrasts) + "\n")
    (target / "residuals.jsonl").write_text(
        "".join(canonical(r) + "\n" for r in residuals)
    )
    coefficients = [
        {"feature": name, **reports.interval(samples["beta"][:, i])}
        for i, name in enumerate(design.features)
    ]
    (target / "coefficients.json").write_text(canonical(coefficients) + "\n")
    with (target / "group-effects.jsonl").open("w") as stream:
        for kind, ids, draws in [
            ("building", design.time.buildings, samples["building_effect"]),
            (
                "unit",
                design.time.unit_ids,
                samples["sigma_unit"][:, None] * samples["unit_z"],
            ),
        ]:
            for i, identity in enumerate(ids):
                stream.write(
                    canonical(
                        {
                            "kind": kind,
                            "id": identity,
                            "log_effect": reports.interval(draws[:, i]),
                            "percent_effect": reports.interval(
                                100 * np.expm1(draws[:, i])
                            ),
                        }
                    )
                    + "\n"
                )
    curves = structure.bedroom_time_summary(inference, design)
    (target / "bedroom-time.json").write_text(canonical(curves) + "\n")
    walk = building_time_summary(inference, design, data, protocol, building_samples)
    (target / "building-time.json").write_text(canonical(walk) + "\n")
    drift = unit_drift_summary(inference)
    (target / "unit-drift.json").write_text(canonical(drift) + "\n")
    extensions = extensions_summary(inference, design)
    (target / "structure-extensions.json").write_text(canonical(extensions) + "\n")
    acceptable = (
        acceptable
        and curves["diagnostics"]["acceptable"]
        and walk["diagnostics"]["acceptable"]
        and drift["diagnostics"]["acceptable"]
        and extensions["diagnostics"]["acceptable"]
    )
    summary = {
        "protocol_sha256": protocol_hash,
        "design_support": design.support,
        "diagnostics": diag,
        "derived_diagnostics": derived,
        "bedroom_time_diagnostics": curves["diagnostics"],
        "building_time_diagnostics": walk["diagnostics"],
        "unit_drift_diagnostics": drift["diagnostics"],
        "structure_extensions_diagnostics": extensions["diagnostics"],
        "median_absolute_loo_log_residual": float(
            np.median([abs(r["loo_residual_log"]) for r in residuals])
        ),
        "loo_pareto_k_above_0_7": int(
            sum(
                r["loo_pareto_k"] is not None and r["loo_pareto_k"] > 0.7
                for r in residuals
            )
        ),
        "loo_unit_prior_rows": int(
            sum(r["loo_method"] == "unit_prior" for r in residuals)
        ),
        "status": "exploratory_converged"
        if acceptable
        else "diagnostic_only_do_not_interpret_intervals",
        "median_absolute_log_residual": float(
            np.median([abs(r["residual_log"]) for r in residuals])
        ),
        "latent_intervals": "Uncertainty in the conditional median asking rent of observed units; not predictive intervals or causal values.",
        "bathroom_balance": contrasts["balance"],
        "main_model_changed": False,
    }
    (target / "summary.json").write_text(canonical(summary) + "\n")
    return summary


def completed_fit(target, protocol_hash, configuration):
    manifest, files = _verified_bundle(
        target,
        retain={
            "summary.json",
            "graph-configuration.json",
            "posterior-checkpoint.json",
        },
    )
    if (
        manifest.get("version") != VERSION
        or manifest.get("protocol_sha256") != protocol_hash
        or not REQUIRED_FIT <= manifest["files"].keys()
    ):
        raise ValueError("Completed drift fit protocol/version or products differ")
    summary = json.loads(files["summary.json"])
    if (
        summary.get("protocol_sha256") != protocol_hash
        or json.loads(files["graph-configuration.json"]) != configuration
        or json.loads(files["posterior-checkpoint.json"])
        != {
            "protocol_sha256": protocol_hash,
            "posterior_sha256": manifest["files"]["posterior.nc"],
        }
    ):
        raise ValueError("Completed drift fit summaries or checkpoint differ")
    return summary


def run(args):
    """`bayesian_attribute_experiment.run` with per-unit drift and its bounded reports."""
    validate_args(args)
    root = Path(args.output)
    root.mkdir(exist_ok=True, parents=True)
    with (root / ".run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        data, source = load_data(args.dataset)
        units, evidence_sha = attributes(args, data)
        paths = implementation_paths()
        code = {p.name: digest(p) for p in paths}
        configuration = graph.configuration(
            data, **{k: v for k, v in graph_kwargs(args).items()}
        )
        protocol = make_protocol(
            args, data, source, code, configuration, units, evidence_sha
        )
        ph = hashlib.sha256(canonical(protocol).encode()).hexdigest()
        publish_bundle(
            root / "protocol",
            {
                "protocol.json": canonical(protocol) + "\n",
                **{p.name: p.read_text() for p in paths},
            },
            {"version": VERSION, "protocol_sha256": ph},
        )
        cache_code = Path(report_cache.__file__)
        reporting = {
            "version": report_cache.VERSION,
            "protocol_sha256": ph,
            "implementation_sha256": digest(cache_code),
        }
        publish_bundle(
            root / "reporting-protocol",
            {
                "reporting.json": canonical(reporting) + "\n",
                cache_code.name: cache_code.read_text(),
            },
            reporting,
        )
        target = root / "fit"
        target.mkdir(exist_ok=True)
        if (target / "complete.json").exists():
            result = completed_fit(target, ph, configuration)
            execution.verify_products(
                protocol,
                json.loads((target / "storage.json").read_text()),
                json.loads((target / "trace-manifest.json").read_text()),
                json.loads((target / "complete.json").read_text())["files"][
                    "posterior.nc"
                ],
            )
            return result
        v2.sampler.write_status(
            root / "progress.json",
            "design",
            rows=len(data),
            execution_version=disk_protocol.VERSION,
        )
        design = asof.FeatureDesign(
            data,
            args.spec,
            floor_prior_scale=args.floor_prior_scale,
            attribute_audits=units,
            evidence_manifest_sha256=evidence_sha,
        )
        design.save(target)
        (target / "graph-configuration.json").write_text(
            canonical(configuration) + "\n"
        )
        checkpoint = target / "posterior-checkpoint.json"
        if checkpoint.exists():
            if json.loads(checkpoint.read_text()) != {
                "protocol_sha256": ph,
                "posterior_sha256": digest(target / "posterior.nc"),
            }:
                raise ValueError("Invalid posterior checkpoint")
            inference = xr.open_datatree(
                target / "posterior.nc", engine="h5netcdf", cache=False
            )
        else:
            model = graph.build_model(data, design, **graph_kwargs(args))
            if model.graph_configuration != configuration:
                raise ValueError("Built graph differs from protocol")
            unique_rows = len(np.unique(design.matrix(data), axis=0))
            (target / "compression.json").write_text(
                canonical(
                    {
                        "version": graph.VERSION,
                        "observations": len(data),
                        "features": len(design.features),
                        "unique_feature_rows": unique_rows,
                        "interpretation": "Exact sharing of repeated feature rows; no rounding or aggregation of targets.",
                    }
                )
                + "\n"
            )
            names = [
                "alpha",
                "beta",
                "sigma",
                "sigma_building",
                "sigma_unit",
                "annual_drift",
                "bedroom_time",
                "building_time_scale",
                "unit_slope_scale",
                "nu",
                "building_bedroom_slope_scale",
                "building_feature_slope_scale",
                "citywide_walk_scale",
            ]
            # QR samples an improper flat theta; draw prior values from the
            # identity-basis model, whose prior is identical by construction.
            prior_model = (
                graph.build_model(
                    data, design, **{**graph_kwargs(args), "feature_basis": "identity"}
                )
                if args.feature_basis == "qr"
                else model
            )
            with prior_model:
                prior = v2.pm.sample_prior_predictive(
                    draws=80, random_seed=args.seed + 1, var_names=names
                )
            prior.to_netcdf(target / "prior.nc", engine="h5netcdf")
            inference = storage.sample_to_netcdf(
                model,
                output=target / "posterior.nc",
                trace_root=root / "trace",
                protocol_hash=ph,
                draws=args.draws,
                tune=args.tune,
                chains=args.chains,
                seed=args.seed,
                adaptation=args.adaptation,
                target_accept=args.target_accept,
                status_path=root / "progress.json",
                **execution.sample_options(protocol),
            )
            validate_posterior(inference, args, design, configuration)
            (target / "trace-manifest.json").write_bytes(
                (root / "trace/complete.json").read_bytes()
            )
            storage.atomic_json(
                checkpoint,
                {
                    "protocol_sha256": ph,
                    "posterior_sha256": digest(target / "posterior.nc"),
                },
            )
        try:
            validate_posterior(inference, args, design, configuration)
            v2.sampler.write_status(root / "progress.json", "diagnostics_and_reports")
            posterior_hash = digest(target / "posterior.nc")
            building_samples = building_cache(
                v2.base.posterior_dataset(inference),
                root / "building-cache",
                posterior_hash,
            )
            unit_slopes = unit_cache(
                v2.base.posterior_dataset(inference),
                root / "unit-slope-cache",
                posterior_hash,
            )
            with report_cache.bounded_unit_samples(
                v2.base, inference, root / "report-cache", posterior_hash
            ) as cached:
                result = write_reports(
                    target,
                    inference,
                    design,
                    data,
                    ph,
                    protocol,
                    building_samples,
                    unit_slopes,
                )
            (target / cache_code.name).write_bytes(cache_code.read_bytes())
            (target / "reporting-cache.json").write_text(
                canonical(
                    {
                        **reporting,
                        "posterior_sha256": posterior_hash,
                        "reporting_manifest_sha256": digest(
                            root / "reporting-protocol/complete.json"
                        ),
                        "cache_manifest_sha256": digest(
                            root / "report-cache/complete.json"
                        ),
                        "maximum_source_block_bytes": cached[
                            "maximum_source_block_bytes"
                        ],
                        "chains": args.chains,
                        "draws": args.draws,
                        "units": len(design.time.unit_ids),
                        "sample_order": "chain_major_then_draw",
                        "all_retained_draws": True,
                    }
                )
                + "\n"
            )
            floors = floor_contrasts(inference, design)
            (target / "floor-contrasts.json").write_text(canonical(floors) + "\n")
            result["floor_diagnostics"] = floors["diagnostics"]
            if not floors["diagnostics"]["acceptable"]:
                result["status"] = "diagnostic_only_do_not_interpret_intervals"
            (target / "summary.json").write_text(canonical(result) + "\n")
            (target / "residual-scales.json").write_text(
                canonical(residual_scale_summary(inference, data, configuration)) + "\n"
            )
        finally:
            inference.close()
        if any(digest(p) != code[p.name] for p in paths):
            raise ValueError("Implementation changed during combined experiment")
        if not REQUIRED_FIT | {
            "storage.json",
            "trace-manifest.json",
            "reporting-cache.json",
            cache_code.name,
        } <= {p.name for p in target.iterdir()}:
            raise ValueError("Required disk inference products missing")
        execution.verify_products(
            protocol,
            json.loads((target / "storage.json").read_text()),
            json.loads((target / "trace-manifest.json").read_text()),
            digest(target / "posterior.nc"),
        )
        v2.sampler.publish_fit(target, version=VERSION, protocol_hash=ph)
        v2.sampler.write_status(
            root / "progress.json", "complete", status=result["status"]
        )
        v2.base.emit("complete", status=result["status"], output=str(target))
        return result


def argument_parser():
    parser = previous.argument_parser()
    parser.description = __doc__
    parser.add_argument("--feature-basis", choices=("identity", "qr"), default="qr")
    parser.set_defaults(tune=1000, draws=4000, chains=8)
    return parser


if __name__ == "__main__":
    args = argument_parser().parse_args()
    with threadpool_limits(limits=1, user_api="blas"):
        run(args)
