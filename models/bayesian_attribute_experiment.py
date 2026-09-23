"""Building-drift structure model plus unit attribute features.

Same stages as `bayesian_structure_experiment` (bedroom-group time curve,
per-building random walk, bounded building reports). The feature design is
`bayesian_attribute_design`: the spline design plus penthouse-label, duplex,
private-outdoor and shared-bath unit flags, computed once from the
hash-verified description archive bound to the dataset. The archive manifest
hash and the flagged unit lists are part of the protocol.
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

from apartments.bayesian_evidence import load_evidence
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle
from . import bayesian_structure_experiment as previous
from . import bayesian_attribute_design as attribute

VERSION = "observable-bayesian-attribute-structure-experiment-v1"
graph, location_terms = previous.graph, previous.location_terms
floor, storage, disk_protocol, execution, report_cache = (
    previous.floor,
    previous.storage,
    previous.disk_protocol,
    previous.execution,
    previous.report_cache,
)
v2 = previous.v2
load_data, graph_kwargs, validate_posterior = (
    previous.load_data,
    previous.graph_kwargs,
    previous.validate_posterior,
)
residual_scale_summary, floor_contrasts = (
    previous.residual_scale_summary,
    previous.floor_contrasts,
)
building_cache, write_reports = previous.building_cache, previous.write_reports
REQUIRED_FIT = previous.REQUIRED_FIT


def validate_args(args):
    previous.validate_args(args)
    if not (Path(args.evidence) / "complete.json").is_file():
        raise ValueError("A verified description archive is required")


def attributes(args, data):
    captures = load_evidence(args.dataset, args.evidence)
    return attribute.attribute_units(data, captures), digest(
        Path(args.evidence) / "complete.json"
    )


def implementation_paths(base=None):
    return [*previous.implementation_paths(), Path(attribute.__file__), Path(__file__)]


def make_protocol(args, data, source, code, configuration, units, evidence_sha):
    result = previous.make_protocol(args, data, source, code, configuration)
    result.update(
        version=VERSION,
        feature_design_version=attribute.VERSION,
        attribute_policy=attribute.policy(),
        evidence_manifest_sha256=evidence_sha,
        attribute_units_sha256=hashlib.sha256(canonical(units).encode()).hexdigest(),
        attribute_counts={k: len(v) for k, v in units.items()},
    )
    return result


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
        raise ValueError("Completed attribute fit protocol/version or products differ")
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
        raise ValueError("Completed attribute fit summaries or checkpoint differ")
    return summary


def run(args):
    """`bayesian_structure_experiment.run` with the unit-attribute feature design."""
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
            with report_cache.bounded_unit_samples(
                v2.base, inference, root / "report-cache", posterior_hash
            ) as cached:
                result = write_reports(
                    target, inference, design, data, ph, protocol, building_samples
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
            raise ValueError("Implementation changed during attribute experiment")
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
    parser.add_argument(
        "--evidence",
        type=Path,
        required=True,
        help="Verified description archive bound to the dataset",
    )
    return parser


if __name__ == "__main__":
    args = argument_parser().parse_args()
    with threadpool_limits(limits=1, user_api="blas"):
        run(args)
