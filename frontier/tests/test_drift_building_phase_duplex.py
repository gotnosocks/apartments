"""L1 with a factor on the noise and the unit's process of duplex rows
(`rentfrontier.drift_building_phase_duplex`), and the drift model's `Design.unit_factor`."""

import dataclasses
import hashlib

import numpy as np
import pandas as pd
import pytest
import test_drift as td

from rentfrontier import (
    b0,
    building_zones,
    drift,
    drift_building,
    drift_building_phase,
    drift_building_phase_duplex,
    drift_score,
    run,
)

M = drift_building_phase_duplex
P, K = len(M.PHASES), len(M.MARKS)
FREE = P
# The unit factor of the tests' states, far enough from 1 that every gain matters.
KAPPA = 1.6


def test_a_cells_factor_is_its_phases_times_k_on_marked_rows():
    names, A = M.cells(), M.cell_map()
    assert names[:2] == ("10-13|other", "10-13|duplex") and len(names) == P * K
    assert A.shape == (P * K, FREE) and not A[0].any()
    assert M.DUPLEX == FREE - 1
    np.testing.assert_array_equal(A[:, M.DUPLEX], np.tile([0, 1], P))
    rng = np.random.default_rng(1)
    lf = 0.3 * rng.standard_normal(FREE)
    cell = np.exp(A @ lf)
    phase, k = M.factors(cell)
    np.testing.assert_allclose(phase, np.exp(np.r_[0, lf[: P - 1]]))
    np.testing.assert_allclose(k, np.exp(lf[M.DUPLEX]))
    np.testing.assert_allclose(cell.reshape(P, K), np.outer(phase, [1, k]))


def test_each_rows_mark_is_its_own_duplex_column():
    # Two ads of a unit: the marked ad's mark stays on its own row.
    frame = pd.DataFrame(
        {
            "unit_id": ["a", "a", "b", "b"],
            "duplex": pd.array([True, False, None, True], dtype="boolean"),
        }
    )
    np.testing.assert_array_equal(M.mark_index(frame), [1, 0, 0, 1])
    with pytest.raises(ValueError, match="duplex"):
        M.design(frame.drop(columns="duplex"))


def _duplexed(seed=4, marked=0.25, **kw):
    """`td._design` with random phases, about `marked` of the rows marked, the cells' map
    and k's column as the unit factor."""
    full = td._design(**kw)
    rng = np.random.default_rng(seed)
    n = len(full.y)
    cell = rng.integers(0, P, n) * K + (rng.random(n) < marked)
    return dataclasses.replace(
        full,
        phase=cell,
        phases=M.cells(),
        phase_map=M.cell_map(),
        unit_factor=M.DUPLEX,
    )


def _gained(st, rng):
    """`st` with random phase factors and k at KAPPA."""
    _, jnp = b0._jax()
    f = np.exp(0.2 * rng.standard_normal(FREE))
    f[M.DUPLEX] = KAPPA
    return st | {"phase_scale": jnp.asarray(f)}


def test_unit_loglik_matches_the_dense_density_as_k_moves():
    train, _, _ = td._split(_duplexed(per_unit=9))
    _, init, _, parts = td._sampler(train)
    jax, jnp = b0._jax()
    D = parts["data"]
    rng = np.random.default_rng(1)
    e = jnp.asarray(0.2 * rng.standard_normal(len(train.y)))
    st0 = _gained(td._state(init, parts), rng)

    def both(hyp, k):
        f = np.asarray(st0["phase_scale"]).copy()
        f[M.DUPLEX] = k
        st = st0 | {"hyp": jnp.log(jnp.asarray(hyp)), "phase_scale": jnp.asarray(f)}
        c = parts["weights"](D, st)
        gain = parts["row_gains"](D, st)
        ll = float(parts["unit_loglik"](D, st["hyp"], c, e, None, gain))
        V, _, cd = td._dense_cov(train, parts, st)
        ev = np.asarray(e)
        # The filter leaves out the rows' sum of log c / 2.
        want = (
            -0.5 * np.linalg.slogdet(V)[1]
            - 0.5 * np.log(cd).sum()
            - 0.5 * ev @ np.linalg.solve(V, ev)
        )
        return ll, want

    base = both((0.08, 0.1, 0.2), KAPPA)
    for hyp, k in (
        ((0.08, 0.1, 0.2), 1.0),
        ((0.08, 0.1, 0.2), 2.2),
        ((0.03, 0.2, 1.5), 0.8),
    ):
        got, want = both(hyp, k)
        np.testing.assert_allclose(got - base[0], want - base[1], rtol=1e-9)
        assert abs(want - base[1]) > 1.0


def test_scales_logp_matches_the_dense_density_as_the_factors_move():
    train, _, _ = td._split(_duplexed(per_unit=9))
    _, init, _, parts = td._sampler(train, dof=4.0)
    assert parts["phased"]
    jax, jnp = b0._jax()
    D = parts["data"]
    rng = np.random.default_rng(5)
    st = td._state(init, parts)
    S = len(parts["zone"])
    F = 0.1 * rng.standard_normal(S)
    tgt = F[train.site[parts["order"]]] + 0.2 * rng.standard_normal(len(train.y))
    m, s = parts["lam_moments"](jnp.log(st["nu"]))
    eta = (np.log(np.asarray(st["lam"])) - float(m)) / float(s)
    head = np.log([0.08, 0.1, 0.2, 0.05, 0.06, 0.07, 0.08, 4.0])

    def both(lf):
        x = np.concatenate([head, lf])
        got = parts["scales_logp"](
            D,
            jnp.asarray(x),
            jnp.asarray(eta),
            jnp.asarray(tgt),
            st["bld_sd"],
            None,
            jnp.asarray(F),
            st.get("kap"),
        )
        return float(got), td._scales_want(train, parts, st, eta, tgt, F, x)

    base = both(np.zeros(FREE))
    k_alone = np.zeros(FREE)
    k_alone[M.DUPLEX] = np.log(KAPPA)
    for lf in (
        k_alone,
        np.r_[[0.3, 0, 0, -0.2, 0, 0], [-0.3]],
        0.25 * rng.standard_normal(FREE),
    ):
        got, want = both(np.asarray(lf, float))
        np.testing.assert_allclose(got - base[0], want - base[1], rtol=1e-8)
        assert abs(want - base[1]) > 1.0


def test_draw_u_has_the_conditional_mean_and_covariance_under_the_gains():
    train, _, _ = td._split(_duplexed(n=400, per_unit=9, marked=0.4))
    _, init, _, parts = td._sampler(train)
    jax, jnp = b0._jax()
    D = parts["data"]
    rng = np.random.default_rng(2)
    st = _gained(td._state(init, parts), rng)
    e = jnp.asarray(0.2 * rng.standard_normal(len(train.y)))
    c = parts["weights"](D, st)
    gain = parts["row_gains"](D, st)
    assert np.isin(np.asarray(gain), [1.0, KAPPA]).all()
    w1, Wb = parts["unit_W"](D, st["hyp"], c, None, gain)
    draw = jax.jit(
        jax.vmap(lambda k: parts["draw_u"](D, k, st["hyp"], c, w1, Wb, e, gain))
    )
    u = np.asarray(draw(jax.random.split(jax.random.PRNGKey(3), 4000)))
    V, Kg, _ = td._dense_cov(train, parts, st)
    mean = Kg @ np.linalg.solve(V, np.asarray(e))
    cov = Kg - Kg @ np.linalg.solve(V, Kg)
    sd = np.sqrt(np.diag(cov))
    assert np.abs((u.mean(0) - mean) / sd).max() < 5 / np.sqrt(4000) * 1.2
    emp = np.cov(u.T)
    assert np.abs(emp - cov).max() < 0.15 * sd.max() ** 2


def test_predict_matches_the_dense_conditional_under_the_gains():
    train, test, _ = td._split(_duplexed(per_unit=9, marked=0.4))
    assert (test.unit < 0).any()
    _, init, _, parts = td._sampler(train)
    jax, jnp = b0._jax()
    D = parts["data"]
    rng = np.random.default_rng(4)
    st = _gained(td._state(init, parts), rng)
    st = st | {
        "theta": jnp.asarray(0.01 * rng.standard_normal(parts["G"])),
        "lev": jnp.asarray(0.1 * rng.standard_normal(st["lev"].shape[0])),
    }
    loc, sd, mean = (np.asarray(v) for v in parts["predict"](D, st))
    order = parts["order"]
    e = np.asarray(D["y"] - parts["all_means"](D, st["theta"]) - st["lev"][D["site"]])
    V, _, _ = td._dense_cov(train, parts, st)
    ss, s_d, tau = np.exp(np.asarray(st["hyp"]))
    t, unit = drift.years(train)[order], train.unit[order]
    pmap = train.phase_map[:, M.DUPLEX]
    g = KAPPA ** pmap[train.phase[order]]
    gp = KAPPA ** pmap[train.pred["phase"]]
    same = train.pred["unit"][:, None] == unit[None, :]
    k = np.where(
        same,
        ss**2
        + s_d**2 * np.exp(-np.abs(train.pred["years"][:, None] - t[None, :]) / tau),
        0.0,
    )
    k = gp[:, None] * k * g[None, :]
    want_mean = k @ np.linalg.solve(V, e)
    want_var = gp**2 * (ss**2 + s_d**2) - np.einsum(
        "pi,ip->p", k, np.linalg.solve(V, k.T)
    )
    np.testing.assert_allclose(mean, want_mean, atol=1e-6)
    np.testing.assert_allclose(sd, np.sqrt(want_var), atol=1e-6)
    # A marked row of a unit with no training row has k times the prior sd of u.
    unseen = train.pred["unit"] < 0
    for m in (0, 1):
        rows = unseen & (pmap[train.pred["phase"]] == m)
        assert rows.any()
        np.testing.assert_allclose(sd[rows], KAPPA**m * np.hypot(ss, s_d), rtol=1e-6)
    # The location adds the rows' own columns, walk and building level, as in L1.
    sl_b, sl_M, _, _ = parts["slices"]
    theta, lev = np.asarray(st["theta"]), np.asarray(st["lev"])
    alpha = train.names.index("alpha")
    others = [j for j in range(len(train.names)) if j != alpha]
    W = theta[sl_M]
    fixed = (
        test.x[:, others] @ theta[sl_b]
        + (1 - test.frac) * W[test.week]
        + test.frac * W[test.week + 1]
        + lev[test.site]
    )
    np.testing.assert_allclose(loc, fixed + mean, atol=1e-5)


def test_update_scales_moves_k_and_scales_the_marked_rows_noise():
    train, _, _ = td._split(_duplexed(per_unit=9))
    _, init, _, parts = td._sampler(train)
    jax, jnp = b0._jax()
    st = td._state(init, parts)
    assert st["phase_scale"].shape[-1] == FREE
    assert st["hyp_dirs"].shape == (8 + FREE,) * 2
    rng = np.random.default_rng(6)
    F = jnp.asarray(0.1 * rng.standard_normal(len(parts["zone"])))
    tgt = jnp.asarray(0.2 * rng.standard_normal(len(train.y)))
    new = parts["update_scales"](parts["data"], jax.random.PRNGKey(4), st, tgt, F)
    assert float(jnp.abs(new["phase_scale"] - st["phase_scale"]).min()) > 0
    sd = np.asarray(parts["row_sd"](parts["data"], new["sigma"], new["phase_scale"]))
    cell = train.phase[parts["order"]]
    f = np.asarray(new["phase_scale"])
    phase = np.r_[1.0, f[: P - 1]]
    want = (
        np.asarray(new["sigma"])[train.group[parts["order"]]]
        * phase[cell // K]
        * f[M.DUPLEX] ** (cell % K)
    )
    np.testing.assert_allclose(sd, want, rtol=1e-6)


def test_a_run_finds_a_planted_k():
    """Marked rows with noise and a unit level both 1.5 times as wide as the others' give k
    near 1.5, and the phase factors stay near 1."""
    full = _duplexed(n=1600, per_unit=6, marked=0.3)
    rng = np.random.default_rng(7)
    marked = full.phase % K == 1
    # Simulated noise is sigma times a Student-t on 4 degrees of freedom, so an added draw
    # of the same law scaled by sqrt(1.5^2 - 1) widens a marked row's noise 1.5 times.
    sigma = np.array([0.12, 0.15, 0.18, 0.2])[full.group]
    extra = np.sqrt(1.5**2 - 1) * sigma * rng.standard_t(4.0, len(full.y))
    # Each unit gets a level v, and a marked row takes 1.5 v, as D1 scales u.
    v = 0.1 * rng.standard_normal(full.units)[full.unit]
    gain = np.where(marked, 1.5, 1.0)
    full = dataclasses.replace(full, y=full.y + gain * v + np.where(marked, extra, 0.0))
    train, _, _ = td._split(full)
    out = M.run(
        train,
        building_zones.Priors(),
        drift.Settings(chains=2, warmup=150, draws=60, level_dof=4.0, seed=3),
        log=lambda m: None,
    )
    phase, k = M.factors(out["kept"]["phase_scale"].reshape(-1, P * K))
    assert 1.3 < np.median(k) < 1.75, np.median(k)
    np.testing.assert_allclose(np.median(phase, axis=0), 1.0, atol=0.2)


@pytest.fixture(scope="module")
def duplex_run():
    full = _duplexed(n=400, per_unit=9)
    train, _, held = td._split(full)
    out = M.run(
        train,
        building_zones.Priors(),
        drift.Settings(
            chains=2, warmup=60, draws=8, keep_every=2, level_dof=4.0, seed=3
        ),
        log=lambda m: None,
    )
    return full, held, out


def test_a_run_keeps_every_cells_factor_and_traces_k(duplex_run):
    full, held, out = duplex_run
    trace, kept = out["trace"], out["kept"]
    assert trace["phase_scale"].shape == (2, 8, P * K)
    assert kept["phase_scale"].shape == (2, 4, P * K)
    phase, k = M.factors(trace["phase_scale"])
    np.testing.assert_allclose(
        trace["phase_scale"],
        (
            phase[..., :, None] * np.stack([np.ones_like(k), k], -1)[..., None, :]
        ).reshape(2, 8, -1),
        rtol=1e-6,
    )
    np.testing.assert_array_equal(kept["pred_phase"], full.phase[held])
    assert len(out["result"]["gibbs"]["hyp_dirs"]) == 8 + FREE
    rows = drift.diagnostics(trace, full.names)["per_quantity"]
    # k is the factor of the reference phase's marked cell.
    assert "phase_scale[1]" in rows
    assert {f"phase_scale[{p * K}]" for p in range(1, P)} <= set(rows)


def test_scores_scale_each_rows_sigma_by_its_cells_factor(duplex_run, tmp_path):
    _, held, out = duplex_run
    d = tmp_path / "r"
    d.mkdir()
    np.savez(
        d / "posterior.npz",
        **{f"trace/{k}": v for k, v in out["trace"].items()},
        **{f"kept/{k}": v for k, v in out["kept"].items()},
        names=np.array(["a"]),
        heldout=held,
    )
    got = drift_score.score_run(d)
    kept = out["kept"]
    flat = lambda k: kept[k].reshape(-1, *kept[k].shape[2:])  # noqa: E731
    cell, group = kept["pred_phase"], kept["pred_group"]
    phase, k = M.factors(flat("phase_scale"))
    want = drift_score.score_rows(
        flat("pred_loc"),
        flat("pred_unit_sd"),
        flat("sigma")[:, group] * phase[:, cell // K] * k[:, None] ** (cell % K),
        flat("nu"),
        kept["pred_y"],
        0,
    )
    np.testing.assert_allclose(got["elpd"], want["elpd"], rtol=1e-6)


# The sha256 of every traced and kept array of the run below on the CPU, as drawn when the
# duplex factor was added. A deliberate change to the duplex model's draws changes it.
DUPLEX_RUN_SHA256 = "60d1f39172dab13338739b4bd82d0703ea8abbfe5bdad47a1c211c06162993c3"


def test_a_duplex_design_draws_what_it_drew_when_the_factor_was_added():
    train, _, _ = td._split(_duplexed(n=400, per_unit=9))
    out = M.run(
        train,
        building_zones.Priors(),
        drift.Settings(chains=2, warmup=60, draws=8, level_dof=4.0, seed=3),
        log=lambda m: None,
    )
    arrays = {f"trace/{k}": v for k, v in out["trace"].items()}
    arrays |= {f"kept/{k}": v for k, v in out["kept"].items()}
    h = hashlib.sha256()
    for k in sorted(arrays):
        h.update(k.encode())
        h.update(np.ascontiguousarray(arrays[k]).tobytes())
    assert h.hexdigest() == DUPLEX_RUN_SHA256, h.hexdigest()


def test_the_model_is_l1_with_the_duplex_factor():
    assert M.LEVEL_DOF == drift_building.LEVEL_DOF
    assert M.GROUPS == ("building",)
    assert M.NAME == "drift-building-phase-duplex"
    assert M.PHASES == drift_building_phase.PHASES
    assert M.run is drift_building_phase.run
    assert (
        '("drift-building-phase-duplex", "drift_building_phase_duplex")'
        in open(run.__file__).read()
    )
    d = _duplexed(n=300)
    rec = M.run_record(d)["phase"]
    assert rec["reference"] == "10-13" and rec["marks"] == ["other", "duplex"]
    assert sum(rec["rows"].values()) == sum(rec["mark_rows"].values()) == len(d.y)
    assert rec["mark_rows"]["duplex"] == int((d.phase % K == 1).sum())
