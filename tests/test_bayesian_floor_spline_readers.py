"""Spline reports retain source, prior and convergence gates without step semantics."""

from copy import deepcopy
import json
import math
from types import SimpleNamespace

import pytest

from apartments.corrections import canonical
from apartments.research_pipeline import digest
from models import bayesian_floor_spline_contract as contract
from models import bayesian_feature_report as report
from .test_bayesian_feature_report import (
    diagnostics,
    interval,
    experiment,
    v3_fixture,
    rewrite_v3,
    publish_binary,
)


def floor_payload(rows):
    levels = sorted(
        {r["listed_floor"] for r in rows if r.get("listed_floor") is not None}
    )
    knots = sorted(
        {
            levels[0],
            levels[-1],
            *[k for k in (5.0, 10.0, 20.0, 35.0) if levels[0] < k < levels[-1]],
        }
    )
    common = {
        "floor_prior_scale": 0.1,
        "floor_levels": levels,
        "floor_knots": knots,
        "floor_reference": 2.0 if levels[0] <= 2 <= levels[-1] else levels[0],
        "floor_policy": {"basis": "regularized natural cubic spline"},
    }
    protocol = {
        "version": contract.EXPERIMENT,
        "feature_design_version": contract.DESIGN,
        "chains": 4,
        "draws": 1000,
        **common,
    }
    cells = {
        level: [r for r in rows if r.get("listed_floor") == level] for level in levels
    }
    counts = [{"level": level, **report.support(cells[level])} for level in levels]
    names = ["listed_floor_spline_" + str(i) for i in range(len(knots) - 1)]
    design = {
        "version": contract.DESIGN,
        **common,
        "features": names,
        "prior_scales": [0.1] * len(names),
        "floor_support": {
            "levels": counts,
            "known_rows": sum(len(v) for v in cells.values()),
            "unknown_rows": sum(r.get("listed_floor") is None for r in rows),
        },
    }
    pairs = list(zip(levels[:-1], levels[1:])) + (
        [(levels[0], levels[-1])] if len(levels) > 2 else []
    )
    contrasts = []
    for low, high in pairs:
        adjacent = levels.index(high) == levels.index(low) + 1
        value = interval(0.02)
        percent = {
            **value,
            **{
                k: 100 * math.expm1(value[k])
                for k in ("median", "lower_95", "upper_95")
            },
        }
        overlap = (
            {
                "lower_supported_level": low,
                "upper_supported_level": high,
                "shared_buildings": len(
                    {r["building"] for r in cells[low]}
                    & {r["building"] for r in cells[high]}
                ),
                "shared_units": len(
                    {r["unit_id"] for r in cells[low]}
                    & {r["unit_id"] for r in cells[high]}
                ),
            }
            if adjacent
            else None
        )
        contrasts.append(
            {
                "lower_floor": low,
                "upper_floor": high,
                "kind": "adjacent_observed_levels" if adjacent else "observed_range",
                "support_lower": counts[levels.index(low)],
                "support_upper": counts[levels.index(high)],
                "adjacent_overlap": overlap,
                "log_effect": value,
                "percent_effect": percent,
            }
        )
    floors = {
        "version": contract.CONTRAST,
        **common,
        "interpretation": contract.INTERPRETATION,
        "contrasts": contrasts,
        "diagnostics": diagnostics(),
        "draws": 4000,
    }
    return protocol, design, floors, {"floor_diagnostics": diagnostics()}


@pytest.fixture
def payload():
    rows = [
        {"listed_floor": f, "building": "b", "unit_id": "u" + str(i)}
        for i, f in enumerate([1.0, 2.0, 6.0, 20.0, 52.0, None])
    ]
    return (*floor_payload(rows), rows)


def test_source_supported_spline_report_has_no_threshold_parameterization(payload):
    protocol, design, floors, summary, rows = payload
    assert contract.verify_contrasts(protocol, design, floors, rows, summary) == floors
    assert len(design["features"]) == 5


@pytest.mark.parametrize(
    "mutation",
    [
        "prior",
        "knots",
        "reference",
        "thresholds",
        "features",
        "source",
        "counts",
        "overlap",
        "interval",
        "gate",
        "policy",
    ],
)
def test_rehashed_spline_semantic_or_diagnostic_changes_rejected(payload, mutation):
    protocol, design, floors, summary, rows = deepcopy(payload)
    if mutation == "prior":
        design["floor_prior_scale"] = 0.2
    if mutation == "knots":
        for value in (protocol, design, floors):
            value["floor_knots"] = [1.0, 5.0, 10.0, 20.0, 52.0]
    if mutation == "reference":
        for value in (protocol, design, floors):
            value["floor_reference"] = 1.0
    if mutation == "thresholds":
        protocol["floor_thresholds"] = protocol["floor_levels"][:-1]
    if mutation == "features":
        design["features"][0] = "listed_floor_gt_1"
    if mutation == "source":
        rows[0]["listed_floor"] = 3.0
    if mutation == "counts":
        design["floor_support"]["known_rows"] += 1
    if mutation == "overlap":
        floors["contrasts"][0]["adjacent_overlap"]["shared_buildings"] += 1
    if mutation == "interval":
        floors["contrasts"][0]["percent_effect"]["median"] += 1
    if mutation == "gate":
        floors["diagnostics"]["max_rhat"] = 1.03
        summary["floor_diagnostics"] = floors["diagnostics"]
    if mutation == "policy":
        floors["floor_policy"] = {"wrong": True}
    with pytest.raises(ValueError):
        contract.verify_contrasts(protocol, design, floors, rows, summary)


def test_spline_build_report_and_main_selection(experiment, tmp_path):
    root, dataset, protocol, files, _ = v3_fixture(
        experiment,
        mode="shared",
        source_version="reviewed-bathroom-counts-projection-v1",
    )
    rows = report.jsonl((dataset / "observations.jsonl").read_bytes())
    for row, value in zip(rows, [1.0, 2.0, 10.0, 52.0]):
        row["listed_floor"] = value
    sm = json.loads((dataset / "complete.json").read_text())
    source_files = {name: (dataset / name).read_bytes() for name in sm["files"]}
    source_files["observations.jsonl"] = "".join(canonical(r) + "\n" for r in rows)
    sm = publish_binary(
        dataset, source_files, {k: v for k, v in sm.items() if k != "files"}
    )
    p, design, floors, _ = floor_payload(rows)
    protocol.update(
        p,
        source_manifest_sha256=digest(dataset / "complete.json"),
        source_observations_sha256=sm["files"]["observations.jsonl"],
    )
    old = json.loads(files["feature-design.json"])
    design.update(
        spec=old["spec"],
        support={**old["support"], "features": len(design["features"])},
        numeric={},
    )
    summary = json.loads(files["summary.json"])
    summary.update(
        design_support=design["support"], floor_diagnostics=floors["diagnostics"]
    )
    files.update(
        {
            "feature-design.json": canonical(design) + "\n",
            "floor-contrasts.json": canonical(floors) + "\n",
            "summary.json": canonical(summary) + "\n",
            "coefficients.json": canonical(
                [{"feature": name, **interval()} for name in design["features"]]
            )
            + "\n",
        }
    )
    rewrite_v3(root, protocol, files)
    result, _ = report.build_report(root, dataset)
    assert result["method"]["floor_knots"] == [1.0, 5.0, 10.0, 20.0, 35.0, 52.0]
    assert "floor_increment_prior_scale" not in result["method"]
    assert result["floors"] == floors
    assert (
        "natural-spline basis"
        in result["coefficients"]["encoded_value_coefficients"][0]["encoded_unit"]
    )
    assert "Listed-floor component contrasts" in report.html_report(result)
    from apartments.main_analysis import select

    chosen = select(root, dataset, tmp_path / "selection.json")
    assert chosen["experiment"] == str(root.resolve())


def test_spline_analysis_controls_and_interpretation():
    from apartments.bayesian_analysis import BayesianAnalysis

    analysis = BayesianAnalysis()
    analysis.protocol = {"version": contract.EXPERIMENT}
    analysis.design = SimpleNamespace(
        numeric={}, categories={}, floor_levels=[1.0, 2.0, 52.0]
    )
    assert analysis._fields()["listed_floor"]["observed_levels"] == [1.0, 2.0, 52.0]
    warnings = analysis._warnings({})
    assert any("natural cubic spline" in text for text in warnings)
    assert not any("linear standardized" in text for text in warnings)


from .test_bayesian_feature_design_v2 import data


def test_actual_spline_loader_and_joint_contrast_match(data, tmp_path):
    import numpy as np
    from models.bayesian_floor_spline_design import FeatureDesign
    from models.bayesian_feature_design_v2 import load_design

    trained = FeatureDesign(data)
    trained.save(tmp_path)
    metadata = json.loads((tmp_path / "feature-design.json").read_text())
    protocol = {
        "version": contract.EXPERIMENT,
        "feature_design_version": contract.DESIGN,
        **{k: metadata[k] for k in contract.FIELDS - {"feature_design_version"}},
    }
    restored = load_design(tmp_path, data, protocol)
    np.testing.assert_array_equal(restored.matrix(data), trained.matrix(data))
    pair = data.iloc[[0, 0]].copy()
    pair["listed_floor"] = [2.0, 10.0]
    difference = np.diff(restored.matrix(pair), axis=0)[0]
    np.testing.assert_allclose(
        restored.contrast_vector(2.0, 10.0), difference, rtol=0, atol=1e-15
    )
    with pytest.raises(ValueError, match="explicit spline protocol"):
        load_design(tmp_path, data)
    bad = {**protocol, "floor_prior_scale": 0.2}
    with pytest.raises(ValueError, match="metadata"):
        load_design(tmp_path, data, bad)


def test_actual_spline_source_reconstruction_binds_basis_and_helper(data, tmp_path):
    import hashlib
    import importlib.metadata
    from apartments.research_pipeline import publish_bundle
    from models import bayesian_source_sensitivity as source
    from .test_bayesian_source_sensitivity import design_source, converted

    rows = design_source(data)
    frame = converted(rows)
    protocol = {
        "version": contract.EXPERIMENT,
        "feature_design_version": contract.DESIGN,
        "floor_prior_scale": 0.1,
        "specification": "full_half_balance",
        "rows": len(rows),
        "versions": {
            n: importlib.metadata.version(n) for n in ("numpy", "pandas", "scipy")
        },
    }
    design_module, paths = source.reconstruction_dependencies(protocol)
    assert "bayesian_floor_increment_design.py" in {p.name for p in paths}
    codes = {p.name: p.read_bytes() for p in paths}
    dataset = tmp_path / "source"
    sm = publish_bundle(
        dataset,
        {"observations.jsonl": "".join(canonical(r) + "\n" for r in rows)},
        {"version": "reviewed-bathroom-counts-projection-v1"},
    )
    protocol.update(
        source_version=sm["version"],
        source_manifest_sha256=digest(dataset / "complete.json"),
        source_observations_sha256=sm["files"]["observations.jsonl"],
        implementation_sha256={
            k: hashlib.sha256(v).hexdigest() for k, v in codes.items()
        },
    )
    ph = hashlib.sha256(canonical(protocol).encode()).hexdigest()
    root = tmp_path / "experiment"
    target = root / "fit"
    design_module.FeatureDesign(frame).save(target)
    pm = publish_binary(
        root / "protocol",
        {"protocol.json": canonical(protocol) + "\n", **codes},
        {"version": contract.EXPERIMENT, "protocol_sha256": ph},
    )
    files = {name: (target / name).read_bytes() for name in source.comparison.DESIGNS}
    fm = publish_binary(
        target, files, {"version": contract.EXPERIMENT, "protocol_sha256": ph}
    )
    provenance = {"protocol_manifest": pm, "fit_manifest": fm}
    assert source.verify_design(root, dataset, protocol, provenance)["verified"]
    metadata = json.loads(files["feature-design.json"])
    metadata["floor_basis"][0][0] += 0.01
    files["feature-design.json"] = canonical(metadata) + "\n"
    provenance["fit_manifest"] = publish_binary(
        target, files, {"version": contract.EXPERIMENT, "protocol_sha256": ph}
    )
    with pytest.raises(ValueError, match="exact source reconstruction"):
        source.verify_design(root, dataset, protocol, provenance)


def test_producer_joint_floor_summaries_pass_reader_contract(data, tmp_path):
    import numpy as np
    import xarray as xr
    from models.bayesian_floor_spline_design import FeatureDesign
    from models.bayesian_floor_spline_experiment import floor_contrasts

    trained = FeatureDesign(data)
    trained.save(tmp_path)
    metadata = json.loads((tmp_path / "feature-design.json").read_text())
    rng = np.random.default_rng(80371)
    beta = rng.normal(0, 0.03, (4, 1000, len(trained.features)))
    posterior = xr.Dataset(
        {"beta": (("chain", "draw", "feature"), beta)},
        coords={"chain": range(4), "draw": range(1000), "feature": trained.features},
    )
    stats = xr.Dataset(
        {
            "energy": (("chain", "draw"), rng.normal(size=(4, 1000))),
            "diverging": (("chain", "draw"), np.zeros((4, 1000), dtype=bool)),
            "maxdepth_reached": (("chain", "draw"), np.zeros((4, 1000), dtype=bool)),
        }
    )
    inference = xr.DataTree.from_dict({"posterior": posterior, "sample_stats": stats})
    floors = floor_contrasts(inference, trained)
    protocol = {
        "version": contract.EXPERIMENT,
        "feature_design_version": contract.DESIGN,
        "chains": 4,
        "draws": 1000,
        **{k: metadata[k] for k in contract.FIELDS - {"feature_design_version"}},
    }
    summary = {"floor_diagnostics": floors["diagnostics"]}
    assert (
        contract.verify_contrasts(
            protocol, metadata, floors, data.to_dict("records"), summary
        )
        == floors
    )
    first = floors["contrasts"][0]
    expected = beta.reshape((-1, beta.shape[-1])) @ trained.contrast_vector(
        first["lower_floor"], first["upper_floor"]
    )
    np.testing.assert_allclose(
        first["log_effect"]["median"], np.median(expected), rtol=0, atol=1e-16
    )
