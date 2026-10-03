"""Data rules: one unit id per physical unit (unit-labels-v1) and the
divergence-review quarantine (quarantine-v1)."""

import json

import numpy as np
import pandas as pd
import pytest
from rentfrontier import data


def test_unit_label_key_writes_a_label_one_way():
    same = {
        "4B": ["APT-4B", "UNIT4B", "4-B", "04B", "4b", "#4B"],
        "7THFL": ["7TH-FLOOR", "7THFL", "7TH-FLR"],
        "PHA": ["PH-A", "PHA"],
        "2": ["02", "2"],
    }
    for key, labels in same.items():
        assert {data.unit_label_key(label) for label in labels} == {key}
    assert data.unit_label_key("NORTH1") == "NORTH1"
    assert data.unit_label_key("NO.5") == "5"


def test_merge_unit_labels_joins_units_of_one_building_only():
    url = "https://streeteasy.com/building/{}/{}".format
    frame = pd.DataFrame(
        {
            "building": ["a", "a", "a", "b"],
            "unit_id": ["u1", "u2", "u3", "u4"],
            "canonical_unit_url": [
                url("a", "4-b"),
                url("a", "4b"),
                url("a", "5b"),
                url("b", "4b"),
            ],
            "asking_rent": [1.0, 2.0, 3.0, 4.0],
        }
    )
    out = data.merge_unit_labels(frame)
    assert out.unit_id.tolist() == ["u1", "u1", "u3", "u4"]
    assert out.asking_rent.tolist() == frame.asking_rent.tolist()
    ruled, heldout = data.apply_rules(
        frame, [False, True, False, False], ["unit-labels-v1"]
    )
    assert ruled.unit_id.tolist() == out.unit_id.tolist()
    assert heldout.tolist() == [False, True, False, False]


def test_quarantine_drops_rows_from_the_frame_and_the_heldout_mask(monkeypatch):
    frame = pd.DataFrame({"audit_id": ["a", "b", "c", "d", "e"], "x": range(5)})
    frame.attrs["source_sha256"] = "s"
    heldout = np.array([False, True, True, False, True])
    monkeypatch.setattr(data, "quarantined", lambda: frozenset({"b", "d"}))
    ruled, mask = data.apply_rules(frame, heldout, ["quarantine-v1"])
    assert ruled.audit_id.tolist() == ["a", "c", "e"]
    assert ruled.index.tolist() == [0, 1, 2]
    # Every kept row keeps its side of the split.
    assert dict(zip(ruled.audit_id, mask)) == {"a": False, "c": True, "e": True}
    assert ruled.attrs["source_sha256"] == "s"


@pytest.mark.parametrize(
    "path", [data.QUARANTINE_V1, data.QUARANTINE_V2, data.QUARANTINE_V3]
)
def test_quarantine_file_names_each_row_once_with_its_evidence(path):
    with open(path) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    actions = {
        "quarantine_nonresidential",
        "quarantine_location_conflict",
        "quarantine_product_scope",
        "quarantine_explicit_short_term_offer",
        "quarantine_price_basis",
        "quarantine_attribute_conflict",
    }
    assert (
        len(rows) == len({r["audit_id"] for r in rows}) == len(data.quarantined(path))
    )
    for r in rows:
        assert r["action"] in actions and r["reason"], r
        assert r["evidence"] or r.get("external_evidence"), r
    assert data.quarantined(path) <= data.dropped_rows()


def test_quarantine_v2_keeps_every_v1_row():
    assert data.quarantined() < data.quarantined(data.QUARANTINE_V2)


def test_quarantine_v3_keeps_every_v2_row():
    assert data.quarantined(data.QUARANTINE_V2) < data.quarantined(data.QUARANTINE_V3)


def test_unit_line_key():
    url = "https://streeteasy.com/building/{}/{}".format
    labels = [
        "23c",
        "4-c",
        "1204",
        "304",
        "4th",
        "2nd",
        "ph",
        "garden-a",
        "12",
        "4thfl",
    ]
    frame = pd.DataFrame(
        {"building": "b", "canonical_unit_url": [url("b", x) for x in labels]}
    )
    got = data.unit_line_key(frame).tolist()
    assert got[:6] == ["b/C", "b/C", "b/04", "b/04", "b/FL", "b/FL"]
    assert all(pd.isna(x) for x in got[6:9]) and got[9] == "b/FL"


def test_recorded_rules_refuse_an_unknown_rule_or_a_changed_file(tmp_path, monkeypatch):
    path = tmp_path / "q.jsonl"
    path.write_text('{"audit_id": "a"}\n')
    monkeypatch.setitem(data.RULE_SOURCES, "quarantine-v1", path)
    good = {
        "data_rules": ["unit-labels-v1", "quarantine-v1"],
        "data_rule_sources": {"quarantine-v1": {"sha256": data.sha256(path)}},
    }
    assert data.recorded_rules(good) == ("unit-labels-v1", "quarantine-v1")
    assert data.recorded_rules({}) == ()  # older records: no rules, nothing to check
    with pytest.raises(SystemExit, match="unknown data rule"):
        data.recorded_rules({"data_rules": ["no-such-rule"]})
    with pytest.raises(SystemExit, match="records no hash"):
        data.recorded_rules({"data_rules": ["quarantine-v1"]})
    path.write_text('{"audit_id": "b"}\n')
    with pytest.raises(SystemExit, match="differs from the run's record"):
        data.recorded_rules(good)


def test_dropped_rows_are_the_union_of_every_rule_file(tmp_path, monkeypatch):
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    a.write_text('{"audit_id": "x"}\n')
    b.write_text('{"audit_id": "y"}\n{"audit_id": "x"}\n')
    monkeypatch.setattr(data, "RULE_SOURCES", {"quarantine-v1": a, "quarantine-v2": b})
    monkeypatch.setattr(data, "DROPPING_RULES", ("quarantine-v1", "quarantine-v2"))
    assert data.dropped_rows() == {"x", "y"}


def test_tuning_subset_is_a_stable_share_of_buildings():
    import numpy as np

    buildings = [f"b{i}" for i in range(4000)]
    keep = np.array([data.in_tuning_subset(b) for b in buildings])
    assert 0.32 < keep.mean() < 0.38
    assert data.in_tuning_subset("b7") == data.in_tuning_subset("b7")
    frame = pd.DataFrame({"building": buildings, "x": range(4000)})
    out, held = data.apply_rules(frame, np.zeros(4000, bool), ("tune-b35-v1",))
    assert len(out) == keep.sum() and not held.any()


def test_bedroom_corrections_change_only_bedrooms(tmp_path, monkeypatch):
    import numpy as np

    path = tmp_path / "c.jsonl"
    path.write_text(
        '{"audit_id": "b", "field": "bedrooms", "corrected": 2.0}\n'
        '{"audit_id": "z", "field": "bedrooms", "corrected": 0.0}\n'
    )
    monkeypatch.setitem(data.RULE_SOURCES, "bedrooms-ad-v1", path)
    frame = pd.DataFrame({"audit_id": ["a", "b", "c"], "bedrooms": [1.0, 1.0, 3.0]})
    out, held = data.apply_rules(frame, np.array([0, 1, 0], bool), ["bedrooms-ad-v1"])
    assert out.audit_id.tolist() == ["a", "b", "c"]
    assert out.bedrooms.tolist() == [1.0, 2.0, 3.0]
    assert held.tolist() == [False, True, False]
    assert frame.bedrooms.tolist() == [1.0, 1.0, 3.0]  # the input is untouched
    assert "z" not in data.dropped_rows() and "b" not in data.dropped_rows()


def test_bedroom_corrections_file_names_each_row_once_with_its_evidence():
    with open(data.BEDROOM_CORRECTIONS) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    assert rows and len(rows) == len({r["audit_id"] for r in rows})
    for r in rows:
        assert r["action"] == "correct_bedrooms" and r["field"] == "bedrooms", r
        assert r["corrected"] != r["recorded"] and r["evidence"], r
    assert len(data.corrections()) == len(rows)


def test_unit_labels_v2_joins_confirmed_alias_groups_through_v1(tmp_path, monkeypatch):
    """v2 = v1 plus the alias table's confirmed groups; groups chained through
    either rule become one unit with the smallest id; unconfirmed groups and
    rows are untouched."""
    url = "https://streeteasy.com/building/{}/{}".format
    frame = pd.DataFrame(
        {
            "building": ["a", "a", "a", "a", "a", "a"],
            "unit_id": ["u5", "u2", "u3", "u4", "u6", "u7"],
            "canonical_unit_url": [
                url("a", "ph-4"),  # v1 joins u5 and u2 (punctuation)
                url("a", "ph4"),
                url("a", "ph04"),  # the alias table joins u3 with u2 ...
                url("a", "r01"),
                url("a", "r1"),  # ... and u4 with u6, but unconfirmed
                url("a", "9c"),
            ],
            "asking_rent": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        }
    )
    aliases = tmp_path / "aliases.jsonl"
    lines = [
        {"alias_group_id": "g1", "unit_id": "u3", "history_confirmed": True},
        {"alias_group_id": "g1", "unit_id": "u2", "history_confirmed": True},
        {"alias_group_id": "g2", "unit_id": "u4", "history_confirmed": False},
        {"alias_group_id": "g2", "unit_id": "u6", "history_confirmed": False},
    ]
    aliases.write_text("".join(json.dumps(x) + "\n" for x in lines))
    groups = data.unit_aliases.__wrapped__(aliases)
    monkeypatch.setattr(data, "unit_aliases", lambda path=None: groups)
    out = data.merge_unit_aliases(frame)
    assert out.unit_id.tolist() == ["u2", "u2", "u2", "u4", "u6", "u7"]
    assert out.asking_rent.tolist() == frame.asking_rent.tolist()
    assert data.DATA_RULES["unit-labels-v2"] is data.merge_unit_aliases


def test_the_alias_file_is_hashed_but_drops_no_rows():
    assert "unit-labels-v2" in data.RULE_SOURCES
    assert "unit-labels-v2" not in data.DROPPING_RULES
    groups = data.unit_aliases()
    assert len(groups) == 248 and all(len(g) > 1 for g in groups)
    assert data.dropped_rows() == data.quarantined(data.QUARANTINE_V3)
