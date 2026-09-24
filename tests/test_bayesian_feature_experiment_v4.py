import json
from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr

from models import bayesian_feature_experiment_v4 as m
from tests.test_bayesian_feature_experiment_v3 import setup


def configure(setup, monkeypatch, acceptable=True):
    args, design, events = setup
    args.floor_increment_prior_scale = 0.15
    calls = []

    def construct(data, spec, **kwargs):
        calls.append(kwargs)
        return design

    monkeypatch.setattr(m.floor, "FeatureDesign", construct)
    monkeypatch.setattr(
        m,
        "floor_contrasts",
        lambda *a: {
            "version": m.FLOOR_CONTRAST_VERSION,
            "diagnostics": {"acceptable": acceptable},
            "contrasts": [],
        },
    )
    return args, design, events, calls


def test_floor_runner_archives_design_and_reuses_completed_fit(setup, monkeypatch):
    args, _, events, calls = configure(setup, monkeypatch)
    result = m.run(args)
    protocol = json.loads((args.output / "protocol/protocol.json").read_text())
    assert protocol["version"] == m.VERSION
    assert protocol["feature_design_version"] == m.floor.VERSION
    assert protocol["floor_increment_prior_scale"] == 0.15
    assert {
        "bayesian_floor_increment_design.py",
        "bayesian_feature_experiment_v4.py",
    } <= protocol["implementation_sha256"].keys()
    assert calls == [{"floor_increment_prior_scale": 0.15}]
    assert result["floor_diagnostics"] == {"acceptable": True}
    assert m.run(args) == result
    assert len(calls) == events["sample"] == 1
    assert (
        "floor-contrasts.json"
        in json.loads((args.output / "fit/complete.json").read_text())["files"]
    )


def test_floor_diagnostic_failure_cannot_be_promoted(setup, monkeypatch):
    args, _, _, _ = configure(setup, monkeypatch, acceptable=False)
    original = m.v2.write_reports

    def reports(*a):
        result = original(*a)
        result["status"] = "exploratory_converged"
        return result

    monkeypatch.setattr(m.v2, "write_reports", reports)
    assert m.run(args)["status"] == "diagnostic_only_do_not_interpret_intervals"


@pytest.mark.parametrize("value", [0, -1, True, float("nan"), float("inf"), "0.15"])
def test_invalid_increment_scale_rejected_before_sampling(setup, value):
    args, _, events = setup
    args.floor_increment_prior_scale = value
    with pytest.raises(ValueError, match="Floor increment"):
        m.run(args)
    assert events["sample"] == 0


def test_joint_floor_contrasts_preserve_covariance(monkeypatch):
    shape = (4, 1000)
    rng = np.random.default_rng(144)
    common = rng.normal(0, 0.2, shape)
    beta = np.stack([common + 0.05, -common + 0.03], axis=-1)
    posterior = xr.Dataset(
        {"beta": (("chain", "draw", "feature"), beta)},
        coords={"feature": ["listed_floor_gt_1", "listed_floor_gt_3"]},
    )
    design = SimpleNamespace(
        features=list(posterior.feature.values),
        floor_levels=[1.0, 3.0, 8.0],
        floor_thresholds=[1.0, 3.0],
        floor_support={
            "levels": [
                {"level": level, "rows": 1, "units": 1, "buildings": 1}
                for level in (1.0, 3.0, 8.0)
            ],
            "adjacent_supported_contrasts": [
                {
                    "lower_supported_level": low,
                    "upper_supported_level": high,
                    "shared_buildings": 0,
                }
                for low, high in ((1.0, 3.0), (3.0, 8.0))
            ],
        },
    )
    captured = {}

    def diagnostics(inference):
        captured.update(inference)
        return {"acceptable": True}, None

    monkeypatch.setattr(m.v2.base, "diagnostics", diagnostics)
    result = m.floor_contrasts({"posterior": posterior, "sample_stats": {}}, design)
    assert result["draws"] == 4000
    assert result["contrasts"][-1]["kind"] == "observed_range"
    interval = result["contrasts"][-1]["log_effect"]
    assert interval["lower_95"] == pytest.approx(0.08)
    assert interval["upper_95"] == pytest.approx(0.08)
    assert "floor_contrast" in captured["posterior"].data_vars
    np.testing.assert_allclose(
        captured["posterior"].floor_contrast.isel(contrast=2), 0.08
    )
    assert result["contrasts"][0]["adjacent_overlap"]["shared_buildings"] == 0


def test_floor_contrasts_pass_through_real_diagnostics_without_coordinate_collision():
    rng = np.random.default_rng(771)
    names = ["listed_floor_gt_1", "listed_floor_gt_3"]
    posterior = xr.Dataset(
        {"beta": (("chain", "draw", "feature"), rng.normal(0, 0.1, (4, 1000, 2)))},
        coords={"feature": names},
    )
    stats = xr.Dataset(
        {
            "diverging": (("chain", "draw"), np.zeros((4, 1000), dtype=bool)),
            "maxdepth_reached": (("chain", "draw"), np.zeros((4, 1000), dtype=bool)),
            "energy": (("chain", "draw"), rng.normal(size=(4, 1000))),
        }
    )
    inference = xr.DataTree.from_dict({"posterior": posterior, "sample_stats": stats})
    design = SimpleNamespace(
        features=names,
        floor_levels=[1.0, 3.0, 8.0],
        floor_thresholds=[1.0, 3.0],
        floor_support={
            "levels": [
                {"level": x, "rows": 1, "units": 1, "buildings": 1}
                for x in (1.0, 3.0, 8.0)
            ],
            "adjacent_supported_contrasts": [],
        },
    )
    result = m.floor_contrasts(inference, design)
    assert result["diagnostics"]["acceptable"]
    assert result["diagnostics"]["parameters"] == 3
    assert len(result["contrasts"]) == 3


def test_protocol_changes_when_floor_prior_changes(setup):
    args, _, _ = setup
    args.floor_increment_prior_scale = 0.15
    data, source = m.load_data(args.dataset)
    code = {p.name: m.digest(p) for p in m.implementation_paths()}
    graph = m.graph.graph_configuration(data)
    first = m.make_protocol(args, data, source, code, graph)
    args.floor_increment_prior_scale = 0.05
    second = m.make_protocol(args, data, source, code, graph)
    assert first != second
    assert first["source_observations_sha256"] == second["source_observations_sha256"]


def test_default_retained_draws_and_new_protocol():
    args = m.argument_parser().parse_args(["--dataset", "d", "--output", "o"])
    assert (args.chains, args.draws, args.tune, args.floor_increment_prior_scale) == (
        4,
        4000,
        2000,
        0.15,
    )


@pytest.mark.parametrize(
    "mutation",
    ["none", "missing_compression_dependency", "changed_dependency", "changed_prior"],
)
def test_floor_graph_proof_binds_all_dependencies(setup, monkeypatch, mutation):
    args, _, _ = setup
    args.floor_increment_prior_scale = 0.15
    data, source = m.load_data(args.dataset)
    code = {p.name: m.digest(p) for p in m.implementation_paths()}
    configuration = m.graph.graph_configuration(data)
    protocol = m.make_protocol(args, data, source, code, configuration)
    proof = {
        key: protocol[key]
        for key in (
            "source_manifest_sha256",
            "source_observations_sha256",
            "floor_increment_prior_scale",
            "floor_levels",
        )
    }
    dependencies = {p.name: code[p.name] for p in m.previous.implementation_paths()}
    dependencies["bayesian_floor_increment_design.py"] = code[
        "bayesian_floor_increment_design.py"
    ]
    proof.update(
        version="bayesian-floor-graph-parity-v1",
        passed=True,
        specification=args.spec,
        rows=len(data),
        implementation_sha256=dependencies,
        graph_configuration=dict(configuration),
    )
    if mutation == "missing_compression_dependency":
        dependencies.pop("bayesian_feature_graph.py")
    elif mutation == "changed_dependency":
        dependencies["bayesian_feature_graph.py"] = "0" * 64
    elif mutation == "changed_prior":
        proof["graph_configuration"]["building_prior_scale"] = 0.7
    from apartments.research_pipeline import publish_bundle

    args.graph_validation = args.output.parent / "proof"
    publish_bundle(
        args.graph_validation,
        {"parity.json": json.dumps(proof)},
        {"version": proof["version"]},
    )
    if mutation == "none":
        assert m.make_protocol(args, data, source, code, configuration)[
            "graph_verification"
        ]["rows"] == len(data)
    else:
        with pytest.raises(ValueError, match="Floor graph proof"):
            m.make_protocol(args, data, source, code, configuration)
