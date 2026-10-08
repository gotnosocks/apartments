import pandas as pd

from rentfrontier import cleaning, data


def _frame():
    return pd.DataFrame(
        {
            "audit_id": ["a", "b", "c", "d", "e"],
            "unit_id": ["u1", "u1", "u1", "u2", "u2b"],
            "building": ["b1", "b1", "b1", "b2", "b2"],
            "price_basis": ["ask"] * 5,
            "price_at": ["2024-01", "2024-06", "2025-01", "2024-01", "2024-06"],
            "bedrooms": [1, 1, 4, 2, 2],
            "full_baths": [1, 1, 2, 1, 1],
            "log_rent": [8.0, 8.05, 9.0, 8.2, 8.21],
        }
    )


def test_steps_count_each_rule(monkeypatch):
    def fix(frame):
        out = frame.copy()
        out.loc[out.audit_id == "b", "full_baths"] = 2
        return out

    def drop(frame):
        return frame[frame.audit_id != "a"]

    def join(frame):
        return frame.assign(unit_id=frame.unit_id.replace({"u2b": "u2"}))

    def split(frame):
        return frame.assign(unit_id=frame.unit_id.where(frame.bedrooms < 4, "u1~1"))

    rules = {
        "baths-ad-x": fix,
        "quarantine-x": drop,
        "unit-labels-x": join,
        "unit-splits-x": split,
    }
    monkeypatch.setattr(data, "DATA_RULES", rules)
    doc = cleaning.steps(_frame(), list(rules))
    start = doc["start"]
    assert (start["rows"], start["units"], start["pairs"]) == (5, 3, 2)
    assert start["bed_changes"] == 0.5 and start["big_jumps"] == 0.5
    fixed, dropped, joined, split_ = doc["steps"]
    assert fixed["family"] == "correct" and fixed["changed"] == {"full_baths": 1}
    assert dropped["dropped"] == 1 and dropped["rows"] == 4
    assert joined["family"] == "join" and joined["units"] == 2 and joined["pairs"] == 2
    assert split_["units"] == 3 and split_["bed_changes"] == 0.0
    assert split_["big_jumps"] == 0.0
