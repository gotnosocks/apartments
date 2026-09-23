"""Noise-only comparisons bind saved fits and never pair posterior samples."""

import copy
import hashlib
import json
import math
import shutil
import statistics

import pytest

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest
from models import bayesian_noise_sensitivity as m
from .test_bayesian_feature_report import experiment, publish_binary, v3_fixture


def saved(root):
    protocol = json.loads((root / "protocol" / "protocol.json").read_text())
    manifest = json.loads((root / "fit" / "complete.json").read_text())
    files = {name: (root / "fit" / name).read_bytes() for name in manifest["files"]}
    code = {
        name: (root / "protocol" / name).read_bytes()
        for name in protocol["implementation_sha256"]
    }
    return protocol, files, code


@pytest.mark.parametrize("parameterization", ["centered", "noncentered"])
def test_noise_comparison_allows_computational_parameterization(pair, parameterization):
    reference, candidate, _ = pair
    a, _, _ = saved(reference)
    b, _, _ = saved(candidate)
    b["residual_parameterization"] = parameterization
    m.check_protocols(a, b)


def test_noise_comparison_rejects_unknown_parameterization(pair):
    reference, candidate, _ = pair
    a, _, _ = saved(reference)
    b, _, _ = saved(candidate)
    b["residual_parameterization"] = "unknown"
    with pytest.raises(ValueError, match="parameterization"):
        m.check_protocols(a, b)


def seal(root, protocol, files, code):
    protocol["implementation_sha256"] = {
        name: hashlib.sha256(value).hexdigest() for name, value in code.items()
    }
    ph = hashlib.sha256(canonical(protocol).encode()).hexdigest()
    publish_binary(
        root / "protocol",
        {"protocol.json": canonical(protocol) + "\n", **code},
        {"version": protocol["version"], "protocol_sha256": ph},
    )
    summary = json.loads(files["summary.json"])
    summary["protocol_sha256"] = ph
    files["summary.json"] = canonical(summary) + "\n"
    publish_binary(
        root / "fit", files, {"version": protocol["version"], "protocol_sha256": ph}
    )


def set_graph(protocol, files, **updates):
    config = copy.deepcopy(protocol["graph_configuration"])
    config.update(updates)
    protocol["graph_configuration"] = config
    files["graph-configuration.json"] = canonical(config) + "\n"
    scales = json.loads(files["residual-scales.json"])
    scales["graph_configuration"] = config
    files["residual-scales.json"] = canonical(scales) + "\n"


@pytest.fixture(params=[m.V2, m.V3], ids=["v2_shared", "v3_shared"])
def pair(experiment, tmp_path, request):
    candidate, dataset, protocol, files, _ = v3_fixture(experiment)
    protocol.update(
        seed=71,
        adaptation="diag",
        target_accept=0.95,
        versions={"synthetic": "1"},
        building_prior_scale=0.35,
        unit_prior_scale=0.25,
    )
    set_graph(protocol, files, building_prior_scale=0.35, unit_prior_scale=0.25)
    old_code = {
        "bayesian_feature_model.py": b"fixed mean implementation",
        "bayesian_feature_experiment_v2.py": b"fixed original runner",
    }
    new_code = old_code | {name: ("fixed " + name).encode() for name in m.V3_CODE}
    seal(candidate, protocol, files, new_code)
    reference = tmp_path / "reference"
    shutil.copytree(candidate, reference)
    protocol, files, code = saved(reference)
    protocol.update(version=request.param, seed=70, draws=1500, tune=1200, chains=6)
    if request.param == m.V2:
        for name in (
            "graph_configuration",
            "residual_scale",
            "building_prior_scale",
            "unit_prior_scale",
        ):
            del protocol[name]
        for name in ("graph-configuration.json", "residual-scales.json"):
            del files[name]
        code = old_code
    else:
        protocol["residual_scale"] = "shared"
        set_graph(
            protocol,
            files,
            residual_scale="shared",
            residual_bedroom_levels=[],
            residual_bedroom_counts=[],
            residual_bedroom_offset_scale_prior=None,
        )
        scales = json.loads(files["residual-scales.json"])
        scales.update(by_bedroom=[], global_sigma_role="Shared observation scale")
        files["residual-scales.json"] = canonical(scales) + "\n"
    seal(reference, protocol, files, code)
    return reference, candidate, dataset


def test_real_saved_summary_comparison_keeps_separate_intervals_and_replays(
    pair, tmp_path
):
    reference, candidate, dataset = pair
    protocol, files, code = saved(candidate)
    contrasts = json.loads(files["bathroom-contrasts.json"])
    expected = {
        "median": 12.0,
        "lower_95": 8.0,
        "upper_95": 16.0,
        "probability_positive": 0.97,
    }
    contrasts["increments"][0]["percent_effect"] = expected
    files["bathroom-contrasts.json"] = canonical(contrasts) + "\n"
    coefficients = json.loads(files["coefficients.json"])
    coefficients[0]["median"] += 0.01
    files["coefficients.json"] = canonical(coefficients) + "\n"
    residuals = m.verified.jsonl(files["residuals.jsonl"])
    for i, row in enumerate(residuals):
        fit = row["asking_rent"] * (0.95 + 0.02 * i)
        row.update(
            fitted_rent=fit,
            latent_rent_lower_95=fit * 0.9,
            latent_rent_upper_95=fit * 1.1,
            residual_dollars=row["asking_rent"] - fit,
            residual_log=math.log(row["asking_rent"] / fit),
        )
    files["residuals.jsonl"] = "".join(canonical(r) + "\n" for r in reversed(residuals))
    summary = json.loads(files["summary.json"])
    summary["median_absolute_log_residual"] = statistics.median(
        abs(r["residual_log"]) for r in residuals
    )
    files["summary.json"] = canonical(summary) + "\n"
    seal(candidate, protocol, files, code)
    report, provenance = m.build_comparison(reference, candidate, dataset)
    change = report["bathrooms"]["full_bath_increments"][0]["changes"]["percent_effect"]
    assert change["reference"]["median"] == 10 and change["candidate"] == expected
    assert change["median_change"] == 2 and change[
        "lower_endpoint_change"
    ] == pytest.approx(-1.95)
    assert set(change) == {
        "reference",
        "candidate",
        "median_change",
        "lower_endpoint_change",
        "upper_endpoint_change",
        "intervals_overlap_descriptively",
    }
    assert report["bathrooms"]["full_bath_increments"][0]["support_before"] == {
        "rows": 1,
        "units": 1,
        "buildings": 1,
    }
    coefficient = next(
        r
        for r in report["coefficients"]["encoded_value_coefficients"]
        if r["feature"] == "bedrooms_gt_1"
    )
    assert coefficient["changes"]["log_coefficient"]["median_change"] == pytest.approx(
        0.01
    )
    assert report["residuals"]["signed_log_residual"]["spearman_rho"] == pytest.approx(
        1 / math.sqrt(5)
    )
    assert report["residuals"]["current_rows"][0]["changes"][
        "residual_dollars"
    ] == pytest.approx(-150)
    assert report["fits"][1]["residual_scales"]["by_bedroom"][1]["support"]["rows"] == 3
    assert len(provenance) == 2 and report["cohort"]["rows"] == 4
    output = tmp_path / "comparison"
    manifest = m.run(reference, candidate, dataset, output)
    assert m.run(reference, candidate, dataset, output) == manifest
    _, blobs = _verified_bundle(output, retain={"comparison.json", "comparison.md"})
    assert json.loads(blobs["comparison.json"]) == report
    assert b"never paired" in blobs["comparison.md"]
    assert b"+12.00% [+8.00, +16.00]" in blobs["comparison.md"]


@pytest.mark.parametrize(
    "change",
    [
        {"prior_multiplier": 0.5},
        {"adaptation": "low_rank"},
        {"target_accept": 0.99},
        {"versions": {"synthetic": "2"}},
        {"purpose": "different estimand"},
        {"bathroom_policy": "numeric repairs permitted"},
        {"source_directory": "different source"},
    ],
)
def test_fixed_mean_prior_environment_and_policy_mismatches_rejected(pair, change):
    reference, candidate, dataset = pair
    protocol, files, code = saved(candidate)
    protocol.update(change)
    if "prior_multiplier" in change:
        set_graph(protocol, files, beta_prior_multiplier=change["prior_multiplier"])
    seal(candidate, protocol, files, code)
    with pytest.raises(ValueError, match="Fixed source, mean"):
        m.build_comparison(reference, candidate, dataset)


@pytest.mark.parametrize("name", ["building_prior_scale", "unit_prior_scale"])
def test_valid_rehashed_group_prior_changes_rejected(pair, name):
    reference, candidate, dataset = pair
    protocol, files, code = saved(candidate)
    protocol[name] *= 2
    set_graph(protocol, files, **{name: protocol[name]})
    seal(candidate, protocol, files, code)
    with pytest.raises(ValueError, match="Group priors differ"):
        m.build_comparison(reference, candidate, dataset)


@pytest.mark.parametrize("name", m.comparison.DESIGNS)
def test_rehashed_design_changes_rejected(pair, name):
    reference, candidate, dataset = pair
    protocol, files, code = saved(candidate)
    files[name] += b" "
    seal(candidate, protocol, files, code)
    with pytest.raises(ValueError, match="Exact saved mean-design hashes differ"):
        m.build_comparison(reference, candidate, dataset)


def test_rehashed_mean_specification_changes_rejected(pair):
    reference, candidate, dataset = pair
    protocol, files, code = saved(candidate)
    protocol["specification"] = "full_half"
    design = json.loads(files["feature-design.json"])
    design["spec"] = "full_half"
    files["feature-design.json"] = canonical(design) + "\n"
    seal(candidate, protocol, files, code)
    with pytest.raises(ValueError, match="Fixed source, mean"):
        m.build_comparison(reference, candidate, dataset)


@pytest.mark.parametrize(
    "mutation", ["changed_old_code", "missing_old_code", "unexpected_code"]
)
def test_archived_old_code_must_match_exactly(pair, mutation):
    reference, candidate, dataset = pair
    protocol, files, code = saved(candidate)
    if mutation == "changed_old_code":
        code["bayesian_feature_model.py"] = b"different mean"
    elif mutation == "missing_old_code":
        del code["bayesian_feature_model.py"]
    else:
        code["extra.py"] = b"unexpected implementation dependency"
    seal(candidate, protocol, files, code)
    with pytest.raises(ValueError, match="archived v2|implementations differ"):
        m.build_comparison(reference, candidate, dataset)


@pytest.mark.parametrize("family", ["diagnostics", "derived_diagnostics"])
def test_each_fit_requires_parameter_and_derived_diagnostics(pair, family):
    reference, candidate, dataset = pair
    protocol, files, code = saved(candidate)
    summary = json.loads(files["summary.json"])
    summary[family]["max_rhat"] = 1.04
    files["summary.json"] = canonical(summary) + "\n"
    files[
        "diagnostics.json" if family == "diagnostics" else "derived-diagnostics.json"
    ] = canonical(summary[family]) + "\n"
    seal(candidate, protocol, files, code)
    with pytest.raises(ValueError, match="Unacceptable.*diagnostics"):
        m.build_comparison(reference, candidate, dataset)


def test_exact_source_and_residual_targets_required(pair):
    reference, candidate, dataset = pair
    protocol, files, code = saved(candidate)
    protocol["source_observations_sha256"] = "0" * 64
    seal(candidate, protocol, files, code)
    with pytest.raises(ValueError, match="Source dataset"):
        m.build_comparison(reference, candidate, dataset)
    protocol["source_observations_sha256"] = digest(dataset / "observations.jsonl")
    rows = m.verified.jsonl(files["residuals.jsonl"])
    rows[0]["asking_rent"] += 100
    files["residuals.jsonl"] = "".join(canonical(row) + "\n" for row in rows)
    seal(candidate, protocol, files, code)
    with pytest.raises(ValueError, match="target or arithmetic"):
        m.build_comparison(reference, candidate, dataset)


def test_unverified_posterior_bytes_are_rejected_before_comparison(pair):
    reference, candidate, dataset = pair
    (candidate / "fit" / "posterior.nc").write_bytes(b"changed after publication")
    with pytest.raises(ValueError, match="integrity"):
        m.build_comparison(reference, candidate, dataset)


@pytest.mark.parametrize(
    "field,value", [("draws", 0), ("chains", True), ("tune", -1), ("seed", -1)]
)
def test_invalid_sampling_metadata_rejected(pair, field, value):
    reference, candidate, _ = pair
    before, _, _ = saved(reference)
    after, _, _ = saved(candidate)
    after[field] = value
    with pytest.raises(ValueError, match="Invalid sampling protocol"):
        m.check_protocols(before, after)


def test_comparison_direction_and_version_are_explicit(pair):
    reference, candidate, _ = pair
    before, _, _ = saved(reference)
    after, _, _ = saved(candidate)
    with pytest.raises(ValueError, match="shared reference|shared reference against"):
        m.check_protocols(after, before)
    invalid = copy.deepcopy(after)
    invalid["version"] = m.V2
    with pytest.raises(ValueError, match="v3 bedroom candidate"):
        m.check_protocols(before, invalid)
    invalid = copy.deepcopy(after)
    invalid["residual_scale"] = "shared"
    with pytest.raises(ValueError, match="bedroom residual scale only"):
        m.check_protocols(before, invalid)
