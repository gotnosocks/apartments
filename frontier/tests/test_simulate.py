import sys
import types

import numpy as np
import pandas as pd
import pytest
import test_building_zones_floor as tbf
import test_building_zones_floor_asof as tba

from rentfrontier import building_zones_floor as bzf
from rentfrontier import building_zones_floor_asof as bzfa
from rentfrontier import building_zones_floor_asof2 as bzfa2
from rentfrontier import building_zones_mundlak as bzm
from rentfrontier import simulate, splits, two_zone


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
    assert set(simulate.SPECS) == {
        "building-zones-floor",
        "building-zones-location",
        "building-zones-parkfront",
        "building-zones-floor-asof2",
    }


def test_term_rows_with_no_terms():
    assert simulate.term_rows(np.zeros((4, 10, 0)), np.zeros(0), []) == []


def test_set_split_points_the_asof_design_at_the_fits_split(monkeypatch):
    monkeypatch.setattr(bzfa, "SPLIT", None)
    other = types.ModuleType("rentfrontier._sim_probe")
    other.SPLIT = None
    monkeypatch.setitem(sys.modules, other.__name__, other)
    frame, tables, units, trucks = tba.tbu._design()
    tables.pop("attrs")
    ads = tba.ads_for(frame)
    kw = dict(
        ads=ads,
        amenities=tba.amenities_for(ads),
        lots=tba.lots_for(frame),
        units=units,
        trucks=trucks,
        ages=tba.tbs.ages_for(frame),
        **tables,
    )
    asof = bzfa.design(frame, held=splits.latest_split(frame), **kw)
    simulate.set_split("latest")
    assert bzfa.SPLIT == "latest" and other.SPLIT == "latest"
    # With no mask the as-of design draws the fit's split, as the fit's own run did.
    d = bzfa2.design(frame, **kw)
    assert list(d.names) == list(asof.names)
    np.testing.assert_array_equal(d.x, asof.x)
    rec = bzfa2.run_record(d)
    assert rec["asof"]["split"] == "latest"
    assert rec["asof"]["pipeline_rows"] == str(bzfa2.ROWS)


def test_record_values_compare_through_json():
    rec = {"split": "latest", "lots": ["a", "b"], "pipeline_rows": "/r2"}
    fit = {"pipeline_rows": "/r2", "lots": ["a", "b"], "split": "latest"}
    assert simulate.same(rec, fit)
    assert not simulate.same(rec, fit | {"pipeline_rows": "/r1"})
    assert not simulate.same(rec | {"split": None}, fit)
    assert simulate.same(None, None)
    assert "asof" in simulate.SNAPSHOT_KEYS


def _mundlak(d, rows, seed=5):
    """A Mundlak fit's medians over the source columns and the building means."""
    rng = np.random.default_rng(seed)
    names = list(d.names)
    mk_names = names + list(bzm.COLUMNS)
    mk_beta = rng.normal(0, 0.05, len(mk_names))
    n = sum(s["sites"] for s in d.surfaces)
    means = simulate.site_means(d.x, names, d.site, n)
    return (
        mk_names,
        mk_beta,
        means,
        simulate.contextual(names, mk_names, mk_beta, means, rows),
    )


def test_site_means_are_the_mundlak_columns():
    *_, d = tbf._design()
    names = list(d.names)
    n = sum(s["sites"] for s in d.surfaces)
    means = simulate.site_means(d.x, names, d.site, n)
    assert means.shape == (n, len(bzm.COLUMNS))
    np.testing.assert_allclose(means[d.site], bzm.columns(d.x, names, d.site))


def test_mundlak_truth_maps_gammas_and_centres_the_level():
    *_, d = tbf._design()
    names = list(d.names)
    n = sum(s["sites"] for s in d.surfaces)
    rows = np.bincount(d.site, minlength=n).astype(float)
    rows[::7] = 0  # sites with no training rows still get a level
    mk_names, mk_beta, means, ctx = _mundlak(d, rows)
    by = dict(zip(mk_names, mk_beta))

    # Each gamma is the Mundlak fit's median for the mean of the same position in COLUMNS.
    np.testing.assert_allclose(ctx["gamma"], [by[c] for c in bzm.COLUMNS])
    assert set(ctx["beta"]) == set(names)
    raw = means @ ctx["gamma"]
    np.testing.assert_allclose(ctx["planted"] - raw, (ctx["planted"] - raw)[0])
    assert abs(np.average(ctx["planted"], weights=rows)) < 1e-12

    med = _medians(d)
    t = simulate.truth(names, med, "mundlak", context=ctx)
    np.testing.assert_allclose(t["beta"], [by[c] for c in names])
    np.testing.assert_allclose(t["bld"], med["bld"] + ctx["planted"])
    np.testing.assert_array_equal(t["planted"], ctx["planted"])

    # A coefficient the Mundlak fit lacks keeps the source fit's median.
    drop = names[3]
    keep = [i for i, c in enumerate(mk_names) if c != drop]
    ctx2 = simulate.contextual(
        names, [mk_names[i] for i in keep], mk_beta[keep], means, rows
    )
    t2 = simulate.truth(names, med, "mundlak", context=ctx2)
    assert t2["beta"][3] == med["beta"][3]

    with pytest.raises(ValueError, match="mundlak"):
        simulate.truth(names, med, "mundlak")
    with pytest.raises(ValueError, match="bld:mean_garden"):
        simulate.contextual(
            names,
            [c for c in mk_names if c != "bld:mean_garden"],
            np.array([b for c, b in zip(mk_names, mk_beta) if c != "bld:mean_garden"]),
            means,
            rows,
        )


def test_contextual_bias_pairs_gammas_with_unit_terms():
    gamma = {c: 0.01 * (j + 1) for j, c in enumerate(bzm.COLUMNS)}
    terms = [
        {"term": c, "truth": 0.1, "median": 0.13, "error": 0.03, "covered": False}
        for c in ("unit:log_size_rel", "unit:elev_floor_unknown", "unit:dishwasher")
    ]
    out = {r["mean_term"]: r for r in simulate.contextual_bias(terms, gamma)}
    assert set(out) == set(bzm.COLUMNS)
    assert out["bld:mean_log_size_rel"]["gamma"] == gamma["bld:mean_log_size_rel"]
    assert [u["term"] for u in out["bld:mean_log_size_rel"]["unit_terms"]] == [
        "unit:log_size_rel"
    ]
    assert out["bld:mean_log_size_rel"]["unit_terms"][0]["error"] == 0.03
    assert [u["term"] for u in out["bld:mean_floor_unknown"]["unit_terms"]] == [
        "unit:elev_floor_unknown"
    ]
    assert out["bld:mean_garden"]["unit_terms"] == []
    assert out["bld:mean_log_floor"]["unit_terms"] == []
