import math

import pytest

from models.group_effect_audit import (
    representative_rows,
    select_groups,
    summarize_group,
)


def row(key, ask, residual, unit="u", month="2020-01-01"):
    return dict(
        audit_id=key,
        asking_rent=ask,
        log_residual=residual,
        unit_id=unit,
        building_id="b",
        source_listing_id=key,
        period=month,
    )


def test_group_support_distinguishes_rows_units_ads_and_robust_support():
    rows = [
        row("a", 2000, 0.1),
        row("b", 3000, 0.4),
        row("c", 5000, -0.8, unit="v", month="2021-02-01"),
    ]
    result = summarize_group("building", "b", math.log(1.2), rows, 10)
    assert (
        result["rows"],
        result["units"],
        result["advertisements"],
        result["months"],
    ) == (3, 2, 3, 2)
    assert result["huber_weight_sum"] == pytest.approx(1.75)
    assert result["conditional_shrinkage_factor"] == pytest.approx(1.75 / 11.75)
    assert result["downweighted_rows"] == 2
    assert result["conditional_multiplier_percent"] == pytest.approx(20)
    assert result["median_log_residual"] == 0.1


def test_separate_group_tails_and_deterministic_ties():
    ranks = [
        dict(kind=kind, group_id=k, log_effect=v)
        for kind in ("unit", "building")
        for k, v in [("z", 2), ("a", 2), ("b", -0.8), ("c", -0.2), ("d", 0)]
    ]
    selected = select_groups(ranks, 1)
    assert [(r["kind"], r["tail"], r["group_id"]) for r in selected] == [
        ("building", "positive", "a"),
        ("building", "negative", "b"),
        ("unit", "positive", "a"),
        ("unit", "negative", "b"),
    ]
    with pytest.raises(ValueError):
        select_groups(ranks, 0)


def test_representatives_keep_typical_case_large_residual_and_latest_deduplicated():
    rows = [
        row("a", 2000, -0.8),
        row("b", 3000, 0.1),
        row("c", 5000, 0.2, month="2021-02-01"),
    ]
    cases = representative_rows(rows)
    assert {c["row"]["audit_id"]: c["selection_reasons"] for c in cases} == {
        "b": ["median_ask"],
        "a": ["largest_absolute_residual"],
        "c": ["latest"],
    }
    assert representative_rows(rows[:1])[0]["selection_reasons"] == [
        "median_ask",
        "largest_absolute_residual",
        "latest",
    ]


def test_audit_rejects_description_identity_and_hash_mismatch(tmp_path, monkeypatch):
    import hashlib
    import json
    from types import SimpleNamespace
    from models import group_effect_audit as audit
    from apartments.corrections import canonical

    source = row("a", 2000, 0.1)
    protocol = {"settings": {"building_penalty": 10, "unit_penalty": 8}}
    protocol_bytes = (canonical(protocol) + "\n").encode()
    model = SimpleNamespace(
        artifact={"training": {"source_manifest": {"dataset": 1}}},
        manifest={
            "revision_protocol_sha256": hashlib.sha256(
                canonical(protocol).encode()
            ).hexdigest()
        },
    )
    monkeypatch.setattr(
        audit.robust_pricing.RobustPricingModel, "load", lambda _: model
    )
    description = dict(
        audit_id="a",
        unit_id="wrong",
        building_id="b",
        source_listing_id="a",
        description="shared bathroom",
        description_sha256="invalid",
    )

    def verify(path, retain):
        if path == "dataset":
            return {"dataset": 1}, {
                "observations.jsonl": (json.dumps(source) + "\n").encode()
            }
        if path == "descriptions":
            return {"dataset_manifest": {"dataset": 1}}, {
                "evidence.jsonl": (json.dumps(description) + "\n").encode()
            }
        return {}, {"protocol.json": protocol_bytes}

    monkeypatch.setattr(audit, "_verified_bundle", verify)
    with pytest.raises(ValueError, match="identity mismatch"):
        audit.run("model", "dataset", "descriptions", "protocol", tmp_path)
    description["unit_id"] = "u"
    with pytest.raises(ValueError, match="hash mismatch"):
        audit.run("model", "dataset", "descriptions", "protocol", tmp_path)
    model.manifest["revision_protocol_sha256"] = "wrong"
    with pytest.raises(ValueError, match="Protocol"):
        audit.run("model", "dataset", "descriptions", "protocol", tmp_path)
