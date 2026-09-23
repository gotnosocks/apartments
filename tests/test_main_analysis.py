import json

import pytest

from apartments import main_analysis as m
from apartments import bayesian_evidence
from apartments.research_pipeline import publish_bundle
from .test_bayesian_feature_report import experiment


def test_selection_records_verified_pymc_fit_and_source(experiment, tmp_path):
    fit, dataset = experiment[:2]
    target = tmp_path / "main.json"
    selected = m.select(fit, dataset, target)
    saved, actual_fit, actual_source = m.load_selection(target)
    assert saved == selected
    assert actual_fit == fit and actual_source == dataset
    assert selected["model_family"] == "pymc_bayesian"
    assert selected["cohort"]["rows"] == 4


@pytest.mark.parametrize("relative", ["fit/complete.json", "protocol/complete.json"])
def test_changed_selected_experiment_is_rejected(experiment, tmp_path, relative):
    fit, dataset = experiment[:2]
    target = tmp_path / "main.json"
    m.select(fit, dataset, target)
    (fit / relative).write_text((fit / relative).read_text() + " ")
    with pytest.raises(ValueError, match="binding differs"):
        m.load_selection(target)


def test_changed_source_manifest_is_rejected(experiment, tmp_path):
    fit, dataset = experiment[:2]
    target = tmp_path / "main.json"
    m.select(fit, dataset, target)
    (dataset / "complete.json").write_text("{}")
    with pytest.raises(ValueError, match="source_manifest"):
        m.load_selection(target)


def test_no_surrogate_fallback_and_failed_selection_preserves_existing_file(
    experiment, tmp_path
):
    fit, dataset = experiment[:2]
    target = tmp_path / "main.json"
    m.select(fit, dataset, target)
    original = target.read_bytes()
    (fit / "fit/summary.json").write_text("{}")
    with pytest.raises(ValueError):
        m.select(fit, dataset, target)
    assert target.read_bytes() == original
    value = json.loads(original)
    value["model_family"] = "robust_regression"
    target.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="PyMC Bayesian"):
        m.load_selection(target)


def test_relative_paths_resolve_against_repository_root(tmp_path):
    assert m.resolve_path("data/model/main", tmp_path) == tmp_path / "data/model/main"
    with pytest.raises(ValueError):
        m.resolve_path("")


def test_selection_verifies_and_binds_optional_description_archive(
    experiment, tmp_path, monkeypatch
):
    fit, dataset = experiment[:2]
    target = tmp_path / "main.json"
    archive = tmp_path / "evidence"
    publish_bundle(archive, {"evidence.jsonl": ""}, {"version": "test"})
    calls = []
    monkeypatch.setattr(
        bayesian_evidence, "load_evidence", lambda *args: calls.append(args)
    )
    selected = m.select(fit, dataset, target, evidence=archive)
    assert calls == [(dataset, archive)]
    assert m.load_selection(target)[0] == selected
    assert selected["evidence"] == str(archive)
    (archive / "complete.json").write_text("{}")
    with pytest.raises(ValueError, match="evidence_manifest"):
        m.load_selection(target)


def test_failed_evidence_verification_preserves_existing_selection(
    experiment, tmp_path, monkeypatch
):
    fit, dataset = experiment[:2]
    target = tmp_path / "main.json"
    m.select(fit, dataset, target)
    original = target.read_bytes()

    def fail(*args):
        raise ValueError("Wrong evidence cohort")

    monkeypatch.setattr(bayesian_evidence, "load_evidence", fail)
    with pytest.raises(ValueError, match="evidence cohort"):
        m.select(fit, dataset, target, evidence=tmp_path / "wrong")
    assert target.read_bytes() == original


def test_selection_binds_source_review_and_rejects_changed_manifest(
    experiment, tmp_path, monkeypatch
):
    from apartments import bayesian_source_review

    fit, dataset = experiment[:2]
    archive, review, target = (
        tmp_path / "evidence",
        tmp_path / "review",
        tmp_path / "main.json",
    )
    publish_bundle(archive, {"evidence.jsonl": ""}, {"version": "test"})
    publish_bundle(review, {"cases.jsonl": ""}, {"version": "test"})
    monkeypatch.setattr(bayesian_evidence, "load_evidence", lambda *a: {})
    calls = []

    def checked(*args, **kwargs):
        calls.append((args, kwargs))
        return {"a": {"kind": "conflict"}}

    monkeypatch.setattr(bayesian_source_review, "load_source_review", checked)
    value = m.select(fit, dataset, target, evidence=archive, source_review=review)
    assert value["source_review_cases"] == 1 and len(calls) == 1
    assert m.load_selection(target)[0] == value
    (review / "complete.json").write_text("{}")
    with pytest.raises(ValueError, match="source_review_manifest"):
        m.load_selection(target)


def test_missing_review_evidence_preserves_existing_selection(experiment, tmp_path):
    fit, dataset = experiment[:2]
    target = tmp_path / "main.json"
    m.select(fit, dataset, target)
    original = target.read_bytes()
    with pytest.raises(ValueError, match="matching description archive"):
        m.select(fit, dataset, target, source_review=tmp_path / "review")
    assert target.read_bytes() == original


def test_selection_verifies_source_issues_and_binds_case_count(
    experiment, tmp_path, monkeypatch
):
    from apartments import source_issues

    fit, dataset = experiment[:2]
    archive, issues, target = (
        tmp_path / "evidence",
        tmp_path / "issues",
        tmp_path / "main.json",
    )
    publish_bundle(archive, {"evidence.jsonl": ""}, {"version": "test"})
    publish_bundle(issues, {"issues.jsonl": ""}, {"version": "test"})
    monkeypatch.setattr(bayesian_evidence, "load_evidence", lambda *a: {})
    calls = []

    def checked(*args, **kwargs):
        calls.append((args, kwargs))
        return {"historical-a": {}, "current-b": {}}

    monkeypatch.setattr(source_issues, "load_source_issues", checked)
    value = m.select(fit, dataset, target, evidence=archive, source_issues=issues)
    assert value["source_issue_cases"] == 2
    assert calls == [((dataset, issues), {"evidence": archive})]
    assert m.load_selection(target)[0] == value
    (issues / "complete.json").write_text("{}")
    with pytest.raises(ValueError, match="source_issues_manifest_sha256"):
        m.load_selection(target)


def test_source_issues_require_evidence_and_failed_verification_preserves_selection(
    experiment, tmp_path, monkeypatch
):
    from apartments import source_issues

    fit, dataset = experiment[:2]
    target = tmp_path / "main.json"
    m.select(fit, dataset, target)
    original = target.read_bytes()
    with pytest.raises(ValueError, match="matching description archive"):
        m.select(fit, dataset, target, source_issues=tmp_path / "issues")
    assert target.read_bytes() == original
    archive = tmp_path / "evidence"
    publish_bundle(archive, {"evidence.jsonl": ""}, {"version": "test"})
    monkeypatch.setattr(bayesian_evidence, "load_evidence", lambda *a: {})

    def fail(*a, **k):
        raise ValueError("Source issue evidence binding differs")

    monkeypatch.setattr(source_issues, "load_source_issues", fail)
    with pytest.raises(ValueError, match="issue evidence binding"):
        m.select(
            fit, dataset, target, evidence=archive, source_issues=tmp_path / "issues"
        )
    assert target.read_bytes() == original


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_path",
        "missing_hash",
        "missing_count",
        "missing_evidence",
        "boolean_count",
        "negative_count",
    ],
)
def test_incomplete_source_issue_selection_rejected(
    experiment, tmp_path, monkeypatch, mutation
):
    from apartments import source_issues

    fit, dataset = experiment[:2]
    archive, issues, target = (
        tmp_path / "evidence",
        tmp_path / "issues",
        tmp_path / "main.json",
    )
    publish_bundle(archive, {"evidence.jsonl": ""}, {"version": "test"})
    publish_bundle(issues, {"issues.jsonl": ""}, {"version": "test"})
    monkeypatch.setattr(bayesian_evidence, "load_evidence", lambda *a: {})
    monkeypatch.setattr(source_issues, "load_source_issues", lambda *a, **k: {"a": {}})
    value = m.select(fit, dataset, target, evidence=archive, source_issues=issues)
    if mutation == "missing_path":
        value.pop("source_issues")
    if mutation == "missing_hash":
        value.pop("source_issues_manifest_sha256")
    if mutation == "missing_count":
        value.pop("source_issue_cases")
    if mutation == "missing_evidence":
        value.pop("evidence")
        value.pop("evidence_manifest_sha256")
    if mutation == "boolean_count":
        value["source_issue_cases"] = True
    if mutation == "negative_count":
        value["source_issue_cases"] = -1
    target.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="source issue"):
        m.load_selection(target)
