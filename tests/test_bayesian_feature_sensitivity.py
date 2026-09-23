"""Prior sensitivity requires comparable converged fits, not merely valid files."""

import copy
import hashlib
import json
import math
import shutil
import statistics

import pytest

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, publish_bundle
from models import bayesian_feature_sensitivity as m
from .test_bayesian_feature_report import experiment, publish_binary


def rewrite(root, protocol_change=None, fit_change=None):
    protocol = json.loads((root / "protocol" / "protocol.json").read_text())
    protocol.update(protocol_change or {})
    ph = hashlib.sha256(canonical(protocol).encode()).hexdigest()
    pm = json.loads((root / "protocol" / "complete.json").read_text())
    files = {name: (root / "protocol" / name).read_bytes() for name in pm["files"]}
    files["protocol.json"] = canonical(protocol) + "\n"
    publish_binary(
        root / "protocol",
        files,
        {"version": m.verified.EXPERIMENT_VERSION, "protocol_sha256": ph},
    )
    fm = json.loads((root / "fit" / "complete.json").read_text())
    files = {name: (root / "fit" / name).read_bytes() for name in fm["files"]}
    summary = json.loads(files["summary.json"])
    summary["protocol_sha256"] = ph
    files["summary.json"] = canonical(summary) + "\n"
    if fit_change:
        fit_change(files)
    publish_binary(
        root / "fit",
        files,
        {"version": m.verified.EXPERIMENT_VERSION, "protocol_sha256": ph},
    )


@pytest.fixture
def pair(experiment, tmp_path):
    first, dataset, *_ = experiment
    rewrite(
        first,
        {
            "seed": 71,
            "adaptation": "diag",
            "target_accept": 0.95,
            "versions": {"synthetic": "1"},
        },
    )
    second = tmp_path / "second"
    shutil.copytree(first, second)
    rewrite(
        second,
        {"prior_multiplier": 0.5, "seed": 72, "draws": 1200, "tune": 1500, "chains": 6},
    )
    return first, second, dataset


def test_saved_summary_comparison_and_immutable_replay(pair, tmp_path):
    first, second, dataset = pair

    def change(files):
        coefficients = json.loads(files["coefficients.json"])
        coefficients[0]["median"] += 0.01
        files["coefficients.json"] = canonical(coefficients) + "\n"
        contrasts = json.loads(files["bathroom-contrasts.json"])
        contrasts["increments"][0]["percent_effect"]["median"] += 0.02
        files["bathroom-contrasts.json"] = canonical(contrasts) + "\n"
        residuals = m.verified.jsonl(files["residuals.jsonl"])
        for index, row in enumerate(residuals):
            fit = row["asking_rent"] * (0.95 + 0.02 * index)
            row.update(
                fitted_rent=fit,
                latent_rent_lower_95=fit * 0.9,
                latent_rent_upper_95=fit * 1.1,
                residual_dollars=row["asking_rent"] - fit,
                residual_log=math.log(row["asking_rent"] / fit),
            )
        # File ordering must not create spurious pairing or ranking changes.
        files["residuals.jsonl"] = "".join(
            canonical(r) + "\n" for r in reversed(residuals)
        )
        summary = json.loads(files["summary.json"])
        summary["median_absolute_log_residual"] = statistics.median(
            abs(r["residual_log"]) for r in residuals
        )
        files["summary.json"] = canonical(summary) + "\n"

    rewrite(second, fit_change=change)
    report, provenance = m.build_comparison([second, first], dataset)
    assert report["reference_prior_multiplier"] == 1
    assert report["cohort"]["rows"] == 4
    comparison = report["comparisons"][0]
    full = comparison["bathrooms"]["full_bath_increments"][0]
    assert full["changes"]["percent_effect"]["median_change"] == pytest.approx(0.02)
    assert full["support_before"] == {"rows": 1, "units": 1, "buildings": 1}
    coef = next(
        r
        for r in comparison["coefficients"]["encoded_value_coefficients"]
        if r["feature"] == "bedrooms_gt_1"
    )
    assert coef["changes"]["log_coefficient"]["median_change"] == pytest.approx(0.01)
    assert "not a fixed-square-footage" in coef["encoded_unit"]
    assert report["omitted_category_basis_coefficients"] == ["laundry_type.contrast_0"]
    residuals = comparison["residuals"]
    assert residuals["signed_log_residual"]["spearman_rho"] == pytest.approx(
        1 / math.sqrt(5)
    )
    current = residuals["current_rows"][0]
    assert current["audit_id"] == "a0" and current["source_listing_id"] == "100"
    assert current["changes"]["residual_dollars"] == pytest.approx(-150)
    assert (
        current["source_record"]["analysis_price_basis"] == "current_capture_gross_ask"
    )
    assert set(full["changes"]["percent_effect"]) == {
        "reference",
        "candidate",
        "median_change",
        "lower_endpoint_change",
        "upper_endpoint_change",
        "intervals_overlap_descriptively",
    }
    assert len(provenance) == 2
    output = tmp_path / "comparison"
    manifest = m.run([first, second], dataset, output)
    assert m.run([second, first], dataset, output) == manifest
    _, blobs = _verified_bundle(output, retain={"comparison.json", "comparison.md"})
    assert json.loads(blobs["comparison.json"]) == report
    assert b"never paired" in blobs["comparison.md"]
    assert b"https://streeteasy.com/rental/100" in blobs["comparison.md"]
    rewrite(second, {"draws": 1300})
    with pytest.raises(ValueError, match="Run identity changed"):
        m.run([first, second], dataset, output)


@pytest.mark.parametrize(
    "change",
    [
        {"adaptation": "low_rank"},
        {"target_accept": 0.99},
        {"versions": {"synthetic": "2"}},
        {"purpose": "changed estimand"},
        {"likelihood": "changed target"},
    ],
)
def test_fixed_protocol_changes_rejected(pair, change):
    first, second, dataset = pair
    rewrite(second, change)
    with pytest.raises(ValueError, match="Fixed protocol identity"):
        m.build_comparison([first, second], dataset)


@pytest.mark.parametrize(
    "name", ["feature-design.json", "time-design.json", "time-design.npz"]
)
def test_design_must_match_exactly_despite_rehashed_products(pair, name):
    first, second, dataset = pair

    def change(files):
        files[name] += (
            b" "  # Valid JSON whitespace or changed binary, with a valid manifest.
        )

    rewrite(second, fit_change=change)
    with pytest.raises(ValueError, match="design hashes differ"):
        m.build_comparison([first, second], dataset)


@pytest.mark.parametrize("multiplier", [1, 0, -1, True])
def test_distinct_positive_finite_prior_multipliers(pair, multiplier):
    first, second, dataset = pair
    rewrite(second, {"prior_multiplier": multiplier})
    with pytest.raises(ValueError, match="multiplier"):
        m.build_comparison([first, second], dataset)


@pytest.mark.parametrize(
    "change", [{"draws": 0}, {"tune": -1}, {"chains": True}, {"seed": -1}]
)
def test_invalid_sampling_metadata_refused(pair, change):
    first, second, dataset = pair
    rewrite(second, change)
    with pytest.raises(ValueError, match="Invalid sampling"):
        m.build_comparison([first, second], dataset)


@pytest.mark.parametrize("family", ["diagnostics", "derived_diagnostics"])
def test_both_diagnostic_gates_apply(pair, family):
    first, second, dataset = pair

    def change(files):
        summary = json.loads(files["summary.json"])
        summary[family]["max_rhat"] = 1.03
        files["summary.json"] = canonical(summary) + "\n"
        name = (
            "diagnostics.json"
            if family == "diagnostics"
            else "derived-diagnostics.json"
        )
        files[name] = canonical(summary[family]) + "\n"

    rewrite(second, fit_change=change)
    with pytest.raises(ValueError, match="Unacceptable.*diagnostics"):
        m.build_comparison([first, second], dataset)


def test_source_and_target_mismatch_rejected(pair, tmp_path):
    first, second, dataset = pair

    def change(files):
        rows = m.verified.jsonl(files["residuals.jsonl"])
        rows[0]["asking_rent"] += 1
        files["residuals.jsonl"] = "".join(canonical(r) + "\n" for r in rows)

    rewrite(second, fit_change=change)
    with pytest.raises(ValueError, match="target or arithmetic"):
        m.build_comparison([first, second], dataset)
    other = tmp_path / "other-source"
    rows = m.verified.jsonl((dataset / "observations.jsonl").read_bytes())
    rows[0]["asking_rent"] += 2
    publish_bundle(
        other,
        {"observations.jsonl": "".join(canonical(r) + "\n" for r in rows)},
        {"version": "reviewed-bathroom-counts-projection-v1"},
    )
    with pytest.raises(ValueError, match="Source dataset"):
        m.build_comparison([first, second], other)


def test_archived_implementation_and_incomplete_fit_rejected(pair):
    first, second, dataset = pair
    rewrite(second, {"implementation_sha256": {"missing.py": "bad"}})
    with pytest.raises(ValueError, match="archived implementation"):
        m.build_comparison([first, second], dataset)
    rewrite(second, {"implementation_sha256": {}})
    (second / "fit" / "complete.json").unlink()
    with pytest.raises((FileNotFoundError, ValueError)):
        m.build_comparison([first, second], dataset)
    with pytest.raises(ValueError, match="At least two"):
        m.build_comparison([first], dataset)


def test_same_valid_archived_implementation_required(pair):
    first, second, dataset = pair
    for root, content in [
        (first, b"original implementation"),
        (second, b"changed implementation"),
    ]:
        protocol_dir = root / "protocol"
        manifest = json.loads((protocol_dir / "complete.json").read_text())
        (protocol_dir / "implementation.py").write_bytes(content)
        manifest["files"]["implementation.py"] = hashlib.sha256(content).hexdigest()
        (protocol_dir / "complete.json").write_text(canonical(manifest) + "\n")
        rewrite(
            root,
            {
                "implementation_sha256": {
                    "implementation.py": manifest["files"]["implementation.py"]
                }
            },
        )
    with pytest.raises(ValueError, match="Fixed protocol identity"):
        m.build_comparison([first, second], dataset)


def test_different_valid_specification_rejected(pair):
    first, second, dataset = pair

    def change(files):
        design = json.loads(files["feature-design.json"])
        design["spec"] = "alternative"
        files["feature-design.json"] = canonical(design) + "\n"

    rewrite(second, {"specification": "alternative"}, change)
    with pytest.raises(ValueError, match="Fixed protocol identity"):
        m.build_comparison([first, second], dataset)


def test_nonunit_reference_rule_and_three_fits(pair, tmp_path):
    first, second, dataset = pair
    third = tmp_path / "third"
    shutil.copytree(first, third)
    rewrite(third, {"prior_multiplier": 2})
    report, _ = m.build_comparison([third, second, first], dataset)
    assert len(report["comparisons"]) == 2
    assert [r["candidate_prior_multiplier"] for r in report["comparisons"]] == [0.5, 2]
    report, _ = m.build_comparison([third, second], dataset)
    assert report["reference_prior_multiplier"] == 0.5


def test_ranks_ties_and_constant_guard():
    assert m.ranks([3, 1, 1, 2]) == [4, 1.5, 1.5, 3]
    assert m.rank_correlation([1, 2, 3], [3, 2, 1])["spearman_rho"] == -1
    assert m.rank_correlation([1, 1], [1, 2])["spearman_rho"] is None
    assert m.rank_correlation([], [])["spearman_rho"] is None


def test_support_semantics_and_duplicate_contrasts_cannot_be_paired():
    interval = {"median": 1, "lower_95": 0, "upper_95": 2, "probability_positive": 0.9}
    before = [{"bedrooms": 2, "support": 3, "effect": interval}]
    after = copy.deepcopy(before)
    after[0]["support"] = 4
    with pytest.raises(ValueError, match="identity, support or semantics"):
        m.compare_tables(before, after, ("effect",))
    with pytest.raises(ValueError, match="Duplicate"):
        m.compare_tables(before * 2, before, ("effect",))
