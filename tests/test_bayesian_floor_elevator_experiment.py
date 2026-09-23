from copy import deepcopy
import json

import numpy as np
import pytest
import xarray as xr

from apartments.research_pipeline import publish_bundle
from models import bayesian_floor_elevator_experiment as m
from tests.test_bayesian_feature_experiment_v3 import setup
from tests.test_bayesian_floor_elevator_design import data


def configure(setup):
    args, _, _ = setup
    args.floor_increment_prior_scale = 0.15
    args.interaction_mode = "pooled"
    args.interaction_prior_scale = 0.15
    frame, source = m.previous.load_data(args.dataset)
    code = {p.name: m.digest(p) for p in m.implementation_paths()}
    config = m.previous.graph.graph_configuration(frame)
    return args, frame, source, code, config


def test_protocol_binds_new_representation_and_sampler_defaults(setup):
    args, frame, source, code, config = configure(setup)
    a = m.make_protocol(args, frame, source, code, config)
    args.interaction_mode = "separate"
    b = m.make_protocol(args, frame, source, code, config)
    assert a["version"] == m.VERSION and a["interaction_thresholds"] == [2, 3, 4]
    assert m.disk_protocol.verify_protocol(a)
    assert a["source_observations_sha256"] == b["source_observations_sha256"]
    assert a["interaction_mode"] != b["interaction_mode"]
    defaults = m.argument_parser().parse_args(["--dataset", "d", "--output", "o"])
    assert (defaults.chains, defaults.tune, defaults.draws) == (4, 4000, 6000)


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "source",
        "mode",
        "scale",
        "thresholds",
        "code",
        "missing_code",
        "version",
        "failed",
    ],
)
def test_graph_proof_is_bound_to_full_interaction_contract(setup, fault):
    args, frame, source, code, config = configure(setup)
    protocol = m.make_protocol(args, frame, source, code, config)
    keys = (
        "source_manifest_sha256",
        "source_observations_sha256",
        "specification",
        "floor_increment_prior_scale",
        "floor_levels",
        "graph_configuration",
        "rows",
        "interaction_mode",
        "interaction_prior_scale",
        "interaction_thresholds",
    )
    proof = {k: deepcopy(protocol[k]) for k in keys}
    proof.update(
        version=m.PARITY_VERSION, passed=True, implementation_sha256=deepcopy(code)
    )
    if fault == "source":
        proof["source_observations_sha256"] = "wrong"
    elif fault == "mode":
        proof["interaction_mode"] = "separate"
    elif fault == "scale":
        proof["interaction_prior_scale"] = 0.3
    elif fault == "thresholds":
        proof["interaction_thresholds"].append(5)
    elif fault == "code":
        proof["implementation_sha256"]["bayesian_floor_elevator_design.py"] = "wrong"
    elif fault == "missing_code":
        del proof["implementation_sha256"]["bayesian_feature_graph.py"]
    elif fault == "version":
        proof["version"] = "old-proof"
    elif fault == "failed":
        proof["passed"] = False
    args.graph_validation = args.output.parent / "proof"
    publish_bundle(
        args.graph_validation,
        {"parity.json": json.dumps(proof)},
        {"version": proof["version"]},
    )
    if fault:
        with pytest.raises(ValueError, match="Interaction graph proof"):
            m.make_protocol(args, frame, source, code, config)
    else:
        assert m.make_protocol(args, frame, source, code, config)["graph_verification"][
            "rows"
        ] == len(frame)


@pytest.mark.parametrize("fault", [None, "coordinates", "unmixed"])
def test_joint_floor_access_contrasts_preserve_covariance_and_gate_intervals(fault):
    frame = data()
    design = m.feature.FeatureDesign(frame, mode="separate")
    rng = np.random.default_rng(148)
    beta = rng.normal(0, 0.02, size=(4, 1200, len(design.features)))
    i, j = [
        design.features.index(k) for k in ("listed_floor_gt_2", "floor_elevator_gt_2")
    ]
    beta[:, :, i] = rng.normal(0, 0.3, size=(4, 1200))
    beta[:, :, j] = -2 * beta[:, :, i] + rng.normal(0.1, 0.002, size=(4, 1200))
    if fault == "unmixed":
        beta[0, :, i] += 10
    coords = design.features[::-1] if fault == "coordinates" else design.features
    p = xr.Dataset(
        {"beta": (("chain", "draw", "feature"), beta)}, coords={"feature": coords}
    )
    if fault == "coordinates":
        with pytest.raises(ValueError, match="coordinates"):
            m.joint_contrasts({"posterior": p}, design, frame)
        return
    result, _ = m.joint_contrasts({"posterior": p}, design, frame, prior_multiplier=2)
    case = next(r for r in result["contrasts"] if r["id"] == "floor:2->3:elevator=1")
    assert result["all_joint_beta_draws"] and result["draws_per_chain"] == 1200
    if fault == "unmixed":
        assert not result["all_contrasts_acceptable"] and case["log_effect"] is None
    else:
        assert result["all_contrasts_acceptable"]
        expected = (beta[:, :, i] + 0.5 * beta[:, :, j]).ravel()
        np.testing.assert_allclose(
            [case["log_effect"][k] for k in ("lower_95", "median", "upper_95")],
            np.quantile(expected, [0.025, 0.5, 0.975]),
        )
        assert case["log_contrast_prior_sd"] == pytest.approx(2 * np.hypot(0.15, 0.075))


def test_absent_endpoint_is_explicit_even_when_global_floor_is_supported():
    frame = data()
    design = m.feature.FeatureDesign(frame)
    reduced = frame.loc[~(frame.advertised_floor.eq(8) & frame.elevator.eq(False))]
    case = next(
        r
        for r in m.construct_contrasts(design, reduced)
        if r["id"] == "floor:5->8:elevator=0"
    )
    assert case["support_after"]["rows"] == 0 and not case["supported_endpoints"]


def test_no_parity_proof_refuses_sampling_before_creating_output(tmp_path):
    args = m.argument_parser().parse_args(
        ["--dataset", str(tmp_path / "missing"), "--output", str(tmp_path / "output")]
    )
    with pytest.raises(ValueError, match="parity"):
        m.run(args)
    assert not args.output.exists()


def configure_runner(setup, monkeypatch, acceptable=True):
    from tests.test_bayesian_disk_experiment import configure as configure_disk
    import pandas as pd

    args, design, events = configure_disk(setup, monkeypatch)
    args.interaction_mode = "pooled"
    args.interaction_prior_scale = 0.15
    save_base = design.save

    def save(root):
        save_base(root)
        (root / "interaction-design.json").write_text("{}\n")

    design.save = save
    monkeypatch.setattr(m.feature, "FeatureDesign", lambda *a, **k: design)
    monkeypatch.setattr(
        m,
        "joint_contrasts",
        lambda *a, **k: (
            {"version": m.CONTRAST_VERSION, "all_contrasts_acceptable": acceptable},
            pd.DataFrame({"ess_bulk": [1000]}),
        ),
    )
    original = m.previous.v2.write_reports

    def report(*a):
        value = original(*a)
        value["status"] = "exploratory_converged"
        return value

    monkeypatch.setattr(m.previous.v2, "write_reports", report)
    frame, source = m.previous.load_data(args.dataset)
    code = {p.name: m.digest(p) for p in m.implementation_paths()}
    config = m.previous.graph.graph_configuration(frame)
    protocol = m.make_protocol(args, frame, source, code, config)
    fields = (
        "source_manifest_sha256",
        "source_observations_sha256",
        "specification",
        "floor_increment_prior_scale",
        "floor_levels",
        "graph_configuration",
        "rows",
        "interaction_mode",
        "interaction_prior_scale",
        "interaction_thresholds",
    )
    proof = {k: protocol[k] for k in fields}
    proof.update(version=m.PARITY_VERSION, passed=True, implementation_sha256=code)
    args.graph_validation = args.output.parent / "proof"
    publish_bundle(
        args.graph_validation,
        {"parity.json": json.dumps(proof)},
        {"version": m.PARITY_VERSION},
    )
    return args, events


@pytest.mark.parametrize("acceptable", [False, True])
def test_disk_lifecycle_gates_joint_contrasts_and_reuses_completed_fit(
    setup, monkeypatch, acceptable
):
    args, events = configure_runner(setup, monkeypatch, acceptable)
    result = m.run(args)
    assert result["floor_elevator_contrasts_acceptable"] is acceptable
    assert result["status"] == (
        "exploratory_converged"
        if acceptable
        else "diagnostic_only_do_not_interpret_intervals"
    )
    manifest = json.loads((args.output / "fit/complete.json").read_text())
    assert (
        manifest["version"] == m.VERSION and m.REQUIRED_FIT <= manifest["files"].keys()
    )
    assert m.run(args) == result and events["sample"] == events["reports"] == 1


def test_reporting_resume_keeps_existing_joint_draws(setup, monkeypatch):
    args, events = configure_runner(setup, monkeypatch)
    original = m.previous.v2.write_reports
    monkeypatch.setattr(
        m.previous.v2,
        "write_reports",
        lambda *a: (_ for _ in ()).throw(RuntimeError("report interrupted")),
    )
    with pytest.raises(RuntimeError, match="interrupted"):
        m.run(args)
    assert (args.output / "fit/posterior-checkpoint.json").is_file()
    monkeypatch.setattr(m.previous.v2, "write_reports", original)
    assert m.run(args)["status"] == "exploratory_converged"
    assert events["sample"] == 1
