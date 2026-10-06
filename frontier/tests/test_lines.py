import numpy as np
import pandas as pd
from rentfrontier import features, lines


def test_line_of_groups_express_and_drops_shuttles():
    assert lines.line_of("6X") == "4/5/6"
    assert lines.line_of("FX") == "F/M"
    assert lines.line_of("A") == "A/C/E"
    assert lines.line_of("GS") is None
    assert lines.line_of("SI") is None


def _table(walks):
    return pd.DataFrame(
        [(b, g, w, f"{g} St") for (b, g), w in walks.items()],
        columns=["building", "line", "walk_min", "station"],
    )


def test_priced_lines_need_enough_near_buildings():
    walks = {(f"b{i}", "L"): 3.0 if i == 0 else 20.0 for i in range(200)}
    walks |= {(f"b{i}", "J/Z"): 40.0 for i in range(200)}
    table = _table(walks)
    assert lines.priced_lines(table) == []  # the L near 0.5% of buildings
    table.loc[(table.line == "L") & table.building.isin(["b1", "b2"]), "walk_min"] = 5.0
    assert lines.priced_lines(table) == ["L"]


def test_near_lines_as_of_the_month(monkeypatch):
    now = _table({("x", "7"): 4.0, ("y", "7"): 30.0, ("x", "L"): 9.0, ("y", "L"): 2.0})
    before = now.assign(walk_min=[25.0, 30.0, 9.0, 2.0])  # before Hudson Yards
    tables = {frozenset(): now, frozenset({"726"}): before}
    monkeypatch.setattr(
        lines, "building_lines", lambda exclude=frozenset(): tables[exclude]
    )
    frame = pd.DataFrame(
        {
            "building": ["x", "x", "y", "z"],
            "period": ["2015-08", "2015-10", "2015-10", "2015-10"],
        }
    )
    near = lines.near_lines(frame)
    assert list(near.columns) == ["7", "L"]
    np.testing.assert_array_equal(near["7"], [0.0, 1.0, 0.0, 0.0])
    np.testing.assert_array_equal(near["L"], [0.0, 0.0, 1.0, 0.0])
    assert features.stops_not_open("2015-08") == frozenset({"726"})
