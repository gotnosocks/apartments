"""Building drift, unit attributes and per-unit linear drift.

Same stages as `bayesian_attribute_experiment` (attribute feature design,
bedroom-group time curve, per-building half-year random walk, bounded
reports). The graph is `bayesian_structure_graph_v2` with a per-unit linear
drift, scale ~ HalfNormal(0.01), centered on each unit's own training years.
Readers use `bayesian_location_terms_v2`. Unit-drift draws are read one unit
at a time from a unit-major memory map. Research fit: publishing it never
changes the main selection.
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
from . import bayesian_structure_graph_v2 as graph
from . import bayesian_location_terms_v2 as location_terms

structure = previous.previous
VERSION = location_terms.DRIFT_EXPERIMENT
UNIT_DRIFT_VERSION = "unit-drift-summary-v1"
attribute = previous.attribute
floor, storage, disk_protocol, execution, report_cache = (
    previous.floor,
    previous.storage,
    previous.disk_protocol,
    previous.execution,
    previous.report_cache,
)
v2 = previous.v2
load_data, attributes = previous.load_data, previous.attributes
residual_scale_summary, floor_contrasts = (
    previous.residual_scale_summary,
    previous.floor_contrasts,
)
building_cache = structure.building_cache
REQUIRED_FIT = previous.REQUIRED_FIT | {"unit-drift.json"}
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
    }


def implementation_paths(base=None):
    return [
        *previous.implementation_paths(),
        Path(graph.__file__),
        Path(location_terms.__file__),
        Path(__file__),
    ]


def make_protocol(args, data, source, code, configuration, units, evidence_sha):
    result = previous.make_protocol(
        args, data, source, code, configuration, units, evidence_sha
    )
    result.update(
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


def fitted_summary(inference, design, data, protocol, building_samples, unit_slopes):
    """Residual rows in source order; mu adds bedroom curve, building walk and unit drift."""
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
    knot_years = protocol["building_knot_years"]
    basis, _ = location_terms.v1.building_knots(d.periods, knot_years)
    centers = location_terms.v1.building_centers(
        a["building"], a["period"], len(d.buildings), basis
    )
    unit_years = location_terms.unit_year_centers(design, data)
    years = (np.arange(len(d.periods)) - d.anchor) / 12.0
    width = basis.shape[1]
    rows = [None] * len(data)
    order = np.argsort(a["building"], kind="stable")
    for building in np.unique(a["building"]):
        members = order[a["building"][order] == building]
        z = np.asarray(building_samples[:, building * width : (building + 1) * width])
        for start in range(0, len(members), 128):
            sl = members[start : start + 128]
            walk = location_terms.v1.building_walk(
                z,
                samples["building_time_scale"],
                knot_years,
                basis[a["period"][sl]],
                centers[building],
            )
            units = a["unit"][sl]
            drift = (
                samples["unit_slope_scale"][:, None]
                * np.asarray(unit_slopes[:, units])
                * (years[a["period"][sl]] - unit_years[units])[None]
            )
            mu = (
                samples["alpha"][:, None]
                + samples["beta"] @ x[sl].T
                + samples["trend_coefficients"]
                @ (d.time_matrix - d.time_center)[a["period"][sl]].T
                + samples["annual_drift"][:, None]
                * (d.linear_time - d.linear_center)[a["period"][sl]]
                + samples["season_coefficients"]
                @ (d.season_matrix - d.season_weights @ d.season_matrix)[
                    a["season"][sl]
                ].T
                + samples["building_effect"][:, a["building"][sl]]
                + samples["sigma_unit"][:, None] * samples["unit_z"][:, units]
                + curve[:, group[sl], a["period"][sl]]
                + walk
                + drift
            )
            quantiles = np.exp(np.quantile(mu, [0.025, 0.5, 0.975], axis=0))
            for j, i in enumerate(sl):
                row = data.iloc[i]
                estimate = float(quantiles[1, j])
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
                }
    if any(r is None for r in rows):
        raise ValueError("Every source row needs a fitted residual")
    return rows, samples


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
    walk = structure.building_time_summary(
        inference, design, data, protocol, building_samples
    )
    (target / "building-time.json").write_text(canonical(walk) + "\n")
    drift = unit_drift_summary(inference)
    (target / "unit-drift.json").write_text(canonical(drift) + "\n")
    acceptable = (
        acceptable
        and curves["diagnostics"]["acceptable"]
        and walk["diagnostics"]["acceptable"]
        and drift["diagnostics"]["acceptable"]
    )
    summary = {
        "protocol_sha256": protocol_hash,
        "design_support": design.support,
        "diagnostics": diag,
        "derived_diagnostics": derived,
        "bedroom_time_diagnostics": curves["diagnostics"],
        "building_time_diagnostics": walk["diagnostics"],
        "unit_drift_diagnostics": drift["diagnostics"],
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
        design = attribute.FeatureDesign(
            data,
            args.spec,
            floor_prior_scale=args.floor_prior_scale,
            attribute_units=units,
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
            ]
            with model:
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
            raise ValueError("Implementation changed during drift experiment")
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
    return parser


if __name__ == "__main__":
    args = argument_parser().parse_args()
    with threadpool_limits(limits=1, user_api="blas"):
        run(args)
