"""The building model with a Student-t lasting level for each unit
(`rentfrontier.drift_building_unitt`), and the drift model's `unit_t` in general."""

import dataclasses

import numpy as np
import pytest
import test_drift as td
from scipy import special, stats

from rentfrontier import (
    b0,
    building_zones,
    drift,
    drift_building,
    drift_building_unitt,
    run,
)


def _sampler(train, dof=4.0):
    settings = drift.Settings(chains=2, warmup=10, draws=10, level_dof=dof)
    return drift.make_sampler(train, building_zones.Priors(), settings, unit_t=True)


def _state(init, parts, seed=0, hyp=(0.08, 0.1, 0.2), unit_dof=3.0):
    """`td._state` with random unit mixing scales and prior draws for the rows to
    predict."""
    _, jnp = b0._jax()
    st = td._state(init, parts, seed, hyp)
    rng = np.random.default_rng(seed + 1)
    U, P = st["ukap"].shape[0], st["pred_ukap"].shape[0]
    return st | {
        "ukap": jnp.asarray(rng.gamma(1.5, 1 / 1.5, U)),
        "pred_ukap": jnp.asarray(rng.gamma(1.5, 1 / 1.5, P)),
        "unit_dof": jnp.asarray(unit_dof),
    }


def _lasting(train, parts, st):
    """In the sampler's row order, each row's unit and its lasting variance ss^2 / kap."""
    unit = train.unit[parts["order"]]
    ss = np.exp(float(st["hyp"][0]))
    return unit, ss**2 / np.asarray(st["ukap"])[unit]


def _extra(train, parts, st):
    """What `td._dense_cov`'s K misses under `unit_t`: the lasting part's change from ss^2
    to ss^2 / kap within each unit."""
    unit, v = _lasting(train, parts, st)
    ss = np.exp(float(st["hyp"][0]))
    return np.where(unit[:, None] == unit[None, :], (v - ss**2)[:, None], 0.0)


def _dense(train, parts, st):
    V, K, c = td._dense_cov(train, parts, st)
    X = _extra(train, parts, st)
    return V + X, K + X, c


def test_init_and_parts_carry_the_unit_scales():
    train, _, _ = td._split(td._design(n=400, per_unit=9))
    _, init, _, parts = _sampler(train)
    jax, _ = b0._jax()
    st = init(jax.random.split(jax.random.PRNGKey(0), 2))
    assert parts["unit_t"]
    assert st["ukap"].shape == (2, train.units)
    assert st["pred_ukap"].shape == (2, len(train.pred["unit"]))
    assert st["unit_dof"].shape == (2,)


def test_unit_loglik_reads_the_unit_scales():
    train, _, _ = td._split(td._design(per_unit=9))
    _, init, _, parts = _sampler(train)
    _, jnp = b0._jax()
    D = parts["data"]
    rng = np.random.default_rng(1)
    e = jnp.asarray(0.2 * rng.standard_normal(len(train.y)))

    def both(hyp, seed):
        # The rows' lam stay put, so the constant left out stays put too.
        kap = np.random.default_rng(seed).gamma(1.5, 1 / 1.5, train.units)
        st = _state(init, parts, hyp=hyp) | {"ukap": jnp.asarray(kap)}
        c = parts["weights"](D, st)
        ll = float(parts["unit_loglik"](D, st["hyp"], c, e, st["ukap"]))
        V, _, _ = _dense(train, parts, st)
        ev = np.asarray(e)
        return ll, -0.5 * np.linalg.slogdet(V)[1] - 0.5 * ev @ np.linalg.solve(V, ev)

    a, b = both((0.08, 0.1, 0.2), 0), both((0.03, 0.2, 1.5), 3)
    np.testing.assert_allclose(a[0] - b[0], a[1] - b[1], rtol=1e-9)


def test_draw_us_has_the_joint_conditional_mean_and_covariance():
    train, _, _ = td._split(td._design(n=400, per_unit=9))
    _, init, _, parts = _sampler(train)
    jax, jnp = b0._jax()
    D = parts["data"]
    st = _state(init, parts)
    rng = np.random.default_rng(2)
    e = jnp.asarray(0.2 * rng.standard_normal(len(train.y)))
    c = parts["weights"](D, st)
    w1, Wb = parts["unit_W"](D, st["hyp"], c, st["ukap"])
    draw = jax.jit(
        jax.vmap(lambda k: parts["draw_us"](D, k, st["hyp"], c, w1, Wb, e, st["ukap"]))
    )
    u, s = (np.asarray(v) for v in draw(jax.random.split(jax.random.PRNGKey(3), 4000)))
    V, K, _ = _dense(train, parts, st)
    unit, _ = _lasting(train, parts, st)
    ss = np.exp(float(st["hyp"][0]))
    vk = ss**2 / np.asarray(st["ukap"])
    # Cov(s_k, u_i) is v_k for a row of unit k.
    C = np.where(np.arange(train.units)[:, None] == unit[None, :], vk[:, None], 0.0)
    z = np.concatenate([u, s], axis=1)
    A = np.concatenate([K, C])
    mean = A @ np.linalg.solve(V, np.asarray(e))
    prior = np.block([[K, C.T], [C, np.diag(vk)]])
    cov = prior - A @ np.linalg.solve(V, A.T)
    sd = np.sqrt(np.diag(cov))
    assert np.abs((z.mean(0) - mean) / sd).max() < 5 / np.sqrt(4000) * 1.2
    assert np.abs(np.cov(z.T) - cov).max() < 0.15 * sd.max() ** 2


def test_scales_logp_matches_the_dense_density_as_the_units_dof_moves():
    train, _, _ = td._split(td._design(per_unit=9))
    _, init, _, parts = _sampler(train)
    _, jnp = b0._jax()
    D = parts["data"]
    rng = np.random.default_rng(5)
    st = _state(init, parts)
    F = 0.1 * rng.standard_normal(len(parts["zone"]))
    tgt = F[train.site[parts["order"]]] + 0.2 * rng.standard_normal(len(train.y))
    m, s = parts["lam_moments"](jnp.log(st["nu"]))
    eta = (np.log(np.asarray(st["lam"])) - float(m)) / float(s)
    a0 = float(st["unit_dof"]) / 2
    m0, s0 = special.digamma(a0) - np.log(a0), np.sqrt(special.polygamma(1, a0))
    keta = (np.log(np.asarray(st["ukap"])) - m0) / s0

    def both(hyp, nu_u):
        x = np.concatenate(
            [np.log(hyp), np.log(np.asarray(st["sigma"])), [np.log(float(st["nu"]))]]
        )
        got = parts["scales_logp"](
            D,
            jnp.asarray(np.r_[x, np.log(nu_u)]),
            jnp.asarray(eta),
            jnp.asarray(tgt),
            st["bld_sd"],
            None,
            jnp.asarray(F),
            st["kap"],
            jnp.asarray(keta),
        )
        a = nu_u / 2
        m, s = special.digamma(a) - np.log(a), np.sqrt(special.polygamma(1, a))
        kap = np.exp(m + s * keta)
        at = st | {"hyp": jnp.log(jnp.asarray(hyp)), "ukap": jnp.asarray(kap)}
        ua, ub = drift.UNIT_DOF_PRIOR
        want = (
            td._scales_want(train, parts, st, eta, tgt, F, x, _extra(train, parts, at))
            + stats.gamma.logpdf(kap, a, scale=1 / a).sum()
            + np.log(kap * s).sum()
            + ua * np.log(nu_u)
            - ub * nu_u
        )
        return float(got), want

    base = both((0.08, 0.1, 0.2), 3.0)
    for at in (((0.08, 0.1, 0.2), 9.0), ((0.05, 0.07, 0.6), 1.7)):
        got, want = both(*at)
        np.testing.assert_allclose(got - base[0], want - base[1], rtol=1e-8)
        assert abs(want - base[1]) > 1.0


def test_update_unit_t_keeps_each_units_lasting_variance_along_the_orbit():
    train, _, _ = td._split(td._design(n=400, per_unit=9))
    _, init, _, parts = _sampler(train)
    jax, jnp = b0._jax()
    st = _state(init, parts)
    rng = np.random.default_rng(6)
    s = jnp.asarray(0.08 * rng.standard_t(2.0, train.units))
    keys = jax.random.split(jax.random.PRNGKey(7), 3000)
    nu, kap, hyp, pred = jax.vmap(
        lambda k: parts["update_unit_t"](k, st, s, st["hyp"])
    )(keys)
    nu, kap, hyp, pred = (np.asarray(v) for v in (nu, kap, hyp, pred))
    # The draw moves only log ss among the unit scales.
    np.testing.assert_array_equal(hyp[:, 1:], np.broadcast_to(st["hyp"][1:], (3000, 2)))
    assert np.ptp(hyp[:, 0]) > 0 and (nu > 0).all() and (kap > 0).all()
    # The rows to predict take kap from Gamma(nu / 2, rate nu / 2), with mean 1.
    assert pred.shape == (3000, len(train.pred["unit"]))
    assert abs(pred.mean() - 1) < 0.05
    # The orbit keeps kap / ss^2. Before it, kap_k is Gamma((nu + 1) / 2, rate
    # (nu + s_k^2 / ss^2) / 2) at the old ss, so kap_k / ss^2 has mean
    # (nu + 1) / (nu ss^2 + s_k^2).
    ss2 = np.exp(2 * float(st["hyp"][0]))
    held = kap / np.exp(2 * hyp[:, :1])
    ratio = held * (nu[:, None] * ss2 + np.asarray(s)[None] ** 2) / (nu[:, None] + 1)
    assert abs(ratio.mean() - 1) < 0.05


def test_predict_reads_each_units_scale_and_the_prior_draw_for_a_new_unit():
    full = td._design(per_unit=9)
    train, test, _ = td._split(full)
    _, init, _, parts = _sampler(train)
    jax, jnp = b0._jax()
    D = parts["data"]
    st = _state(init, parts)
    rng = np.random.default_rng(4)
    st = st | {
        "theta": jnp.asarray(0.01 * rng.standard_normal(parts["G"])),
        "lev": jnp.asarray(0.1 * rng.standard_normal(st["lev"].shape[0])),
    }
    _, sd, mean = (np.asarray(v) for v in parts["predict"](D, st))
    order = parts["order"]
    e = np.asarray(D["y"] - parts["all_means"](D, st["theta"]) - st["lev"][D["site"]])
    V, _, _ = _dense(train, parts, st)
    ss, s_d, tau = np.exp(np.asarray(st["hyp"]))
    t, unit = drift.years(train)[order], train.unit[order]
    pu = train.pred["unit"]
    kp = np.where(pu >= 0, np.asarray(st["ukap"])[np.maximum(pu, 0)], st["pred_ukap"])
    vp = ss**2 / kp
    same = pu[:, None] == unit[None, :]
    dt = np.abs(train.pred["years"][:, None] - t[None, :])
    k = np.where(same, vp[:, None] + s_d**2 * np.exp(-dt / tau), 0.0)
    want_var = vp + s_d**2 - np.einsum("pi,ip->p", k, np.linalg.solve(V, k.T))
    np.testing.assert_allclose(mean, k @ np.linalg.solve(V, e), atol=1e-6)
    np.testing.assert_allclose(sd, np.sqrt(want_var), atol=1e-6)
    unseen = pu < 0
    assert unseen.any() and (mean[unseen] == 0).all()
    np.testing.assert_allclose(sd[unseen], np.sqrt(vp[unseen] + s_d**2), rtol=1e-6)


def _planted(dof, n=6000, per_unit=6, ss=0.25, sd=0.04, tau=0.3, seed=5):
    """`td._design` with unit levels from Student-t(dof) with scale ss (normal when dof is
    None) and an Ornstein-Uhlenbeck walk."""
    full = td._design(n=n, per_unit=per_unit)
    rng = np.random.default_rng(seed)
    t, unit = drift.years(full), full.unit
    z = rng.standard_t(dof, full.units) if dof else rng.standard_normal(full.units)
    u = ss * z[unit]
    for k in range(full.units):
        rows = np.flatnonzero(unit == k)
        dt = np.abs(t[rows][:, None] - t[rows][None, :])
        u[rows] += rng.multivariate_normal(
            np.zeros(len(rows)), sd**2 * np.exp(-dt / tau)
        )
    return dataclasses.replace(full, y=full.y + u)


@pytest.mark.parametrize("dof", [2.5, None])
def test_recovers_a_heavy_and_a_light_tailed_unit_level(dof):
    train, test, held = td._split(_planted(dof))
    out = drift.run(
        train,
        building_zones.Priors(),
        drift.Settings(chains=2, warmup=150, draws=300, keep_every=5),
        log=lambda m: None,
        gp=None,
        unit_t=True,
    )
    x = out["trace"]["unit_dof"]
    assert x.shape == (2, 300) and np.ptp(x) > 0
    if dof:
        assert np.median(x) < 4 and np.quantile(x, 0.99) < 6, np.quantile(
            x, [0.5, 0.99]
        )
    else:
        assert np.median(x) > 8 and np.quantile(x, 0.01) > 3, np.quantile(
            x, [0.01, 0.5]
        )
    # The planted Student-t's scale is 0.25. A normal level of sd 0.25 matches a Student-t
    # whose sd, scale * sqrt(nu / (nu - 2)), is 0.25.
    scale = out["trace"]["unit_sd"]
    if not dof:
        keep = x > 2
        scale = scale[keep] * np.sqrt(x[keep] / (x[keep] - 2))
    lo, hi = np.quantile(scale, [0.001, 0.999])
    assert lo < 0.25 < hi, (lo, hi)
    assert out["kept"]["unit_dof"].shape == (2, 60)
    assert "unit_dof" in drift.diagnostics(out["trace"], train.names)["per_quantity"]
    assert "unit_dof" in drift.summarize(out["kept"], train.names)["unit"]


def test_the_model_is_the_building_model_with_student_t_unit_levels():
    assert drift_building_unitt.LEVEL_DOF == drift_building.LEVEL_DOF
    assert drift_building_unitt.GROUPS == drift_building.GROUPS
    assert drift_building_unitt.NAME == "drift-building-unitt"
    assert (
        '("drift-building-unitt", "drift_building_unitt")' in open(run.__file__).read()
    )
    rec = drift_building_unitt.run_record(td._design(n=300))
    assert rec["unit_t"]["unit_dof_prior"] == "Gamma(2.0, rate 0.1)"
