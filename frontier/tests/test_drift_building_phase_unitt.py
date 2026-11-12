"""L1 with a Student-t lasting level for each unit at fixed degrees of freedom
(`rentfrontier.drift_building_phase_unitt`), and the drift model's noise phases together
with `unit_t`, its degrees of freedom free or fixed."""

import hashlib

import numpy as np
import test_drift as td
import test_drift_building_phase as tp
import test_drift_building_unitt as tu
from scipy import special, stats

from rentfrontier import (
    b0,
    building_zones,
    drift,
    drift_building_phase,
    drift_building_phase_unitt,
    run,
)

P = drift_building_phase.PHASES
DOF = drift_building_phase_unitt.UNIT_DOF


def _sampler(train, fixed=DOF):
    settings = drift.Settings(chains=2, warmup=10, draws=10, level_dof=4.0)
    return drift.make_sampler(
        train, building_zones.Priors(), settings, unit_t=True, unit_dof_fixed=fixed
    )


def _setup(fixed, seed=5):
    """A phased design's training rows, its sampler's parts, a state, the targets, the
    buildings' means and the rows' and units' standardized log mixing scales."""
    train, _, _ = td._split(tp._phased(per_unit=9))
    _, init, _, parts = _sampler(train, fixed)
    assert parts["phased"] and parts["unit_t"]
    _, jnp = b0._jax()
    rng = np.random.default_rng(seed)
    st = tu._state(init, parts, unit_dof=DOF)
    F = 0.1 * rng.standard_normal(len(parts["zone"]))
    tgt = F[train.site[parts["order"]]] + 0.2 * rng.standard_normal(len(train.y))
    m, s = parts["lam_moments"](jnp.log(st["nu"]))
    eta = (np.log(np.asarray(st["lam"])) - float(m)) / float(s)
    a0 = DOF / 2
    m0, s0 = special.digamma(a0) - np.log(a0), np.sqrt(special.polygamma(1, a0))
    keta = (np.log(np.asarray(st["ukap"])) - m0) / s0
    return train, parts, st, tgt, F, eta, keta


def _logp(parts, st, x, eta, tgt, F, keta):
    _, jnp = b0._jax()
    return float(
        parts["scales_logp"](
            parts["data"],
            jnp.asarray(x),
            jnp.asarray(eta),
            jnp.asarray(tgt),
            st["bld_sd"],
            None,
            jnp.asarray(F),
            st["kap"],
            jnp.asarray(keta),
        )
    )


def test_scales_logp_matches_the_dense_density_with_phases_and_a_free_unit_dof():
    train, parts, st, tgt, F, eta, keta = _setup(None)
    _, jnp = b0._jax()

    def both(hyp, lf, nu_u):
        x = np.concatenate(
            [
                np.log(hyp),
                np.log(np.asarray(st["sigma"])),
                [np.log(float(st["nu"]))],
                lf,
            ]
        )
        got = _logp(parts, st, np.r_[x, np.log(nu_u)], eta, tgt, F, keta)
        a = nu_u / 2
        m, s = special.digamma(a) - np.log(a), np.sqrt(special.polygamma(1, a))
        kap = np.exp(m + s * keta)
        at = st | {"hyp": jnp.log(jnp.asarray(hyp)), "ukap": jnp.asarray(kap)}
        ua, ub = drift.UNIT_DOF_PRIOR
        want = (
            td._scales_want(
                train, parts, st, eta, tgt, F, x, tu._extra(train, parts, at)
            )
            + stats.gamma.logpdf(kap, a, scale=1 / a).sum()
            + np.log(kap * s).sum()
            + ua * np.log(nu_u)
            - ub * nu_u
        )
        return got, want

    zero = np.zeros(len(P) - 1)
    base = both((0.08, 0.1, 0.2), zero, DOF)
    for at in (
        ((0.08, 0.1, 0.2), np.array([0.3, 0, 0, 0, -0.2, 0]), DOF),
        ((0.08, 0.1, 0.2), zero, 9.0),
        ((0.05, 0.07, 0.6), np.array([0, -0.4, 0.1, 0, 0.2, 0]), 1.7),
    ):
        got, want = both(*at)
        np.testing.assert_allclose(got - base[0], want - base[1], rtol=1e-8)
        assert abs(want - base[1]) > 1.0


def test_scales_logp_matches_the_dense_density_with_phases_and_a_fixed_unit_dof():
    train, parts, st, tgt, F, eta, keta = _setup(DOF)
    _, jnp = b0._jax()
    # log nu_u is out of the scale step's coordinates, and out of its slice directions.
    x0 = np.asarray(parts["scales_x"](st))
    assert len(x0) == 8 + len(P) - 1
    assert st["hyp_dirs"].shape == (len(x0),) * 2
    extra = tu._extra(train, parts, st)

    def both(hyp, lf):
        x = np.concatenate(
            [
                np.log(hyp),
                np.log(np.asarray(st["sigma"])),
                [np.log(float(st["nu"]))],
                lf,
            ]
        )
        got = _logp(parts, st, x, eta, tgt, F, keta)
        at = st | {"hyp": jnp.log(jnp.asarray(hyp))}
        # With nu_u fixed the kap stay put, so their density is a constant.
        want = td._scales_want(
            train, parts, st, eta, tgt, F, x, tu._extra(train, parts, at)
        )
        return got, want

    zero = np.zeros(len(P) - 1)
    base = both((0.08, 0.1, 0.2), zero)
    assert np.abs(extra).max() > 0
    for at in (
        ((0.08, 0.1, 0.2), np.array([0.3, 0, 0, 0, -0.2, 0])),
        ((0.05, 0.07, 0.6), zero),
        ((0.03, 0.2, 1.5), np.array([0, -0.4, 0.1, 0, 0.2, 0])),
    ):
        got, want = both(*at)
        np.testing.assert_allclose(got - base[0], want - base[1], rtol=1e-8)
        assert abs(want - base[1]) > 1.0


def test_update_unit_t_holds_the_dof_and_draws_the_kap():
    train, parts, st, _, _, _, _ = _setup(DOF)
    jax, jnp = b0._jax()
    rng = np.random.default_rng(6)
    s = jnp.asarray(0.08 * rng.standard_t(DOF, train.units))
    keys = jax.random.split(jax.random.PRNGKey(7), 2000)
    nu, kap, hyp, pred = (
        np.asarray(v)
        for v in jax.vmap(lambda k: parts["update_unit_t"](k, st, s, st["hyp"]))(keys)
    )
    assert (nu == DOF).all()
    assert np.ptp(kap, axis=0).min() > 0 and np.ptp(hyp[:, 0]) > 0
    # Before the orbit kap_k is Gamma((nu + 1) / 2, rate (nu + s_k^2 / ss^2) / 2) at the
    # old ss, and the orbit keeps kap / ss^2.
    ss2 = np.exp(2 * float(st["hyp"][0]))
    held = kap / np.exp(2 * hyp[:, :1])
    ratio = held * (DOF * ss2 + np.asarray(s)[None] ** 2) / (DOF + 1)
    assert abs(ratio.mean() - 1) < 0.05
    assert abs(pred.mean() - 1) < 0.05


def test_sweeps_keep_the_dof_at_three_and_move_the_kap():
    train, _, _ = td._split(tp._phased(n=400, per_unit=9))
    sweep, init, _, parts = _sampler(train)
    jax, _ = b0._jax()
    assert not parts["dof_free"]
    st = init(jax.random.split(jax.random.PRNGKey(0), 2))
    first = np.asarray(st["ukap"])
    key = jax.random.PRNGKey(1)
    for _ in range(5):
        key, sub = jax.random.split(key)
        st, out = sweep(jax.random.split(sub, 2), st)
        assert (np.asarray(st["unit_dof"]) == DOF).all()
        assert "unit_dof" not in out
    assert np.abs(np.asarray(st["ukap"]) - first).min() > 0
    assert np.ptp(np.asarray(st["ukap"]), axis=1).min() > 0


# The sha256 of every traced and kept array of the run below on the CPU, as drawn when
# drift-building-phase-unitt was added. A deliberate change to the model's draws changes it.
PHASE_UNITT_RUN_SHA256 = (
    "e54260ea0c9e9964d035e0832b2e3cbd962f98dab49383f7859ef0e6d91ff234"
)


def test_a_run_draws_what_it_drew_when_the_model_was_added():
    train, _, _ = td._split(tp._phased(n=400, per_unit=9))
    out = drift_building_phase_unitt.run(
        train,
        building_zones.Priors(),
        drift.Settings(chains=2, warmup=60, draws=8, level_dof=4.0, seed=3),
        log=lambda m: None,
    )
    assert "unit_dof" not in out["trace"] and "unit_dof" not in out["kept"]
    assert out["trace"]["phase_scale"].shape == (2, 8, len(P))
    assert len(out["result"]["gibbs"]["hyp_dirs"]) == 8 + len(P) - 1
    arrays = {f"trace/{k}": v for k, v in out["trace"].items()}
    arrays |= {f"kept/{k}": v for k, v in out["kept"].items()}
    h = hashlib.sha256()
    for k in sorted(arrays):
        h.update(k.encode())
        h.update(np.ascontiguousarray(arrays[k]).tobytes())
    assert h.hexdigest() == PHASE_UNITT_RUN_SHA256


def test_the_model_is_l1_with_student_t_unit_levels_at_three_dof():
    m = drift_building_phase_unitt
    assert m.NAME == "drift-building-phase-unitt"
    assert m.UNIT_DOF == 3.0
    assert m.LEVEL_DOF == drift_building_phase.LEVEL_DOF
    assert m.GROUPS == drift_building_phase.GROUPS
    assert m.PHASES == P and m.design is drift_building_phase.design
    assert (
        '("drift-building-phase-unitt", "drift_building_phase_unitt")'
        in open(run.__file__).read()
    )
    rec = m.run_record(tp._phased(n=300))
    assert rec["unit_t"]["unit_dof_fixed"] == 3.0
    assert rec["phase"]["reference"] == "10-13"
