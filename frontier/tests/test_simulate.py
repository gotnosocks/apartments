import numpy as np
import pandas as pd

import test_building_zones_floor as tbf
from rentfrontier import building_zones_floor as bzf
from rentfrontier import simulate, two_zone


def _medians(d, seed=0):
    rng = np.random.default_rng(seed)
    n = sum(s["sites"] for s in d.surfaces)
    waves = sum(s["basis"].shape[1] for s in d.surfaces)
    return {
        "beta": rng.normal(0, 0.05, len(d.names)),
        "L": np.cumsum(rng.normal(0, 0.01, d.weeks + 1)),
        "gp_w": rng.normal(0, 0.1, waves),
        "bld": rng.normal(0, 0.1, n),
        "nu": 4.0,
        "sigma": np.array([0.08, 0.08, 0.09, 0.10]),
    }


def test_truth_sets_the_scenario_terms():
    *_, d = tbf._design()
    med = _medians(d)
    names = list(d.names)
    ix = {n: j for j, n in enumerate(names)}

    t = simulate.truth(names, med, "realistic")
    assert np.isclose(t["beta"][ix["unit:walkup_f4"]], 3 * simulate.WALKUP_SLOPE)
    assert np.isclose(t["beta"][ix["unit:elev_top"]], np.log(1.04))
    assert t["beta"][ix["unit:lower"]] == 0
    for k in range(2, bzf.ELEV_CAP + 1):
        j = ix[f"unit:elev_f{k}"]
        assert t["beta"][j] == med["beta"][j]
    np.testing.assert_array_equal(t["bld"], med["bld"])

    t = simulate.truth(names, med, "null")
    for n in simulate.floor_terms(names) + simulate.feature_terms(names):
        assert t["beta"][ix[n]] == 0
    assert "bld:elevator" in simulate.feature_terms(names)
    assert "unit:dishwasher" in simulate.feature_terms(names)
    j = ix["unit:log_size_rel"]
    assert t["beta"][j] == med["beta"][j]

    planted = np.linspace(-0.01, 0.01, len(med["bld"]))
    t = simulate.truth(names, med, "height", planted)
    for n in simulate.floor_terms(names):
        assert t["beta"][ix[n]] == 0
    j = ix["bld:elevator"]
    assert t["beta"][j] == med["beta"][j]
    np.testing.assert_allclose(t["bld"], med["bld"] + planted)


def test_surface_matches_the_model_centring():
    *_, d = tbf._design()
    med = _medians(d)
    w = np.stack([med["gp_w"], 2 * med["gp_w"]])
    F = simulate.surface([s["basis"] for s in d.surfaces], two_zone.site_share(d), w)
    np.testing.assert_allclose(F, two_zone.surface_draws(d, {"gp_w": w}))
    np.testing.assert_allclose(F @ two_zone.site_share(d), 0, atol=1e-12)


def test_draw_adds_noise_at_the_group_scale():
    *_, d = tbf._design(n=20000)
    med = _medians(d)
    mu = simulate.mean(d, med["beta"], med["L"], np.zeros(len(med["bld"])), med["bld"])
    y = simulate.draw(d, mu, 30.0, med["sigma"], seed=1)
    r = y - mu
    for g in range(4):
        on = d.group == g
        if on.sum() > 500:
            assert abs(r[on].std() / med["sigma"][g] - np.sqrt(30 / 28)) < 0.08
    np.testing.assert_array_equal(y, simulate.draw(d, mu, 30.0, med["sigma"], seed=1))


def test_planted_height_is_centred_on_rows():
    floors = np.array([2.0, 6.0, np.nan, 10.0])
    rows = np.array([3.0, 1.0, 5.0, 0.0])
    p = simulate.planted_height(floors, rows)
    assert p[2] == 0
    assert np.isclose(p[:2] @ rows[:2], 0)
    assert np.isclose(p[1] - p[0], 4 * simulate.HEIGHT_SLOPE)


def test_scores_cover_and_measure_shrinkage():
    rng = np.random.default_rng(5)
    truth = rng.normal(0, 1, 6)
    draws = truth + rng.normal(0, 0.1, (4, 100, 6))
    rows = simulate.term_rows(draws, truth, [f"t{j}" for j in range(6)])
    assert all(r["covered"] for r in rows)
    assert all(len(r["chain_medians"]) == 4 for r in rows)

    truth = rng.normal(0, 1, 400)
    est = 0.5 * truth
    draws = est + rng.normal(0, 0.05, (200, 400))
    cov = simulate.site_coverage(draws, truth, np.full(400, 10.0))
    assert abs(cov["all"]["slope"] - 0.5) < 0.02
    assert cov["all"]["coverage"] < 0.2
    assert cov["by_rows"]["5-19"]["sites"] == 400


def test_pluto_floors_joins_through_bbl(tmp_path, monkeypatch):
    reg = pd.DataFrame({"building": ["a", "b", "c"], "bbl": ["1", "2", None]})
    reg.to_parquet(tmp_path / "registry.parquet")
    pd.DataFrame({"bbl": ["1", "2"], "numfloors": ["4.5", "0"]}).to_parquet(
        tmp_path / "pluto.parquet"
    )
    monkeypatch.setattr(simulate.building_attrs, "PLUTO", tmp_path / "pluto.parquet")
    f = simulate.pluto_floors(
        np.array(["a", "b", "c", "d"]), tmp_path / "registry.parquet"
    )
    np.testing.assert_array_equal(np.isnan(f), [False, True, True, True])
    assert f[0] == 4.0


def test_fitted_keeps_the_medians():
    *_, d = tbf._design()
    med = _medians(d)
    t = simulate.truth(list(d.names), med, "fitted")
    np.testing.assert_array_equal(t["beta"], med["beta"])
    np.testing.assert_array_equal(t["bld"], med["bld"])
    assert not t["planted"].any()
    assert set(simulate.SPECS) == {"building-zones-floor", "building-zones-location"}
