import pandas as pd
from rentfrontier import bedsize


def test_stated_size_takes_the_largest_bed_stated():
    assert bedsize.stated_size("bedroom fits a king bed") == "king"
    assert bedsize.stated_size("king-size bedroom with closets") == "king"
    assert bedsize.stated_size("room for a queen-sized bed") == "queen"
    assert bedsize.stated_size("will fit a full or queen bed") == "queen"
    assert bedsize.stated_size("fits a twin mattress") == "full"
    assert bedsize.stated_size("california king bedroom") == "king"


def test_stated_size_ignores_names_and_bare_rooms():
    assert bedsize.stated_size("on king street, a huge bedroom") is None
    assert bedsize.stated_size("") is None


def test_apartments_pools_only_ads_stating_a_size(monkeypatch):
    frame = pd.DataFrame(
        {
            "unit_id": ["u1", "u1", "u1", "u2"],
            "building": ["b1", "b1", "b1", "b2"],
            "period": pd.to_datetime(["2020-01", "2021-01", "2022-01", "2020-01"]),
        }
    )
    text = pd.Series(["fits a king bed", "queen size bedroom", "sunny", "sunny"])
    monkeypatch.setattr(bedsize.descriptions, "attach", lambda f: text)
    out = bedsize.apartments(frame).set_index("unit_id")
    assert list(out.index) == ["u1"]
    assert out.loc["u1", "largest"] == "king"
    assert out.loc["u1", "latest"] == "queen"
    assert out.loc["u1", "listings"] == 2
