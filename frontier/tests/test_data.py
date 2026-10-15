"""Data rules: one unit id per physical unit (unit-labels-v1) and the
divergence-review quarantine (quarantine-v1)."""

import functools
import json
import re

import numpy as np
import pandas as pd
import pytest
from rentfrontier import autoselect, brooklyn, data


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
    "path",
    [
        data.QUARANTINE_V1,
        data.QUARANTINE_V2,
        data.QUARANTINE_V3,
        data.QUARANTINE_V4,
        data.QUARANTINE_V5,
    ],
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


def test_quarantine_v4_keeps_every_v3_row():
    assert data.quarantined(data.QUARANTINE_V3) < data.quarantined(data.QUARANTINE_V4)
    assert len(data.quarantined(data.QUARANTINE_V4)) == 272


def test_quarantine_v5_keeps_every_v4_row():
    assert data.quarantined(data.QUARANTINE_V4) < data.quarantined(data.QUARANTINE_V5)
    assert len(data.quarantined(data.QUARANTINE_V5)) == 277


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


def test_bath_corrections_change_only_the_bath_counts(tmp_path, monkeypatch):
    import numpy as np

    path = tmp_path / "c.jsonl"
    path.write_text('{"audit_id": "b", "full_baths": 1, "half_baths": 1}\n')
    monkeypatch.setitem(data.RULE_SOURCES, "baths-ad-v1", path)
    frame = pd.DataFrame(
        {"audit_id": ["a", "b"], "full_baths": [1, 1], "half_baths": [0, 0]}
    )
    out, _ = data.apply_rules(frame, np.zeros(2, bool), ["baths-ad-v1"])
    assert out.full_baths.tolist() == [1, 1]
    assert out.half_baths.tolist() == [0, 1]
    assert out.full_baths.dtype == frame.full_baths.dtype
    assert frame.half_baths.tolist() == [0, 0]
    assert "b" not in data.dropped_rows()


def test_bath_corrections_keep_a_dataset_with_none_of_their_rows(tmp_path, monkeypatch):
    import numpy as np

    path = tmp_path / "c.jsonl"
    path.write_text('{"audit_id": "z", "full_baths": 2, "half_baths": 0}\n')
    monkeypatch.setitem(data.RULE_SOURCES, "baths-ad-v1", path)
    frame = pd.DataFrame(
        {"audit_id": ["a", "b"], "full_baths": [1, 1], "half_baths": [0, 0]}
    )
    out, _ = data.apply_rules(frame, np.zeros(2, bool), ["baths-ad-v1"])
    pd.testing.assert_frame_equal(out, frame)


def test_bath_corrections_file_names_each_row_once_with_its_evidence():
    with open(data.BATH_CORRECTIONS) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    assert rows and len(rows) == len({r["audit_id"] for r in rows})
    for r in rows:
        assert r["action"] == "correct_baths" and r["corrected"] > r["recorded"], r
        assert r["full_baths"] + 0.5 * r["half_baths"] == r["corrected"], r
        assert r["evidence"], r


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
    assert data.dropped_rows() == data.quarantined(
        data.QUARANTINE_V8
    ) | data.quarantined(data.QUARANTINE_V9) | data.quarantined(
        data.QUARANTINE_V10
    ) | data.quarantined(data.QUARANTINE_V12) | data.quarantined(
        data.QUARANTINE_V13
    ) | data.quarantined(data.QUARANTINE_V14) | data.quarantined(
        data.QUARANTINE_V15
    ) | data.quarantined(data.QUARANTINE_V16) | data.quarantined(
        data.QUARANTINE_V17
    ) | data.quarantined(data.QUARANTINE_V31)


@pytest.mark.parametrize(
    "path,action",
    [
        (data.BEDROOM_CORRECTIONS_V2, "correct_bedrooms"),
        (data.BATH_CORRECTIONS_V2, "correct_baths"),
    ],
)
def test_v2_corrections_files_are_strict_subsets_of_v1(path, action):
    v1_path = {
        data.BEDROOM_CORRECTIONS_V2: data.BEDROOM_CORRECTIONS,
        data.BATH_CORRECTIONS_V2: data.BATH_CORRECTIONS,
    }[path]
    with open(path) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    with open(v1_path) as f:
        v1 = {json.loads(line)["audit_id"] for line in f if line.strip()}
    assert rows and len(rows) == len({r["audit_id"] for r in rows})
    assert {r["audit_id"] for r in rows} < v1
    assert all(r["action"] == action and r["evidence"] for r in rows)
    assert not {r["audit_id"] for r in rows} & data.dropped_rows()


def test_fields_review_corrects_bedrooms_and_baths_only(tmp_path, monkeypatch):
    path = tmp_path / "r.jsonl"
    path.write_text(
        '{"audit_id": "a", "field": "bedrooms", "corrected": 0.0}\n'
        '{"audit_id": "b", "field": "baths", "corrected": 2.5, '
        '"full_baths": 2, "half_baths": 1}\n'
    )
    monkeypatch.setitem(data.RULE_SOURCES, "fields-review-v1", path)
    frame = pd.DataFrame(
        {
            "audit_id": ["a", "b", "c"],
            "bedrooms": [1.0, 2.0, 1.0],
            "full_baths": [1, 3, 1],
            "half_baths": [0.0, 0.0, 0.0],
        }
    )
    out, _ = data.apply_rules(frame, np.zeros(3, bool), ["fields-review-v1"])
    assert out.bedrooms.tolist() == [0.0, 2.0, 1.0]
    assert out.full_baths.tolist() == [1, 2, 1]
    assert out.half_baths.tolist() == [0.0, 1.0, 0.0]
    assert out.full_baths.dtype == frame.full_baths.dtype


def test_fields_review_v3_reverts_v1_and_is_current():
    from rentfrontier import autoselect

    frame = pd.DataFrame({"audit_id": ["a"], "bedrooms": [1.0], "full_baths": [1]})
    out, _ = data.apply_rules(frame, np.zeros(1, bool), ["fields-review-v3"])
    pd.testing.assert_frame_equal(out.reset_index(drop=True), frame)
    current = autoselect.current_rules()
    assert "fields-review-v3" in current and "fields-review-v1" not in current


def test_fields_review_file_names_each_row_once_with_its_evidence():
    with open(data.FIELD_REVIEW) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    assert len(rows) == len({r["audit_id"] for r in rows}) == 16
    for r in rows:
        assert r["field"] in ("bedrooms", "baths") and r["evidence"], r
        assert r["corrected"] != r["recorded"], r
        if r["field"] == "baths":
            assert r["full_baths"] + 0.5 * r["half_baths"] == r["corrected"], r


def test_unit_labels_v3_joins_number_words_with_matching_bedrooms(monkeypatch):
    url = "https://streeteasy.com/building/{}/{}".format
    frame = pd.DataFrame(
        {
            "building": ["b", "b", "b", "b", "b"],
            "unit_id": ["u4", "uF", "u3", "uT", "u1"],
            "canonical_unit_url": [
                url("b", "4"),
                url("b", "four"),  # joins u4: both one-bedrooms
                url("b", "3fl"),
                url("b", "third-fl"),  # joins u3
                url("b", "one"),  # no unit "1": left alone
            ],
            "bedrooms": [1.0, 1.0, 2.0, 2.0, 1.0],
        }
    )
    monkeypatch.setattr(data, "unit_aliases", lambda path=None: ())
    out = data.merge_word_labels(frame)
    assert out.unit_id.tolist() == ["u4", "u4", "u3", "u3", "u1"]
    frame.loc[1, "bedrooms"] = 2.0  # "four" a two-bedroom: not the same apartment
    assert data.merge_word_labels(frame).unit_id.tolist()[:2] == ["u4", "uF"]


def test_a_held_out_row_without_a_training_building_moves_to_training():
    frame = pd.DataFrame(
        {
            "building": ["a", "a", "b"],
            "unit_id": ["a1", "a1", "b1"],
            "audit_id": ["1", "2", "3"],
        }
    )
    _, held = data.apply_rules(frame, np.array([True, False, True]), [])
    assert held.tolist() == [True, False, False]


def test_unit_labels_v5_adds_greenwich_villages_alias_groups():
    """v5 is v3 on the West Village table with Greenwich Village's appended."""
    rule = data.DATA_RULES["unit-labels-v5"]
    assert rule.func is data.merge_word_labels
    assert rule.keywords == {"aliases": data.UNIT_ALIASES_GV}
    assert data.RULE_SOURCES["unit-labels-v5"] == data.UNIT_ALIASES_GV
    assert "unit-labels-v5" not in data.DROPPING_RULES
    wv = set(data.unit_aliases())
    both = set(data.unit_aliases(data.UNIT_ALIASES_GV))
    assert wv < both and len(both - wv) == 136


def test_unit_labels_v6_joins_history_pairs_when_bedrooms_agree(tmp_path):
    """A unit-page history pair joins two units of one building whose bedroom
    counts agree; pairs that disagree, cross buildings, name a unit not in
    the frame or lack bedrooms stay apart; a pair naming a unit v5 already
    merged joins through it; groups that share a unit become one, with the
    smallest id."""
    url = "https://streeteasy.com/building/{}/{}".format
    frame = pd.DataFrame(
        {
            "building": ["b1"] * 5 + ["b2"] + ["b1"] * 3,
            "canonical_unit_url": [
                url("b1", "3"),
                url("b1", "3f"),
                url("b1", "three-a"),
                url("b1", "5"),
                url("b1", "5r"),
                url("b2", "3"),
                url("b1", "07"),
                url("b1", "7"),
                url("b1", "7r"),
            ],
            "unit_id": ["u1", "u2", "u3", "u4", "u5", "u6", "u7", "u8", "u9"],
            "bedrooms": [1.0, 1.0, 1.0, 2.0, 3.0, 1.0, 2.0, 2.0, np.nan],
        }
    )
    pairs = tmp_path / "pairs.jsonl"
    pairs.write_text(
        "".join(
            json.dumps({"unit_id": a, "other_unit_id": b}) + "\n"
            for a, b in [
                ("u2", "u3"),
                ("u1", "u2"),
                ("u4", "u5"),
                ("u1", "u6"),
                ("u8", "u4"),
                ("u1", "u99"),
                ("u9", "u7"),
            ]
        )
    )
    out = data.merge_history_pairs(frame, pairs)
    # "07" and "7" are one unit under v5 (u7); the pair names u8 and joins u4.
    assert out.unit_id.tolist() == ["u1", "u1", "u1", "u4", "u5", "u6"] + ["u4"] * 2 + [
        "u9"
    ]
    assert data.DATA_RULES["unit-labels-v6"] is data.merge_history_pairs
    assert data.RULE_SOURCES["unit-labels-v6"] == data.UNIT_HISTORY_PAIRS
    assert "unit-labels-v6" not in data.DROPPING_RULES


def test_unit_labels_v8_joins_letter_first_labels_to_digit_first_twins(tmp_path):
    """v8 is v6 plus swaps: "C7" joins "7C" and "d-4" joins "4D" in the same
    building when bedroom counts agree; a disagreeing pair, another building's
    twin, and labels with no twin or no bedroom counts stay apart; a history
    pair and a swap chain into one unit with the smallest id."""
    url = "https://streeteasy.com/building/{}/{}".format
    frame = pd.DataFrame(
        {
            "building": ["b1"] * 7 + ["b2"] * 3,
            "canonical_unit_url": [
                url("b1", "7c"),
                url("b1", "c7"),
                url("b1", "4d"),
                url("b1", "d-4"),
                url("b1", "a2"),
                url("b1", "2b"),
                url("b1", "9"),
                url("b2", "b2"),
                url("b2", "e5"),
                url("b2", "5e"),
            ],
            "unit_id": ["u3", "u2", "u4", "u5", "u6", "u7", "u1", "u8", "u9", "u10"],
            "bedrooms": [1.0, 1.0, 2.0, 1.0, 1.0, 1.0, 1.0, 1.0, np.nan, np.nan],
        }
    )
    pairs = tmp_path / "pairs.jsonl"
    pairs.write_text(json.dumps({"unit_id": "u1", "other_unit_id": "u3"}) + "\n")
    rule = functools.partial(
        data.merge_swapped_labels,
        base=functools.partial(data.merge_history_pairs, pairs=pairs),
    )
    out = rule(frame)
    assert out.unit_id.tolist() == [
        "u1",
        "u1",
        "u4",
        "u5",
        "u6",
        "u7",
        "u1",
        "u8",
        "u9",
        "u10",
    ]
    assert data.DATA_RULES["unit-labels-v8"] is data.merge_swapped_labels
    assert "unit-labels-v8" not in data.DROPPING_RULES
    assert data.RULE_SOURCES["unit-labels-v8"] == data.UNIT_HISTORY_PAIRS


def test_unit_splits_v1_splits_a_history_where_bedrooms_jump_by_two():
    """A listing two or more bedrooms from the unit's previous listing starts a
    new unit; a change of one, another capture of the same ad and other units
    leave ids alone; a later jump starts a third piece; an ad with no count
    neither splits nor hides the count before it."""
    frame = pd.DataFrame(
        {
            "unit_id": ["u1"] * 7 + ["u2", "u2", "u3", "u3"],
            "source_listing_id": [1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            "price_at": [
                "2020-01-01",
                "2020-02-01",
                "2021-01-01",  # 1 -> 2 bedrooms: same unit
                "2022-01-01",  # 2 -> 4: new unit
                "2023-01-01",  # 4 -> 1 bedroom: third piece
                "2024-01-01",  # no count: never splits
                "2025-01-01",  # 1 -> (none) -> 4: a fourth piece
                "2020-01-01",
                "2021-01-01",
                "2021-01-01",
                "2020-01-01",  # u3 rows out of date order
            ],
            "bedrooms": [1.0, 3.0, 2.0, 4.0, 1.0, np.nan, 4.0, 0.0, 1.0, 3.0, 1.0],
        }
    )
    out = data.DATA_RULES["unit-splits-v1"](frame)
    assert out.unit_id.tolist() == [
        "u1",
        "u1",  # a second capture of ad 1 is never compared with ad 1
        "u1",
        "u1~1",
        "u1~2",
        "u1~2",
        "u1~3",
        "u2",
        "u2",
        "u3~1",
        "u3",
    ]
    assert out.drop(columns="unit_id").equals(frame.drop(columns="unit_id"))


def test_unit_splits_v1_keeps_an_ad_whole_and_breaks_ties_by_listing():
    """An ad seen again after a jump stays in its first piece, and ads of one
    date are taken in listing-id order whatever the row order."""
    frame = pd.DataFrame(
        {
            "unit_id": ["u1"] * 3 + ["u2"] * 3,
            "source_listing_id": [1, 2, 1, 5, 7, 6],
            "price_at": ["2020-01-01", "2021-01-01", "2022-01-01"]
            + ["2020-01-01", "2021-01-01", "2021-01-01"],
            "bedrooms": [1.0, 3.0, 1.0, 1.0, 1.0, 3.0],
        }
    )
    rule = data.DATA_RULES["unit-splits-v1"]
    assert rule(frame).unit_id.tolist() == ["u1", "u1~1", "u1", "u2", "u2~2", "u2~1"]
    flipped = frame.iloc[::-1]
    assert rule(flipped).unit_id.tolist() == rule(frame).unit_id.tolist()[::-1]


def test_unit_splits_v2_splits_at_any_change_of_bedrooms():
    frame = pd.DataFrame(
        {
            "unit_id": ["u1"] * 4,
            "source_listing_id": [1, 2, 3, 4],
            "price_at": ["2020-01-01", "2021-01-01", "2022-01-01", "2023-01-01"],
            "bedrooms": [1.0, 1.0, 2.0, 0.0],
        }
    )
    out = data.DATA_RULES["unit-splits-v2"](frame)
    assert out.unit_id.tolist() == ["u1", "u1", "u1~1", "u1~2"]


def test_unit_splits_v3_rejoins_an_earlier_bedroom_count():
    frame = pd.DataFrame(
        {
            "unit_id": ["u1"] * 5,
            "source_listing_id": [1, 2, 3, 4, 5],
            "price_at": [f"{y}-01-01" for y in range(2020, 2025)],
            "bedrooms": [1.0, 2.0, np.nan, 1.0, 3.0],
        }
    )
    out = data.DATA_RULES["unit-splits-v3"](frame)
    assert out.unit_id.tolist() == ["u1", "u1~1", "u1~1", "u1", "u1~2"]
    v2 = data.DATA_RULES["unit-splits-v2"](frame)
    assert v2.unit_id.tolist() == ["u1", "u1~1", "u1~1", "u1~2", "u1~3"]


def test_unit_splits_v3_keeps_an_ad_whole_and_resets_per_unit():
    """Every row of an ad lands in one piece, and a second unit starts fresh."""
    frame = pd.DataFrame(
        {
            "unit_id": ["u1"] * 5 + ["u2"] * 2,
            "source_listing_id": [1, 2, 2, 3, 3, 4, 5],
            "price_at": [
                "2020-01-01",
                "2021-01-01",
                "2021-06-01",
                "2022-01-01",
                "2022-06-01",
                "2020-01-01",
                "2021-01-01",
            ],
            "bedrooms": [1.0, 2.0, 2.0, 1.0, 1.0, 2.0, 1.0],
        }
    )
    out = data.DATA_RULES["unit-splits-v3"](frame)
    assert out.unit_id.tolist() == ["u1", "u1~1", "u1~1", "u1", "u1", "u2", "u2~1"]


def test_unit_splits_v4_holds_a_change_that_adds_square_footage():
    """A one-bedroom change splits under v4 unless the earlier ad had no square
    footage and the new one has; a two-bedroom change still splits."""
    frame = pd.DataFrame(
        {
            "unit_id": ["u1"] * 3 + ["u2"] * 2 + ["u3"] * 2,
            "source_listing_id": [1, 2, 3, 4, 5, 6, 7],
            "price_at": [
                f"{y}-01-01" for y in (2015, 2017, 2020, 2015, 2017, 2015, 2017)
            ],
            "bedrooms": [1.0, 2.0, 0.0, 2.0, 1.0, 1.0, 3.0],
            "square_feet": [np.nan, 1600.0, np.nan, 900.0, np.nan, np.nan, 1600.0],
        }
    )
    out = data.DATA_RULES["unit-splits-v4"](frame)
    assert out.unit_id.tolist() == ["u1", "u1", "u1~1", "u2", "u2~1", "u3", "u3~1"]
    v3 = data.DATA_RULES["unit-splits-v3"](frame)
    assert v3.unit_id.tolist() == ["u1", "u1~1", "u1~2", "u2", "u2~1", "u3", "u3~1"]


def test_unit_splits_rules_must_come_last():
    frame = pd.DataFrame({"building": ["b"], "unit_id": ["u"]})
    with pytest.raises(ValueError, match="must come last"):
        data.apply_rules(frame, np.zeros(1, bool), ["unit-splits-v1", "unit-labels-v8"])


def test_unit_labels_v9_joins_number_word_letter_labels_to_their_twins(tmp_path):
    """v9 is v8 plus number words with a letter: "fourb" joins "4B", "five-a"
    joins "5a" and "eleven" joins "11" when bedroom counts agree; "fourth"
    reads as 4, not "four" and "th"; a disagreeing pair, another building's
    twin, a word with no twin and a word with three letters stay apart; a
    history pair and a word join chain into one unit with the smallest id."""
    url = "https://streeteasy.com/building/{}/{}".format
    frame = pd.DataFrame(
        {
            "building": ["b1"] * 10 + ["b2"] * 2,
            "canonical_unit_url": [
                url("b1", "fourb"),
                url("b1", "4b"),
                url("b1", "five-a"),
                url("b1", "5a"),
                url("b1", "eleven"),
                url("b1", "11"),
                url("b1", "sixc"),
                url("b1", "6c"),
                url("b1", "fourth"),
                url("b1", "tenant"),
                url("b2", "4b"),
                url("b2", "twod"),
            ],
            "unit_id": [f"u{i}" for i in [4, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]],
            "bedrooms": [1.0, 1.0, 2.0, 2.0, 0.0, 0.0, 1.0, 2.0, 1.0, 1.0, 1.0, 1.0],
        }
    )
    pairs = tmp_path / "pairs.jsonl"
    pairs.write_text(json.dumps({"unit_id": "u1", "other_unit_id": "u3"}) + "\n")
    frame.loc[len(frame)] = ["b1", url("b1", "7"), "u1", 1.0]
    frame.loc[len(frame)] = ["b1", url("b1", "4th"), "u15", 1.0]
    frame.loc[len(frame)] = ["b1", url("b1", "10ant"), "u16", 1.0]
    base = functools.partial(
        data.merge_swapped_labels,
        base=functools.partial(data.merge_history_pairs, pairs=pairs),
    )
    out = data.merge_word_letter_labels(frame, base=base)
    assert out.unit_id.tolist() == [
        "u1",
        "u1",
        "u5",
        "u5",
        "u7",
        "u7",
        "u9",
        "u10",
        "u11",
        "u12",
        "u13",
        "u14",
        "u1",
        "u15",
        "u16",
    ]
    assert data.DATA_RULES["unit-labels-v9"] is data.merge_word_letter_labels
    assert "unit-labels-v9" not in data.DROPPING_RULES
    assert data.RULE_SOURCES["unit-labels-v9"] == data.UNIT_HISTORY_PAIRS


def test_unit_labels_v11_is_v9_on_the_tables_with_flatiron_gramercys_appended():
    """v11 reads the alias table and history pairs that start with the files
    v5 to v9 read, line for line, and add Flatiron + Gramercy Park's; on a
    frame of other neighbourhoods' units it joins what v9 joins."""
    for old, new in (
        (data.UNIT_ALIASES_GV, data.UNIT_ALIASES_FGP),
        (data.UNIT_HISTORY_PAIRS, data.UNIT_HISTORY_PAIRS_FGP),
    ):
        before, after = old.read_text(), new.read_text()
        assert after.startswith(before) and len(after) > len(before)
    gv, fgp = (
        set(data.unit_aliases(data.UNIT_ALIASES_GV)),
        set(data.unit_aliases(data.UNIT_ALIASES_FGP)),
    )
    assert gv < fgp and len(fgp - gv) == 522
    assert data.RULE_SOURCES["unit-labels-v11"] == data.UNIT_ALIASES_FGP
    assert "unit-labels-v11" not in data.DROPPING_RULES
    url = "https://streeteasy.com/building/{}/{}".format
    group = next(iter(fgp - gv))
    frame = pd.DataFrame(
        {
            "building": ["b1"] * 4 + ["b2"] * 2,
            "canonical_unit_url": [
                url("b1", "fourb"),
                url("b1", "4b"),
                url("b1", "c7"),
                url("b1", "7c"),
                url("b2", "2a"),
                url("b2", "2b"),
            ],
            "unit_id": ["u4", "u3", "u5", "u6", group[0], group[1]],
            "bedrooms": [1.0, 1.0, 2.0, 2.0, 1.0, 1.0],
        }
    )
    v9 = data.DATA_RULES["unit-labels-v9"](frame)
    v11 = data.DATA_RULES["unit-labels-v11"](frame)
    assert (
        v11.unit_id.tolist()[:4]
        == v9.unit_id.tolist()[:4]
        == [
            "u3",
            "u3",
            "u5",
            "u5",
        ]
    )
    assert v9.unit_id.iat[4] != v9.unit_id.iat[5]
    assert v11.unit_id.iat[4] == v11.unit_id.iat[5] == min(group[:2])


def test_unit_reviews_v1_joins_each_reviewed_group(tmp_path):
    """A reviewed group's units take the group's smallest unit id, whatever
    spelling the label has; other labels and other buildings keep theirs."""
    url = "https://streeteasy.com/building/{}/{}".format
    frame = pd.DataFrame(
        {
            "building": ["b1"] * 4 + ["b2"],
            "canonical_unit_url": [
                url("b1", "5r"),
                url("b1", "5-B"),
                url("b1", "5f"),
                url("b1", "5"),
                url("b2", "5b"),
            ],
            "unit_id": ["u3", "u2", "u1", "u4", "u0"],
        }
    )
    joins = tmp_path / "joins.jsonl"
    joins.write_text(json.dumps({"building": "b1", "unit_labels": ["5R", "5B"]}))
    out = data.join_reviewed_units(frame, joins)
    assert out.unit_id.tolist() == ["u2", "u2", "u1", "u4", "u0"]
    assert data.DATA_RULES["unit-reviews-v1"] is data.join_reviewed_units
    assert "unit-reviews-v1" not in data.DROPPING_RULES


def test_unit_reviews_v1_amended_with_21_west_12th_rear():
    """unit-reviews-v1 amended in place (2026-10-11): the list is the first one
    with 21 West 12th Street's 2, 2B, 2F and 2R appended, which become one unit.
    A run that recorded the first list rebuilds with it, under the alias rule;
    a new run gets the amended list; the alias is never a current rule."""
    old = data.UNIT_JOINS_20261007.read_text().splitlines()
    now = data.UNIT_JOINS.read_text().splitlines()
    assert now[: len(old)] == old and len(now) == len(old) + 1
    added = json.loads(now[-1])
    assert added["building"] == "21-west-12-street-new_york"
    assert sorted(added["unit_labels"]) == ["2", "2B", "2F", "2R"]

    def url(b, label):
        return f"https://streeteasy.com/building/{b}/{label}"

    b = "21-west-12-street-new_york"
    frame = pd.DataFrame(
        {
            "building": [b] * 6,
            "canonical_unit_url": [
                url(b, x) for x in ("2", "2b", "2f", "2r", "3b", "1b")
            ],
            "unit_id": ["u5", "u2", "u4", "u3", "u1", "u0"],
        }
    )
    out = data.DATA_RULES["unit-reviews-v1"](frame)
    assert out.unit_id.tolist() == ["u2", "u2", "u2", "u2", "u1", "u0"]
    alias = "unit-reviews-v1@20261007"
    before = data.DATA_RULES[alias](frame)
    assert before.unit_id.tolist() == frame.unit_id.tolist()

    def record(path):
        return {
            "data_rules": ["unit-labels-v15", "unit-reviews-v1"],
            "data_rule_sources": {
                "unit-labels-v15": {
                    "sha256": data.sha256(data.RULE_SOURCES["unit-labels-v15"])
                },
                "unit-reviews-v1": {"sha256": data.sha256(path)},
            },
        }

    old_run = record(data.UNIT_JOINS_20261007)
    assert old_run["data_rule_sources"]["unit-reviews-v1"]["sha256"] == (
        "a3f9630b57bd52019c7e0b5a190f835bf107a9da304f916659f5df2dd0bb66c2"
    )
    assert data.recorded_rules(old_run) == ("unit-labels-v15", alias)
    assert data.recorded_rules(record(data.UNIT_JOINS)) == (
        "unit-labels-v15",
        "unit-reviews-v1",
    )
    # Any other hash is still refused, and the alias cannot be recorded by name.
    other = record(data.UNIT_JOINS)
    other["data_rule_sources"]["unit-reviews-v1"]["sha256"] = "0" * 64
    with pytest.raises(SystemExit, match="differs"):
        data.recorded_rules(other)
    with pytest.raises(SystemExit, match="unknown"):
        data.recorded_rules({"data_rules": [alias], "data_rule_sources": {}})
    assert data.RULE_SOURCES["unit-reviews-v1"] == data.UNIT_JOINS
    assert {"unit-reviews-v1", alias}.isdisjoint(data.DROPPING_RULES)


def test_unit_reviews_v2_joins_as_v1_and_splits_reviewed_listings():
    """unit-reviews-v2 carries v1's join lines verbatim and splits each reviewed
    listing off its unit, keyed on building, unit id and listing; it is the
    current unit-reviews rule and drops nothing."""
    lines = data.UNIT_REVIEWS.read_text().splitlines()
    joins = [x for x in lines if json.loads(x)["action"] == "join_units"]
    assert joins == data.UNIT_JOINS.read_text().splitlines()
    splits = [json.loads(x) for x in lines if json.loads(x)["action"] != "join_units"]
    assert {s["action"] for s in splits} == {"split_listings"} and len(splits) == 4

    b = "110-west-26-street-new_york"
    p = "1-patchin-place-new_york"
    u = "unit:30dc8309-a93b-5a2f-b87f-b4c5949c650c"
    frame = pd.DataFrame(
        {
            "building": [b, b, p, p, p, "elsewhere"],
            "canonical_unit_url": [
                f"https://streeteasy.com/building/{b}/4r",
                f"https://streeteasy.com/building/{b}/4b",
                f"https://streeteasy.com/building/{p}/2",
                f"https://streeteasy.com/building/{p}/2",
                f"https://streeteasy.com/building/{p}/2",
                "https://streeteasy.com/building/elsewhere/2",
            ],
            "unit_id": ["u9", "u3", u, u, u, u],
            "source_listing_id": ["1", "2", "1398907", "3198355", "3233740", "3198355"],
        }
    )
    out = data.DATA_RULES["unit-reviews-v2"](frame)
    piece = f"{u}~review-3198355"
    assert out.unit_id.tolist() == ["u3", "u3", u, piece, piece, u]
    assert out.drop(columns="unit_id").equals(frame.drop(columns="unit_id"))
    assert data.RULE_SOURCES["unit-reviews-v2"] == data.UNIT_REVIEWS
    assert "unit-reviews-v2" not in data.DROPPING_RULES
    assert "unit-reviews-v2" in autoselect.current_rules()
    assert "unit-reviews-v1" not in autoselect.current_rules()


def test_quarantine_v6_is_v5_and_110_west_26th_bare_numbers():
    """v6 keeps all of v5's rows and adds 110 West 26th Street's five ads with a
    bare floor number."""
    v5 = data.quarantined(data.QUARANTINE_V5)
    v6 = data.quarantined(data.QUARANTINE_V6)
    assert v5 < v6 and len(v6 - v5) == 5
    with open(data.QUARANTINE_V6) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    added = [r for r in rows if r["audit_id"] in v6 - v5]
    assert {r["building"] for r in added} == {"110-west-26-street-new_york"}
    assert sorted(r["unit_label"] for r in added) == ["3", "3", "4", "5", "6"]
    assert "quarantine-v6" in data.DROPPING_RULES


def test_apply_rules_refuses_unit_reviews_before_unit_labels():
    frame = pd.DataFrame({"audit_id": ["a"], "unit_id": ["u"]})
    with pytest.raises(ValueError, match="unit-reviews"):
        data.apply_rules(
            frame, np.zeros(1, bool), ["unit-reviews-v1", "unit-labels-v9"]
        )


def test_dataset_nb5_splits_flatiron_gramercy_park_by_building():
    """DATASET_NB5 is DATASET_NB4 with Flatiron + Gramercy Park's rows named
    Flatiron or Gramercy Park."""
    complete = data.DATASET_NB5 / "complete.json"
    if not complete.exists():
        pytest.skip("five-neighbourhood dataset not on this machine")
    record = json.loads(complete.read_text())
    fgp = data.Path(record["parts"]["Flatiron + Gramercy Park"]["path"])
    split = json.loads((fgp / "complete.json").read_text())
    assert split["source"]["path"] == (
        "/data1/apartments/frontier/datasets/flatiron-gramercy-park-analysis-20261007-34b958d"
    )
    assert record["neighbourhoods"] == {
        "Chelsea": 52614,
        "West Village": 34205,
        "Greenwich Village": 18425,
        "Gramercy Park": 18333,
        "Flatiron": 12182,
    }


def test_dataset_nb4_is_the_current_dataset_plus_flatiron_gramercy_park():
    """DATASET_NB4 combines the Chelsea + West Village + Greenwich Village
    dataset (the current one until DATASET_NB5), unchanged, with Flatiron +
    Gramercy Park's rows, each named by its neighbourhood."""
    complete = data.DATASET_NB4 / "complete.json"
    if not complete.exists():
        pytest.skip("combined dataset not on this machine")
    record = json.loads(complete.read_text())
    paths = {p["path"] for p in record["parts"].values()}
    # The path itself: data.DATASET is now DATASET_NB5.
    current = (
        "/data1/apartments/frontier/datasets/chelsea-wv-gv-analysis-20261005-2d5b3b6"
    )
    assert current in paths
    assert record["neighbourhoods"]["Flatiron + Gramercy Park"] == 30515
    assert sum(record["neighbourhoods"].values()) == sum(record["rows"].values())


def test_ad_corrections_v3_keep_v2s_rows_and_values():
    import json

    def rows(path):
        with open(path) as f:
            return {r["audit_id"]: r["corrected"] for r in map(json.loads, f) if r}

    for v2, v3, missing in (
        (data.BEDROOM_CORRECTIONS_V2, data.BEDROOM_CORRECTIONS_V3, 1),
        (data.BATH_CORRECTIONS_V2, data.BATH_CORRECTIONS_V3, 0),
    ):
        old, new = rows(v2), rows(v3)
        # One v2 row has left the dataset since; the rest are kept as they were.
        assert len(set(old) - set(new)) == missing
        assert all(new[a] == c for a, c in old.items() if a in new)
    assert {"bedrooms-ad-v3", "baths-ad-v3"} <= set(data.RULE_SOURCES)


def test_quarantine_v7_is_v6_and_the_three_new_neighbourhoods():
    """v7 keeps all of v6's rows and adds 45, each with its quote and reason."""
    v6 = data.quarantined(data.QUARANTINE_V6)
    v7 = data.quarantined(data.QUARANTINE_V7)
    assert v6 < v7 and len(v7 - v6) == 45
    with open(data.QUARANTINE_V7) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    added = [r for r in rows if r["audit_id"] in v7 - v6]
    assert all(r["evidence"] and r["reason"] for r in added)
    assert {r["action"] for r in added} <= {r["action"] for r in rows[: len(v6)]}
    assert "quarantine-v7" in data.DROPPING_RULES


def test_quarantine_v8_is_v7_and_the_model_outliers_of_the_three():
    """v8 keeps v7's file as its first lines and adds 51, each with its quote
    and reason."""
    v7 = data.quarantined(data.QUARANTINE_V7)
    v8 = data.quarantined(data.QUARANTINE_V8)
    assert v7 < v8 and len(v8 - v7) == 51
    assert data.QUARANTINE_V8.read_text().startswith(data.QUARANTINE_V7.read_text())
    with open(data.QUARANTINE_V8) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    assert all(r["evidence"] and r["reason"] for r in rows[len(v7) :])
    assert "quarantine-v8" in data.DROPPING_RULES


def test_quarantine_v9_is_v6_and_rent_blind_text_checks():
    """v9 keeps v6's file as its first lines and adds 95, each with its quote
    and reason; it replaces v7 and v8, not extends them."""
    v6 = data.quarantined(data.QUARANTINE_V6)
    v9 = data.quarantined(data.QUARANTINE_V9)
    assert v6 < v9 and len(v9 - v6) == 95
    assert data.QUARANTINE_V9.read_text().startswith(data.QUARANTINE_V6.read_text())
    with open(data.QUARANTINE_V9) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    assert all(r["evidence"] and r["reason"] for r in rows[len(v6) :])
    assert not data.quarantined(data.QUARANTINE_V8) <= v9
    assert "quarantine-v9" in data.DROPPING_RULES


def test_quarantine_v10_is_rent_blind_only():
    """v10 is v9's 95 rows of the three and 124 Chelsea and West Village rows
    from the same checks, each with its quote and reason; it keeps none of
    v6's rows the checks don't reach."""
    v6 = data.quarantined(data.QUARANTINE_V6)
    v9 = data.quarantined(data.QUARANTINE_V9)
    v10 = data.quarantined(data.QUARANTINE_V10)
    assert len(v10) == 219 and v9 - v6 <= v10
    assert len(v10 & v6) == 91 and len(v10 - v9) == 124 - 91
    with open(data.QUARANTINE_V10) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    assert len(rows) == 219 and all(r["evidence"] and r["reason"] for r in rows)
    assert "quarantine-v10" in data.DROPPING_RULES


def test_unit_labels_v13_is_v11_on_the_tables_with_stuyvesant_towns_appended():
    """v13 reads the alias table and history pairs v11 reads, line for line,
    with Stuyvesant Town/PCV's added; on other neighbourhoods' units it joins
    what v11 joins, and it joins a Stuyvesant Town alias group."""
    for old, new in (
        (data.UNIT_ALIASES_FGP, data.UNIT_ALIASES_STUY),
        (data.UNIT_HISTORY_PAIRS_FGP, data.UNIT_HISTORY_PAIRS_STUY),
    ):
        before, after = old.read_text(), new.read_text()
        assert after.startswith(before) and len(after) > len(before)
    fgp, stuy = (
        set(data.unit_aliases(data.UNIT_ALIASES_FGP)),
        set(data.unit_aliases(data.UNIT_ALIASES_STUY)),
    )
    assert fgp < stuy and len(stuy - fgp) == 265
    assert data.RULE_SOURCES["unit-labels-v13"] == data.UNIT_ALIASES_STUY
    assert "unit-labels-v13" not in data.DROPPING_RULES
    url = "https://streeteasy.com/building/{}/{}".format
    group = next(iter(stuy - fgp))
    frame = pd.DataFrame(
        {
            "building": ["b1"] * 4 + ["b2"] * 2,
            "canonical_unit_url": [
                url("b1", "fourb"),
                url("b1", "4b"),
                url("b1", "c7"),
                url("b1", "7c"),
                url("b2", "2a"),
                url("b2", "2b"),
            ],
            "unit_id": ["u4", "u3", "u5", "u6", group[0], group[1]],
            "bedrooms": [1.0, 1.0, 2.0, 2.0, 1.0, 1.0],
        }
    )
    v11 = data.DATA_RULES["unit-labels-v11"](frame)
    v13 = data.DATA_RULES["unit-labels-v13"](frame)
    assert (
        v13.unit_id.tolist()[:4] == v11.unit_id.tolist()[:4] == ["u3", "u3", "u5", "u5"]
    )
    assert v11.unit_id.iat[4] != v11.unit_id.iat[5]
    assert v13.unit_id.iat[4] == v13.unit_id.iat[5] == min(group[:2])


def test_unit_labels_v14_is_v13_on_the_tables_with_nomads_appended():
    """v14 reads the alias table and history pairs v13 reads, line for line,
    with NoMad's added; on other neighbourhoods' units it joins what v13
    joins, and it joins a NoMad alias group."""
    for old, new in (
        (data.UNIT_ALIASES_STUY, data.UNIT_ALIASES_NOMAD),
        (data.UNIT_HISTORY_PAIRS_STUY, data.UNIT_HISTORY_PAIRS_NOMAD),
    ):
        before, after = old.read_text(), new.read_text()
        assert after.startswith(before) and len(after) > len(before)
    stuy, nomad = (
        set(data.unit_aliases(data.UNIT_ALIASES_STUY)),
        set(data.unit_aliases(data.UNIT_ALIASES_NOMAD)),
    )
    assert stuy < nomad and len(nomad - stuy) == 107
    assert data.RULE_SOURCES["unit-labels-v14"] == data.UNIT_ALIASES_NOMAD
    assert "unit-labels-v14" not in data.DROPPING_RULES
    url = "https://streeteasy.com/building/{}/{}".format
    group = next(iter(nomad - stuy))
    frame = pd.DataFrame(
        {
            "building": ["b1"] * 4 + ["b2"] * 2,
            "canonical_unit_url": [
                url("b1", "fourb"),
                url("b1", "4b"),
                url("b1", "c7"),
                url("b1", "7c"),
                url("b2", "2a"),
                url("b2", "2b"),
            ],
            "unit_id": ["u4", "u3", "u5", "u6", group[0], group[1]],
            "bedrooms": [1.0, 1.0, 2.0, 2.0, 1.0, 1.0],
        }
    )
    v13 = data.DATA_RULES["unit-labels-v13"](frame)
    v14 = data.DATA_RULES["unit-labels-v14"](frame)
    assert (
        v14.unit_id.tolist()[:4] == v13.unit_id.tolist()[:4] == ["u3", "u3", "u5", "u5"]
    )
    assert v13.unit_id.iat[4] != v13.unit_id.iat[5]
    assert v14.unit_id.iat[4] == v14.unit_id.iat[5] == min(group[:2])


def test_quarantine_v12_adds_the_new_neighbourhoods_to_v10():
    """v12 is v10's 219 rows and 50 more from the rent-blind checks over East
    Village, NoMad and Stuyvesant Town/PCV, each with its quote and reason, all
    among the rows read."""
    v10 = data.quarantined(data.QUARANTINE_V10)
    v12 = data.quarantined(data.QUARANTINE_V12)
    assert v10 < v12 and len(v12 - v10) == 50
    read = set(data.QUARANTINE_V12_READ.read_text().split())
    assert len(read) == 510 and v12 - v10 <= read
    with open(data.QUARANTINE_V12) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    assert len(rows) == 269 and all(r["evidence"] and r["reason"] for r in rows)
    assert "quarantine-v12" in data.DROPPING_RULES


def test_quarantine_v13_adds_two_read_price_screen_hits_to_v12():
    """v13 is v12's 269 rows and 2 more, both among the 11 price-screen hits
    read, each with its quote and reason."""
    v12 = data.quarantined(data.QUARANTINE_V12)
    v13 = data.quarantined(data.QUARANTINE_V13)
    assert v12 < v13 and len(v13 - v12) == 2
    read = set(data.QUARANTINE_V13_READ.read_text().split())
    assert len(read) == 11 and v13 - v12 <= read
    with open(data.QUARANTINE_V13) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    assert len(rows) == 271 and all(r["evidence"] and r["reason"] for r in rows)
    assert "quarantine-v13" in data.DROPPING_RULES


def test_quarantine_v14_adds_thirteen_read_shop_rows_to_v13():
    """v14 is v13's 271 rows and 13 more, all among the 693 screen hits read,
    each with its evidence and reason."""
    v13 = data.quarantined(data.QUARANTINE_V13)
    v14 = data.quarantined(data.QUARANTINE_V14)
    assert v13 < v14 and len(v14 - v13) == 13
    read = set(data.QUARANTINE_V14_READ.read_text().split())
    assert len(read) == 693 and v14 - v13 <= read
    with open(data.QUARANTINE_V14) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    assert len(rows) == 284 and all(r["evidence"] and r["reason"] for r in rows)
    assert "quarantine-v14" in data.DROPPING_RULES


def test_latest_ask_v2_prices_rows_from_the_file(monkeypatch, tmp_path):
    path = tmp_path / "latest-ask.parquet"
    pd.DataFrame({"audit_id": ["a", "b"], "latest_ask": [2900.0, 10000.0]}).to_parquet(
        path
    )
    monkeypatch.setattr(data, "LATEST_ASK", path)
    frame = pd.DataFrame(
        {
            "audit_id": ["a", "b", "c"],
            "asking_rent": [3000.0, 1000.0, 4000.0],
            "log_rent": np.log([3000.0, 1000.0, 4000.0]),
        }
    )
    out = data.DATA_RULES["latest-ask-v2"](frame)
    # A row the file lacks keeps its own ask.
    assert out.asking_rent.tolist() == [2900.0, 10000.0, 4000.0]
    np.testing.assert_allclose(out.log_rent, np.log(out.asking_rent))
    assert data.RULE_SOURCES["latest-ask-v2"].name == "latest-ask.parquet"


def test_latest_ask_v3_reads_its_own_file(tmp_path):
    path = tmp_path / "latest-ask.parquet"
    pd.DataFrame({"audit_id": ["a"], "latest_ask": [2900.0]}).to_parquet(path)
    frame = pd.DataFrame(
        {
            "audit_id": ["a", "c"],
            "asking_rent": [3000.0, 4000.0],
            "log_rent": np.log([3000.0, 4000.0]),
        }
    )
    out = data.latest_ask_v3(frame, path=path)
    assert out.asking_rent.tolist() == [2900.0, 4000.0]
    np.testing.assert_allclose(out.log_rent, np.log(out.asking_rent))
    assert data.RULE_SOURCES["latest-ask-v3"] == data.LATEST_ASK_V3
    assert data.DATA_RULES["latest-ask-v3"] is data.latest_ask_v3


def test_tune_westcoast_split_v1_splits_the_lot_by_label_scheme():
    url = "https://streeteasy.com/building/x/"
    frame = pd.DataFrame(
        {
            "building": ["the-west-coast"] * 6
            + ["97-horatio-street-new_york"] * 2
            + ["other"],
            "canonical_unit_url": [
                url + l
                for l in ("425", "007e", "7E", "phd", "6dd", "42", "712", "26", "4b")
            ],
        }
    )
    out = data.DATA_RULES["tune-westcoast-split-v1"](frame)
    letters, digits = data.WESTCOAST[1], data.WESTCOAST[0]
    assert out.building.tolist() == [
        digits,
        letters,
        letters,
        letters,
        letters,
        "the-west-coast",
        digits,
        "97-horatio-street-new_york",
        "other",
    ]
    assert data.amended_rule("tune-westcoast-split-v1") is False
    assert "tune-westcoast-split-v1".startswith(data.TUNING_PREFIX)


def test_unit_labels_v15_is_v14_on_the_tables_with_east_villages_appended():
    """v15 reads the alias table and history pairs v14 reads, line for line,
    with East Village's added; on other neighbourhoods' units it joins what v14
    joins, and it joins an East Village alias group."""
    for old, new in (
        (data.UNIT_ALIASES_NOMAD, data.UNIT_ALIASES_EV),
        (data.UNIT_HISTORY_PAIRS_NOMAD, data.UNIT_HISTORY_PAIRS_EV),
    ):
        before, after = old.read_text(), new.read_text()
        assert after.startswith(before) and len(after) > len(before)
    nomad, ev = (
        set(data.unit_aliases(data.UNIT_ALIASES_NOMAD)),
        set(data.unit_aliases(data.UNIT_ALIASES_EV)),
    )
    assert nomad < ev and len(ev - nomad) == 405
    assert data.RULE_SOURCES["unit-labels-v15"] == data.UNIT_ALIASES_EV
    assert "unit-labels-v15" not in data.DROPPING_RULES
    url = "https://streeteasy.com/building/{}/{}".format
    group = next(iter(ev - nomad))
    frame = pd.DataFrame(
        {
            "building": ["b1"] * 4 + ["b2"] * 2,
            "canonical_unit_url": [
                url("b1", "fourb"),
                url("b1", "4b"),
                url("b1", "c7"),
                url("b1", "7c"),
                url("b2", "2a"),
                url("b2", "2b"),
            ],
            "unit_id": ["u4", "u3", "u5", "u6", group[0], group[1]],
            "bedrooms": [1.0, 1.0, 2.0, 2.0, 1.0, 1.0],
        }
    )
    v14 = data.DATA_RULES["unit-labels-v14"](frame)
    v15 = data.DATA_RULES["unit-labels-v15"](frame)
    assert (
        v15.unit_id.tolist()[:4] == v14.unit_id.tolist()[:4] == ["u3", "u3", "u5", "u5"]
    )
    assert v14.unit_id.iat[4] != v14.unit_id.iat[5]
    assert v15.unit_id.iat[4] == v15.unit_id.iat[5] == min(group[:2])


def test_spelled_label_key_shortens_spelled_out_labels():
    cases = {
        "3RD-FL": "3", "3FL": "3", "third": "3", "THREE-FL": "3", "2W-FL": "2W",
        "4-REAR": "4R", "4BACK": "4R", "2FRONT": "2F", "PENTHOUSE-A": "PHA",
        "GARDEN": "G", "GDN": "G", "GROUND": "G", "PARLOUR": "PARLOR",
        "PARLOR-FL": "PARLOR", "4B": "4B", "PH4": "PH4",
    }  # fmt: skip
    assert {k: data.spelled_label_key(k) for k in cases} == cases


def test_unit_labels_v16_joins_spelled_out_labels_where_bedrooms_agree():
    """A spelled-out label joins its short spelling when both units' median
    bedrooms agree, and not otherwise."""
    url = "https://streeteasy.com/building/{}/{}".format
    frame = pd.DataFrame(
        {
            "building": ["b1"] * 4 + ["b2"] * 2,
            "canonical_unit_url": [
                url("b1", "3rd-fl"),
                url("b1", "3"),
                url("b1", "penthouse-a"),
                url("b1", "pha"),
                url("b2", "garden"),
                url("b2", "g"),
            ],
            "unit_id": ["u9", "u8", "u7", "u6", "h1", "h0"],
            "bedrooms": [1.0, 1.0, 3.0, 2.0, 1.0, float("nan")],
        }
    )
    out = data.merge_spelled_labels(frame, base=pd.DataFrame.copy)
    # Bedrooms agree; bedrooms differ; one unit has no bedroom count.
    assert out.unit_id.tolist() == ["u8", "u8", "u7", "u6", "h1", "h0"]
    v16 = data.DATA_RULES["unit-labels-v16"]
    assert v16.func is data.merge_spelled_labels
    assert data.RULE_SOURCES["unit-labels-v16"] == data.UNIT_ALIASES_EV
    assert "unit-labels-v16" not in data.DROPPING_RULES
    v15 = data.DATA_RULES["unit-labels-v15"](frame)
    assert v16(frame).unit_id.tolist()[:2] == ["u8", "u8"]
    assert v15.unit_id.tolist()[:2] == ["u9", "u8"]


def test_unit_labels_v17_is_v16_on_the_tables_with_midtown_wests_appended():
    """v17 reads v16's alias table and history pairs, line for line, with
    Midtown West's added; on other neighbourhoods' units it joins what v16
    joins, and it joins a Midtown West alias group."""
    for old, new in (
        (data.UNIT_ALIASES_EV, data.UNIT_ALIASES_MW),
        (data.UNIT_HISTORY_PAIRS_EV, data.UNIT_HISTORY_PAIRS_MW),
    ):
        before, after = old.read_text(), new.read_text()
        assert after.startswith(before) and len(after) > len(before)
    ev, mw = (
        set(data.unit_aliases(data.UNIT_ALIASES_EV)),
        set(data.unit_aliases(data.UNIT_ALIASES_MW)),
    )
    assert ev < mw and len(mw - ev) == 833
    assert data.RULE_SOURCES["unit-labels-v17"] == data.UNIT_ALIASES_MW
    assert "unit-labels-v17" not in data.DROPPING_RULES
    url = "https://streeteasy.com/building/{}/{}".format
    group = next(iter(mw - ev))
    frame = pd.DataFrame(
        {
            "building": ["b1"] * 4 + ["b2"] * 2,
            "canonical_unit_url": [
                url("b1", "3rd-fl"),
                url("b1", "3"),
                url("b1", "c7"),
                url("b1", "7c"),
                url("b2", "2a"),
                url("b2", "2b"),
            ],
            "unit_id": ["u4", "u3", "u5", "u6", group[0], group[1]],
            "bedrooms": [1.0, 1.0, 2.0, 2.0, 1.0, 1.0],
        }
    )
    v16 = data.DATA_RULES["unit-labels-v16"](frame)
    v17 = data.DATA_RULES["unit-labels-v17"](frame)
    assert (
        v17.unit_id.tolist()[:4] == v16.unit_id.tolist()[:4] == ["u3", "u3", "u5", "u5"]
    )
    assert v16.unit_id.iat[4] != v16.unit_id.iat[5]
    assert v17.unit_id.iat[4] == v17.unit_id.iat[5] == min(group[:2])


def test_quarantine_v15_adds_two_read_midtown_west_rows_to_v14():
    """v15 is v14's 284 rows and 2 more, both among the 4 screen hits read,
    each with its evidence and reason."""
    v14 = data.quarantined(data.QUARANTINE_V14)
    v15 = data.quarantined(data.QUARANTINE_V15)
    assert v14 < v15 and len(v15 - v14) == 2
    read = set(data.QUARANTINE_V15_READ.read_text().split())
    assert len(read) == 4 and v15 - v14 <= read
    with open(data.QUARANTINE_V15) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    assert len(rows) == 286 and all(r["evidence"] and r["reason"] for r in rows)
    assert data.QUARANTINE_V14.read_text() in data.QUARANTINE_V15.read_text()
    assert "quarantine-v15" in data.DROPPING_RULES


def test_quarantine_v16_adds_33_read_rows_to_v15():
    """v16 is v15's 286 rows and 33 more, all among the 44 rows read: 28 of
    the screen's 39 hits and the five asks at 110 W 26th St."""
    v15 = data.quarantined(data.QUARANTINE_V15)
    v16 = data.quarantined(data.QUARANTINE_V16)
    assert v15 < v16 and len(v16 - v15) == 33
    read = set(data.QUARANTINE_V16_READ.read_text().split())
    assert len(read) == 44 and v16 - v15 <= read
    with open(data.QUARANTINE_V16) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    assert len(rows) == 319 and all(r["evidence"] and r["reason"] for r in rows)
    assert sum(r["building"] == "110-west-26-street-new_york" for r in rows) == 5
    assert data.QUARANTINE_V15.read_text() in data.QUARANTINE_V16.read_text()
    assert "quarantine-v16" in data.DROPPING_RULES


def test_quarantine_v17_adds_brooklyn_rows_to_v16():
    """v17 is v16 with seven more Brooklyn rows; every Brooklyn row carries
    `brooklyn_misjoin` and has an entry in the misjoin file."""
    v16 = data.quarantined(data.QUARANTINE_V16)
    v17 = data.quarantined(data.QUARANTINE_V17)
    with open(brooklyn.MISJOINS) as f:
        misjoins = {
            r["audit_id"]
            for r in map(json.loads, filter(str.strip, f))
            if r["review"] == "2026-10-14"
        }
    assert len(misjoins) == 35 and len(misjoins - v16) == 7
    assert v17 == v16 | misjoins and len(v17) == 326
    read = set(data.QUARANTINE_V16_READ.read_text().split())
    read |= set(data.QUARANTINE_V17_READ.read_text().split())
    assert misjoins <= read
    with open(data.QUARANTINE_V17) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    assert all(r["evidence"] and r["reason"] for r in rows)
    assert {
        r["audit_id"] for r in rows if r["action"] == "brooklyn_misjoin"
    } == misjoins
    with open(data.QUARANTINE_V16) as f:
        rows16 = {r["audit_id"]: r for r in map(json.loads, f)}
    assert all(
        r == rows16[r["audit_id"]] for r in rows if r["audit_id"] not in misjoins
    )
    assert "quarantine-v17" in data.DROPPING_RULES


def test_quarantine_v18_changes_only_the_110_w_26th_reasons():
    """v18 holds out v17's rows; only the five 110 W 26th St rows differ,
    and they move from a location conflict to product scope."""
    with open(data.QUARANTINE_V17) as f:
        v17 = {r["audit_id"]: r for r in map(json.loads, f)}
    with open(data.QUARANTINE_V18) as f:
        v18 = {r["audit_id"]: r for r in map(json.loads, f)}
    assert v18.keys() == v17.keys() and len(v18) == 326
    changed = {a for a in v18 if v18[a] != v17[a]}
    assert len(changed) == 5
    assert all(
        v18[a]["building"] == "110-west-26-street-new_york"
        and v17[a]["action"] == "quarantine_location_conflict"
        and v18[a]["action"] == "quarantine_product_scope"
        and v18[a]["evidence"]
        for a in changed
    )
    assert "quarantine-v18" in data.DROPPING_RULES


def test_brooklyn_misjoins_record_the_evidence_for_a_remap():
    with open(brooklyn.MISJOINS) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    for r in rows:
        assert r["source_listing_id"] and r["building"] and r["unit_id"]
        assert r["streeteasy_address"] and r["ad_phrase"] in r["ad_context"]
        assert r["candidate_brooklyn_address"] or r["note"]


def test_brooklyn_screen_skips_known_false_alarms():
    frame = pd.DataFrame(
        {
            "audit_id": list("abcdef"),
            "source_listing_id": list("123456"),
            "building": ["b"] * 6,
            "unit_id": ["u"] * 6,
            "neighbourhood": ["Gramercy Park"] * 5 + ["Hell's Kitchen"],
            "price_at": ["2020-01-01"] * 6,
        }
    )
    text = pd.Series(
        [
            "sunny one bedroom steps from prospect park",
            "art deco studio in kensington house on 7th avenue",
            "broker: 184 noll street suite 2 brooklyn ny 11237",
            "i also have studios with terraces in park slope",
            "quiet one bedroom on a gorgeous clinton hill block",
            "a prime clinton hill location near 9th avenue",
        ]
    )
    hits = brooklyn.screen(frame, text)
    assert hits.audit_id.tolist() == ["a", "e"]


def test_brooklyn_screen_finds_bare_ditmas_park_and_cortelyou_wording():
    frame = pd.DataFrame(
        {
            "audit_id": list("abcd"),
            "source_listing_id": list("1234"),
            "building": ["b"] * 4,
            "unit_id": ["u"] * 4,
            "neighbourhood": ["Gramercy Park"] * 3 + ["Hell's Kitchen"],
            "price_at": ["2020-01-01"] * 4,
        }
    )
    text = pd.Series(
        [
            "welcome to 319 east 19th st ditmas park - luxury building",
            "one block from the best restaurants at cortelyou road",
            "the hottest area of prospect park south!!!",
            "the midtown west / hell's kitchen / clinton hill area",
        ]
    )
    assert brooklyn.screen(frame, text).audit_id.tolist() == ["a", "b", "c"]


def test_every_registered_dataset_is_screened_for_brooklyn_ads():
    """Registering a dataset newer than NB8 means running
    `frontier/scripts/brooklyn_screen.py` on it and adding its cohort to
    `brooklyn.SCREENED`."""
    screened = set(brooklyn.SCREENED.read_text().split())
    for name in dir(data):
        m = re.fullmatch(r"DATASET_NB(\d+)", name)
        if m and int(m[1]) >= 9:
            assert getattr(data, name).name in screened, name


def test_tune_westcoast_split_v2_swaps_v1s_names():
    """v2 sends each scheme to the other name: floor-and-letter rows to the
    taller BIN's the-west-coast, three-digit rows to 97-horatio."""
    url = "https://streeteasy.com/building/x/"
    frame = pd.DataFrame(
        {
            "building": ["the-west-coast"] * 4
            + ["97-horatio-street-new_york"] * 2
            + ["other"],
            "canonical_unit_url": [
                url + l for l in ("425", "007e", "phd", "42", "7E", "712", "4b")
            ],
        }
    )
    out = data.DATA_RULES["tune-westcoast-split-v2"](frame)
    assert out.building.tolist() == [
        "97-horatio-street-new_york",
        "the-west-coast",
        "the-west-coast",
        "the-west-coast",
        "the-west-coast",
        "97-horatio-street-new_york",
        "other",
    ]
    v1 = data.DATA_RULES["tune-westcoast-split-v1"](frame)
    lot = frame.building.isin(data.WESTCOAST) & ~frame.canonical_unit_url.str.endswith(
        "/42"
    )
    assert (out.building[lot] != v1.building[lot]).all()
    assert "tune-westcoast-split-v2".startswith(data.TUNING_PREFIX)


def test_building_joins_v1_folds_97_horatio_before_the_wing_split():
    url = "https://streeteasy.com/building/x/"
    frame = pd.DataFrame(
        {
            "building": ["97-horatio-street-new_york"] * 3
            + ["the-west-coast", "other"],
            "canonical_unit_url": [url + l for l in ("7e", "712", "26", "425", "4b")],
        }
    )
    out = data.DATA_RULES["building-joins-v1"](frame)
    assert out.building.tolist() == ["the-west-coast"] * 4 + ["other"]
    held = np.zeros(len(frame), dtype=bool)
    rules = ("building-joins-v1", "tune-westcoast-split-v2")
    split, _ = data.apply_rules(frame, held, rules)
    assert split.building.tolist() == [
        "the-west-coast",
        "97-horatio-street-new_york",
        "the-west-coast",
        "97-horatio-street-new_york",
        "other",
    ]
    with pytest.raises(ValueError, match="must precede"):
        data.apply_rules(frame, held, rules[::-1])
    assert autoselect._rule_order(rules[0]) < autoselect._rule_order(rules[1])
    assert not data.amended_rule("building-joins-v1")


def test_west_coast_wings_v1_moves_three_digit_labels_to_the_west_wing():
    url = "https://streeteasy.com/building/x/"
    frame = pd.DataFrame(
        {
            "building": ["97-horatio-street-new_york"] * 2
            + ["the-west-coast"] * 5
            + ["other"],
            "canonical_unit_url": [
                url + l for l in ("712", "7e", "425", "9L", "phd", "26", "1234", "425")
            ],
        }
    )
    held = np.zeros(len(frame), dtype=bool)
    rules = ("building-joins-v1", "west-coast-wings-v1")
    out, _ = data.apply_rules(frame, held, rules)
    west, main = data.WESTCOAST_WEST_WING, data.WESTCOAST[0]
    assert out.building.tolist() == [west, main, west, main, main, main, main, "other"]
    with pytest.raises(ValueError, match="must precede"):
        data.apply_rules(frame, held, rules[::-1])
    with pytest.raises(ValueError, match="must precede unit-labels"):
        data.apply_rules(frame, held, ("unit-labels-v17", "west-coast-wings-v1"))
    assert autoselect._rule_order(rules[0]) < autoselect._rule_order(rules[1])
    assert autoselect._rule_order(rules[1]) < autoselect._rule_order("unit-labels-v17")
    assert "west-coast-wings-v1" in autoselect.current_rules()


def test_elevator_from_ad_v1_fills_unknowns_only(tmp_path, monkeypatch):
    assert data.RULE_SOURCES["elevator-from-ad-v1"] == data.ELEVATOR_FROM_AD
    path = tmp_path / "elevator.parquet"
    pd.DataFrame(
        {"audit_id": ["a", "b", "c", "d"], "elevator": ["no", "yes", "no", "yes"]}
    ).to_parquet(path)
    monkeypatch.setattr(data, "ELEVATOR_FROM_AD", path)
    frame = pd.DataFrame(
        {
            "audit_id": ["a", "b", "c", "d", "e"],
            "elevator": ["unknown", "unknown", "yes", "no", "unknown"],
        }
    )
    out = data.DATA_RULES["elevator-from-ad-v1"](frame)
    assert out.elevator.tolist() == ["no", "yes", "yes", "no", "unknown"]
    assert not data.amended_rule("elevator-from-ad-v1")


def test_adfills_elevator_reads_one_class_per_ad():
    from rentfrontier import adfills

    text = pd.Series(
        [
            "Charming walk-up, 3 flights up.",
            "Elevator building with a doorman.",
            "The building does not have an elevator.",
            "No elevator; the elevator next door is not ours.",
            "Sunny one bedroom.",
            None,
            "There is no laundry or elevator in the building.",
            "A no-elevator building.",
            "Elevator building, a short walk up to Astor Place.",
            "First floor, so no stairs to walk up. Elevator in lobby.",
            "Elevator building. Private roof deck one flight up.",
            "Two flights up to the roof deck. Elevator to the 9th floor.",
            "Three short flights up in a quiet brownstone.",
            "If you don't like walk-ups, this elevator building is for you.",
            "Not a walk-up! Elevator building with laundry.",
            "This apartment is not a walk up.",
            "Pets allowed provided no damage to building or elevator.",
        ]
    )
    out = adfills.elevator(text)
    assert out.elevator.to_dict() == {
        0: "no",
        1: "yes",
        2: "no",
        6: "no",
        7: "no",
        8: "yes",
        9: "yes",
        10: "yes",
        11: "yes",
        12: "no",
        13: "yes",
        14: "yes",
        16: "yes",
    }
    assert out.evidence.str.contains("elevator|walk-up|flights up").all()


def test_pets_from_ad_v1_fills_unknowns_only(tmp_path, monkeypatch):
    assert data.RULE_SOURCES["pets-from-ad-v1"] == data.PETS_FROM_AD
    path = tmp_path / "pets.parquet"
    pd.DataFrame(
        {
            "audit_id": ["a", "b", "c"],
            "pets": ["not_allowed", "approval_required", "not_allowed"],
        }
    ).to_parquet(path)
    monkeypatch.setattr(data, "PETS_FROM_AD", path)
    frame = pd.DataFrame(
        {
            "audit_id": ["a", "b", "c", "d"],
            "pets": ["unknown", "unknown", "allowed_restrictions_unknown", "unknown"],
        }
    )
    out = data.DATA_RULES["pets-from-ad-v1"](frame)
    assert out.pets.tolist() == [
        "not_allowed",
        "approval_required",
        "allowed_restrictions_unknown",
        "unknown",
    ]
    assert not data.amended_rule("pets-from-ad-v1")


def test_adfills_pets_writes_existing_codes_only():
    from rentfrontier import adfills

    text = pd.Series(
        [
            "Sorry, no pets.",
            "Pets on a case by case basis.",
            "Pet friendly building!",
            "Cats only, no dogs.",
            "Sunny one bedroom.",
            None,
            "Guarantors considered on a case-by-case basis.",
            "Dogs up to 50 lbs. Above that is considered case by case.",
            "Sorry, no pet dogs permitted.",
            "No fee apartment! No pet fees!",
            "No pet fees! Pets ok.",
            "Pets: no dogs. Cats are permitted.",
            "No board approval, pets ok.",
            "Pets: no.",
            "Fees may include parking, amenities, late fees, pet fees, insufficient funds.",
            "Pet fees or deposits may apply.",
            "Pet fee: $25 per pet per month.",
            "No board approval or pets.",
            "Cats are ok/ sorry dogs aren't allowed.",
            "Pets ok with landlord's approval.",
            "Pets ok. No smoking or pets allowed in common areas.",
            "Assistance animals welcome. Unfortunately, no other pets allowed.",
            "Cats ok, dogs aren't aren't allowed.",
            "-no board approval -small dog or cat allowed",
            "Pets ok with permission of the owner.",
            "Sorry, no cats or dogs.",
            "Fast approvals, pets and out of state guarantors allowed.",
            "Fast approvals. Pets ok.",
            "1 small dog allowed under 25 pounds.",
            "Small pets okay. Case by case on dogs.",
            "Most pets permitted with landlord consent.",
            "Cats ok, sorry no doggies.",
            "Cats welcome. Not dogs sorry.",
        ]
    )
    out = adfills.pets(text)
    assert out.pets.to_dict() == {
        0: "not_allowed",
        1: "approval_required",
        2: "allowed_restrictions_unknown",
        7: "approval_required",
        10: "allowed_restrictions_unknown",
        12: "allowed_restrictions_unknown",
        13: "not_allowed",
        16: "allowed_restrictions_unknown",
        19: "approval_required",
        23: "allowed_restrictions_unknown",
        24: "approval_required",
        25: "not_allowed",
        27: "allowed_restrictions_unknown",
        28: "allowed_restrictions_unknown",
        29: "approval_required",
        30: "approval_required",
    }
    assert out.evidence.notna().all()


def test_quarantine_v19_adds_the_ad_fit_hold_outs():
    """v19 holds out v18's rows unchanged, plus each quarantine verdict in the
    first ad-fit reads, quoting the read's evidence."""
    with open(data.QUARANTINE_V18) as f:
        v18 = {r["audit_id"]: r for r in map(json.loads, f)}
    with open(data.QUARANTINE_V19) as f:
        v19 = {r["audit_id"]: r for r in map(json.loads, f)}
    reads = data.REPO / "config" / "reviews" / "ad-fit-reads-20261014.jsonl"
    with open(reads) as f:
        held = {
            r["audit_id"]: r
            for r in map(json.loads, f)
            if r["verdict"].startswith("quarantine_")
        }
    assert all(v19[a] == v18[a] for a in v18)
    assert v19.keys() - v18.keys() == held.keys() and len(held) == 51
    assert all(
        v19[a]["action"] == r["verdict"] and v19[a]["evidence"] == r["quote"]
        for a, r in held.items()
    )
    assert "quarantine-v19" in data.DROPPING_RULES


def test_quarantine_v20_adds_the_second_ad_fit_hold_outs():
    """v20 holds out v19's rows unchanged, plus each quarantine verdict in the
    second ad-fit reads, quoting the read's evidence."""
    with open(data.QUARANTINE_V19) as f:
        v19 = {r["audit_id"]: r for r in map(json.loads, f)}
    with open(data.QUARANTINE_V20) as f:
        v20 = {r["audit_id"]: r for r in map(json.loads, f)}
    held = {}
    for name in ("ad-fit-reads-20261014-2.jsonl", "ad-fit-reads-20261014-3.jsonl"):
        with open(data.REPO / "config" / "reviews" / name) as f:
            for r in map(json.loads, f):
                if r["verdict"].startswith("quarantine_"):
                    held[r["audit_id"]] = r
    assert all(v20[a] == v19[a] for a in v19)
    assert v20.keys() - v19.keys() == held.keys() and len(held) == 58
    assert all(
        v20[a]["action"] == r["verdict"] and v20[a]["evidence"] == r["quote"]
        for a, r in held.items()
    )
    assert "quarantine-v20" in data.DROPPING_RULES


def test_bedrooms_ad_v4_takes_counts_from_quoted_reads():
    """Each v4 correction is a bedroom-check read with a `correct_bedrooms`
    verdict, a quote from an ad and the count it states; v3's rows apply first."""
    with open(data.BEDROOM_CORRECTIONS_V4) as f:
        fixes = {r["audit_id"]: r for r in map(json.loads, f)}
    with open(data.REPO / "config/reviews/ad-fit-reads-20261015-bedrooms.jsonl") as f:
        reads = {r["audit_id"]: r for r in map(json.loads, f)}
    assert fixes
    for a, fix in fixes.items():
        read = reads[a]
        assert read["verdict"] == "correct_bedrooms" and read["quote"]
        assert read["second_signal"]
        assert fix["field"] == "bedrooms" and fix["corrected"] == read["bedrooms"]
    assert {a for a, r in reads.items() if r["verdict"] == "correct_bedrooms"} == set(
        fixes
    )
    frame = pd.DataFrame(
        {"audit_id": [next(iter(fixes)), "other"], "bedrooms": [9.0, 2.0]}
    )
    out = data.correct_bedrooms_v4(frame)
    assert out.bedrooms.tolist() == [fixes[frame.audit_id[0]]["corrected"], 2.0]


def test_bedrooms_ad_v5_takes_counts_a_listing_floor_plan_shows():
    """Each v5 row is a v4-review row kept at its coded count, whose floor
    plan read is a clear plan from the listing's own page showing the ad's
    count; v4's rows apply first."""
    with open(data.BEDROOM_CORRECTIONS_V5) as f:
        fixes = {r["audit_id"]: r for r in map(json.loads, f)}
    with open(data.REPO / "config/reviews/floor-plans-20261015-bedrooms.jsonl") as f:
        plans = [json.loads(line) for line in f]
    with open(data.REPO / "config/reviews/ad-fit-reads-20261015-bedrooms.jsonl") as f:
        reads = {r["audit_id"]: r for r in map(json.loads, f)}
    backed = {p["audit_id"]: p for p in plans if p["verdict"] == "correct_bedrooms"}
    assert len(fixes) == 4 and backed.keys() == fixes.keys()
    for a, p in backed.items():
        assert p["plan_page"] == "StreetEasy listing page" and p["plan_clear"]
        assert p["plan_bedrooms"] == p["ad_bedrooms"] != p["bedrooms_coded"]
        assert reads[a]["verdict"] == "keep"
        assert fixes[a]["recorded"] == p["bedrooms_coded"]
        assert (
            fixes[a]["corrected"] == p["ad_bedrooms"]
            and p["plan"] in fixes[a]["evidence"]
        )
    frame = pd.DataFrame(
        {"audit_id": [next(iter(fixes)), "other"], "bedrooms": [9.0, 2.0]}
    )
    out = data.correct_bedrooms_v5(frame)
    assert out.bedrooms.tolist() == [fixes[frame.audit_id[0]]["corrected"], 2.0]


def test_quarantine_v22_adds_the_blank_studios_of_the_bedroom_review():
    """v22 holds out v21's rows unchanged, plus each bedroom-review read with
    the `quarantine_bedrooms_unknown` verdict, quoting the read's whole ad."""
    with open(data.QUARANTINE_V21) as f:
        v21 = {r["audit_id"]: r for r in map(json.loads, f)}
    with open(data.QUARANTINE_V22) as f:
        v22 = {r["audit_id"]: r for r in map(json.loads, f)}
    with open(data.REPO / "config/reviews/ad-fit-reads-20261015-bedrooms.jsonl") as f:
        reads = [json.loads(line) for line in f]
    held = {
        r["audit_id"]: r for r in reads if r["verdict"] == "quarantine_bedrooms_unknown"
    }
    assert len(held) == 146
    assert all(
        r["bedrooms_coded"] == 0 and r["quote_is_whole_ad"] for r in held.values()
    )
    assert all(v22[a] == v21[a] for a in v21)
    assert v22.keys() - v21.keys() == held.keys()
    assert all(v22[a]["evidence"] == r["quote"] for a, r in held.items())
    assert "quarantine-v22" in data.DROPPING_RULES


def test_bedrooms_ad_v6_takes_backed_counts_from_the_studio_review():
    """Each v6 row is a studio read with the `correct_bedrooms` verdict and a
    second signal; plan-backed rows cite a clear plan from the listing's own
    page. v5's rows apply first."""
    with open(data.BEDROOM_CORRECTIONS_V6) as f:
        fixes = {r["audit_id"]: r for r in map(json.loads, f)}
    with open(data.REPO / "config/reviews/ad-fit-reads-20261015-studios.jsonl") as f:
        reads = {r["audit_id"]: r for r in map(json.loads, f)}
    with open(data.REPO / "config/reviews/floor-plans-20261015-studios.jsonl") as f:
        plans = {p["audit_id"]: p for p in map(json.loads, f)}
    took = {a for a, r in reads.items() if r["verdict"] == "correct_bedrooms"}
    assert len(fixes) == 13 and took == fixes.keys()
    for a, fix in fixes.items():
        assert fix["recorded"] == reads[a]["bedrooms_coded"] == 0
        assert fix["corrected"] == reads[a]["bedrooms"] > 0
        assert reads[a]["second_signal"]
        if reads[a]["second_signal"].startswith("floor plan"):
            p = plans[a]
            assert p["plan_page"] == "StreetEasy listing page" and p["plan_clear"]
            assert (
                p["plan_bedrooms"] == fix["corrected"] and p["plan"] in fix["evidence"]
            )
    frame = pd.DataFrame(
        {"audit_id": [next(iter(fixes)), "other"], "bedrooms": [9.0, 2.0]}
    )
    out = data.correct_bedrooms_v6(frame)
    assert out.bedrooms.tolist() == [fixes[frame.audit_id[0]]["corrected"], 2.0]


def test_quarantine_v31_adds_far_apart_misfiled_ads():
    """v31 keeps every v30 row and adds the 7 rows the far-apart readers called
    misfiled and review held."""
    with open(data.QUARANTINE_V30) as f:
        old = [json.loads(line) for line in f]
    with open(data.QUARANTINE_V31) as f:
        rows = [json.loads(line) for line in f]
    assert rows[: len(old)] == old
    added = rows[len(old) :]
    assert len(added) == 7
    assert {r["action"] for r in added} == {"quarantine_location_conflict"}
    with open(brooklyn.REVIEWS / "duplicate-ad-far-reads-20261015.jsonl") as f:
        reads = [json.loads(line) for line in f]
    held = {
        a for r in reads if r.get("held_in_review") for a in r["misfiled_audit_ids"]
    }
    assert {r["audit_id"] for r in added} == held
    assert "quarantine-v31" in data.DROPPING_RULES


def test_quarantine_v30_adds_three_same_month_twins():
    """v30 keeps every v29 row and adds the 3 rows the twin readers called
    misfiled and review kept."""
    with open(data.QUARANTINE_V29) as f:
        old = [json.loads(line) for line in f]
    with open(data.QUARANTINE_V30) as f:
        rows = [json.loads(line) for line in f]
    assert rows[: len(old)] == old
    added = rows[len(old) :]
    assert len(added) == 3
    assert {r["action"] for r in added} == {"quarantine_location_conflict"}
    with open(brooklyn.REVIEWS / "duplicate-ad-twin-reads-20261015.jsonl") as f:
        reads = [json.loads(line) for line in f]
    misfiled = {
        a
        for r in reads
        if "dropped_in_review" not in r
        for a in r["misfiled_audit_ids"]
    }
    assert {r["audit_id"] for r in added} == misfiled
    assert "quarantine-v30" in data.DROPPING_RULES


def test_quarantine_v29_adds_the_older_mews_listings():
    """v29 keeps every v28 row and adds the 2016 and 2019 rows of the 1 Fifth
    Avenue mews unit whose 2022 and 2024 rows v28 holds."""
    with open(data.QUARANTINE_V28) as f:
        old = [json.loads(line) for line in f]
    with open(data.QUARANTINE_V29) as f:
        rows = [json.loads(line) for line in f]
    assert rows[: len(old)] == old
    added = rows[len(old) :]
    assert [r["source_listing_id"] for r in added] == ["1937379", "2867212"]
    held_unit = {r["unit_id"] for r in old if r["source_listing_id"] == "3869550"}
    assert {r["unit_id"] for r in added} == held_unit
    assert "quarantine-v29" in data.DROPPING_RULES


def test_quarantine_v28_adds_three_listings_backed_by_floor_plans():
    """v28 keeps every v27 row and adds the 3 rows whose floor plans name the
    other building, each from a group v27 kept on unit history alone."""
    with open(data.QUARANTINE_V27) as f:
        old = [json.loads(line) for line in f]
    with open(data.QUARANTINE_V28) as f:
        rows = [json.loads(line) for line in f]
    assert rows[: len(old)] == old
    added = rows[len(old) :]
    assert len(added) == 3
    assert {r["action"] for r in added} == {"quarantine_location_conflict"}
    with open(brooklyn.REVIEWS / "duplicate-ad-screen-reads-20261015.jsonl") as f:
        kept = {
            g["gid"]: g
            for g in map(json.loads, f)
            if g["decision"] == "kept: reader backed it by unit history alone"
        }
    with open(brooklyn.REVIEWS / "duplicate-ad-floor-plans-20261015.jsonl") as f:
        plans = [json.loads(line) for line in f]
    assert {p["gid"] for p in plans} <= set(kept)
    held = {a for p in plans for a in p["held"]}
    assert held == {r["audit_id"] for r in added}
    for p in plans:
        assert set(p["held"]) <= set(kept[p["gid"]]["audit_ids"])
        assert bool(p["held"]) == (p["building_on_plan"] is not None)
    assert "quarantine-v28" in data.DROPPING_RULES


def test_quarantine_v27_adds_fifty_wrong_building_listings():
    """v27 keeps every v26 row and adds the 50 rows the duplicate-ad screen
    held, each one from a group the readers decided."""
    with open(data.QUARANTINE_V26) as f:
        old = [json.loads(line) for line in f]
    with open(data.QUARANTINE_V27) as f:
        rows = [json.loads(line) for line in f]
    assert rows[: len(old)] == old
    added = rows[len(old) :]
    assert len(added) == 50
    assert {r["action"] for r in added} == {"quarantine_location_conflict"}
    read = set(
        (brooklyn.REVIEWS / "quarantine-v27-read-20261015.txt").read_text().split()
    )
    with open(brooklyn.REVIEWS / "duplicate-ad-screen-reads-20261015.jsonl") as f:
        groups = [json.loads(line) for line in f]
    assert len(groups) == 120
    held = {a for g in groups for a in g["held"]}
    assert held == {r["audit_id"] for r in added}
    assert {a for g in groups for a in g["audit_ids"]} == read
    assert all(len(g["held"]) <= 1 for g in groups)
    assert "quarantine-v27" in data.DROPPING_RULES


def test_quarantine_v26_adds_five_midtown_west_listings():
    """v26 holds out v25's rows unchanged, plus 5 rows from the Midtown West
    screen. Every held row is in v26's read list and has a held read in the
    reads record."""
    with open(data.QUARANTINE_V25) as f:
        v25 = {r["audit_id"]: r for r in map(json.loads, f)}
    with open(data.QUARANTINE_V26) as f:
        v26 = {r["audit_id"]: r for r in map(json.loads, f)}
    assert all(v26[a] == v25[a] for a in v25)
    added = {a: v26[a] for a in v26.keys() - v25.keys()}
    assert len(added) == 5
    assert sorted(r["action"] for r in added.values()) == [
        "quarantine_location_conflict",
        "quarantine_location_conflict",
        "quarantine_nonresidential",
        "quarantine_nonresidential",
        "quarantine_nonresidential",
    ]
    read = set(
        (brooklyn.REVIEWS / "quarantine-v26-read-20261015.txt").read_text().split()
    )
    assert added.keys() <= read
    with open(brooklyn.REVIEWS / "midtown-west-screen-reads-20261015.jsonl") as f:
        reads = [json.loads(line) for line in f]
    assert {a for r in reads if r["held"] for a in r["audit_ids"]} == added.keys()
    assert {a for r in reads for a in r["audit_ids"]} == read
    assert "quarantine-v26" in data.DROPPING_RULES


def test_quarantine_v25_adds_eight_brooklyn_listings():
    """v25 holds out v24's rows unchanged, plus 8 Brooklyn rows. Each one is in
    the misjoin file and in v25's read list."""
    with open(data.QUARANTINE_V24) as f:
        v24 = {r["audit_id"]: r for r in map(json.loads, f)}
    with open(data.QUARANTINE_V25) as f:
        v25 = {r["audit_id"]: r for r in map(json.loads, f)}
    assert all(v25[a] == v24[a] for a in v24)
    added = {a: v25[a] for a in v25.keys() - v24.keys()}
    assert len(added) == 8
    assert all(r["action"] == "brooklyn_misjoin" for r in added.values())
    assert (
        sorted(r["building"] for r in added.values()).count(
            "317-east-19-street-new_york"
        )
        == 7
    )
    with open(brooklyn.MISJOINS) as f:
        misjoins = {json.loads(line)["audit_id"] for line in f if line.strip()}
    assert added.keys() <= misjoins
    assert added.keys() == set(
        (brooklyn.REVIEWS / "quarantine-v25-read-20261015.txt").read_text().split()
    )
    assert "quarantine-v25" in data.DROPPING_RULES


def test_quarantine_v24_adds_four_listings_filed_under_the_wrong_building():
    """v24 holds out v23's rows unchanged, plus the two listings of 3B and 3BB
    at 222 East 17th Street and the two of 20C at 318 East 15th Street."""
    with open(data.QUARANTINE_V23) as f:
        v23 = {r["audit_id"]: r for r in map(json.loads, f)}
    with open(data.QUARANTINE_V24) as f:
        v24 = {r["audit_id"]: r for r in map(json.loads, f)}
    assert all(v24[a] == v23[a] for a in v23)
    added = [v24[a] for a in v24.keys() - v23.keys()]
    assert sorted((r["building"], r["unit_label"], r["action"]) for r in added) == [
        ("222-east-17-street-new_york", "3B", "brooklyn_misjoin"),
        ("222-east-17-street-new_york", "3BB", "brooklyn_misjoin"),
        ("318-east-15-street-new_york", "20C", "quarantine_location_conflict"),
        ("318-east-15-street-new_york", "20C", "quarantine_location_conflict"),
    ]
    with open(brooklyn.MISJOINS) as f:
        misjoins = {json.loads(line)["audit_id"] for line in f if line.strip()}
    brooklyn_rows = {r["audit_id"] for r in added if r["action"] == "brooklyn_misjoin"}
    assert brooklyn_rows <= misjoins
    read = set(
        (brooklyn.REVIEWS / "quarantine-v24-read-20261015.txt").read_text().split()
    )
    assert brooklyn_rows == read
    assert "quarantine-v24" in data.DROPPING_RULES


def test_quarantine_v23_adds_the_blank_studios_of_the_studio_review():
    """v23 holds out v22's rows unchanged, plus each studio-review read with
    the `quarantine_bedrooms_unknown` verdict, quoting the read's whole ad."""
    with open(data.QUARANTINE_V22) as f:
        v22 = {r["audit_id"]: r for r in map(json.loads, f)}
    with open(data.QUARANTINE_V23) as f:
        v23 = {r["audit_id"]: r for r in map(json.loads, f)}
    with open(data.REPO / "config/reviews/ad-fit-reads-20261015-studios.jsonl") as f:
        reads = [json.loads(line) for line in f]
    held = {
        r["audit_id"]: r for r in reads if r["verdict"] == "quarantine_bedrooms_unknown"
    }
    assert len(held) == 56
    assert all(
        r["bedrooms_coded"] == 0 and r["quote_is_whole_ad"] for r in held.values()
    )
    assert all(v23[a] == v22[a] for a in v22)
    assert v23.keys() - v22.keys() == held.keys()
    assert all(v23[a]["evidence"] == r["quote"] for a, r in held.items())
    assert "quarantine-v23" in data.DROPPING_RULES


def test_quarantine_v21_adds_the_stock_wording_hold_outs():
    """v21 holds out v20's rows unchanged, plus each quarantine verdict in the
    reads of the stock-wording search, quoting the read's evidence."""
    with open(data.QUARANTINE_V20) as f:
        v20 = {r["audit_id"]: r for r in map(json.loads, f)}
    with open(data.QUARANTINE_V21) as f:
        v21 = {r["audit_id"]: r for r in map(json.loads, f)}
    with open(data.REPO / "config" / "reviews" / "ad-fit-reads-20261014-4.jsonl") as f:
        reads = [json.loads(line) for line in f]
    held = {r["audit_id"]: r for r in reads if r["verdict"] != "keep"}
    assert len(reads) == 90 and len(held) == 52
    assert all(v21[a] == v20[a] for a in v20)
    assert v21.keys() - v20.keys() == held.keys()
    assert all(
        v21[a]["action"] == r["verdict"] and v21[a]["evidence"] == r["quote"]
        for a, r in held.items()
    )
    assert "quarantine-v21" in data.DROPPING_RULES


def test_sqft_units_v1_takes_sizes_the_unit_or_its_line_agree_on():
    """Each v1 row is a candidate with the `correct` outcome and the same size,
    about 1.5x or more from the recorded one (rounded to the square foot)."""
    with open(data.SQFT_CORRECTIONS) as f:
        fixes = {r["audit_id"]: r for r in map(json.loads, f)}
    with open(data.REPO / "config/reviews/sqft-units-reads-20261015.jsonl") as f:
        reads = {r["audit_id"]: r for r in map(json.loads, f)}
    took = {a for a, r in reads.items() if r["outcome"] == "correct"}
    assert len(fixes) == 12 and len(reads) == 43 and took == fixes.keys()
    for a, fix in fixes.items():
        assert reads[a]["second_read"] == "correct"
        assert reads[a]["proposed"] == fix["corrected"]
        assert fix["basis"] in ("unit", "line")
        assert max(fix["recorded"], fix["corrected"]) > 1.49 * min(
            fix["recorded"], fix["corrected"]
        )
    a = next(iter(fixes))
    frame = pd.DataFrame(
        {"audit_id": [a, "other"], "square_feet": [fixes[a]["recorded"], 700.0]}
    )
    out = data.correct_square_feet_v1(frame)
    assert out.square_feet.tolist() == [fixes[a]["corrected"], 700.0]
    assert "sqft-units-v1" not in data.DROPPING_RULES
