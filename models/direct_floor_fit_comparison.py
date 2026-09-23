"""Compare full PyMC fits before and after reviewed explicit floor additions."""

import argparse
from pathlib import Path

from threadpoolctl import threadpool_limits

from apartments import direct_floor_projection as projection
from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest
from apartments.reviewed_cohort_quarantine import sha
from . import expanded_floor_fit_comparison as expanded
from . import direct_floor_fit_checks as checks

shared, smooth, spline = expanded.shared, expanded.smooth, expanded.spline
check_protocols = checks.check_protocols
check_implementation_sources = checks.check_implementation_sources
check_designs = expanded.check_designs
prior_comparison = expanded.prior_comparison
VERSION = "matched-direct-floor-spline-fit-comparison-v1"


def verify_revision(reference, candidate):
    bundles = [
        _verified_bundle(path, retain={"observations.jsonl", projection.SIDECAR})
        for path in (reference, candidate)
    ]
    before, after = [
        shared.report.jsonl(files["observations.jsonl"]) for _, files in bundles
    ]
    changes = shared.report.jsonl(bundles[1][1][projection.SIDECAR])
    if sha(projection.parent_rows(bundles[1][0], after, changes)) != sha(
        (bundles[0][0], before)
    ):
        raise ValueError(
            "Direct floor revision does not restore exact reference source"
        )
    if [r["audit_id"] for r in before] != [r["audit_id"] for r in after]:
        raise ValueError("Direct floor revision changed membership or order")
    allowed = {*projection.FIELDS, projection.FIELD}
    if any(
        sha({k: v for k, v in a.items() if k not in allowed})
        != sha({k: v for k, v in b.items() if k not in allowed})
        for a, b in zip(before, after, strict=True)
    ):
        raise ValueError("Direct floor revision changed nonfloor data")
    return before, after


def residual_slices(before, after, movements):
    import numpy as np
    import pandas as pd

    if [r["audit_id"] for r in before] != [r["audit_id"] for r in after]:
        raise ValueError("Residual source membership or order differs")
    old, new = [
        smooth.increment.listed_floor_values(pd.DataFrame(rows))
        for rows in (before, after)
    ]
    masks = {
        "all": np.ones(len(after), dtype=bool),
        "current_capture": np.array(
            [r["analysis_price_basis"] == "current_capture_gross_ask" for r in after]
        ),
        "new_explicit_floor": ~np.isfinite(old) & np.isfinite(new),
        "previously_known_floor": np.isfinite(old),
        "remaining_unknown_floor": ~np.isfinite(new),
    }
    indexed = {r["audit_id"]: r for r in movements}
    if len(indexed) != len(movements) or set(indexed) != {r["audit_id"] for r in after}:
        raise ValueError("Residual movement membership differs")
    return {
        name: {
            **shared.laundry.summarize_slice(
                [
                    indexed[r["audit_id"]]
                    for r, keep in zip(after, mask, strict=True)
                    if keep
                ]
            ),
            "buildings": len(
                {r["building"] for r, keep in zip(after, mask, strict=True) if keep}
            ),
        }
        for name, mask in masks.items()
    }


def build_comparison(reference, candidate, reference_dataset, dataset):
    before, after = verify_revision(reference_dataset, dataset)
    a, b = shared.load_fits(
        reference, candidate, reference_dataset, dataset, before, after
    )
    changed = check_protocols(a["protocol"], b["protocol"])
    implementation_check = check_implementation_sources(a, b, changed)
    names = check_designs(a, b)
    movements, residuals = shared.compare_residuals(
        a["residuals"], b["residuals"], before, after
    )
    groups, removed = shared.compare_groups(a["groups"], b["groups"], before, after)
    if removed or residuals["excluded_reference_rows"]:
        raise ValueError("Matched population lost observations or groups")
    buildings = sorted({r["building"] for r in after})
    common = [shared.building_contrasts(f, buildings) for f in (a, b)]
    building_changes = [
        {
            "id": x["id"],
            "log_effect": shared.common.interval_change(
                x["log_effect"], y["log_effect"]
            ),
        }
        for x, y in zip(common[0]["contrasts"], common[1]["contrasts"], strict=True)
    ]
    building_changes.sort(
        key=lambda r: (-abs(r["log_effect"]["median_change"]), r["id"])
    )
    curves = [
        smooth.curve_from_draws(
            f["design"],
            smooth.elevator.beta_draws(f),
            f["protocol"]["prior_multiplier"],
        )
        for f in (a, b)
    ]
    distinct, seen = [], set()
    for row in movements:
        if row["unit_id"] not in seen:
            distinct.append(row)
            seen.add(row["unit_id"])
        if len(distinct) == 25:
            break
    result = {
        "version": VERSION,
        "main_selection_changed": False,
        "rows": len(after),
        "changed_loader_implementations": changed,
        "implementation_scope_verification": implementation_check,
        "unchanged_nonfloor_features": names,
        "curves": curves,
        "floor_prior_comparison": prior_comparison(
            a["design"], b["design"], a["protocol"]["prior_multiplier"]
        ),
        "fits": [
            {
                "protocol": f["protocol"],
                "diagnostics": f["report"]["diagnostics"],
                "design_reconstruction": f["reconstruction"],
                "floor_parameter_diagnostics": smooth.floor_parameter_diagnostics(f),
                "retained_sampler_work": smooth.sampler_work(f),
                "bindings": {
                    k: digest(path / "complete.json")
                    for k, path in [
                        ("fit", f["root"] / "fit"),
                        ("protocol", f["root"] / "protocol"),
                        ("source", f["dataset"]),
                    ]
                },
            }
            for f in (a, b)
        ],
        "floor_support": [f["design"].floor_support for f in (a, b)],
        "residuals": residuals,
        "residual_slices": residual_slices(before, after, movements),
        "largest_distinct_unit_movements": distinct,
        "largest_unit_offset_movements": [r for r in groups if r["kind"] == "unit"][
            :25
        ],
        "largest_common_reference_building_movements": building_changes[:25],
        "building_reference": {
            "definition": "Unweighted mean of the identical building population subtracted within each joint posterior draw.",
            "buildings": buildings,
            "diagnostics": [value["diagnostics"] for value in common],
        },
        "limitations": [
            shared.common.LIMITATION,
            "Only the reviewed additions of explicit own-ad advertised floors change; all observations, nonfloor data, spline support, knots, priors and sampling settings are matched.",
            "Floor coverage and missingness centering change. Advertised floor claims do not establish physical height. The joint function prior comparison verifies whether matching support and knots preserve the induced floor-curve prior.",
            "Residuals are in sample and include unit effects. Current is a dated capture cohort, not a representative test panel.",
            "Joint curve intervals are pointwise conditional associations. Between-fit shifts are descriptive; independent fits are never paired.",
            "Residual and group movements identify units for source review; improvement alone cannot establish identification or justify feature adoption.",
        ],
    }
    for fit in (a, b):
        if (
            digest(fit["root"] / "fit/posterior.nc")
            != fit["provenance"]["fit_manifest"]["files"]["posterior.nc"]
        ):
            raise ValueError("Posterior changed during comparison")
    return result, movements, groups, building_changes


def run(output, **kwargs):
    modules = (
        projection,
        checks,
        expanded,
        shared,
        shared.report,
        shared.source,
        shared.common,
        shared.laundry,
        shared.floors,
        smooth,
        smooth.increment,
        smooth.contrasts,
        smooth.elevator,
        spline,
        checks.experiment,
        checks.execution,
        smooth.publisher,
    )
    paths = [Path(__file__), *[Path(module.__file__) for module in modules]]
    hashes = {path.name: digest(path) for path in paths}
    result, movements, groups, buildings = build_comparison(**kwargs)
    files = {
        "comparison.json": (canonical(result) + "\n").encode(),
        "movements.jsonl": "".join(canonical(r) + "\n" for r in movements).encode(),
        "residual-movements.jsonl": "".join(
            canonical(r) + "\n" for r in movements
        ).encode(),
        "raw-group-movements.jsonl": "".join(
            canonical(r) + "\n" for r in groups
        ).encode(),
        "common-reference-building-movements.jsonl": "".join(
            canonical(r) + "\n" for r in buildings
        ).encode(),
        **{path.name: path.read_bytes() for path in paths},
    }
    if any(digest(path) != hashes[path.name] for path in paths):
        raise ValueError("Comparison implementation changed")
    smooth.publisher._publish(
        output,
        files,
        {
            "version": VERSION,
            "fits": [fit["bindings"] for fit in result["fits"]],
            "implementation_sha256": hashes,
        },
    )
    print(
        canonical(
            {
                "rows": result["rows"],
                "output": str(output),
                "main_selection_changed": False,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("reference", "reference-dataset", "candidate", "dataset", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    with threadpool_limits(limits=1, user_api="blas"):
        run(**vars(parser.parse_args()))
