"""Data rules: one unit id per physical unit (unit-labels-v1)."""

import pandas as pd
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
    assert (
        data.apply_rules(frame, ["unit-labels-v1"]).unit_id.tolist()
        == out.unit_id.tolist()
    )
