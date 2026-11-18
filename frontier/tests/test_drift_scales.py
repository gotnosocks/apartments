"""`drift.Settings.scales_fixed`: the sweep holds a set's scales and draws the rest."""

import dataclasses

import numpy as np
import pytest
import test_drift as td
import test_drift_local as tl

from rentfrontier import b0, building_zones, drift, drift_building, drift_scales

SET = {
    "nu": 3.0,
    "sigma": [0.11, 0.12, 0.13, 0.14],
    "unit_sd": 0.05,
    "drift_sd": 0.06,
    "drift_tau": 2.5,
    "bld_sd": [0.21, 0.17],
    "building_ar_sd": 0.04,
    "building_ar_rho": 0.8,
    "tau": 0.004,
}


def _train():
    full = td._design(n=600, per_unit=4)
    train, _, _ = td._split(full)
    return train


def _sampler(train, scales, dof=4.0):
    settings = drift.Settings(
        chains=2, warmup=10, draws=10, site_block=7, level_dof=dof
    )
    return drift.make_sampler(
        train,
        building_zones.Priors(),
        settings,
        groups=tl._groups(train),
        scales_fixed=scales,
    )


def _sweeps(sweep, init, count=6, seed=5):
    jax, _ = b0._jax()
    key = jax.random.PRNGKey(seed)
    states = [init(jax.random.split(key, 2))]
    for _ in range(count):
        key, sub = jax.random.split(key)
        st, _ = sweep(jax.random.split(sub, 2), states[-1])
        states.append(st)
    return states


def test_the_sweep_holds_the_sets_scales_and_draws_the_rest():
    train = _train()
    sweep, init, _, parts = _sampler(train, SET)
    assert parts["held"] == {"noise", "cells", "tau"}
    states = _sweeps(sweep, init)
    want = {
        "nu": SET["nu"],
        "sigma": SET["sigma"],
        "hyp": np.log([SET["unit_sd"], SET["drift_sd"], SET["drift_tau"]]),
        "bld_sd": SET["bld_sd"],
        "tau": SET["tau"],
    }
    par = [np.log(SET["building_ar_sd"]), np.log(0.8 / 0.2)]
    for st in states:
        for k, v in want.items():
            got = np.asarray(st[k])
            np.testing.assert_allclose(got, np.broadcast_to(v, got.shape), rtol=1e-12)
        np.testing.assert_allclose(np.asarray(st["ar_par"])[:, 0], [par, par])
    first, last = states[1], states[-1]
    # The amplitudes are outside the set, and the sweep draws them with everything else.
    for k in ("amp", "theta", "lev", "lam", "kap"):
        assert not np.allclose(np.asarray(first[k]), np.asarray(last[k])), k
    assert not np.allclose(np.asarray(first["ar"][0]), np.asarray(last["ar"][0]))
    jax, _ = b0._jax()
    assert all(np.isfinite(np.asarray(v)).all() for v in jax.tree.leaves(last))


def test_a_sampler_with_no_set_draws_every_scale():
    train = _train()
    sweep, init, _, parts = _sampler(train, None)
    assert parts["held"] == frozenset()
    states = _sweeps(sweep, init, count=3)
    for k in ("nu", "sigma", "hyp", "bld_sd", "tau", "amp", "ar_par"):
        assert not np.allclose(np.asarray(states[1][k]), np.asarray(states[-1][k])), k


def test_a_set_holds_all_of_a_steps_scales_or_none():
    groups = [{"name": "building", "collapsed": True}]
    assert drift.held_steps(None, groups) == frozenset()
    assert drift.held_steps({"tau": 0.1, "amp": [1.0, 1.0]}, groups) == {"tau", "amp"}
    with pytest.raises(AssertionError, match="in one step"):
        drift.held_steps({"nu": 2.0, "sigma": [0.1] * 4}, groups)
    with pytest.raises(AssertionError, match="not scales to hold"):
        drift.held_steps({"tau": 0.1, "unit_dof": 3.0}, groups)
    with pytest.raises(AssertionError, match="collapsed"):
        drift.held_steps(
            {k: SET[k] for k in ("bld_sd",)} | {"None_ar_sd": 1, "None_ar_rho": 0.5}, []
        )


def test_the_stored_sets_name_whole_steps_and_a_source():
    groups = [{"name": "building", "collapsed": True}]
    assert set(drift_scales.SETS) == set(drift_scales.SOURCES)
    for scales in drift_scales.SETS.values():
        assert drift.held_steps(scales, groups) == {"noise", "cells", "tau"}
        assert 0 < scales["building_ar_rho"] < 1
        assert all(np.all(np.asarray(v) > 0) for v in scales.values())


def test_a_run_records_the_set_and_its_gate_leaves_the_held_scales_out(monkeypatch):
    monkeypatch.setitem(drift_scales.SETS, "test", SET)
    monkeypatch.setitem(drift_scales.SOURCES, "test", "a test")
    train = _train()
    settings = drift.Settings(
        chains=2,
        warmup=12,
        draws=20,
        keep_every=5,
        site_block=7,
        level_dof=4.0,
        scales_fixed="test",
    )
    lines = []
    out = drift.run(
        train,
        building_zones.Priors(),
        settings,
        log=lines.append,
        gp=None,
        groups=tl._groups(train),
    )
    assert any("scales held at the set 'test'" in line for line in lines)
    assert not any("slice directions" in line for line in lines)
    assert out["result"]["gibbs"]["scales_fixed"] == {
        "set": "test",
        "source": "a test",
        "values": SET,
    }
    trace = out["trace"]
    for k in ("nu", "tau", "unit_sd", "building_ar_sd", "building_ar_rho"):
        assert np.ptp(trace[k]) == 0, k
    np.testing.assert_allclose(trace["unit_sd"], SET["unit_sd"])
    np.testing.assert_allclose(trace["building_ar_rho"], SET["building_ar_rho"])
    diag = drift_building.diagnostics(trace, train.names)
    rows = diag["per_quantity"]
    assert not {"nu", "tau", "unit_sd", "drift_sd", "drift_tau"} & set(rows)
    assert not any(k.startswith(("sigma", "bld_sd", "building_ar")) for k in rows)
    assert any(k.startswith("amp") for k in rows)
    assert np.isfinite(diag["max_rhat"]) and np.isfinite(diag["min_ess"])


def test_the_command_line_takes_a_stored_set():
    base = ["--split", "latest", "--name", "x"]
    assert drift.run_parser().parse_args(base).scales_fixed is None
    args = drift.run_parser().parse_args([*base, "--scales-fixed", "base-n9"])
    assert args.scales_fixed == "base-n9"
    assert "scales_fixed" in {f.name for f in dataclasses.fields(drift.Settings)}
