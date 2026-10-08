"""Data rules: one unit id per physical unit (unit-labels-v1) and the
divergence-review quarantine (quarantine-v1)."""

import functools
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
    ) | data.quarantined(data.QUARANTINE_V11)


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


def test_quarantine_v11_adds_shops_to_v10():
    """v11 is v10's 219 rows and 13 more from the wider shop and restaurant
    checks, each with its quote and reason, all among the rows read."""
    v10 = data.quarantined(data.QUARANTINE_V10)
    v11 = data.quarantined(data.QUARANTINE_V11)
    assert v10 < v11 and len(v11 - v10) == 13
    read = set(data.QUARANTINE_V11_READ.read_text().split())
    assert len(read) == 693 and v11 - v10 <= read
    with open(data.QUARANTINE_V11) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    assert len(rows) == 232 and all(r["evidence"] and r["reason"] for r in rows)
    assert "quarantine-v11" in data.DROPPING_RULES
