from types import SimpleNamespace

import numpy as np
import pytest

from rentfrontier import newbuilding


def rows(month, beds):
    month = np.asarray(month)
    return SimpleNamespace(
        y=np.zeros(len(month)),
        month=month,
        knot=month // 6,
        knot_frac=(month % 6) / 6,
        beds_centered=np.asarray(beds, float),
        unit_time=np.zeros(len(month)),
    )


def test_building_variance_adds_level_walk_from_its_origin_and_slopes():
    kept = {
        "alpha": np.zeros(2),
        "building_scale": np.array([0.2, 0.3]),
        "walk_scale": np.array([0.05, 0.1]),
        "bedroom_slope_scale": np.array([0.04, 0.0]),
        "fslope_scales": np.array([[0.1], [0.2]]),
    }
    # First knot 2 (months 12-17); rows at month 12 (knot 2, frac 0) and 27
    # (knot 4, frac 0.5): 0 and 2.25 walk steps.
    a = rows([12, 27], [0, 2])
    x = np.array([[1.0], [0.5]])
    var = newbuilding.building_variance(kept, a, np.array([2, 2]), x, None, 6)
    expect = np.array(
        [
            [0.04 + 0 + 0 + 0.01, 0.04 + 0.0025 * 2.25 + 0.0016 * 4 + 0.01 * 0.25],
            [0.09 + 0 + 0 + 0.04, 0.09 + 0.01 * 2.25 + 0 + 0.04 * 0.25],
        ]
    )
    np.testing.assert_allclose(var, expect)


def test_scores_cover_asks_drawn_from_the_predictive():
    rng = np.random.default_rng(0)
    draws, n = 400, 4000
    mean = rng.normal(0, 0.05, (draws, 1)).repeat(n, 1)
    sigma = np.full((draws, n), 0.1)
    nu = np.full(draws, 5.0)
    extra = np.full((draws, n), 0.2)
    s = rng.integers(0, draws, n)
    y = mean[s, 0] + 0.2 * rng.standard_normal(n) + 0.1 * rng.standard_t(5.0, n)
    median, pit, lpd = newbuilding.scores(y, mean, extra, sigma, nu, rng)
    out = newbuilding.summarize_rows(y, median, pit, {"all": np.ones(n, bool)})["all"]
    assert out["cover_80"] == pytest.approx(0.80, abs=0.02)
    assert out["cover_95"] == pytest.approx(0.95, abs=0.015)
    assert np.median(median) == pytest.approx(0.0, abs=0.02)
    assert np.all(np.isfinite(lpd))


def test_lpd_is_the_log_of_the_draw_mean_student_t_density():
    from scipy.stats import t

    rng = np.random.default_rng(3)
    mean = np.array([[0.0, 1.0], [0.5, 1.0]])
    sigma = np.array([[0.1, 0.2], [0.3, 0.2]])
    nu = np.array([4.0, 9.0])
    y = np.array([0.2, 0.9])
    _, _, lpd = newbuilding.scores(y, mean, None, sigma, nu, rng)
    dens = t.pdf((y - mean) / sigma, nu[:, None]) / sigma
    np.testing.assert_allclose(lpd, np.log(dens.mean(axis=0)))


def test_walk_origin_first_moves_an_unanchored_walk_to_the_first_knot():
    config = SimpleNamespace(walk_t=False, walk_zero_sum=False, walk_anchor_data=False)
    first = np.array([3, 7])
    np.testing.assert_array_equal(newbuilding.walk_origin(config, first), [0, 0])
    np.testing.assert_array_equal(
        newbuilding.walk_origin(config, first, first=True), first
    )


def test_groups_split_each_group_by_listing_year():
    x = np.array([[1.0], [0.0], [0.0]])
    g = newbuilding._groups(
        ["sqft_unknown"], x, np.array([3, 50, 200]), np.array([2015, 2025, 2015])
    )
    assert g["size unknown, listed 2014-16"].tolist() == [True, False, False]
    assert g["all, listed 2014-16"].tolist() == [True, False, True]
    assert g["building rows 101+, listed 2024-26"].sum() == 0


def test_unitsres_terciles_are_cut_over_buildings():
    building = np.array(["a", "a", "a", "b", "c", "d"])
    units = np.array([5, 5, 5, 20, 100, 0])
    out = newbuilding.unitsres_tercile(building, units)
    assert out.tolist() == ["small"] * 3 + ["mid", "large", "unknown"]


def test_building_weighted_counts_each_building_once():
    import pandas as pd

    rows = pd.DataFrame(
        {
            # Building a has three rows that miss by 10%, b one exact row.
            "building": ["a", "a", "a", "b"],
            "bbl": ["1", "1", "1", "2"],
            "y": np.zeros(4),
            "median": np.log([1.1, 1.1, 1.1, 1.0]),
            "pit": [0.5, 0.5, 0.5, 0.99],
            "lpd": [1.0, 1.0, 1.0, -2.0],
        }
    )
    out = newbuilding.building_weighted(rows, reps=50)
    assert out["buildings"] == 2 and out["lots"] == 2
    assert out["cover_80"] == pytest.approx(0.5)
    assert out["cover_95"] == pytest.approx(0.5)
    assert out["lpd_sum"] == pytest.approx(1.0 - 2.0)
    assert out["lpd_sum_se"] > 0


def test_unit_draws_are_clipped_student_t_at_the_unit_scale():
    rng = np.random.default_rng(1)
    kept = {
        "alpha": np.zeros(3),
        "unit_scale": np.array([0.1, 0.2, 0.0]),
        "unit_nu": np.array([3.0, 3.0, 3.0]),
    }
    a = rows(np.zeros(20000, int), np.zeros(20000))
    u = newbuilding.unit_draws(kept, a, np.zeros(20000, bool), rng)
    assert np.all(u[2] == 0)
    # t(3) has sd sqrt(3); the clip at 40 barely touches it.
    assert u[1].std() / u[0].std() == pytest.approx(2.0, rel=0.05)
    assert np.abs(u[0]).max() <= 0.1 * 40


def test_draw_lots_holds_out_every_building_of_a_chosen_lot():
    import pandas as pd

    buildings = np.array([f"b{i}" for i in range(200)])
    lots = pd.Series([f"L{i // 2}" for i in range(200)], index=buildings)
    out = newbuilding.draw_lots(np.repeat(buildings, 3), lots, fraction=0.1, seed=1)
    assert out.lot.nunique() == 10 and len(out) == 20
    assert set(out.building) == set(lots.index[lots.isin(set(out.lot))])


def test_holdout_rule_drops_the_listed_buildings(tmp_path):
    import pandas as pd

    from rentfrontier import data

    path = tmp_path / "lots.tsv"
    path.write_text("# lot\tbuilding\n1\ta\n1\tb\n")
    frame = pd.DataFrame({"building": ["a", "b", "c", "c"], "y": range(4)})
    assert data.holdout_buildings(path) == {"a", "b"}
    assert data.drop_holdout_lots(frame, path).building.tolist() == ["c", "c"]
    assert "tune-holdout-lots-v1" in data.DATA_RULES
    assert data.RULE_SOURCES["tune-holdout-lots-v1"] == data.HOLDOUT_LOTS_V1
    assert data.holdout_buildings() and "tune-holdout-lots-v1".startswith(
        data.HOLDOUT_PREFIX
    )


def test_final_ask_rule_prices_ended_listings_at_their_last_ask(monkeypatch):
    import pandas as pd

    from rentfrontier import data, listing_outcomes

    frame = pd.DataFrame(
        {
            "source_listing_id": ["1", "2", "3", "4", "5"],
            "asking_rent": [3000.0, 3000.0, 3000.0, 3000.0, 3000.0],
            "log_rent": np.log([3000.0] * 5),
        }
    )
    outcomes = {
        "final_ask": [2900.0, None, 3100.0, 900000.0, 2800.0],
        "still_listed": [False, False, True, False, False],
    }
    monkeypatch.setattr(
        listing_outcomes,
        "attach",
        lambda f: f.assign(
            **{
                k: np.array(v, dtype=float if k == "final_ask" else bool)
                for k, v in outcomes.items()
            }
        ),
    )
    out = data.DATA_RULES["tune-finalask-v1"](frame)
    assert out.source_listing_id.tolist() == ["1", "5"]
    assert out.asking_rent.tolist() == [2900.0, 2800.0]
    np.testing.assert_allclose(out.log_rent, np.log([2900.0, 2800.0]))
    assert str(data.RULE_SOURCES["tune-finalask-v1"]) == listing_outcomes.OUTCOMES_FILE


def test_walk_origin_is_the_panel_start_unless_anchored():
    from dataclasses import replace

    from rentfrontier import model

    first = np.array([3, 7])
    config = model.MODELS[
        "m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise-sizeunkslope"
    ]
    np.testing.assert_array_equal(newbuilding.walk_origin(config, first), [0, 0])
    anchored = replace(config, walk_anchor_data=True)
    np.testing.assert_array_equal(newbuilding.walk_origin(anchored, first), first)
    with pytest.raises(ValueError):
        newbuilding.walk_origin(replace(config, walk_t=True), first)


def test_finalask_compare_scores_shared_held_out_rows_against_the_final_ask(
    monkeypatch,
):
    import pandas as pd

    from rentfrontier import data, finalask

    def frame(ids, prices):
        return pd.DataFrame({"audit_id": ids, "log_rent": np.log(prices)})

    loads = {
        "final": (
            frame(["a", "b", "c"], [2900.0, 3000.0, 3100.0]),
            np.array([True, True, False]),
        ),
        "base": (
            frame(["a", "b", "c"], [3000.0, 3200.0, 3300.0]),
            np.array([False, True, True]),
        ),
    }
    monkeypatch.setattr(
        newbuilding, "_load", lambda name: ("dir", {}, {}, "config", *loads[name])
    )
    monkeypatch.setattr(newbuilding.explain, "load_run", lambda name: ("dir", {}, {}))
    monkeypatch.setattr(data, "recorded_rules", lambda result: [finalask.RULE])
    calls = []

    def score(name, ids, y=None):
        calls.append((name, list(ids), None if y is None else y.to_dict()))
        return {"all": {"rows": len(ids)}}

    monkeypatch.setattr(finalask, "score", score)
    out = finalask.compare("final", "base")
    assert out["rows"] == 1
    assert [c[:2] for c in calls] == [
        ("final", ["b"]),
        ("base", ["b"]),
        ("base", ["b"]),
    ]
    # The base fit is scored against the final-ask run's price, then its own.
    assert calls[1][2]["b"] == pytest.approx(np.log(3000.0))
    assert calls[2][2] is None


def test_finalask_compare_reads_the_served_latest_ask_rule(monkeypatch):
    import pandas as pd

    from rentfrontier import data, finalask

    frame = pd.DataFrame({"audit_id": ["a"], "log_rent": [np.log(3000.0)]})
    monkeypatch.setattr(
        newbuilding,
        "_load",
        lambda name: ("dir", {}, {}, "config", frame, np.array([True])),
    )
    monkeypatch.setattr(newbuilding.explain, "load_run", lambda name: ("dir", {}, {}))
    monkeypatch.setattr(
        data, "recorded_rules", lambda result: ["latest-ask-v2", "quarantine-v13"]
    )
    monkeypatch.setattr(finalask, "score", lambda name, ids, y=None: {"all": {}})
    out = finalask.compare("final", "base")
    assert out["rule"] == "latest-ask-v2"
    assert "latest ask fit vs latest ask" in out["scores"]


def test_scores_do_not_depend_on_how_many_workers_ran_them(monkeypatch):
    def fake_chunk(kept, config, prep, a, building, rungs, ctx, rng):
        noise = rng.standard_normal(len(a.y))
        return {
            r: (a.y + noise, np.full(len(a.y), 0.5), np.zeros(len(a.y))) for r in rungs
        }, {"building_part": np.zeros(len(a.y)), "knot": np.zeros(len(a.y))}

    monkeypatch.setattr(newbuilding, "_score_chunk", fake_chunk)
    monkeypatch.setattr(newbuilding.summary, "chunk_rows", lambda draws: 3)
    n = 10
    frame = np.zeros(n)

    def building_of(m):
        i = np.flatnonzero(m)
        a = SimpleNamespace(y=i.astype(float), x=np.zeros((len(i), 1)))
        return a, np.zeros(len(i), int)

    seen = {}

    def summarize(y, median, pit, groups):
        seen.setdefault("runs", []).append((y.copy(), median.copy()))
        return {}

    monkeypatch.setattr(newbuilding, "summarize_rows", summarize)
    args = (
        {"alpha": np.zeros(4)},
        None,
        SimpleNamespace(features=SimpleNamespace(names=["a"])),
        frame,
        np.ones(n, bool),
        ("new building",),
        {"rows": np.ones(1, int)},
        building_of,
        7,
    )
    _, rows = newbuilding._score(*args, workers=1)
    newbuilding._score(*args, workers=3)
    assert rows == n
    (y1, m1), (y3, m3) = seen["runs"]
    np.testing.assert_array_equal(y1, np.arange(n))
    np.testing.assert_array_equal(y3, y1)
    np.testing.assert_array_equal(m3, m1)


def test_latest_ask_rule_keeps_every_row_at_its_latest_ask(monkeypatch):
    import pandas as pd

    from rentfrontier import data, listing_outcomes

    frame = pd.DataFrame(
        {
            "source_listing_id": ["1", "2", "3", "4"],
            "asking_rent": [3000.0, 3000.0, 3000.0, 3000.0],
            "log_rent": np.log([3000.0] * 4),
        }
    )
    final = np.array([2900.0, np.nan, 3100.0, 900000.0])
    seen = []

    def attach(f, path):
        seen.append(path)
        return f.assign(final_ask=final, still_listed=[False, False, True, False])

    monkeypatch.setattr(listing_outcomes, "attach", attach)
    out = data.DATA_RULES["tune-latestask-v1"](frame)
    # Ended and still-live listings take their last ask; an uncaptured listing
    # and an implausible last ask keep the row's own.
    assert out.asking_rent.tolist() == [2900.0, 3000.0, 3100.0, 3000.0]
    np.testing.assert_allclose(out.log_rent, np.log(out.asking_rent))
    assert seen == [data.LATEST_ASK_OUTCOMES]
    assert data.RULE_SOURCES["tune-latestask-v1"] == data.LATEST_ASK_OUTCOMES


def test_ask_rules_v2_read_the_rebuilt_outcomes(monkeypatch):
    import pandas as pd

    from rentfrontier import data, listing_outcomes

    frame = pd.DataFrame(
        {
            "source_listing_id": ["1", "2", "3", "4", "5"],
            "asking_rent": [3000.0] * 5,
            "log_rent": np.log([3000.0] * 5),
        }
    )
    final = np.array([2900.0, np.nan, 3100.0, 900000.0, 2800.0])
    seen = []

    def attach(f, path):
        seen.append(path)
        return f.assign(
            final_ask=final, still_listed=[False, False, True, False, False]
        )

    monkeypatch.setattr(listing_outcomes, "attach", attach)
    out = data.DATA_RULES["tune-finalask-v2"](frame)
    assert out.source_listing_id.tolist() == ["1", "5"]
    assert out.asking_rent.tolist() == [2900.0, 2800.0]
    np.testing.assert_allclose(out.log_rent, np.log([2900.0, 2800.0]))
    out = data.DATA_RULES["tune-latestask-v2"](frame)
    assert out.asking_rent.tolist() == [2900.0, 3000.0, 3100.0, 3000.0, 2800.0]
    np.testing.assert_allclose(out.log_rent, np.log(out.asking_rent))
    assert seen == [data.ASK_OUTCOMES_V2] * 2
    for rule in ("tune-finalask-v2", "tune-latestask-v2"):
        assert data.RULE_SOURCES[rule] == data.ASK_OUTCOMES_V2
