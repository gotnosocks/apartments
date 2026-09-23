from copy import deepcopy
import json

import numpy as np
import pytest
import xarray as xr

from models import bayesian_floor_elevator_contract as reader
from models import bayesian_floor_elevator_experiment as experiment
from models.bayesian_feature_report import check_interval
from tests.test_bayesian_floor_elevator_design import data


def bundle(tmp_path, mode="pooled"):
    frame = data()
    design = experiment.feature.FeatureDesign(frame, mode=mode)
    design.save(tmp_path)
    base = json.loads((tmp_path / "feature-design.json").read_text())
    extra = json.loads((tmp_path / "interaction-design.json").read_text())
    protocol = {
        "version": experiment.VERSION,
        "feature_design_version": reader.DESIGN,
        "base_feature_design_version": reader.BASE,
        "interaction_mode": mode,
        "interaction_prior_scale": 0.15,
        "floor_increment_prior_scale": 0.15,
        "interaction_thresholds": reader.THRESHOLDS,
        "interaction_policy": experiment.POLICY,
        "floor_levels": design.floor_levels,
        "floor_thresholds": design.floor_levels[:-1],
        "prior_multiplier": 1.0,
        "chains": 4,
        "draws": 1000,
    }
    summary = {
        "design_support": design.support,
        "floor_elevator_contrasts_acceptable": True,
    }
    return protocol, base, extra, frame.to_dict("records"), summary, design, frame


@pytest.mark.parametrize("mode", ["pooled", "separate"])
def test_reader_metadata_matches_actual_extended_encoder_without_relabeling_base(
    tmp_path, mode
):
    p, b, e, rows, s, d, frame = bundle(tmp_path, mode)
    merged = reader.merge_design(p, b, e, rows, s)
    assert merged["features"] == d.features
    assert merged["prior_scales"] == d.prior_scales.tolist()
    assert merged["support"] == d.support
    assert b["features"] == d.base.features and b["features"] != d.features
    assert merged["means"] == d.base.means.tolist() + d.interaction_means.tolist()


@pytest.mark.parametrize(
    "fault",
    [
        "version",
        "base",
        "mode",
        "thresholds",
        "prior",
        "centering",
        "order",
        "support",
        "source",
    ],
)
def test_misbound_interaction_design_is_rejected(tmp_path, fault):
    p, b, e, rows, s, *_ = bundle(tmp_path)
    if fault == "version":
        p["version"] = "observable-bayesian-floor-experiment-v4"
    elif fault == "base":
        b["version"] = "old-design"
    elif fault == "mode":
        p["interaction_mode"] = "separate"
    elif fault == "thresholds":
        e["thresholds"].append(5)
    elif fault == "prior":
        e["prior_scales"][-1] *= 2
    elif fault == "centering":
        e["interaction_means"][0] += 0.01
    elif fault == "order":
        e["features"].reverse()
    elif fault == "support":
        e["endpoint_support"][0]["rows"] += 1
    elif fault == "source":
        rows[0]["elevator"] = False
    with pytest.raises(ValueError):
        reader.merge_design(p, b, e, rows, s)


@pytest.mark.parametrize("mode", ["pooled", "separate"])
def test_joint_report_contract_recomputes_actual_scenarios_and_support(tmp_path, mode):
    p, b, e, rows, s, d, frame = bundle(tmp_path, mode)
    merged = reader.merge_design(p, b, e, rows, s)
    rng = np.random.default_rng(93)
    posterior = xr.Dataset(
        {
            "beta": (
                ("chain", "draw", "feature"),
                rng.normal(0, 0.1, (4, 1000, len(d.features))),
            )
        },
        coords={"feature": d.features},
    )
    joint, _ = experiment.joint_contrasts({"posterior": posterior}, d, frame)
    assert reader.verify_contrasts(p, merged, joint, rows, s, check_interval) == joint
    for fault in (
        "count",
        "direction",
        "vector",
        "support",
        "prior",
        "chain",
        "gate",
        "interval",
    ):
        bad = deepcopy(joint)
        if fault == "count":
            bad["contrasts"].pop()
        elif fault == "direction":
            bad["contrasts"][0]["upper_floor"] = 5
        elif fault == "vector":
            bad["contrasts"][0]["design_vector"][-1] += 0.2
        elif fault == "support":
            bad["contrasts"][0]["support_after"]["units"] += 1
        elif fault == "prior":
            bad["contrasts"][0]["log_contrast_prior_sd"] *= 2
        elif fault == "chain":
            bad["chains"] = 2
        elif fault == "gate":
            bad["contrasts"][0]["diagnostics"]["ess_bulk"] = 20
        elif fault == "interval":
            bad["contrasts"][0]["log_effect"]["lower_95"] = float("nan")
        with pytest.raises(ValueError):
            reader.verify_contrasts(p, merged, bad, rows, s, check_interval)
